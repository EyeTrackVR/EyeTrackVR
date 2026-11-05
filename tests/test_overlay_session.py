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
from utils.overlay_launch import OVERLAY_SIGNAL_PORT, OverlayExited, OverlaySession

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
    script.write_text(FAKE_OVERLAY.format(port=OVERLAY_SIGNAL_PORT))
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
        sock.bind(("127.0.0.1", OVERLAY_SIGNAL_PORT))


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
    assert struct.unpack(">i", overlay.sock.recvfrom(16)[0])[0] == 0
    overlay.close()

    assert overlay.process.returncode is not None
    _port_is_free()
