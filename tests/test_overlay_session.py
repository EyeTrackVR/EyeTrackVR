"""OverlaySession runs one calibration overlay from launch until it has stopped.

A small Python script stands in for the overlay: it sends the given signals to
the app's signal port, prints a line, then stays alive for a while."""

import socket
import struct
import sys
import time
from types import SimpleNamespace

import pytest

import overlay_calibration as calibration
from utils import logging_utils, overlay_launch
from utils.calibration_elipse import CalibrationEllipse
from utils.overlay_launch import OverlayExited, OverlaySession, OverlayStopped

FAKE_OVERLAY = """
import socket, struct, sys, time
print("fake overlay started", flush=True)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for value in filter(None, sys.argv[1].split(",")):
    sock.sendto(struct.pack(">i", int(value)), ("127.0.0.1", {port}))
    time.sleep(0.05)
time.sleep(float(sys.argv[2]))
"""


@pytest.fixture
def fake_overlay(monkeypatch, tmp_path):
    """Launch the stand-in instead of the overlay binary; returns a setter
    for the signals it sends and how long it then stays alive."""
    script = tmp_path / "fake_overlay.py"
    script.write_text(FAKE_OVERLAY.format(port=overlay_launch.OVERLAY_SIGNAL_PORT))
    monkeypatch.setattr(logging_utils, "log_directory", lambda: tmp_path)
    behaviour = {"signals": [], "linger": 0.0}

    def command(*_args):
        signals = ",".join(str(value) for value in behaviour["signals"])
        return [sys.executable, str(script), signals, str(behaviour["linger"])]

    monkeypatch.setattr(overlay_launch, "overlay_command", command)

    def configure(signals=(), linger=0.0):
        behaviour.update(signals=list(signals), linger=linger)
        return tmp_path

    return configure


def _port_is_free():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", overlay_launch.OVERLAY_SIGNAL_PORT))


def test_finished_overlay_receives_signals_and_closes_by_itself(fake_overlay):
    log_dir = fake_overlay(signals=[0, 9], linger=0.5)

    with OverlaySession("ellipse") as overlay:
        received = [struct.unpack(">i", overlay.recv())[0] for _ in range(2)]
        overlay.finish()

    assert received == [0, 9]
    # It had time for its completion card and exited on its own.
    assert overlay.process.returncode == 0
    assert "fake overlay started" in (log_dir / "calibration-overlay.log").read_text()
    _port_is_free()


def test_overlay_that_quits_early_is_reported_without_waiting_for_the_timeout(fake_overlay):
    fake_overlay(signals=[], linger=0.0)

    started = time.monotonic()
    with pytest.raises(OverlayExited), OverlaySession("center", timeout=60) as overlay:
        overlay.recv()

    assert time.monotonic() - started < 10
    _port_is_free()


def test_silent_overlay_times_out_and_is_stopped(fake_overlay):
    fake_overlay(signals=[], linger=60)

    with pytest.raises(TimeoutError), OverlaySession("finetune", timeout=0.5) as overlay:
        overlay.recv()

    assert overlay.process.returncode is not None
    _port_is_free()


def test_timeout_counts_from_the_last_signal(fake_overlay):
    fake_overlay(signals=[1, 2, 3, 4, 5, 6, 7, 8], linger=60)

    with OverlaySession("finetune", timeout=0.3) as overlay:
        # Eight signals 50 ms apart outlast one timeout but never leave a gap.
        values = [struct.unpack(">i", overlay.recv())[0] for _ in range(8)]

    assert values == [1, 2, 3, 4, 5, 6, 7, 8]


def test_unfinished_overlay_is_stopped_on_exit(fake_overlay):
    fake_overlay(signals=[0], linger=60)

    with OverlaySession("ellipse") as overlay:
        overlay.recv()

    assert overlay.process.returncode is not None
    _port_is_free()


def test_center_calibration_returns_when_the_overlay_quits(fake_overlay):
    # The centre recenter used to block on the overlay's signal forever, which
    # left overlay_active set and silently disabled every later calibration.
    fake_overlay(signals=[], linger=0.0)
    processor = SimpleNamespace(
        settings=SimpleNamespace(gui_recenter_eyes=True),
        calibration_start_time=1.0,
    )

    calibration.center_overlay_calibrate(processor).wait(timeout=10)

    assert not calibration.var.overlay_active
    assert not processor.settings.gui_recenter_eyes
    assert processor.calibration_start_time is None


def _ellipse_processor():
    return SimpleNamespace(
        cal=CalibrationEllipse(),
        config=SimpleNamespace(calib_evecs=[], calib_axes=[1.0, 2.0], calib_XOFF=5.0, calib_YOFF=6.0),
        baseconfig=SimpleNamespace(save=lambda: None),
        _ellipse_collect_active=False,
    )


def _run_ellipse_until_the_overlay_quits(processor, settings):
    run = calibration.overlay_ellipse_calibrate([processor], settings, None)
    deadline = time.monotonic() + 10
    while not processor._ellipse_collect_active and time.monotonic() < deadline:
        time.sleep(0.01)
    assert processor._ellipse_collect_active
    processor.cal.xs = [0.0, 1.0, 2.0]
    processor.cal.ys = [0.0, 1.0, 2.0]
    run.wait(timeout=10)


def test_overlay_quitting_early_keeps_the_saved_ellipse(fake_overlay):
    fake_overlay(signals=[0], linger=0.3)
    processor = _ellipse_processor()
    settings = SimpleNamespace(calib_mode="next")

    _run_ellipse_until_the_overlay_quits(processor, settings)

    assert processor.config.calib_axes == [1.0, 2.0]
    assert settings.calib_mode == "next"


def test_overlay_quitting_after_the_orbit_saves_a_partial_ellipse(fake_overlay, monkeypatch):
    monkeypatch.setattr(calibration, "ELLIPSE_PARTIAL_MIN_S", 0.0)
    fake_overlay(signals=[0], linger=0.3)
    processor = _ellipse_processor()
    settings = SimpleNamespace(calib_mode="next")

    _run_ellipse_until_the_overlay_quits(processor, settings)

    assert processor.config.calib_axes != [1.0, 2.0]
    assert settings.calib_mode == "classic"


def test_calibration_stays_active_until_the_overlay_is_gone(fake_overlay):
    # A second calibration can't bind the signal port before this one closes it.
    fake_overlay(signals=[0, 9], linger=0.5)
    settings = SimpleNamespace(calib_mode="next")

    run = calibration.overlay_ellipse_calibrate([], settings, None)
    deadline = time.monotonic() + 10
    while settings.calib_mode != "classic" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert settings.calib_mode == "classic"
    assert calibration.var.overlay_active
    run.wait(timeout=10)
    assert not calibration.var.overlay_active


def test_start_and_close_work_without_a_with_block(fake_overlay):
    fake_overlay(signals=[0], linger=60)

    overlay = OverlaySession("interactive").start()
    # recv waits out the stand-in's startup; the raw socket gives up after POLL_S.
    assert struct.unpack(">i", overlay.recv(16))[0] == 0
    overlay.close()

    assert overlay.process.returncode is not None
    _port_is_free()


def test_a_pause_ends_early_when_stopped_or_when_the_overlay_quits(fake_overlay):
    fake_overlay(signals=[], linger=5.0)
    with OverlaySession("interactive") as overlay:
        started = time.monotonic()
        with pytest.raises(OverlayStopped):
            overlay.pause(5.0, keep_going=lambda: time.monotonic() - started < 0.2)
        assert time.monotonic() - started < 2.0

    fake_overlay(signals=[], linger=0.0)
    with OverlaySession("interactive") as overlay, pytest.raises(OverlayExited):
        overlay.pause(10.0)
    _port_is_free()


def test_a_wait_for_a_silent_overlay_ends_soon_after_a_stop(fake_overlay):
    # The overlay sends nothing here, and the session's own timeout is far off.
    fake_overlay(signals=[], linger=30.0)
    with OverlaySession("interactive", timeout=120.0) as overlay:
        started = time.monotonic()
        with pytest.raises(OverlayStopped):
            overlay.wait_for(20, keep_going=lambda: time.monotonic() - started < 0.3)
        assert time.monotonic() - started < 0.3 + 2 * OverlaySession.POLL_S + 0.2
    _port_is_free()


def test_a_stop_is_only_taken_from_a_run_that_can_stop():
    from calibration_state import begin_overlay_run, end_overlay_run, overlay_keep_going, request_overlay_stop, var

    request_overlay_stop()  # nothing runs: not left behind for the next run
    assert not var.overlay_stop_requested
    assert begin_overlay_run("smartcal") and not begin_overlay_run("range_check")
    try:
        assert overlay_keep_going() and var.overlay_run == "smartcal"
        request_overlay_stop()
        # Still the active run until its overlay is gone.
        assert var.overlay_active and not overlay_keep_going()
    finally:
        end_overlay_run()
    assert not var.overlay_active and var.overlay_run is None and not var.overlay_stop_requested


# ------------------------------------------------------------------ the app's end of it


# Ignores SIGTERM like a hung overlay would, and says so once it does.
HUNG_OVERLAY = (
    "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(60)"
)


def test_stop_live_overlays_kills_a_hung_overlay_within_its_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_utils, "log_directory", lambda: tmp_path)
    monkeypatch.setattr(overlay_launch, "overlay_command", lambda *_a: [sys.executable, "-c", HUNG_OVERLAY])
    overlay = OverlaySession("preview").start()
    try:
        log = tmp_path / "calibration-overlay.log"
        deadline = time.monotonic() + 10
        while "ready" not in (log.read_text() if log.exists() else "") and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "ready" in log.read_text(), "the stand-in never started ignoring SIGTERM"
        started = time.monotonic()
        overlay_launch.stop_live_overlays(timeout=0.5)
        overlay.process.wait(timeout=2)
        assert time.monotonic() - started < 2
    finally:
        overlay.close()
    assert overlay.process not in overlay_launch._live


@pytest.fixture
def notices(monkeypatch):
    """What the app would tell the user (calibration_state.notify_user)."""
    import calibration_state

    shown = []
    monkeypatch.setattr(calibration_state, "_user_notifier", shown.append)
    return shown


@pytest.fixture
def no_overlay_binary(monkeypatch):
    def missing(*_args):
        raise FileNotFoundError("in-VR overlay binary not found")

    monkeypatch.setattr(overlay_launch, "overlay_command", missing)


OVERLAY_RUN_SETTINGS = SimpleNamespace(
    calib_mode="next",
    gui_NEXT_gaze_mode="fused",
    gui_NEXT_calib_lids_brows=False,
    gui_gaze_yaw_max_deg=40.0,
    gui_gaze_pitch_up_deg=15.0,
    gui_gaze_pitch_down_deg=40.0,
    osc_invert_eye_close=False,
)


def test_a_missing_overlay_is_reported_only_when_the_user_asked(monkeypatch, no_overlay_binary, notices):
    import gaze_range_check
    import next_smartcal

    monkeypatch.setattr(next_smartcal, "_save_recording_safely", lambda *_a: None)
    runs = [
        lambda **kw: calibration.overlay_ellipse_calibrate([], OVERLAY_RUN_SETTINGS, None, **kw),
        lambda **kw: next_smartcal.next_smartcal_overlay([], OVERLAY_RUN_SETTINGS, None, **kw),
        lambda **kw: gaze_range_check.gaze_range_check_overlay([], OVERLAY_RUN_SETTINGS, **kw),
    ]
    for run in runs:
        run().wait(timeout=10)  # started by an OSC trigger: nobody is at the window
    assert notices == []
    for run in runs:
        run(notify=True).wait(timeout=10)  # the user clicked the button
    assert notices == ["status.overlay_missing"] * 3
    assert not calibration.var.overlay_active


def test_overlay_quitting_before_its_first_signal_asks_for_steamvr(fake_overlay, notices):
    fake_overlay(signals=[], linger=0.0)  # what the overlay does without a VR runtime
    calibration.overlay_ellipse_calibrate([], SimpleNamespace(calib_mode="next"), None, notify=True).wait(timeout=10)
    assert notices == ["status.steamvr_not_running"]


def test_overlay_closed_after_it_started_is_not_an_error(fake_overlay, notices):
    fake_overlay(signals=[0], linger=0.3)
    calibration.overlay_ellipse_calibrate([], SimpleNamespace(calib_mode="next"), None, notify=True).wait(timeout=10)
    assert notices == []
