"""Serial trackers configured through a symlink (udev rule, /dev/serial/by-id)."""

import os
import sys
import types

import camera
from camera import Camera, CameraState, is_serial_capture_source

LINKS = {
    "/dev/ttyEYELEFT": "/dev/ttyACM1",
    "/dev/serial/by-id/usb-Espressif_ETVR-if00": "/dev/ttyACM1",
    "/dev/eyeleft": "/dev/ttyACM1",
    "/dev/webcam": "/dev/video0",
}


def _fake_linux_links(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os.path, "realpath", lambda p: LINKS.get(p, p))


class FakeSerial:
    def __init__(self, port, **kwargs):
        self.port = port
        self.is_open = True

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False


def _camera():
    cam = Camera.__new__(Camera)
    cam.serial_connection = None
    cam.buffer = b"stale"
    cam.camera_status = CameraState.CONNECTING
    return cam


def test_linked_serial_addresses_are_serial_sources(monkeypatch):
    _fake_linux_links(monkeypatch)
    assert is_serial_capture_source("/dev/ttyEYELEFT")
    assert is_serial_capture_source("/dev/serial/by-id/usb-Espressif_ETVR-if00")
    assert is_serial_capture_source("/dev/eyeleft")
    # Unplugged: udev has removed the link, so it no longer resolves.
    assert is_serial_capture_source("/dev/serial/by-id/usb-Espressif_ETVR-unplugged-if00")
    assert not is_serial_capture_source("/dev/v4l/by-id/usb-Camera-video-index0")
    assert not is_serial_capture_source("/dev/webcam")
    assert not is_serial_capture_source("/dev/video0")


def test_serial_connects_through_symlink(monkeypatch):
    _fake_linux_links(monkeypatch)
    monkeypatch.setattr(
        camera.serial.tools.list_ports, "comports", lambda: [types.SimpleNamespace(device="/dev/ttyACM1")]
    )
    monkeypatch.setattr(camera.serial, "Serial", FakeSerial)
    cam = _camera()

    cam.start_serial_connection("/dev/serial/by-id/usb-Espressif_ETVR-if00")

    assert cam.camera_status == CameraState.CONNECTED
    assert cam.serial_connection.port == "/dev/serial/by-id/usb-Espressif_ETVR-if00"


def test_serial_link_to_unplugged_device_stays_disconnected(monkeypatch):
    _fake_linux_links(monkeypatch)
    monkeypatch.setattr(camera.serial.tools.list_ports, "comports", lambda: [])

    def must_not_open(**kwargs):
        raise AssertionError("opened a port that is not plugged in")

    monkeypatch.setattr(camera.serial, "Serial", must_not_open)
    cam = _camera()

    cam.start_serial_connection("/dev/ttyEYELEFT")

    assert cam.camera_status == CameraState.DISCONNECTED
    assert cam.serial_connection is None
