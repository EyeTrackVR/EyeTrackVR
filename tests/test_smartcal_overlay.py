"""Smart Calib drives the overlay's interactive mode: the app shows each dot,
samples the gaze while it is held, fits and reports."""

import json
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import gaze_capture
import next_smartcal
from calibration_state import var
from eye import EyeId
from next_smartcal import NEXT_SMARTCAL_DOTS, SMARTCAL_SPACE_ANGLE, next_smartcal_dot_tangents, samples_from_recording
from tests import interactive_overlay
from tests.test_next_smartcal import GAZE_RANGE_LINE, _model
from utils import overlay_launch


@pytest.fixture(autouse=True)
def quick_run(monkeypatch):
    monkeypatch.setattr(next_smartcal, "READY_REST_S", 0.05)
    monkeypatch.setattr(next_smartcal, "REACTION_S", 0.0)
    monkeypatch.setattr(next_smartcal, "NEXT_SMARTCAL_CAPTURE_WINDOW_S", 0.04)
    monkeypatch.setattr(next_smartcal, "_SMARTCAL_SUMMARY_S", 0.0)
    monkeypatch.setattr(gaze_capture, "SETTLE_S", 0.03)


@pytest.fixture
def fake_overlay(monkeypatch, tmp_path):
    return interactive_overlay.install(monkeypatch, tmp_path, GAZE_RANGE_LINE)


class _Eye:
    """Looks at whichever dot the overlay was last told to show and feeds the
    raw gaze a model reads for it to the trace, as the NEXT eye thread does.
    It takes ``saccade_s`` to get there, with the gaze still moving."""

    def __init__(self, record, saccade_s=0.0):
        self.processor = SimpleNamespace(
            eye_id=EyeId.LEFT, config=SimpleNamespace(), _next_smartcal_w=None, _next_smartcal_b=None
        )
        self.record = record
        self.saccade_s = saccade_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._feed, daemon=True)
        self._thread.start()

    def _target(self):
        try:
            dots = [line.split()[1:] for line in self.record.read_text().splitlines() if line.startswith("111 ")]
        except OSError:
            return None
        return tuple(map(float, dots[-1])) if dots else None

    def _feed(self):
        target, moved_at, looking = None, 0.0, (0.0, 0.0)
        while not self._stop.is_set():
            now = time.monotonic()
            shown = self._target()
            if shown != target:
                target, moved_at = shown, now
            if target is not None:
                arrived = _model(*next_smartcal_dot_tangents(layout=[target])[0])
                if now - moved_at < self.saccade_s:
                    # Still on the way, correcting: well off the dot and moving.
                    off = 0.1 if int((now - moved_at) / 0.01) % 2 else -0.1
                    looking = (arrived[0] + off, arrived[1] - off)
                else:
                    looking = arrived
            trace = getattr(self.processor, "_next_smartcal_trace", None)
            if trace is not None:
                trace.append((now, *looking, 0.75, 0.5))
            time.sleep(0.002)

    def stop(self):
        self._stop.set()
        self._thread.join()


SETTINGS = SimpleNamespace(gui_NEXT_gaze_mode="fused", gui_NEXT_calib_lids_brows=False)


def _port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_the_app_shows_every_dot_then_fits_and_reports(fake_overlay):
    record = fake_overlay()
    eye = _Eye(record)

    next_smartcal.next_smartcal_overlay([eye.processor], SETTINGS, Mock(), NEXT_SMARTCAL_DOTS).wait(timeout=30)
    eye.stop()

    # The dots spread over the output limits, within the headset's view.
    assert fake_overlay.launched == [
        ("interactive", "--coverage=0.9", "--max-deg=40", "--max-deg-up=20", "--max-deg-down=40")
    ]

    commands = record.read_text().splitlines()
    assert commands[0].startswith("50 Look at the dot|")
    # The centre dot comes up with the instruction, which goes away once the
    # gaze rests on it. That centre dot is the layout's first.
    assert commands[1:4] == ["110", "111 0.0000 0.0000", "98"]
    assert commands[4:-3] == [f"111 {x:.4f} {y:.4f}" for x, y in NEXT_SMARTCAL_DOTS[1:]]
    assert commands[-3] == "119"
    assert commands[-2] == "50 Calibration saved.|Average error 0.0°, worst 0.0°, on 18 of 18 dots."
    assert commands[-1] == "200"
    assert eye.processor._next_smartcal_warp == SMARTCAL_SPACE_ANGLE
    assert not var.overlay_active
    _port_is_free(overlay_launch.OVERLAY_SIGNAL_PORT)


def test_a_dot_is_captured_once_the_gaze_rests_on_it(fake_overlay):
    record = fake_overlay()
    eye = _Eye(record, saccade_s=0.06)

    next_smartcal.next_smartcal_overlay([eye.processor], SETTINGS, Mock()).wait(timeout=30)
    eye.stop()

    for dot, (x, y) in enumerate(NEXT_SMARTCAL_DOTS):
        arrived = _model(*next_smartcal_dot_tangents(layout=[(x, y)])[0])
        samples = eye.processor._next_smartcal_samples[dot]
        assert samples and all(sample[:2] == pytest.approx(arrived) for sample in samples), dot


def test_each_run_is_recorded_and_replays_to_the_same_fit(fake_overlay, tmp_path):
    eye = _Eye(fake_overlay())

    next_smartcal.next_smartcal_overlay([eye.processor], SETTINGS, Mock()).wait(timeout=30)
    eye.stop()

    (path,) = (tmp_path / "smartcal").glob("*.json")
    recording = json.loads(path.read_text())
    assert recording["format"] == 2 and recording["layout"] == [list(dot) for dot in NEXT_SMARTCAL_DOTS]
    assert recording["gaze_range"] == [30.0, 15.0, -40.0, 0.0]
    kinds = [kind for _, kind, _ in recording["events"]]
    assert kinds[:4] == ["ready", "held", "capture", "captured"]
    assert kinds[4:] == ["show", "held", "capture", "captured"] * (len(NEXT_SMARTCAL_DOTS) - 1) + ["end"]
    assert recording["results"][0]["outcome"] == "applied" and recording["results"][0]["eye"] == "left"
    assert eye.processor._next_smartcal_trace is None

    samples = samples_from_recording(recording)["left"]
    assert sorted(samples) == list(range(len(NEXT_SMARTCAL_DOTS)))
    replayed = SimpleNamespace(
        eye_id=EyeId.LEFT,
        config=SimpleNamespace(),
        _next_smartcal_w=None,
        _next_smartcal_b=None,
        _next_smartcal_samples=samples,
    )
    layout = [tuple(dot) for dot in recording["layout"]]
    assert next_smartcal._fit_next_smartcal([replayed], Mock(), SETTINGS, tuple(recording["gaze_range"]), layout)
    # The recording rounds raw gaze to 5 decimals.
    assert replayed._next_smartcal_w == pytest.approx(eye.processor._next_smartcal_w, abs=1e-4)


def test_only_the_newest_recordings_are_kept(tmp_path, monkeypatch):
    from utils import logging_utils

    monkeypatch.setattr(logging_utils, "log_directory", lambda: tmp_path)
    folder = tmp_path / "smartcal"
    folder.mkdir()
    for i in range(next_smartcal.RECORDINGS_KEPT + 3):
        (folder / f"20260101-0000{i:02d}.json").write_text("{}")
    traces = {EyeId.LEFT: [(1.0, 0.1, 0.2, 0.7, 0.5)]}
    path = next_smartcal.save_recording(traces, NEXT_SMARTCAL_DOTS, None, SETTINGS, [], [], 0.0)
    kept = sorted(folder.glob("*.json"))
    assert len(kept) == next_smartcal.RECORDINGS_KEPT and path in kept
    assert next_smartcal.save_recording({EyeId.LEFT: []}, NEXT_SMARTCAL_DOTS, None, SETTINGS, [], [], 0.0) is None


def test_an_overlay_that_quits_mid_run_changes_nothing(fake_overlay):
    eye = _Eye(fake_overlay("quit-early"))

    next_smartcal.next_smartcal_overlay([eye.processor], SETTINGS, Mock()).wait(timeout=30)
    eye.stop()

    assert eye.processor._next_smartcal_w is None
    assert not var.overlay_active
