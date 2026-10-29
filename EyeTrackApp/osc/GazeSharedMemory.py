"""
Writer for the EyeTrackVR gaze shared memory block (version 1).

The layout, names and reader rules are defined by sdk/eyetrackvr_gaze.h and
docs/gaze-shared-memory.md; this module must stay byte-compatible with them.
Readers are foveated rendering / streaming integrations (OpenXR API layer,
SteamVR driver, encoders) that want gaze without parsing OSC.
"""

import logging
import math
import mmap
import os
import struct
import sys
import time
import zlib
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAGIC = b"ETVG"
VERSION = 1
SIZE = 256
CRC_START = 16
WIN32_NAME = "Local\\EyeTrackVR.Gaze.v1"
POSIX_PATH = "/dev/shm/eyetrackvr_gaze_v1"

CLOCK_QPC_NS = 1
CLOCK_MONOTONIC_NS = 2

EYE_LEFT, EYE_RIGHT, EYE_COMBINED = 0, 1, 2
FLAG_GAZE_VALID = 0x1
FLAG_OPENNESS_VALID = 0x2

_HEADER = struct.Struct("<4sHHII")  # magic, version, size, seq, crc32
_BODY = struct.Struct("<IIQqq")  # clock, sample_count, pid, publish_time_ns, sample_time_ns
_EYE = struct.Struct("<3fffI8x")  # direction, openness, confidence, flags, reserved[2]
_FOV = struct.Struct("<3f")
_SEQ_OFFSET = 8
_CRC_OFFSET = 12
_BODY_OFFSET = 16
_EYES_OFFSET = 48
_FOV_OFFSET = _EYES_OFFSET + 3 * _EYE.size
assert _EYE.size == 32 and _FOV_OFFSET == 144


@dataclass
class GazeEye:
    direction: tuple[float, float, float] = (0.0, 0.0, -1.0)
    openness: float = 0.0
    confidence: float = 0.0
    flags: int = 0


def direction_from_pitch_yaw(pitch_deg: float, yaw_deg: float) -> tuple[float, float, float]:
    """Unit head-space vector (OpenXR: +X right, +Y up, -Z forward) from
    VRChat-convention angles (pitch positive down, yaw positive right)."""
    up = math.radians(-pitch_deg)
    yaw = math.radians(yaw_deg)
    return (math.sin(yaw) * math.cos(up), math.sin(up), -math.cos(yaw) * math.cos(up))


def combine(left: GazeEye, right: GazeEye) -> GazeEye:
    """Normalized average of the valid eyes' directions."""
    valid = [e for e in (left, right) if e.flags & FLAG_GAZE_VALID]
    open_ = [e.openness for e in (left, right) if e.flags & FLAG_OPENNESS_VALID]
    out = GazeEye(
        openness=sum(open_) / len(open_) if open_ else 0.0,
        flags=FLAG_OPENNESS_VALID if open_ else 0,
    )
    if valid:
        x, y, z = (sum(e.direction[i] for e in valid) for i in range(3))
        norm = math.sqrt(x * x + y * y + z * z)
        if norm > 1e-6:
            out.direction = (x / norm, y / norm, z / norm)
            out.confidence = min(e.confidence for e in valid)
            out.flags |= FLAG_GAZE_VALID
    return out


def clock_id() -> int | None:
    """The clock time.perf_counter_ns() reads on this OS, as a CLOCK_* id."""
    if sys.platform == "win32":
        return CLOCK_QPC_NS  # CPython's perf_counter is QueryPerformanceCounter
    if sys.platform.startswith("linux"):
        return CLOCK_MONOTONIC_NS  # ... and clock_gettime(CLOCK_MONOTONIC)
    return None


class GazeSharedMemory:
    def __init__(self):
        self._map: mmap.mmap | None = None
        self._fd: int | None = None
        self._seq = 0
        self._count = 0
        self._clock = clock_id()
        self._buf = bytearray(SIZE)
        self.fov = (0.0, 0.0, 0.0)

    @property
    def is_open(self) -> bool:
        return self._map is not None

    def open(self) -> bool:
        if self._map is not None:
            return True
        if self._clock is None:
            logger.info("Gaze shared memory: not supported on %s", sys.platform)
            return False
        try:
            if sys.platform == "win32":
                self._map = mmap.mmap(-1, SIZE, tagname=WIN32_NAME)
            else:
                self._fd = os.open(POSIX_PATH, os.O_RDWR | os.O_CREAT, 0o600)
                os.ftruncate(self._fd, SIZE)
                self._map = mmap.mmap(self._fd, SIZE)
        except OSError as exc:
            logger.warning("Gaze shared memory: could not create (%s)", exc)
            self._close_handles()
            return False
        # A mapping a reader kept open from an earlier run may hold an odd seq.
        _, _, _, seq, _ = _HEADER.unpack_from(self._map, 0)
        self._seq = (seq + 1) & ~1
        self._count = 0
        _HEADER.pack_into(self._map, 0, MAGIC, VERSION, SIZE, self._seq, 0)
        logger.info("Gaze shared memory published at %s", WIN32_NAME if sys.platform == "win32" else POSIX_PATH)
        return True

    def publish(self, left: GazeEye, right: GazeEye, sample_time_ns: int | None = None) -> None:
        if self._map is None:
            return
        now = time.perf_counter_ns()
        self._count = (self._count + 1) & 0xFFFFFFFF or 1
        buf = self._buf
        _BODY.pack_into(
            buf,
            _BODY_OFFSET,
            self._clock,
            self._count,
            os.getpid(),
            now,
            now if sample_time_ns is None else sample_time_ns,
        )
        for i, eye in enumerate((left, right, combine(left, right))):
            _EYE.pack_into(buf, _EYES_OFFSET + i * _EYE.size, *eye.direction, eye.openness, eye.confidence, eye.flags)
        _FOV.pack_into(buf, _FOV_OFFSET, *self.fov)
        struct.pack_into("<I", buf, _CRC_OFFSET, zlib.crc32(memoryview(buf)[CRC_START:]))

        m = self._map
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        struct.pack_into("<I", m, _SEQ_OFFSET, self._seq)  # odd: readers back off
        m[_CRC_OFFSET:SIZE] = buf[_CRC_OFFSET:SIZE]
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        struct.pack_into("<I", m, _SEQ_OFFSET, self._seq)

    def close(self) -> None:
        """Publish "no gaze" so readers fall back at once, then release."""
        if self._map is not None:
            try:
                self.publish(GazeEye(), GazeEye())
            except (ValueError, OSError):
                pass
        self._close_handles()
        if sys.platform != "win32" and self._clock is not None:
            try:
                os.unlink(POSIX_PATH)
            except OSError:
                pass

    def _close_handles(self) -> None:
        if self._map is not None:
            self._map.close()
            self._map = None
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def read(buffer) -> dict | None:
    """Reference reader (tests, debugging): a consistent sample or None.
    Mirrors etvr_gaze_read() in sdk/eyetrackvr_gaze.h."""
    seq1 = struct.unpack_from("<I", buffer, _SEQ_OFFSET)[0]
    if seq1 & 1:
        return None
    raw = bytes(buffer[:SIZE])
    if struct.unpack_from("<I", buffer, _SEQ_OFFSET)[0] != seq1:
        return None
    magic, version, size, _, crc = _HEADER.unpack_from(raw, 0)
    if magic != MAGIC or version != VERSION or size != SIZE or zlib.crc32(raw[CRC_START:]) != crc:
        return None
    clock, count, pid, publish_ns, sample_ns = _BODY.unpack_from(raw, _BODY_OFFSET)
    eyes = []
    for i in range(3):
        dx, dy, dz, openness, confidence, flags = _EYE.unpack_from(raw, _EYES_OFFSET + i * _EYE.size)
        eyes.append(GazeEye((dx, dy, dz), openness, confidence, flags))
    return {
        "clock": clock,
        "sample_count": count,
        "pid": pid,
        "publish_time_ns": publish_ns,
        "sample_time_ns": sample_ns,
        "eyes": eyes,
        "fov": _FOV.unpack_from(raw, _FOV_OFFSET),
    }
