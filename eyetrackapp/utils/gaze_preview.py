"""Live gaze preview in the headset.

While the calibration overlay runs in ``preview`` mode, the app streams the
gaze it outputs to the overlay, which draws it as a ring over a reference dot.
Users look at the dot and see how closely their tracked gaze follows it.

The overlay takes ``>i 140, >f tan_x, >f tan_y, >f openness`` on its command
port: the tangents of the gaze yaw and pitch in head space (+x right, +y up).
Gaze ±1 maps to the configured FOV edge the same way as the pyVRCFT native
endpoint, ``atan(gaze * tan(max))``, so the ring sits where avatars look.
"""

from __future__ import annotations

import math
import socket
import struct
import threading
import time

OVERLAY_CMD_PORT = 2113
CMD_TEXT = 50
CMD_GAZE = 140
CMD_QUIT = 200
SIG_READY = 255

# An eye that has sent nothing for this long no longer counts towards the
# combined gaze, so a stalled camera doesn't hold the ring in place.
EYE_STALE_S = 0.25


def gaze_tangents(x: float, y: float, yaw_max_deg: float, pitch_up_deg: float, pitch_down_deg: float):
    """(tan_x, tan_y) in head space for normalized gaze (x right, y up)."""
    pitch_max = pitch_up_deg if y >= 0.0 else pitch_down_deg
    return x * math.tan(math.radians(yaw_max_deg)), y * math.tan(math.radians(pitch_max))


def _finite(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


class GazePreviewStream:
    """Sends each output gaze sample to the overlay, both eyes combined."""

    def __init__(self, settings, address=("127.0.0.1", OVERLAY_CMD_PORT)):
        self.address = address
        self.fov = (
            float(settings.gui_gaze_yaw_max_deg),
            float(settings.gui_gaze_pitch_up_deg),
            float(settings.gui_gaze_pitch_down_deg),
        )
        self.invert_close = bool(settings.osc_invert_eye_close)
        self._eyes: dict = {}  # eye id -> (x, y, openness, monotonic time)
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_text(self, text: str) -> None:
        self._send(struct.pack(">i", CMD_TEXT) + text.encode("utf-8"))

    def quit(self) -> None:
        self._send(struct.pack(">i", CMD_QUIT))

    def feed(self, eye_id, eye_info, single_eye: bool) -> None:
        x, y, openness = _finite(eye_info.x), _finite(eye_info.y), _finite(eye_info.blink)
        if x is None or y is None or openness is None:
            return
        if self.invert_close:
            openness = 1.0 - openness
        now = time.monotonic()
        with self._lock:
            if single_eye:
                self._eyes.clear()
            self._eyes[eye_id] = (x, y, openness, now)
            fresh = [e for e in self._eyes.values() if now - e[3] <= EYE_STALE_S]
        n = len(fresh)
        x = sum(e[0] for e in fresh) / n
        y = sum(e[1] for e in fresh) / n
        openness = sum(e[2] for e in fresh) / n
        tan_x, tan_y = gaze_tangents(x, y, *self.fov)
        self._send(struct.pack(">ifff", CMD_GAZE, tan_x, tan_y, min(max(openness, 0.0), 1.0)))

    def close(self) -> None:
        self._sock.close()

    def _send(self, payload: bytes) -> None:
        try:
            self._sock.sendto(payload, self.address)
        except OSError:
            pass  # the overlay is gone; the session notices and ends


# The running preview's stream once the overlay is ready, fed by the OSC sender
# thread; None otherwise. _running also covers the overlay starting up.
_active: GazePreviewStream | None = None
_running = False


def set_active(stream: GazePreviewStream | None) -> None:
    global _active
    _active = stream


def set_running(running: bool) -> None:
    global _running
    _running = running


def is_running() -> bool:
    return _running


def feed(eye_id, eye_info, single_eye: bool) -> None:
    """Pass one output gaze sample to the preview, if one is running."""
    stream = _active
    if stream is not None:
        stream.feed(eye_id, eye_info, single_eye)
