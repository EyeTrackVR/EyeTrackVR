"""The gaze preview streams the app's output gaze to the overlay's preview mode."""

import math
import socket
import struct
import sys
import time
from types import SimpleNamespace

import pytest

import overlay_calibration as calibration
from utils import gaze_preview, logging_utils, overlay_launch
from utils.gaze_preview import CMD_GAZE, CMD_QUIT, CMD_TEXT, GazePreviewStream, gaze_tangents
from utils.overlay_launch import OVERLAY_SIGNAL_PORT

SETTINGS = SimpleNamespace(
    gui_gaze_yaw_max_deg=40.0,
    gui_gaze_pitch_up_deg=15.0,
    gui_gaze_pitch_down_deg=40.0,
    osc_invert_eye_close=False,
)


def _info(x, y, blink=1.0):
    return SimpleNamespace(x=x, y=y, blink=blink)


@pytest.fixture
def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    yield sock
    sock.close()


def _gaze(sock):
    code, tan_x, tan_y, openness = struct.unpack(">ifff", sock.recv(64))
    assert code == CMD_GAZE
    return tan_x, tan_y, openness


def test_tangents_use_the_output_fov_edges():
    tan = math.tan(math.radians(40.0))
    assert gaze_tangents(1.0, 0.0, 40.0, 15.0, 40.0) == pytest.approx((tan, 0.0))
    assert gaze_tangents(0.0, 1.0, 40.0, 15.0, 40.0)[1] == pytest.approx(math.tan(math.radians(15.0)))
    assert gaze_tangents(0.0, -0.5, 40.0, 15.0, 40.0)[1] == pytest.approx(-0.5 * tan)


def test_both_eyes_are_averaged(receiver):
    stream = GazePreviewStream(SETTINGS, receiver.getsockname())
    try:
        stream.feed("left", _info(0.2, 0.0, 1.0), single_eye=False)
        _gaze(receiver)
        stream.feed("right", _info(0.6, 0.0, 0.5), single_eye=False)
        tan_x, tan_y, openness = _gaze(receiver)
    finally:
        stream.close()
    assert tan_x == pytest.approx(0.4 * math.tan(math.radians(40.0)), rel=1e-6)
    assert tan_y == 0.0
    assert openness == pytest.approx(0.75)


def test_a_stalled_eye_drops_out(receiver, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(gaze_preview.time, "monotonic", lambda: now[0])
    stream = GazePreviewStream(SETTINGS, receiver.getsockname())
    try:
        stream.feed("left", _info(-1.0, 0.0), single_eye=False)
        _gaze(receiver)
        now[0] += gaze_preview.EYE_STALE_S + 0.1
        stream.feed("right", _info(0.5, 0.0), single_eye=False)
        tan_x, _, _ = _gaze(receiver)
    finally:
        stream.close()
    assert tan_x == pytest.approx(0.5 * math.tan(math.radians(40.0)), rel=1e-6)


def test_inverted_eye_close_and_bad_samples(receiver):
    settings = SimpleNamespace(**{**vars(SETTINGS), "osc_invert_eye_close": True})
    stream = GazePreviewStream(settings, receiver.getsockname())
    try:
        stream.feed("left", _info(float("nan"), 0.0), single_eye=True)
        stream.feed("left", _info(0.0, 0.0, 0.2), single_eye=True)
        _, _, openness = _gaze(receiver)
    finally:
        stream.close()
    assert openness == pytest.approx(0.8)


FAKE_OVERLAY = """
import socket, struct, sys, time
cmd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd.bind(("127.0.0.1", {cmd_port}))
cmd.settimeout(10)
time.sleep(0.6)  # starting up takes longer than the app's polling interval
socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(struct.pack(">i", 255), ("127.0.0.1", {sig_port}))
with open({record!r}, "w") as out:
    while True:
        data = cmd.recv(512)
        code = struct.unpack(">i", data[:4])[0]
        out.write(f"{{code}}\\n")
        out.flush()
        if code == 200 or (code == 50 and sys.argv[1] == "close-after-text"):
            break
"""


@pytest.fixture
def fake_overlay(monkeypatch, tmp_path):
    """Launch a stand-in for the overlay; returns the file its commands go to."""
    record = tmp_path / "commands.txt"
    script = tmp_path / "fake_overlay.py"
    script.write_text(
        FAKE_OVERLAY.format(cmd_port=gaze_preview.OVERLAY_CMD_PORT, sig_port=OVERLAY_SIGNAL_PORT, record=str(record))
    )
    monkeypatch.setattr(logging_utils, "log_directory", lambda: tmp_path)
    behaviour = {"arg": ""}
    monkeypatch.setattr(overlay_launch, "overlay_command", lambda *_a: [sys.executable, str(script), behaviour["arg"]])

    def configure(arg=""):
        behaviour["arg"] = arg
        return record

    return configure


def _wait_until_streaming():
    deadline = time.monotonic() + 10
    while gaze_preview._active is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert gaze_preview._active is not None


def _assert_stopped():
    assert not gaze_preview.is_running()
    assert gaze_preview._active is None
    assert not calibration.var.overlay_active


def test_preview_runs_until_stopped(fake_overlay):
    record = fake_overlay()

    run = calibration.gaze_preview_overlay(SETTINGS)
    _wait_until_streaming()
    assert gaze_preview.is_running()
    gaze_preview.feed("left", _info(0.1, 0.1), single_eye=True)
    time.sleep(0.1)
    calibration.stop_gaze_preview()
    run.wait(timeout=10)

    assert record.read_text().split() == [str(CMD_TEXT), str(CMD_GAZE), str(CMD_QUIT)]
    _assert_stopped()


def test_preview_ends_when_the_overlay_is_closed(fake_overlay):
    fake_overlay("close-after-text")

    run = calibration.gaze_preview_overlay(SETTINGS)
    run.wait(timeout=10)

    _assert_stopped()
