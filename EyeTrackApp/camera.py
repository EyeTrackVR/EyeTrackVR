"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import logging
import cv2
import numpy as np
import queue
import serial
import serial.tools.list_ports
import threading
import time
from config import EyeTrackCameraConfig, EyeTrackSettingsConfig
from enum import Enum
import sys
from camera_enum import is_uvc_named_source, parse_uvc_named_source, resolve_uvc_address_to_index, invalidate_uvc_camera_cache, claim_uvc_address, release_uvc_claim
from PIL import Image
from io import BytesIO

WAIT_TIME = 0.1
logger = logging.getLogger(__name__)
# Serial communication protocol:
# header-begin (2 bytes)
# header-type (2 bytes)
# packet-size (2 bytes)
# packet (packet-size bytes)
ETVR_HEADER = b"\xff\xa0"
ETVR_HEADER_FRAME = b"\xff\xa1"
ETVR_HEADER_LEN = 6


class CameraState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


def is_serial_capture_source(addr: str) -> bool:
    """
    Returns True if the capture source address is a serial port.
    """
    return (
        addr.startswith("COM")
        or addr.startswith("/dev/cu")
        or addr.startswith("/dev/tty")  # Windows  # macOS  # Linux
    )


def is_http_capture_source(addr: str) -> bool:
    """Returns True if the capture source is an http(s) URL. HTTP sources go through
    cv2.VideoCapture (which has a battle-tested FFmpeg-backed MJPEG parser) but we
    flag them here so get_cv2_camera_picture can pick a compressed-byte proxy for
    the bandwidth readout instead of the decoded pixel rate."""
    s = addr.strip().lower()
    return s.startswith("http://") or s.startswith("https://")


# Cap decode rate for sources that can deliver frames faster than the tracker
# pipeline can usefully consume: local video files (disk-speed) and HTTP MJPEG
# cams configured for high fps. Above this, we sleep before reading so we stop
# burning CPU on frames we'd drop anyway.
_FAST_CAPTURE_MAX_FPS = 120.0
_FAST_CAPTURE_MIN_INTERVAL = 1.0 / _FAST_CAPTURE_MAX_FPS
# Network (HTTP/MJPEG) capture timeouts (ms). Well below the old 5 s so a dropped
# Wi-Fi cam (e.g. ETVR.local going offline) is detected in ~2 s instead of stalling
# the capture thread — and, via GIL contention during the blocking native read, the
# GUI — for 5 s per read. Open gets a little longer since the first connect may
# include an mDNS (.local) lookup.
_NETWORK_OPEN_TIMEOUT_MSEC = 3000
_NETWORK_READ_TIMEOUT_MSEC = 2000
# Reconnect backoff for network sources (seconds). Each failed reopen blocks the
# capture thread in native cv2 for up to the open-timeout, so retries are spaced with
# an exponential backoff (min..max) instead of hammering a dead host every loop tick,
# which would peg the thread and starve the UI of the GIL.
_NETWORK_RECONNECT_BACKOFF_MIN = 0.5
_NETWORK_RECONNECT_BACKOFF_MAX = 5.0
# Re-encode quality used as a compressed-byte proxy for HTTP MJPEG streams.
# cv2.VideoCapture only hands us decoded BGR frames, so we can't see the original
# on-wire JPEG length; re-encoding each frame to JPEG at this quality gives a
# stable proxy. It will differ from the server's actual compression (typical
# ESP32-CAM encodes at ~10-15, so 80 overestimates), but sampled periodically it
# is far cheaper than re-encoding every frame and closer than decoded pixel rate.
_HTTP_WIRE_BYTES_PROXY_JPEG_QUALITY = 80
_HTTP_WIRE_BYTES_PROXY_SAMPLE_INTERVAL = 10
# If no JPEG EOI arrives within this many buffered bytes, assume a desync and
# discard the buffer. Prevents unbounded memory growth when the firmware
# sends malformed or truncated frames (cable noise, firmware hang).
_SERIAL_MAX_BUFFER_BYTES = 256 * 1024  # 256 KB ≈ 6 × 40 KB frames
_CV_FILE_VIDEO_EXTENSIONS = (
    ".mp4",
    ".avi",
    ".mkv",
    ".mov",
    ".webm",
    ".m4v",
    ".wmv",
    ".flv",
    ".mpeg",
    ".mpg",
    ".m2v",
    ".3gp",
)


def is_local_file_video_capture_source(capture_source) -> bool:
    """True for local video file paths (by extension). UVC indices, HTTP URLs,
    serial ports, and empty/None are all False."""
    if capture_source is None:
        return False
    if isinstance(capture_source, int):
        return False
    s = str(capture_source).strip()
    if not s:
        return False
    sl = s.lower()
    return any(sl.endswith(ext) for ext in _CV_FILE_VIDEO_EXTENSIONS)


class Camera:
    def __init__(
        self,
        config: EyeTrackCameraConfig,
        settings: EyeTrackSettingsConfig,
        camera_index: int,
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        camera_status_outgoing: "queue.Queue[CameraState]",
        camera_output_outgoing: "queue.Queue(maxsize=20)",
    ):

        self.camera_status = CameraState.CONNECTING
        self.config = config
        self.settings = settings
        self.camera_index = camera_index
        self.camera_address = config.capture_source
        self.camera_status_outgoing = camera_status_outgoing
        self.camera_output_outgoing = camera_output_outgoing
        self._extra_output_queues: list[queue.Queue] = []
        self.capture_event = capture_event
        self.cancellation_event = cancellation_event
        self.current_capture_source = config.capture_source
        self.cv2_camera: "cv2.VideoCapture" = None
        self._file_video_source_cache: tuple[object, bool] | None = None

        self.serial_connection = None
        self.frame_number = 0
        self.fps = 0.0
        self.bps = 0.0
        self.buffer = b""
        # last_frame_time == 0.0 is a "no prior frame" sentinel: the next frame seeds
        # timing without contributing a delta. Keeps the first frame after connect /
        # reconnect / source-change from feeding a multi-second gap into the fps MA.
        self.last_frame_time = 0.0
        self.fl: list[float] = []
        self._last_cv_cap_frame_time = 0.0
        self._last_http_wire_bytes_proxy = 0
        self._http_wire_bytes_proxy_frame_count = 0
        self.error_message = "Capture source {} not found, retrying..."
        # monotonic deadline: don't call resolve_uvc_address_to_index until after this time.
        # Set when the camera is confirmed absent from the enum list; cleared on read failure
        # so a glitch → reconnect cycle doesn't wait unnecessarily.
        self._uvc_not_found_backoff = 0.0
        # Resolved device address currently claimed in the sibling-exclusion registry.
        self._claimed_uvc_address: str | None = None
        # Monotonic deadline for the "not found, retrying" log; throttled to once per 5 s
        # so the log isn't flooded during the 3-second UVC backoff window.
        self._retry_log_backoff: float = 0.0
        # Network (HTTP) reconnect backoff: monotonic deadline before the next reopen
        # attempt, and the current (exponentially growing) delay used to set it.
        self._network_reconnect_backoff: float = 0.0
        self._network_reconnect_delay: float = 0.0

    def __del__(self):
        if self.serial_connection is not None:
            self.serial_connection.close()

    def set_output_queue(self, camera_output_outgoing: "queue.Queue"):
        self.camera_output_outgoing = camera_output_outgoing

    def set_extra_output_queues(self, queues: list["queue.Queue"] | None) -> None:
        """Duplicate each captured frame into these queues (BGR numpy frames). Used for dual-eye same physical camera."""
        self._extra_output_queues = list(queues) if queues else []

    def add_extra_output_queue(self, q: "queue.Queue") -> None:
        if q not in self._extra_output_queues:
            self._extra_output_queues.append(q)

    def remove_extra_output_queue(self, q: "queue.Queue") -> None:
        if q in self._extra_output_queues:
            self._extra_output_queues.remove(q)

    def _is_local_file_video_cached(self, capture_source) -> bool:
        key = capture_source
        if (
            self._file_video_source_cache is not None
            and self._file_video_source_cache[0] == key
        ):
            return self._file_video_source_cache[1]
        v = is_local_file_video_capture_source(capture_source)
        self._file_video_source_cache = (key, v)
        return v

    def _release_cv2_camera(self) -> None:
        cam = self.cv2_camera
        if cam is not None:
            try:
                cam.release()
            except Exception:
                pass
            self.cv2_camera = None
        if self._claimed_uvc_address is not None:
            release_uvc_claim(id(self))
            self._claimed_uvc_address = None

    def _close_serial_connection(self) -> None:
        conn = self.serial_connection
        if conn is None:
            return
        try:
            if conn.is_open:
                conn.close()
        except Exception:
            pass
        self.serial_connection = None
        self.buffer = b""

    def _reset_frame_stats(self) -> None:
        """Clear fps / bps moving-average state. Called on source change so the readouts
        don't blend the old source's rate with the new source's frame timing."""
        self.fl = []
        self.last_frame_time = 0.0
        self.fps = 0.0
        self.bps = 0.0
        self.frame_number = 0
        self._last_http_wire_bytes_proxy = 0
        self._http_wire_bytes_proxy_frame_count = 0

    def _reset_network_reconnect_backoff(self) -> None:
        """Clear the network reconnect backoff. Called on a successful connect and on
        source change so a fresh source starts retrying immediately."""
        self._network_reconnect_backoff = 0.0
        self._network_reconnect_delay = 0.0

    def _bump_network_reconnect_backoff(self) -> None:
        """Grow the network reconnect backoff (exponential, capped at
        _NETWORK_RECONNECT_BACKOFF_MAX) after a failed HTTP open so a permanently
        offline cam doesn't peg the capture thread in back-to-back blocking opens."""
        if self._network_reconnect_delay <= 0.0:
            self._network_reconnect_delay = _NETWORK_RECONNECT_BACKOFF_MIN
        else:
            self._network_reconnect_delay = min(
                self._network_reconnect_delay * 2.0, _NETWORK_RECONNECT_BACKOFF_MAX
            )
        self._network_reconnect_backoff = (
            time.monotonic() + self._network_reconnect_delay
        )

    def _update_frame_rate(self, frame_bytes: int) -> None:
        """Update fps / bps moving averages for the most recently received frame.

        ``frame_bytes`` is the best available byte-count for this frame:
          - Serial path: ``len(jpeg)`` — true compressed bytes on the UART wire.
          - cv2 HTTP:    length of a re-encoded JPEG at a fixed quality — a stable
                         compressed-byte proxy (cv2.VideoCapture hides the original
                         on-wire JPEG length from us). Approximates wire bandwidth.
          - cv2 UVC/file: ``image.nbytes`` pre-resize — decoded pixel bytes, since
                         there's no compressed source to measure. Decoded pixel-rate
                         proxy, not true wire bandwidth.

        The first call after a reset / reconnect only seeds ``last_frame_time`` and
        does NOT contribute an fps sample, which avoids polluting the MA with a
        multi-second gap between camera init and the first frame.
        """
        current_time = time.time()
        if self.last_frame_time > 0.0:
            delta = current_time - self.last_frame_time
            if delta > 0:
                current_fps = 1.0 / delta
                if len(self.fl) < 60:
                    self.fl.append(current_fps)
                else:
                    self.fl.pop(0)
                    self.fl.append(current_fps)
                self.fps = sum(self.fl) / len(self.fl)
                self.bps = frame_bytes * self.fps
        self.last_frame_time = current_time

    def run(self):
        OPENCV_PARAMS = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            _NETWORK_OPEN_TIMEOUT_MSEC,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            _NETWORK_READ_TIMEOUT_MSEC,
        ]
        while True:
            if self.cancellation_event.is_set():
                logger.info("Exiting capture thread")
                # Release ALL backends regardless of which one is active, since we may be mid-
                # transition between them. Guarded against None so early shutdown doesn't crash.
                self._release_cv2_camera()
                self._close_serial_connection()
                return
            should_push = True
            # If things aren't open, retry until they are. Don't let read requests come in any earlier
            # than this, otherwise we can deadlock ourselves.
            new_source = self.config.capture_source
            if new_source is not None and new_source != "":
                source_changed = new_source != self.current_capture_source
                addr = str(new_source)
                if is_serial_capture_source(addr):
                    # Switching to serial from any other backend: release their handles.
                    if source_changed:
                        self._release_cv2_camera()
                        self._reset_frame_stats()
                    if (
                        self.serial_connection is None
                        or self.camera_status == CameraState.DISCONNECTED
                        or source_changed
                    ):
                        self.current_capture_source = new_source
                        self.start_serial_connection(new_source)
                        should_push = False
                else:
                    # Switching to cv2 (local UVC / HTTP MJPEG / file) from any other backend.
                    if source_changed:
                        self._close_serial_connection()
                        self._reset_frame_stats()
                        self._reset_network_reconnect_backoff()
                    if (
                        self.cv2_camera is None
                        or not self.cv2_camera.isOpened()
                        or self.camera_status == CameraState.DISCONNECTED
                        or source_changed
                    ):
                        _is_network_source = is_http_capture_source(addr)
                        # Space out reconnect attempts to a dropped network cam. Each
                        # failed reopen blocks this thread in native cv2 (open-timeout +
                        # a possible mDNS lookup), so without a backoff a permanently
                        # offline ETVR.local pegs the thread in back-to-back multi-second
                        # opens and starves the Tk UI of the GIL — the lag/hang users see.
                        if (
                            _is_network_source
                            and not source_changed
                            and time.monotonic() < self._network_reconnect_backoff
                        ):
                            self.camera_status = CameraState.DISCONNECTED
                            if self.cancellation_event.wait(WAIT_TIME):
                                return
                            continue
                        _now_log = time.monotonic()
                        if source_changed or _now_log >= self._retry_log_backoff:
                            logger.info(self.error_message.format(new_source))
                            self._retry_log_backoff = _now_log + 5.0
                        # Give camera firmware time to settle before retrying the backend open.
                        if self.cancellation_event.wait(WAIT_TIME):
                            return
                        # Release any previously opened handle before replacing it, otherwise we
                        # leak OS resources and can block the new open on busy backends (DSHOW/MSMF).
                        self._release_cv2_camera()
                        self._file_video_source_cache = None
                        self.current_capture_source = new_source
                        # Resolve uvc:Name@Address to a cv2 integer index before
                        # opening — cv2.VideoCapture doesn't understand the uvc: prefix.
                        open_source = new_source
                        if isinstance(new_source, str) and is_uvc_named_source(new_source):
                            _name, _addr = parse_uvc_named_source(new_source)
                            # Skip the (potentially expensive) enumeration until the backoff
                            # expires. This prevents two camera threads from hammering
                            # DirectShow every ~100 ms when the device is absent, which
                            # competes with active cv2 DSHOW handles on the other camera.
                            if time.monotonic() < self._uvc_not_found_backoff:
                                self.camera_status = CameraState.DISCONNECTED
                                if self.cancellation_event.wait(WAIT_TIME):
                                    return
                                continue
                            _result = resolve_uvc_address_to_index(_name, _addr, owner_id=id(self))
                            if _result is None:
                                logger.info(
                                    "UVC camera '%s' not found (not connected?), retrying...",
                                    _name,
                                )
                                self.camera_status = CameraState.DISCONNECTED
                                # Back off for the same duration as the enum cache TTL so
                                # we don't trigger a new pygrabber scan on every loop tick.
                                self._uvc_not_found_backoff = time.monotonic() + 3.0
                                if self.cancellation_event.wait(WAIT_TIME):
                                    return
                                continue
                            _idx, _resolved_addr = _result
                            # Claim this address immediately so that sibling camera threads
                            # (same name, different stored address) can exclude it when
                            # doing their own fallback resolution.
                            if self._claimed_uvc_address != _resolved_addr:
                                if self._claimed_uvc_address is not None:
                                    release_uvc_claim(id(self))
                                self._claimed_uvc_address = _resolved_addr
                                claim_uvc_address(id(self), _resolved_addr)
                            open_source = _idx
                        cam = cv2.VideoCapture()
                        cam.setExceptionMode(True)
                        self.cv2_camera = cam
                        # Only pass network timeout params to HTTP/MJPEG sources.
                        # MSMF and DSHOW log "can't set property 53" and may abort
                        # the open entirely when given unsupported init params.
                        _is_network = isinstance(open_source, str) and is_http_capture_source(open_source)
                        _open_params = OPENCV_PARAMS if _is_network else []
                        # On Windows, use DSHOW explicitly for integer UVC indices.
                        # CAP_ANY tries obsensor/MSMF first, which probes all indices
                        # (causing log spam and ~1 s delay) and is less stable for plain
                        # UVC cams than DSHOW. CAP_ANY is kept for HTTP and file sources.
                        if sys.platform == "win32" and isinstance(open_source, int):
                            _backend = cv2.CAP_DSHOW
                        else:
                            _backend = cv2.CAP_ANY
                        # https://github.com/opencv/opencv/blob/4.8.0/modules/videoio/include/opencv2/videoio.hpp#L803
                        try:
                            cam.open(open_source, _backend, _open_params)
                        except cv2.error as e:
                            logger.warning(
                                "Failed to open capture source %s: %s", new_source, e
                            )
                            self.camera_status = CameraState.DISCONNECTED
                            self._release_cv2_camera()
                            if _is_network_source:
                                self._bump_network_reconnect_backoff()
                            if self.cancellation_event.wait(WAIT_TIME):
                                return
                            continue
                        # A network open can return without raising yet still not be
                        # connected (dead host / timed-out mDNS). Treat that as a failed
                        # attempt so the backoff applies instead of spinning on reopen.
                        if _is_network_source and not cam.isOpened():
                            self.camera_status = CameraState.DISCONNECTED
                            self._release_cv2_camera()
                            self._bump_network_reconnect_backoff()
                            if self.cancellation_event.wait(WAIT_TIME):
                                return
                            continue
                        # Invalidate the UVC cache so the next scan sees the current
                        # device state (e.g. the camera is now held by this process).
                        invalidate_uvc_camera_cache()
            else:
                # We don't have a capture source to try yet, wait for one to show up in the GUI.
                # Release any lingering handles so swapping "no source" then "new source" works cleanly.
                self._release_cv2_camera()
                self._close_serial_connection()
                self.current_capture_source = None
                self.camera_status = CameraState.DISCONNECTED
                if self.cancellation_event.wait(WAIT_TIME):
                    return
                continue
            if self.config.capture_source is not None:
                addr = str(self.current_capture_source)
                if is_serial_capture_source(addr):
                    self.get_serial_camera_picture(True)
                else:
                    self.get_cv2_camera_picture(True)
                if self.camera_status != CameraState.DISCONNECTED:
                    self.camera_status = CameraState.CONNECTED
                    self._retry_log_backoff = 0.0
                    self._reset_network_reconnect_backoff()

    def get_cv2_camera_picture(self, should_push):
        if self.cv2_camera is None or not self.cv2_camera.isOpened():
            self.camera_status = CameraState.DISCONNECTED
            return
        try:
            is_file_video = self._is_local_file_video_cached(
                self.current_capture_source
            )
            is_http = is_http_capture_source(str(self.current_capture_source))
            # HTTP MJPEG cams (esp. ESP32) and local files can hand cv2 frames as fast
            # as the link / disk allows. Both deserve the same throttle; UVC paces
            # itself on hardware fps.
            throttle_source = is_file_video or is_http
            if should_push and throttle_source:
                # [Limiter lag fix] We now handle the main tracking Hz limit in the caller.
                # However, MJPEG/File sources still need a "fast-path" safety cap to prevent
                # them from outrunning the loop's own overhead if max_hz is very high.
                now = time.time()
                last = self._last_cv_cap_frame_time
                if last > 0.0:
                    wait = _FAST_CAPTURE_MIN_INTERVAL - (now - last)
                    if wait > 0:
                        time.sleep(wait)

            ret, image = self.cv2_camera.read()
            if not ret or image is None:
                self.cv2_camera.set(cv2.CAP_PROP_POS_FRAMES, 0)
                raise RuntimeError("Problem while getting frame")
            # Byte count for bps readout. Captured BEFORE downscale so the number
            # reflects what the backend actually delivered, not what we resized to.
            #   - HTTP MJPEG: we never see the server's JPEG; re-encode at fixed
            #     quality as a stable compressed-byte proxy. Approximates wire
            #     bandwidth (factor of ~2-5x off typical low-Q ESP32 streams, but
            #     tracks frame complexity correctly).
            #   - UVC / file: no compressed source to measure; ``image.nbytes`` is
            #     the decoded pixel-rate proxy.
            if is_http:
                should_sample_proxy = (
                    self._last_http_wire_bytes_proxy <= 0
                    or self._http_wire_bytes_proxy_frame_count
                    % _HTTP_WIRE_BYTES_PROXY_SAMPLE_INTERVAL
                    == 0
                )
                self._http_wire_bytes_proxy_frame_count += 1
                if should_sample_proxy:
                    ok, jpeg_buf = cv2.imencode(
                        ".jpg",
                        image,
                        [
                            int(cv2.IMWRITE_JPEG_QUALITY),
                            _HTTP_WIRE_BYTES_PROXY_JPEG_QUALITY,
                        ],
                    )
                    self._last_http_wire_bytes_proxy = (
                        int(jpeg_buf.size) if ok else int(image.nbytes)
                    )
                frame_bytes = self._last_http_wire_bytes_proxy
            else:
                frame_bytes = image.nbytes
            height, width = image.shape[:2]  # Calculate the aspect ratio
            if int(width) > 680:
                aspect_ratio = float(width) / float(
                    height
                )  # Determine the new height based on the desired maximum width
                new_height = int(680 / aspect_ratio)
                image = cv2.resize(image, (680, new_height))
            if should_push and throttle_source:
                self._last_cv_cap_frame_time = time.time()
            frame_number = self.cv2_camera.get(cv2.CAP_PROP_POS_FRAMES)
            self._update_frame_rate(frame_bytes)

            if should_push:
                self.push_image_to_queue(image, frame_number, self.fps)
        except Exception:
            logger.warning(
                "Capture source problem, assuming camera disconnected and waiting for reconnect."
            )
            self.camera_status = CameraState.DISCONNECTED
            # Clear the not-found backoff so we immediately attempt a reconnect rather
            # than waiting up to 3 s — the camera was working moments ago, so it's
            # very likely still present in the DirectShow enum list.
            self._uvc_not_found_backoff = 0.0
            self._last_cv_cap_frame_time = 0.0
            pass

    def get_next_packet_bounds(self):
        # Non-blocking SOI scan: read only bytes already in the OS buffer.
        # Blocking here lets the hardware buffer fill up and overflow, which
        # corrupts the very frame we're waiting for.
        try:
            waiting = self.serial_connection.in_waiting
        except Exception:
            waiting = 0
        if waiting > 0:
            self.buffer += self.serial_connection.read(min(waiting, 4096))

        beg = self.buffer.find(b"\xff\xd8\xff")
        if beg == -1:
            if len(self.buffer) > _SERIAL_MAX_BUFFER_BYTES:
                logger.warning("Serial buffer overrun without JPEG SOI; discarding.")
                self.buffer = b""
            return -1, -1
        if beg > 0:
            self.buffer = self.buffer[beg:]
            beg = 0

        # SOI is in hand – now block for the rest of the frame (EOI).
        # A complete frame arrives in well under 100 ms; 2 s is a safety net.
        end = self.buffer.find(b"\xff\xd9")
        deadline = time.monotonic() + 2.0
        while end == -1:
            if self.cancellation_event.is_set() or self.serial_connection is None:
                return -1, -1
            if self.config.capture_source != self.current_capture_source:
                return -1, -1
            if time.monotonic() > deadline:
                logger.warning("Serial: timed out waiting for JPEG EOI; resyncing.")
                self.buffer = b""
                return -1, -1
            self.buffer += self.serial_connection.read(4096)
            end = self.buffer.find(b"\xff\xd9")
            if len(self.buffer) > _SERIAL_MAX_BUFFER_BYTES:
                logger.warning("Serial buffer overrun without JPEG EOI; discarding.")
                self.buffer = b""
                return -1, -1
        return beg, end

    def get_next_jpeg_frame(self):
        beg, end = self.get_next_packet_bounds()
        if beg < 0 or end < 0:
            return None
        jpeg = self.buffer[beg : end + 2]
        self.buffer = self.buffer[end + 2 :]
        return jpeg

    def get_serial_camera_picture(self, should_push):
        conn = self.serial_connection
        if conn is None:
            return
        try:
            waiting = conn.in_waiting
            # Drain stale frames BEFORE parsing so the OS hardware buffer never
            # overflows mid-frame. Half the buffer size (16 KB) is the trigger:
            # at that point we're already ~1 frame behind and catching up is
            # cheaper than corrupting the one we're assembling.
            if waiting >= 16384:
                logger.info("Discarding the serial buffer (%s bytes)", waiting)
                conn.reset_input_buffer()
                self.buffer = b""
                return
            if not waiting and not self.buffer:
                # No serial data yet. Yield for 1 ms instead of spinning:
                # without this the outer run() loop calls in_waiting tens of
                # thousands of times per second between frames, saturating a CPU
                # core and starving the UI event loop via GIL contention.
                self.cancellation_event.wait(0.001)
                return
            jpeg = self.get_next_jpeg_frame()
            if jpeg and should_push:
                # cv2.imdecode always returns a 3-channel BGR array (even for
                # grayscale IR cameras), which is exactly what the rest of the
                # pipeline expects. No PIL mode gymnastics needed.
                nparr = np.frombuffer(jpeg, dtype=np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if image is None:
                    logger.warning("Frame drop. Corrupted JPEG.")
                    self.buffer = b""
                    return
                # True wire bytes: len(jpeg) is the compressed payload the tracker
                # pushed over UART, so the Mbps readout matches physical link
                # bandwidth instead of decoded-pixel throughput.
                self._update_frame_rate(len(jpeg))
                self.frame_number += 1
                self.push_image_to_queue(image, self.frame_number, self.fps)
        except Exception:
            logger.warning(
                "Serial capture source problem, assuming camera disconnected and waiting for reconnect."
            )
            self._close_serial_connection()
            self.camera_status = CameraState.DISCONNECTED

    def start_serial_connection(self, port):
        if self.serial_connection is not None and self.serial_connection.is_open:
            # Do nothing. The connection is already open on this port.
            if self.serial_connection.port == port:
                self.camera_status = CameraState.CONNECTED
                return
            # Otherwise, close the connection before trying to reopen.
            try:
                self.serial_connection.close()
            except Exception:
                pass
            self.serial_connection = None
        # Always discard the buffer when opening a fresh connection so stale bytes
        # from a previous session can't produce false JPEG boundaries.
        self.buffer = b""
        com_ports = [tuple(p) for p in list(serial.tools.list_ports.comports())]
        # Do not try connecting if no such port i.e. device was unplugged.
        if not any(p for p in com_ports if port in p):
            self.camera_status = CameraState.DISCONNECTED
            return
        try:
            rate = (
                115200 if sys.platform == "darwin" else 3000000
            )  # Higher baud rate not working on macOS
            # timeout=0.25: read() returns every 250 ms so get_next_packet_bounds()
            # can check cancellation/source-change promptly without blocking forever.
            conn = serial.Serial(
                baudrate=rate,
                port=port,
                xonxoff=False,
                dsrdtr=False,
                rtscts=False,
                timeout=0.25,
            )
            # Flush any garbage queued before we opened the port.
            conn.reset_input_buffer()
            # Set explicit buffer size for serial.
            if sys.platform == "win32":
                buffer_size = 32768
                conn.set_buffer_size(rx_size=buffer_size, tx_size=buffer_size)

            logger.info("ETVR Serial Tracker device connected on %s", port)
            self.serial_connection = conn
            self.camera_status = CameraState.CONNECTED
        except Exception:
            logger.info("Failed to connect on %s", port)
            self.camera_status = CameraState.DISCONNECTED

    def _put_frame_drop_oldest(self, q: "queue.Queue", item: tuple) -> None:
        try:
            q.put_nowait(item)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(item)
            except queue.Full:
                pass

    def push_image_to_queue(self, image, frame_number, fps):
        # If there's backpressure, just yell. We really shouldn't have this unless we start getting
        # some sort of capture event conflict though.
        qsize = self.camera_output_outgoing.qsize()
        if qsize > 1:
            logger.warning(
                "Capture queue backpressure of %s. Check for crash or timing issues in algorithm.",
                qsize,
            )
        ts = time.perf_counter()
        self._put_frame_drop_oldest(
            self.camera_output_outgoing, (image, frame_number, fps, ts)
        )
        for extra_q in self._extra_output_queues:
            self._put_frame_drop_oldest(extra_q, (image.copy(), frame_number, fps, ts))
