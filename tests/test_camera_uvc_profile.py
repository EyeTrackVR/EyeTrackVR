import logging

import cv2

from camera import Camera, _UVC_REQUESTED_FPS


class FakeCapture:
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
    capture = FakeCapture()
    caplog.set_level(logging.INFO)

    Camera._negotiate_uvc_profile(object(), capture)

    assert capture.set_calls == [
        (cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")),
        (cv2.CAP_PROP_FPS, _UVC_REQUESTED_FPS),
    ]
    assert "format=MJPG" in caplog.text


def test_fourcc_name_decodes_opencv_property():
    assert Camera._fourcc_name(cv2.VideoWriter_fourcc(*"MJPG")) == "MJPG"
