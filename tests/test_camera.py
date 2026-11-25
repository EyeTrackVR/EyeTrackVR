"""Capture thread (camera.Camera): source classification, the retry loops of
each backend, the UVC profile request, serial trackers behind symlinks and
frame delivery to the tracking queues."""

import logging
import os
import queue
import sys
import threading
import time
import types

import cv2
import numpy as np
import pytest

import camera
from camera import (
    _UVC_REQUESTED_FPS,
    Camera,
    CameraState,
    is_http_capture_source,
    is_local_file_video_capture_source,
    is_serial_capture_source,
)


def _camera(source):
    return Camera(
        types.SimpleNamespace(capture_source=source),
        types.SimpleNamespace(),
        0,
        threading.Event(),
        threading.Event(),
        queue.Queue(),
        queue.Queue(maxsize=20),
    )


class _Cancel:
    """Stands in for the cancellation event: each reconnect wait returns the
    next value of ``waits`` (True = stop requested during that wait), and the
    timeout of every wait is recorded."""

    def __init__(self, waits=(True,)):
        self.flag = False
        self._waits = iter(waits)
        self.timeouts = []

    @classmethod
    def after(cls, n):
        """Stopped during the ``n``th wait."""
        return cls((False,) * (n - 1) + (True,))

    def is_set(self):
        return self.flag

    def wait(self, timeout=None):
        self.timeouts.append(timeout)
        self.flag = next(self._waits)
        return self.flag


class _FakeCapture:
    def __init__(self, opened=False):
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened and not self.released

    def release(self):
        self.released = True


# ── source classification ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "source, serial, http, video_file",
    [
        ("COM5", True, False, False),
        ("/dev/cu.usbmodem101", True, False, False),
        ("/dev/ttyACM0", True, False, False),
        ("http://192.168.0.31/", False, True, False),
        (" HTTPS://etvr.local/stream ", False, True, False),
        ("C:/captures/eye.MP4", False, False, True),
        ("uvc:Eye Cam@dev-1", False, False, False),
    ],
)
def test_capture_sources_are_told_apart(source, serial, http, video_file):
    assert is_serial_capture_source(source) is serial
    assert is_http_capture_source(source) is http
    assert is_local_file_video_capture_source(source) is video_file


@pytest.mark.parametrize("source", [None, 0, 2, "", "   "])
def test_indices_and_empty_sources_are_not_video_files(source):
    assert not is_local_file_video_capture_source(source)


# ── retry loops ──────────────────────────────────────────────────────────────


def test_absent_serial_port_waits_between_retries(monkeypatch):
    calls = []

    def comports():
        calls.append(1)
        if len(calls) > 50:
            pytest.fail("re-scanned the ports without waiting")
        return []

    monkeypatch.setattr(camera.serial.tools.list_ports, "comports", comports)
    cam = _camera("COM7")
    cam.cancellation_event = _Cancel.after(5)

    cam.run()

    # One port check per reconnect wait, not thousands per second.
    assert len(calls) == 5
    assert cam.cancellation_event.timeouts == [camera.WAIT_TIME] * 5 and camera.WAIT_TIME > 0
    assert cam.camera_status == CameraState.DISCONNECTED


def test_busy_serial_port_logs_its_failure_once(monkeypatch, caplog):
    monkeypatch.setattr(camera.serial.tools.list_ports, "comports", lambda: [types.SimpleNamespace(device="COM7")])
    opens = []

    def busy_port(**kwargs):
        opens.append(1)
        if len(opens) > 50:
            pytest.fail("reopened the port without waiting")
        raise OSError("port busy")

    monkeypatch.setattr(camera.serial, "Serial", busy_port)
    cam = _camera("COM7")
    cam.cancellation_event = _Cancel.after(5)

    with caplog.at_level(logging.INFO, logger="camera"):
        cam.run()

    assert len(opens) == 5
    assert cam.cancellation_event.timeouts == [camera.WAIT_TIME] * 5
    assert sum("Failed to connect" in r.getMessage() for r in caplog.records) == 1


def test_stop_during_network_backoff_releases_the_camera(monkeypatch):
    released_claims = []
    monkeypatch.setattr(camera, "release_uvc_claim", released_claims.append)
    cam = _camera("http://etvr.local/")
    cam.current_capture_source = "http://etvr.local/"
    cam.cancellation_event = _Cancel()
    stale = _FakeCapture()
    cam.cv2_camera = stale
    cam._claimed_uvc_address = "dev-1"
    cam._network_reconnect_backoff = time.monotonic() + 60

    cam.run()

    assert stale.released
    assert cam.cv2_camera is None
    assert released_claims == [id(cam)]


def test_offline_network_camera_is_not_reopened_until_its_backoff_expires(monkeypatch):
    attempts = []

    class _DeadHost(_FakeCapture):
        def __init__(self):
            super().__init__()
            attempts.append(self)

        def open(self, *args):
            return False

    monkeypatch.setattr(camera.cv2, "VideoCapture", _DeadHost)
    cam = _camera("http://etvr.local/")
    # Settle wait, the wait after the failed open, then a wait in the backoff.
    cam.cancellation_event = _Cancel.after(3)

    cam.run()

    # One open attempt: the next loop waits out the backoff instead of
    # blocking the thread in another multi-second open of a dead host.
    assert len(attempts) == 1 and attempts[0].released
    assert len(cam.cancellation_event.timeouts) == 3
    assert cam.camera_status == CameraState.DISCONNECTED
    assert cam.cv2_camera is None


class _StopAfterOneFrame:
    def __init__(self):
        self.checks = 0

    def is_set(self):
        self.checks += 1
        return self.checks > 1

    def wait(self, _timeout=None):
        return False


class _WorkingCapture(_FakeCapture):
    def open(self, *_args):
        self.opened = True
        return True

    def set(self, *_args):
        return True

    def get(self, *_args):
        return 0.0

    def read(self):
        return True, np.zeros((4, 4, 3), dtype=np.uint8)


def test_successful_uvc_open_keeps_the_camera_list_cached(monkeypatch):
    invalidations = []
    monkeypatch.setattr(camera, "invalidate_uvc_camera_cache", lambda *a, **k: invalidations.append(1))
    monkeypatch.setattr(camera, "resolve_uvc_address_to_index", lambda *a, **k: (0, "dev-1"))
    monkeypatch.setattr(camera, "claim_uvc_address", lambda *a: None)
    monkeypatch.setattr(camera, "release_uvc_claim", lambda *a: None)
    monkeypatch.setattr(camera.cv2, "VideoCapture", _WorkingCapture)
    cam = _camera("uvc:Eye Cam@dev-1")
    cam.cancellation_event = _StopAfterOneFrame()

    cam.run()

    assert cam.camera_output_outgoing.qsize() == 1  # it opened and delivered a frame
    # The sibling eye resolves next; clearing the list here made it re-run the
    # PowerShell / system_profiler enumeration a second time.
    assert invalidations == []


def test_uvc_resolve_miss_refreshes_the_camera_list(monkeypatch):
    invalidations = []
    monkeypatch.setattr(camera, "invalidate_uvc_camera_cache", lambda *a, **k: invalidations.append(1))
    monkeypatch.setattr(camera, "resolve_uvc_address_to_index", lambda *a, **k: None)
    cam = _camera("uvc:Eye Cam@dev-1")
    # Not stopped by the settle wait before the resolve, only by the one after it.
    cam.cancellation_event = _Cancel(waits=(False, True))

    cam.run()

    assert invalidations == [1]


# ── UVC profile ──────────────────────────────────────────────────────────────


class _ProfileCapture:
    def __init__(self):
        self.set_calls = []
        self.values = {
            cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG"),
            cv2.CAP_PROP_FRAME_WIDTH: 640,
            cv2.CAP_PROP_FRAME_HEIGHT: 480,
            cv2.CAP_PROP_FPS: _UVC_REQUESTED_FPS,
        }

    def set(self, prop, value):
        self.set_calls.append((prop, value))
        return True

    def get(self, prop):
        return self.values[prop]


def test_uvc_profile_requests_mjpg_before_high_fps(caplog):
    capture = _ProfileCapture()
    caplog.set_level(logging.INFO)

    Camera._negotiate_uvc_profile(object(), capture)

    assert capture.set_calls == [
        (cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")),
        (cv2.CAP_PROP_FPS, _UVC_REQUESTED_FPS),
    ]
    assert "format=MJPG" in caplog.text


def test_a_driver_that_rejects_the_profile_does_not_fail_the_open(caplog):
    class _Rejecting(_ProfileCapture):
        def get(self, prop):
            raise cv2.error("property not supported")

    Camera._negotiate_uvc_profile(object(), _Rejecting())

    assert "Could not negotiate UVC MJPEG/FPS profile" in caplog.text


@pytest.mark.parametrize(
    "value, name",
    [(cv2.VideoWriter_fourcc(*"MJPG"), "MJPG"), (cv2.VideoWriter_fourcc(*"YUY2"), "YUY2"), (0, "0"), ("x", "x")],
)
def test_fourcc_name_decodes_opencv_property(value, name):
    assert Camera._fourcc_name(value) == name


# ── serial trackers behind symlinks ──────────────────────────────────────────

LINKS = {
    "/dev/ttyEYELEFT": "/dev/ttyACM1",
    "/dev/serial/by-id/usb-Espressif_ETVR-if00": "/dev/ttyACM1",
    "/dev/eyeleft": "/dev/ttyACM1",
    "/dev/webcam": "/dev/video0",
}


def _fake_linux_links(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os.path, "realpath", lambda p: LINKS.get(p, p))


class _FakeSerial:
    def __init__(self, port, **kwargs):
        self.port = port
        self.is_open = True

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False


def _bare_camera():
    cam = Camera.__new__(Camera)
    cam.serial_connection = None
    cam.buffer = b"stale"
    cam.camera_status = CameraState.CONNECTING
    cam._serial_fail_log_backoff = 0.0
    return cam


@pytest.mark.parametrize(
    "source, serial",
    [
        ("/dev/ttyEYELEFT", True),
        ("/dev/serial/by-id/usb-Espressif_ETVR-if00", True),
        ("/dev/eyeleft", True),
        # Unplugged: udev has removed the link, so it no longer resolves.
        ("/dev/serial/by-id/usb-Espressif_ETVR-unplugged-if00", True),
        ("/dev/v4l/by-id/usb-Camera-video-index0", False),
        ("/dev/webcam", False),
        ("/dev/video0", False),
    ],
)
def test_linked_serial_addresses_are_serial_sources(monkeypatch, source, serial):
    _fake_linux_links(monkeypatch)
    assert is_serial_capture_source(source) is serial


def test_serial_connects_through_symlink(monkeypatch):
    _fake_linux_links(monkeypatch)
    monkeypatch.setattr(
        camera.serial.tools.list_ports, "comports", lambda: [types.SimpleNamespace(device="/dev/ttyACM1")]
    )
    monkeypatch.setattr(camera.serial, "Serial", _FakeSerial)
    cam = _bare_camera()

    cam.start_serial_connection("/dev/serial/by-id/usb-Espressif_ETVR-if00")

    assert cam.camera_status == CameraState.CONNECTED
    assert cam.serial_connection.port == "/dev/serial/by-id/usb-Espressif_ETVR-if00"
    assert cam.buffer == b""  # stale bytes can't fake a JPEG boundary


def test_serial_link_to_unplugged_device_stays_disconnected(monkeypatch):
    _fake_linux_links(monkeypatch)
    monkeypatch.setattr(camera.serial.tools.list_ports, "comports", lambda: [])

    def must_not_open(**kwargs):
        raise AssertionError("opened a port that is not plugged in")

    monkeypatch.setattr(camera.serial, "Serial", must_not_open)
    cam = _bare_camera()

    cam.start_serial_connection("/dev/ttyEYELEFT")

    assert cam.camera_status == CameraState.DISCONNECTED
    assert cam.serial_connection is None


# ── frame delivery ───────────────────────────────────────────────────────────


def test_a_full_tracking_queue_drops_its_oldest_frame():
    cam = _camera("COM7")
    cam.camera_output_outgoing = queue.Queue(maxsize=2)
    for n in range(4):
        cam.push_image_to_queue(np.full((2, 2), n, np.uint8), n, 60.0, ts=float(n))

    numbers = [cam.camera_output_outgoing.get_nowait()[1] for _ in range(2)]
    assert numbers == [2, 3]  # the newest frames, never a stale backlog


def test_extra_queues_get_their_own_copy_of_each_frame():
    cam = _camera("COM7")
    recorder = queue.Queue(maxsize=5)
    cam.add_extra_output_queue(recorder)
    image = np.zeros((2, 2), np.uint8)

    cam.push_image_to_queue(image, 7, 60.0, ts=1.5)
    tracked, recorded = cam.camera_output_outgoing.get_nowait(), recorder.get_nowait()

    assert recorded[1:] == tracked[1:] == (7, 60.0, 1.5)
    image[0, 0] = 255  # the tracker draws on its frame...
    assert recorded[0][0, 0] == 0  # ...the recording keeps the camera's pixels
    cam.remove_extra_output_queue(recorder)
    cam.push_image_to_queue(image, 8, 60.0)
    assert recorder.empty()
