"""Steam Frame built-in eye cameras as a capture source (``frame://left`` / ``frame://right``).

On the headset, Valve's ``dsp_service`` exposes both eye cameras through shared
memory: connecting to its abstract unix socket hands back a dma-buf holding a
control block and two 8-slot rings of 512x512 8-bit IR frames. No root is needed.
The protocol was learned from Project Babble's Babble-Frame-Runtime and our own
on-device notes (Frame-Reverse-Eng repo); this is an independent implementation.

* ``DspClient`` speaks the protocol and uses only the standard library, so it can
  be exercised with the headset's own python3 (no numpy there).
* ``FrameEyeService`` is the one process-wide reader: a thread that polls the ring
  indices, copies new frames for both eyes and publishes the latest frame per eye,
  cropped to the camera image and turned upright. Each eye's Camera thread
  subscribes to it.

How the cameras actually run (measured on a retail headset, 2026-10): SteamVR's
own eye tracker owns the cameras. It runs them only while the headset is worn,
picks the rate (15 fps with no VR app running, 36-72 fps while one is) and takes
each filled slot for itself, then hands it back to the DSP. Each slot's lock word
shows where it is: 1 free, 4 queued to the camera, 8 or 2 filled and being
claimed by SteamVR. So this reader only watches: it copies each new slot and
writes nothing to the shared memory. Babble's reader marks every slot free (1)
as soon as it sees it, which takes frames away from SteamVR's tracker ("Timed
out waiting for image" in its log) and can hand the DSP a slot SteamVR is still
reading. A gap in frames is normal (headset off), not a broken connection: the
reader keeps its mapping and waits, and only reconnects when ``dsp_service``
itself goes away.
"""

from __future__ import annotations

import logging
import mmap
import os
import platform
import socket
import struct
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

FRAME_SOURCE_PREFIX = "frame://"
FRAME_LEFT_SOURCE = "frame://left"
FRAME_RIGHT_SOURCE = "frame://right"

SERVICE_NAME = b"dsp_service"
REGION_BYTES = 0x1000000  # each mapping is 16 MB
# Babble maps the control block from this file offset of the dma-buf. On a
# 2026-10 retail unit it shows the same memory as offset 0, which is the fallback.
CTRL_MAP_OFFSET = 0x80000000
CTRL_BASE_CANDIDATES = (0x234000, 0x124000)
NOT_READY = 0xFFFFFFFF
REQUEST_SHM_ONLY = 0  # shared memory only: no messages, no streaming-state change


@dataclass(frozen=True)
class Layout:
    """Control-block word offsets, relative to ``ctrl_base``. The rings live in the
    data mapping at the same base. Names follow Babble's headers, which are the
    wrong way round from the wearer: see ``EYE_RINGS``."""

    ctrl_base: int = 0
    transition: int = 0x04
    fps: int = 0x10
    enables: int = 0x48
    idx_l: int = 0x80
    locks_l: int = 0x84
    idx_r: int = 0x1001C0
    locks_r: int = 0x1001C4
    ring_l: int = 0xC0
    ring_r: int = 0x100200
    slot_stride: int = 0x40040
    frame_bytes: int = 0x40000
    slots: int = 8
    width: int = 512
    height: int = 512


@dataclass(frozen=True)
class EyeRing:
    ring: str  # Layout field names
    idx: str
    upside_down: bool = False  # camera mounted rotated 180 degrees


# Wearer's eye -> ring. A closed-eye test on a retail headset showed the ring
# Babble calls ``ring_l`` is the wearer's RIGHT eye. The left camera is mounted
# rotated 180 degrees from the right one.
EYE_RINGS = {
    "left": EyeRing("ring_r", "idx_r", upside_down=True),
    "right": EyeRing("ring_l", "idx_l"),
}

MIN_IMAGE_SIDE = 128  # a smaller nonzero box is not the camera image


def find_image_box(img) -> tuple[int, int, int, int] | None:
    """``(x, y, w, h)`` of the camera image inside a 512x512 slot. The DSP puts a
    400x400 image somewhere in the slot (at 64,0 on 2026-10 retail firmware;
    elsewhere on others) and zero-fills the rest. A few metadata bytes sit at the
    start of row 0, so rows and columns are judged from row 1 down. None when no
    plausible box is found."""
    body = img[1:]
    cols = body.any(axis=0).nonzero()[0]
    rows = body.any(axis=1).nonzero()[0]
    if cols.size == 0 or rows.size == 0:
        return None
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    y0, y1 = int(rows[0]) + 1, int(rows[-1]) + 2
    if y0 == 1:
        y0 = 0  # the image reaches the top row
    w, h = x1 - x0, y1 - y0
    if w < MIN_IMAGE_SIDE or h < MIN_IMAGE_SIDE:
        return None
    return x0, y0, w, h


def is_frame_capture_source(addr) -> bool:
    return isinstance(addr, str) and addr.strip().lower().startswith(FRAME_SOURCE_PREFIX)


def frame_source_eye(addr: str) -> str | None:
    """``frame://left`` -> ``"left"``; None for anything that is not a Frame eye."""
    if not is_frame_capture_source(addr):
        return None
    eye = addr.strip().lower()[len(FRAME_SOURCE_PREFIX):].strip("/")
    return eye if eye in EYE_RINGS else None


def _dsp_service_listening() -> bool:
    try:
        with open("/proc/net/unix", encoding="ascii", errors="replace") as f:
            return any(line.rstrip().endswith("@dsp_service") for line in f)
    except OSError:
        return False


_is_steam_frame: bool | None = None

# Set while data collection records on a Steam Frame: the eye threads keep
# draining their camera queues but run no tracking models, so the recording
# gets the CPU and the full camera rate.
models_paused_for_recording = threading.Event()


def is_steam_frame() -> bool:
    """True when running on a Steam Frame with its eye-camera service available."""
    global _is_steam_frame
    if _is_steam_frame is None:
        _is_steam_frame = (
            platform.system() == "Linux"
            and platform.machine() in ("aarch64", "arm64")
            and _dsp_service_listening()
        )
    return _is_steam_frame


def validate_layout(words: memoryview, layout: Layout) -> str | None:
    """Check a control block image (a ``cast("I")`` view) without writing to it.
    Returns None when valid, else the reason. A wrong base reads pointers or floats
    where small integers belong, so these checks reject it."""
    if layout.ctrl_base + max(layout.locks_l, layout.locks_r) + 4 * layout.slots > len(words) * 4:
        return "control words beyond mapping"
    ring_end = (
        layout.ctrl_base + max(layout.ring_l, layout.ring_r)
        + (layout.slots - 1) * layout.slot_stride + layout.frame_bytes
    )
    if ring_end > REGION_BYTES:
        return "frame ring beyond mapping"

    def word(off: int) -> int:
        return words[(layout.ctrl_base + off) // 4]

    for off in (layout.idx_l, layout.idx_r):
        v = word(off)
        if v >= layout.slots and v != NOT_READY:
            return f"index word +0x{off:x} is 0x{v:x}"
    for base in (layout.locks_l, layout.locks_r):
        for i in range(layout.slots):
            v = word(base + 4 * i)
            if v > 0xFF:
                return f"lock word +0x{base + 4 * i:x} is 0x{v:x}"
    for i in range(2):
        v = word(layout.enables + 4 * i)
        if v > 1:
            return f"enable word +0x{layout.enables + 4 * i:x} is 0x{v:x}"
    fps = _as_float(word(layout.fps))
    if not 0.0 < fps <= 240.0:
        return f"fps word is 0x{word(layout.fps):x}"
    return None


class EyeCamerasNotReady(RuntimeError):
    """dsp_service is up but SteamVR's eye tracker has not set up the cameras
    (camera-rate word still 0): not a fault, so it is retried quickly."""


STEAMVR_SETTINGS = os.path.expanduser("~/.config/openvr/config/steamvr.vrsettings")


def steamvr_eye_tracking_allowed(path: str = STEAMVR_SETTINGS) -> bool | None:
    """SteamVR's ``steamvr/allowEyeTracking`` setting: when False, SteamVR never
    starts its eye tracker and the cameras stay off for every app. None when the
    settings file can't be read (or doesn't set it)."""
    import json

    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f).get("steamvr", {}).get("allowEyeTracking")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, bool) else None


def _as_float(bits: int) -> float:
    value = struct.unpack("<f", struct.pack("<I", bits))[0]
    return value if value == value else 0.0  # NaN -> 0


class DspClient:
    """One connection to ``dsp_service``. Not thread-safe; FrameEyeService owns it.
    The memory is mapped read-only: SteamVR's tracker owns the slots."""

    def __init__(self, name: bytes = SERVICE_NAME, candidates=CTRL_BASE_CANDIDATES):
        self.name = name
        self.candidates = tuple(candidates)
        self.layout: Layout | None = None
        self._sock: socket.socket | None = None
        self._fd = -1
        self._fd_size = 0
        self._data: mmap.mmap | None = None
        self._ctrl_map: mmap.mmap | None = None
        self._ctrl: memoryview | None = None

    def connect(self) -> None:
        """Connect, map and probe. Raises OSError / RuntimeError on failure, with
        nothing written to the shared memory."""
        self.close()
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock = sock
            sock.settimeout(2.0)
            sock.connect(b"\0" + self.name)
            # The service sends the memory fd(s) first, then waits for the request type.
            _msg, fds, _flags, _addr = socket.recv_fds(sock, 256, 4)
            if not fds:
                raise RuntimeError("dsp_service sent no shared-memory fd")
            self._fd = fds[0]
            for extra in fds[1:]:
                os.close(extra)
            sock.sendall(struct.pack("<I", REQUEST_SHM_ONLY))
            sock.setblocking(False)
            # Touching a mapping past the end of an ordinary fd is SIGBUS, which
            # would kill the whole app, so mappings are checked against the fd first.
            self._fd_size = os.lseek(self._fd, 0, os.SEEK_END)
            if self._fd_size < REGION_BYTES:
                raise RuntimeError(f"dsp_service memory is only {self._fd_size} bytes")
            self._data = mmap.mmap(self._fd, REGION_BYTES, mmap.MAP_SHARED, mmap.PROT_READ)
            self.layout = self._probe()
        except BaseException:
            self.close()
            raise

    def _fd_is_dmabuf(self) -> bool:
        try:
            return os.readlink(f"/proc/self/fd/{self._fd}").startswith(("/dmabuf", "anon_inode:dmabuf"))
        except OSError:
            return False

    def _probe(self) -> Layout:
        reasons = []
        views = []
        # A dma-buf exporter validates the offset itself (EINVAL, never SIGBUS);
        # any other fd only gets the high mapping when it is really that large.
        if self._fd_is_dmabuf() or self._fd_size >= CTRL_MAP_OFFSET + REGION_BYTES:
            try:
                self._ctrl_map = mmap.mmap(
                    self._fd, REGION_BYTES, mmap.MAP_SHARED, mmap.PROT_READ, offset=CTRL_MAP_OFFSET
                )
                views.append(("ctrl", memoryview(self._ctrl_map).cast("I")))
            except (OSError, ValueError, OverflowError) as exc:
                reasons.append(f"ctrl mapping: {exc}")
        views.append(("data", memoryview(self._data).cast("I")))
        for which, words in views:
            for base in self.candidates:
                layout = Layout(ctrl_base=base)
                why = validate_layout(words, layout)
                if why is None:
                    self._ctrl = words
                    for other, view in views:
                        if other != which:
                            view.release()
                    if which != "ctrl" and self._ctrl_map is not None:
                        self._ctrl_map.close()
                        self._ctrl_map = None
                    logger.info("Steam Frame eye cameras: control block at %s+0x%x", which, base)
                    return layout
                reasons.append(f"{which}+0x{base:x}: {why}")
        for _which, view in views:
            view.release()
        if self._all_fps_unset():
            if steamvr_eye_tracking_allowed() is False:
                raise EyeCamerasNotReady("eye tracking is turned off in SteamVR settings")
            raise EyeCamerasNotReady("waiting for SteamVR to set up the eye cameras")
        raise RuntimeError("unrecognized dsp_service layout (" + "; ".join(reasons) + ")")

    def _all_fps_unset(self) -> bool:
        try:
            words = memoryview(self._data).cast("I")
        except ValueError:
            return False
        try:
            return all(words[(base + Layout.fps) // 4] == 0 for base in self.candidates)
        finally:
            words.release()

    def _word(self, off: int) -> int:
        return self._ctrl[(self.layout.ctrl_base + off) // 4]

    def read_fps(self) -> float:
        fps = _as_float(self._word(self.layout.fps))
        return fps if 0.0 < fps <= 240.0 else 0.0

    def read_index(self, eye: str) -> int:
        return self._word(getattr(self.layout, EYE_RINGS[eye].idx))

    def copy_frame(self, eye: str, idx: int) -> bytes:
        """The full 512x512 frame in slot ``idx`` of ``eye``'s ring. The slot is
        left to SteamVR's tracker, which claims and frees it."""
        lay = self.layout
        off = lay.ctrl_base + getattr(lay, EYE_RINGS[eye].ring) + idx * lay.slot_stride
        return self._data[off:off + lay.width * lay.height]

    def drain(self) -> int:
        """Read and drop any messages; unread ones fill the socket and upset the
        service. Raises ConnectionError once the service has closed the socket."""
        total = 0
        while self._sock is not None:
            try:
                chunk = self._sock.recv(4096)
            except (BlockingIOError, InterruptedError):
                break
            except OSError as exc:
                raise ConnectionError(f"dsp_service connection lost: {exc}") from exc
            if not chunk:
                raise ConnectionError("dsp_service closed the connection")
            total += len(chunk)
        return total

    def close(self) -> None:
        if self._ctrl is not None:
            self._ctrl.release()
        self._ctrl = None
        for m in (self._ctrl_map, self._data):
            if m is not None:
                try:
                    m.close()
                except BufferError:
                    pass
        self._ctrl_map = self._data = None
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        self.layout = None


class FrameEyeService:
    """Process-wide reader shared by the left and right Camera threads."""

    ACTIVE_POLL = 0.001      # while frames are flowing
    IDLE_POLL = 0.02         # after IDLE_AFTER without a frame
    IDLE_AFTER = 0.5
    WAITING_AFTER = 1.0      # report "waiting for frames" to the cameras
    WAIT_LOG_AFTER = 3.0
    MAX_LAYOUT_FAULTS = 3    # consecutive out-of-range index reads before reconnecting
    RETRY_MIN, RETRY_MAX = 5.0, 60.0  # Babble's reopen backoff
    NOT_READY_RETRY = 2.0    # cameras not set up yet: cheap read-only probe, so retry steadily
    CHECK_INTERVAL = 0.5
    PAIR_WINDOW = 0.005      # the two eyes of one camera pair land this close together

    def __init__(self, client_factory=DspClient, clock=time.monotonic):
        self._client_factory = client_factory
        self._clock = clock
        self._cond = threading.Condition()
        self._subscribers = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._latest: dict[str, tuple[object, int, float]] = {}
        self._seq = {eye: 0 for eye in EYE_RINGS}
        self._boxes: dict[str, tuple[int, int, int, int]] = {}
        self._pair_ts = float("-inf")
        self._pair_eyes: set[str] = set()
        self.camera_fps = 0.0
        self.last_error = ""
        self.streaming = False  # connected to dsp_service with a valid layout
        self.waiting = False    # connected, but no frames lately (headset not worn?)
        self.not_ready = False  # dsp_service is up, SteamVR's eye tracker hasn't started
        self.eye_tracking_off = False  # ...because it's turned off in SteamVR settings

    def subscribe(self) -> None:
        with self._cond:
            self._subscribers += 1
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, name="frame-eye", daemon=True)
                self._thread.start()

    def unsubscribe(self) -> None:
        with self._cond:
            self._subscribers = max(0, self._subscribers - 1)
            if self._subscribers:
                return
            self._stop.set()
            thread = self._thread
            self._cond.notify_all()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def latest(self, eye: str, after_seq: int, timeout: float):
        """Newest ``(gray_image, seq, timestamp)`` for ``eye`` newer than ``after_seq``,
        waiting up to ``timeout`` seconds; None if nothing new arrived."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                item = self._latest.get(eye)
                if item is not None and item[1] > after_seq:
                    return item
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._stop.is_set():
                    return None
                self._cond.wait(remaining)

    def _capture_ts(self, eye: str) -> float:
        """Capture time for a new frame. Both eyes of one camera pair get the same
        value, so the stereo model can tell they belong together."""
        now = time.perf_counter()
        if now - self._pair_ts <= self.PAIR_WINDOW and eye not in self._pair_eyes:
            self._pair_eyes.add(eye)
            return self._pair_ts
        self._pair_ts = now
        self._pair_eyes = {eye}
        return now

    def _publish(self, eye: str, frame: bytes, layout: Layout) -> None:
        import numpy as np

        img = np.frombuffer(frame, dtype=np.uint8).reshape(layout.height, layout.width)
        box = self._boxes.get(eye)
        if box is None:
            box = find_image_box(img)
            if box is None:
                return  # blank frame: look again on the next one
            self._boxes[eye] = box
            logger.info("Steam Frame %s eye image at x=%d y=%d, %dx%d", eye, *box)
        x, y, w, h = box
        img = img[y:y + h, x:x + w]
        if EYE_RINGS[eye].upside_down:
            img = img[::-1, ::-1]
        img = np.ascontiguousarray(img)
        with self._cond:
            self._seq[eye] += 1
            self._latest[eye] = (img, self._seq[eye], self._capture_ts(eye))
            self._cond.notify_all()

    def _run(self) -> None:
        delay = self.RETRY_MIN
        while not self._stop.is_set():
            client = self._client_factory()
            retry = self.RETRY_MIN
            try:
                client.connect()
                self._boxes.clear()  # the image position can differ after a firmware update
                self.last_error = ""
                self.not_ready = self.eye_tracking_off = False
                self.streaming = True
                delay = self.RETRY_MIN
                logger.info("Steam Frame eye cameras connected")
                self._stream(client)
            except EyeCamerasNotReady as exc:
                # Not a fault: retry steadily so frames start soon after eye
                # tracking comes on, and keep the backoff for real failures.
                retry = self.NOT_READY_RETRY
                self.not_ready = True
                self.eye_tracking_off = "turned off" in str(exc)
                if str(exc) != self.last_error:
                    logger.warning("Steam Frame eye cameras not ready: %s", exc)
                self.last_error = str(exc)
            except Exception as exc:
                self.not_ready = self.eye_tracking_off = False
                retry = delay
                msg = str(exc) or exc.__class__.__name__
                if msg != self.last_error:
                    logger.warning("Steam Frame eye cameras unavailable: %s; retrying in %.0fs", msg, retry)
                self.last_error = msg
                delay = min(delay * 2.0, self.RETRY_MAX)
            finally:
                self.streaming = False
                self.waiting = False
                client.close()
            if self._stop.wait(retry):
                break
        with self._cond:
            self._latest.clear()
            self._cond.notify_all()

    def _stream(self, client: DspClient) -> None:
        layout = client.layout
        # Slots already in the ring are old frames: start from the next new index.
        last = {eye: client.read_index(eye) for eye in EYE_RINGS}
        last_frame = self._clock()
        next_check = 0.0
        faults = 0
        reported_wait = False
        while not self._stop.is_set():
            now = self._clock()
            if now >= next_check:
                # SteamVR sets the camera rate when the headset is put on and when a VR
                # app starts or stops (15 fps while none is running).
                fps = client.read_fps()
                if fps > 0 and fps != self.camera_fps:
                    logger.info("Steam Frame eye camera rate %.0f fps (set by SteamVR)", fps)
                self.camera_fps = fps
                client.drain()  # raises once dsp_service is gone
                next_check = now + self.CHECK_INTERVAL
            got = False
            for eye in EYE_RINGS:
                idx = client.read_index(eye)
                if idx == NOT_READY or idx == last[eye]:
                    continue
                if idx >= layout.slots:
                    faults += 1
                    if faults >= self.MAX_LAYOUT_FAULTS:
                        raise RuntimeError(f"dsp_service index out of range (0x{idx:x}); layout changed?")
                    continue
                faults = 0
                last[eye] = idx
                frame = client.copy_frame(eye, idx)
                self._publish(eye, frame, layout)
                got = True
            if got:
                last_frame = now
                if reported_wait:
                    logger.info("Steam Frame eye frames resumed")
                    reported_wait = False
                self.waiting = False
                continue
            gap = now - last_frame
            self.waiting = gap > self.WAITING_AFTER
            if gap > self.WAIT_LOG_AFTER and not reported_wait:
                logger.info("No Steam Frame eye frames for %.0fs (headset not worn?); waiting", gap)
                reported_wait = True
            self._stop.wait(self.ACTIVE_POLL if gap < self.IDLE_AFTER else self.IDLE_POLL)


frame_eye_service = FrameEyeService()
