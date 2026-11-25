"""LEAP landmark tracker: the GPU toggle applies without a restart, the GPU
session is only built when asked for, CPU inference never queues behind the
DirectML lock, and a frame without a worker result is not a blink."""

from collections import deque
from queue import Empty, Queue
from types import SimpleNamespace

import numpy as np
import pytest

import leap
from leap import LEAP_C, LEAP_LID_METRIC_VERSION
from utils.onnx_runtime import DML_INFERENCE_LOCK


class _FakeGpuSession:
    def __init__(self):
        self.runs = 0

    def get_inputs(self):
        return [SimpleNamespace(name="input")]

    def run(self, _outputs, feeds):
        self.runs += 1
        return [np.full((1, 24), 0.5, dtype=np.float32)]


@pytest.fixture
def make_leap():
    made = []

    def _make(use_gpu):
        settings = SimpleNamespace(gui_use_gpu=use_gpu, leap_calibration_duration=1.0)
        eye_config = SimpleNamespace(leap_calib_request_seq=0, leap_lid_metric_version=LEAP_LID_METRIC_VERSION)
        runner = LEAP_C(eye_config, SimpleNamespace(settings=settings, left_eye=eye_config))
        made.append(runner)
        return runner

    yield _make
    for runner in made:
        runner.shutdown()


def _infer(runner):
    runner.current_image_gray = runner.current_image_gray_clean = np.zeros((40, 40), dtype=np.uint8)
    runner.leap_run()
    return runner.output_queue.get(timeout=5)


def test_gpu_toggle_applies_without_restart_and_builds_the_session_lazily(make_leap, monkeypatch):
    gpu = _FakeGpuSession()
    built = []
    monkeypatch.setattr(leap, "create_inference_session", lambda *a, **k: built.append(k) or (gpu, False))
    runner = make_leap(use_gpu=False)

    _infer(runner)
    assert built == []  # GPU off: no GPU session

    runner.config.settings.gui_use_gpu = True
    _infer(runner)
    _infer(runner)
    assert gpu.runs == 2
    assert len(built) == 1  # built once, then reused

    runner.config.settings.gui_use_gpu = False
    _infer(runner)
    assert gpu.runs == 2


def test_cpu_inference_does_not_wait_for_the_directml_lock(make_leap):
    runner = make_leap(use_gpu=False)
    with DML_INFERENCE_LOCK:  # e.g. the other eye's NEXT session on DirectML
        try:
            _infer(runner)
        except Empty:
            pytest.fail("CPU LEAP inference blocked on the DirectML lock")


# ── no worker result yet ─────────────────────────────────────────────────────


def _bare_leap():
    runner = LEAP_C.__new__(LEAP_C)
    runner._last_result = None
    runner.last_lid = None
    runner.queues = [Queue(maxsize=1)]
    runner.output_queue = Queue(maxsize=1)
    runner.config = SimpleNamespace(
        settings=SimpleNamespace(gui_use_gpu=False, leap_calibration_duration=1.0),
        left_eye=None,
    )
    runner.eye_config = SimpleNamespace(
        leap_lid_metric_version=LEAP_LID_METRIC_VERSION,
        leap_calib_request_seq=0,
        leap_calibrated=True,
        leap_calibration_percentile_90=0.3,
        leap_calibration_percentile_2=-0.2,
    )
    runner._seen_calib_request_seq = 0
    runner.openlist = deque(maxlen=10)
    runner.one_euro_filter_float = lambda arr: arr
    runner.current_image_gray = np.zeros((40, 60), dtype=np.uint8)
    runner.current_image_gray_clean = np.zeros((40, 60), dtype=np.uint8)
    return runner


def test_leap_no_result_before_first_inference_is_none():
    _, x, y, lid = _bare_leap().leap_run()
    assert (x, y, lid) == (None, None, None)


def test_leap_no_result_repeats_last_valid_result():
    runner = _bare_leap()
    landmarks = np.full((12, 2), 0.5)
    # Lid points 1-3 / 2-4 0.2 apart -> half open against the stored range.
    landmarks[1], landmarks[3] = (0.5, 0.4), (0.5, 0.6)
    landmarks[2], landmarks[4] = (0.4, 0.4), (0.4, 0.6)
    landmarks[6] = (0.25, 0.75)
    runner.output_queue.put((None, landmarks))

    _, x1, y1, lid1 = runner.leap_run()
    assert (x1, y1) == (15.0, 30.0)
    assert lid1 > 0.0

    # Worker busy: the previous result comes back, not a blink + corner gaze.
    runner.queues[0].get_nowait()
    _, x2, y2, lid2 = runner.leap_run()
    assert (x2, y2, lid2) == (x1, y1, lid1)
