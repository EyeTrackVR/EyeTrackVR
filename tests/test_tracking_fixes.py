"""Regression tests for tracking-pipeline defects: HSF buffer sharing between
eye threads, LEAP "no result yet" frames, RANSAC axes + blink file, dilation
axes and NEXT vs standalone eyebrow output."""

import threading
from collections import deque
from queue import Queue
from types import SimpleNamespace

import cv2
import numpy as np

import eye_processor as eye_processor_module
import haar_surround_feature
import ransac
from eye import EyeId, EyeInfoOrigin
from eye_processor import EyeProcessor
from leap import LEAP_C, LEAP_LID_METRIC_VERSION
from osc.osc_message import OSCMessageType


# ── HSF: per-instance scratch buffers ────────────────────────────────────────


def _blob_image(cx, cy, shape=(100, 120), r=8):
    img = np.full(shape, 200, dtype=np.uint8)
    cv2.circle(img, (cx, cy), r, 10, -1)
    return img


def test_hsf_instances_do_not_share_scratch_buffers():
    a = haar_surround_feature.HSF_cls()
    b = haar_surround_feature.HSF_cls()
    key = ((100, 120), 40, 5, 5, 20, 60)

    bufs_a = a._get_buffers(*key)
    bufs_b = b._get_buffers(*key)

    # Same geometry must not mean the same mutable arrays across eyes (the
    # read-only index arrays may stay shared)...
    for arr_a, arr_b in zip(bufs_a, bufs_b):
        if arr_a.flags.writeable:
            assert not np.shares_memory(arr_a, arr_b)
        else:
            assert not arr_b.flags.writeable
    # ...but one instance reuses its own buffers frame to frame.
    assert a._get_buffers(*key)[0] is bufs_a[0]


def test_hsf_two_threads_each_find_their_own_pupil(monkeypatch):
    # External_Run_HSF writes these module globals; restore them afterwards.
    monkeypatch.setattr(haar_surround_feature, "skip_autoradius", False)
    monkeypatch.setattr(haar_surround_feature, "default_radius", 20)

    eyes = {
        "left": ((25, 30), _blob_image(25, 30)),
        "right": ((90, 70), _blob_image(90, 70)),
    }
    results = {name: [] for name in eyes}
    barrier = threading.Barrier(len(eyes))

    def worker(name):
        runner = haar_surround_feature.External_Run_HSF(True, 8)
        _, img = eyes[name]
        barrier.wait()
        for _ in range(250):
            # run() draws markers on its input, so hand it a fresh copy.
            x, y, _, _ = runner.run(img.copy())
            results[name].append((x, y))

    threads = [threading.Thread(target=worker, args=(n,)) for n in eyes]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    for name, ((cx, cy), _) in eyes.items():
        assert len(results[name]) == 250
        for x, y in results[name]:
            assert abs(x - cx) <= 10 and abs(y - cy) <= 10, (name, x, y)


# ── LEAP: no worker result yet ───────────────────────────────────────────────


def _bare_leap():
    leap = LEAP_C.__new__(LEAP_C)
    leap._last_result = None
    leap.last_lid = None
    leap.queues = [Queue(maxsize=1)]
    leap.output_queue = Queue(maxsize=1)
    leap.ort_session_cpu = None
    leap.ort_session_gpu = None
    leap.config = SimpleNamespace(
        settings=SimpleNamespace(gui_use_gpu=False, leap_calibration_duration=1.0),
        left_eye=None,
    )
    leap.eye_config = SimpleNamespace(
        leap_lid_metric_version=LEAP_LID_METRIC_VERSION,
        leap_calib_request_seq=0,
        leap_calibrated=True,
        leap_calibration_percentile_90=0.3,
        leap_calibration_percentile_2=-0.2,
    )
    leap._seen_calib_request_seq = 0
    leap.openlist = deque(maxlen=10)
    leap.one_euro_filter_float = lambda arr: arr
    leap.current_image_gray = np.zeros((40, 60), dtype=np.uint8)
    leap.current_image_gray_clean = np.zeros((40, 60), dtype=np.uint8)
    return leap


def test_leap_no_result_before_first_inference_is_none():
    leap = _bare_leap()
    _, x, y, lid = leap.leap_run()
    assert (x, y, lid) == (None, None, None)


def test_leap_no_result_repeats_last_valid_result():
    leap = _bare_leap()
    landmarks = np.full((12, 2), 0.5)
    # Lid points 1-3 / 2-4 0.2 apart -> half open against the stored range.
    landmarks[1], landmarks[3] = (0.5, 0.4), (0.5, 0.6)
    landmarks[2], landmarks[4] = (0.4, 0.4), (0.4, 0.6)
    landmarks[6] = (0.25, 0.75)
    leap.output_queue.put((None, landmarks))

    _, x1, y1, lid1 = leap.leap_run()
    assert (x1, y1) == (15.0, 30.0)
    assert lid1 > 0.0

    # Worker busy: the previous result comes back, not a blink + corner gaze.
    leap.queues[0].get_nowait()
    _, x2, y2, lid2 = leap.leap_run()
    assert (x2, y2, lid2) == (x1, y1, lid1)


def test_leapm_skips_update_when_leap_has_no_result():
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.eye_id = EyeId.LEFT
    proc.settings = SimpleNamespace(gui_use_gpu=False, gui_LEAP_lid=True)
    proc.current_image_gray = np.zeros((10, 10), dtype=np.uint8)
    proc.current_image_gray_clean = proc.current_image_gray
    proc.leap_runner = SimpleNamespace(run=lambda img, clean, gpu: (img, None, None, None))
    proc.rawx, proc.rawy = 12.0, 34.0
    proc.out_x, proc.out_y = 0.3, -0.2
    proc.eyeopen = 0.8

    proc.LEAPM()

    assert (proc.rawx, proc.rawy) == (12.0, 34.0)
    assert (proc.out_x, proc.out_y) == (0.3, -0.2)
    assert proc.eyeopen == 0.8
    assert proc.current_algorithm == EyeInfoOrigin.LEAP


# ── RANSAC: ellipse axes + blink file ────────────────────────────────────────


def _ransac_processor(eye_id):
    img = np.full((80, 80), 220, dtype=np.uint8)
    cv2.ellipse(img, (40, 40), (14, 8), 0, 0, 360, 0, -1)
    cv2.rectangle(img, (4, 4), (18, 34), 0, -1)  # second, differently-shaped contour
    return SimpleNamespace(
        eye_id=eye_id,
        rawx=40,
        rawy=40,
        radius=10,
        current_image_gray=img.copy(),
        current_image_gray_clean=img.copy(),
        settings=SimpleNamespace(gui_thresh_add=20, gui_RANSACBLINK=True),
        failed=0,
        detector_3d=SimpleNamespace(update_and_detect=lambda *_: (_ for _ in ()).throw(KeyError("x"))),
        last_projected_sphere={},
        current_frame_number=1,
        current_fps=60,
        ran_blink_check_for_file=True,
        blink_list=[],
    )


def test_ransac_returns_ellipse_axes_and_loads_own_blink_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ransac.ransac_blink_file_path(EyeId.LEFT)).write_text("0.1\n0.2\n")
    (tmp_path / ransac.ransac_blink_file_path(EyeId.RIGHT)).write_text("0.9\n")
    monkeypatch.setattr(ransac, "fit_rotated_ellipse_ransac", lambda data, rng: (40.0, 40.0, 7.5, 4.25, 0.0))

    proc = _ransac_processor(EyeId.LEFT)
    *_, w, h = ransac.RANSAC3D(proc, False)

    assert (w, h) == (7.5, 4.25)
    assert proc.blink_list[:2] == [0.1, 0.2]
    assert 0.9 not in proc.blink_list


def test_ransac_blink_percentile_computed_once_per_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    real_percentile = np.percentile

    def counting_percentile(*args, **kwargs):
        calls.append(1)
        return real_percentile(*args, **kwargs)

    monkeypatch.setattr(ransac.np, "percentile", counting_percentile)
    proc = _ransac_processor(EyeId.RIGHT)
    ransac.RANSAC3D(proc, False)
    assert len(proc.blink_list) >= 2  # several contours were sampled...
    assert len(calls) == 1  # ...but the percentile ran once

    # Frozen list (calibration complete): no recomputation at all.
    proc.blink_list = [0.01] * 10001
    proc._ransac_blink_p92 = None
    ransac.RANSAC3D(proc, False)
    ransac.RANSAC3D(proc, False)
    assert len(calls) == 2


# ── Dilation axes for trackers that don't measure them ───────────────────────


def test_dilation_axes_follow_radius_for_non_ransac_trackers():
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.current_algorithm = EyeInfoOrigin.RANSAC
    proc.pupil_width, proc.pupil_height = 30.0, 12.0
    proc.radius = 7
    proc._ensure_pupil_axes_for_dilation()
    assert (proc.pupil_width, proc.pupil_height) == (30.0, 12.0)

    # Switching to HSF: stale RANSAC axes must not freeze the input.
    proc.current_algorithm = EyeInfoOrigin.HSF
    proc._ensure_pupil_axes_for_dilation()
    assert (proc.pupil_width, proc.pupil_height) == (14.0, 14.0)
    proc.radius = 11
    proc._ensure_pupil_axes_for_dilation()
    assert (proc.pupil_width, proc.pupil_height) == (22.0, 22.0)


# ── Eyebrow: NEXT preferred over the standalone model ────────────────────────


class _FakeBrow:
    instances = []

    def __init__(self, variant):
        self.variant = variant
        self.stopped = False
        self.frames = 0
        _FakeBrow.instances.append(self)

    def submit(self, frame):
        self.frames += 1

    def get_result(self):
        return 0.123

    def stop(self):
        self.stopped = True


def _brow_processor(next_on):
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.eye_id = EyeId.LEFT
    proc.settings = SimpleNamespace(
        gui_NEXT=next_on,
        gui_NEXT_BSB=False,
        gui_eyebrow=True,
        gui_model_variant="ETVR",
        gui_setup_mode="default",
    )
    proc.osc_queue = Queue()
    proc.eyebrow_runner = None
    proc.next_eyebrow = 0.77
    return proc


def _brow_messages(proc):
    msgs = []
    while not proc.osc_queue.empty():
        msg = proc.osc_queue.get_nowait()
        if msg.type == OSCMessageType.EYEBROW_INFO:
            msgs.append(msg)
    return msgs


def test_next_active_stops_standalone_eyebrow_and_reports_next_value(monkeypatch):
    monkeypatch.setattr(eye_processor_module, "EyeBrow", _FakeBrow)
    proc = _brow_processor(next_on=True)
    runner = _FakeBrow("ETVR")
    proc.eyebrow_runner = runner

    proc._service_eyebrow_runner(np.zeros((4, 4, 3), dtype=np.uint8))

    assert runner.stopped and proc.eyebrow_runner is None
    assert runner.frames == 0
    assert _brow_messages(proc) == []
    assert proc._current_eyebrow() == 0.77


def test_eyebrow_runner_unchanged_without_next(monkeypatch):
    monkeypatch.setattr(eye_processor_module, "EyeBrow", _FakeBrow)
    proc = _brow_processor(next_on=False)

    proc._service_eyebrow_runner(np.zeros((4, 4, 3), dtype=np.uint8))

    assert isinstance(proc.eyebrow_runner, _FakeBrow)
    assert proc.eyebrow_runner.frames == 1
    msgs = _brow_messages(proc)
    assert len(msgs) == 1 and msgs[0].data == (EyeId.LEFT, 0.123)
    assert proc._current_eyebrow() == 0.123
