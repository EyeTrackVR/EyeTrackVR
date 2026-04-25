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
from config import EyeTrackCameraConfig
from enum import Enum
import sys
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
# Re-encode quality used as a compressed-byte proxy for HTTP MJPEG streams.
# cv2.VideoCapture only hands us decoded BGR frames, so we can't see the original
# on-wire JPEG length; re-encoding each frame to JPEG at this quality gives a
# stable, CPU-cheap proxy. It will differ from the server's actual compression
# (typical ESP32-CAM encodes at ~10-15, so 80 overestimates) but tracks frame
# complexity and is far closer to reality than decoded pixel rate.
_HTTP_WIRE_BYTES_PROXY_JPEG_QUALITY = 80
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
        camera_index: int,
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        camera_status_outgoing: "queue.Queue[CameraState]",
        camera_output_outgoing: "queue.Queue(maxsize=20)",
    ):

        self.camera_status = CameraState.CONNECTING
        self.config = config
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

        self.error_message = "Capture source {} not found, retrying..."

    def __del__(self):
        if self.serial_connection is not None:
            self.serial_connection.close()

    def set_output_queue(self, camera_output_outgoing: "queue.Queue"):
        self.camera_output_outgoing = camera_output_outgoing

    def set_extra_output_queues(self, queues: list["queue.Queue"] | None) -> None:
        """Duplicate each captured frame into these queues (BGR numpy frames). Used for dual-eye same physical camera."""
        self._extra_output_queues = list(queues) if queues else []

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
        if cam is None:
            return
        try:
            cam.release()
        except Exception:
            pass
        self.cv2_camera = None

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
            5000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            5000,
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
                    if (
                        self.cv2_camera is None
                        or not self.cv2_camera.isOpened()
                        or self.camera_status == CameraState.DISCONNECTED
                        or source_changed
                    ):
                        logger.info(self.error_message.format(new_source))
                        # This requires a wait, otherwise we can error and possible screw up the camera
                        # firmware. Fickle things.
                        if self.cancellation_event.wait(WAIT_TIME):
                            return
                        # Release any previously opened handle before replacing it, otherwise we
                        # leak OS resources and can block the new open on busy backends (DSHOW/MSMF).
                        self._release_cv2_camera()
                        self._file_video_source_cache = None
                        self.current_capture_source = new_source
                        cam = cv2.VideoCapture()
                        cam.setExceptionMode(True)
                        self.cv2_camera = cam
                        # https://github.com/opencv/opencv/blob/4.8.0/modules/videoio/include/opencv2/videoio.hpp#L803
                        try:
                            cam.open(new_source, cv2.CAP_ANY, OPENCV_PARAMS)
                        except cv2.error as e:
                            logger.warning(
                                "Failed to open capture source %s: %s", new_source, e
                            )
                            self.camera_status = CameraState.DISCONNECTED
                            self._release_cv2_camera()
                            if self.cancellation_event.wait(WAIT_TIME):
                                return
                            continue
                        should_push = False
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
            # Assuming we can access our capture source, wait for another thread to request a capture.
            # Cycle every so often to see if our cancellation token has fired. This basically uses a
            # python event as a context-less, resettable one-shot channel.
            if should_push and not self.capture_event.wait(timeout=0.05):
                continue
            if self.config.capture_source is not None:
                addr = str(self.current_capture_source)
                if is_serial_capture_source(addr):
                    self.get_serial_camera_picture(should_push)
                else:
                    self.get_cv2_camera_picture(should_push)
                if not should_push:
                    # if we get all the way down here, consider ourselves connected
                    self.camera_status = CameraState.CONNECTED

    def get_cv2_camera_picture(self, should_push):
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
                ok, jpeg_buf = cv2.imencode(
                    ".jpg",
                    image,
                    [
                        int(cv2.IMWRITE_JPEG_QUALITY),
                        _HTTP_WIRE_BYTES_PROXY_JPEG_QUALITY,
                    ],
                )
                frame_bytes = int(jpeg_buf.size) if ok else int(image.nbytes)
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
            self._last_cv_cap_frame_time = 0.0
            pass

    def get_next_packet_bounds(self):
        beg = -1
        while beg == -1:
            if self.cancellation_event.is_set() or self.serial_connection is None:
                return -1, -1
            # Bail early if the capture source was changed out from under us.
            if self.config.capture_source != self.current_capture_source:
                return -1, -1
            self.buffer += self.serial_connection.read(2048)
            beg = self.buffer.find(b"\xff\xd8\xff")
        if beg > 0:
            self.buffer = self.buffer[beg:]
            beg = 0

        end = -1
        while end == -1:
            if self.cancellation_event.is_set() or self.serial_connection is None:
                return -1, -1
            if self.config.capture_source != self.current_capture_source:
                return -1, -1
            self.buffer += self.serial_connection.read(128)
            end = self.buffer.find(b"\xff\xd9")
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
            if conn.in_waiting:
                jpeg = self.get_next_jpeg_frame()
                if jpeg:
                    # Create jpeg frame from byte string
                    try:
                        image = np.array(Image.open(BytesIO(jpeg)))
                    except Exception:
                        logger.warning("Frame drop. Corrupted JPEG.")
                        return
                    # Discard the serial buffer. This is due to the fact that it
                    # may build up some outdated frames. A bit of a workaround here tbh.
                    if conn.in_waiting >= 32768:
                        logger.info(
                            "Discarding the serial buffer (%s bytes)", conn.in_waiting
                        )
                        conn.reset_input_buffer()
                        self.buffer = b""
                    # True wire bytes: len(jpeg) is the compressed payload the tracker
                    # pushed over UART, so the Mbps readout matches physical link
                    # bandwidth instead of decoded-pixel throughput.
                    self._update_frame_rate(len(jpeg))
                    self.frame_number = self.frame_number + 1
                    if should_push:
                        self.push_image_to_queue(image, self.frame_number, self.fps)
        except Exception:
            logger.warning(
                "Serial capture source problem, assuming camera disconnected and waiting for reconnect."
            )
            conn.close()
            self.camera_status = CameraState.DISCONNECTED
            pass

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
            # Short read timeout so get_next_packet_bounds() rechecks cancellation / source
            # changes promptly; otherwise stop()/apply_camera_inputs can hang for seconds.
            conn = serial.Serial(
                baudrate=rate,
                port=port,
                xonxoff=False,
                dsrdtr=False,
                rtscts=False,
                timeout=0.25,
            )
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
        self._put_frame_drop_oldest(
            self.camera_output_outgoing, (image, frame_number, fps)
        )
        for extra_q in self._extra_output_queues:
            self._put_frame_drop_oldest(extra_q, (image.copy(), frame_number, fps))
        self.capture_event.clear()
