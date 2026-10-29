"""Gaze shared memory (sdk/eyetrackvr_gaze.h): layout, seqlock/CRC reader
rules, and the foveation sender publishing into it."""

import math
import mmap
import os
import re
import struct
import sys
import time
import uuid
from queue import Queue
from time import monotonic, sleep
from unittest import mock

import pytest

from eye import EyeId
from osc import GazeSharedMemory as shm_module
from osc.GazeSharedMemory import (
    CLOCK_MONOTONIC_NS,
    CLOCK_QPC_NS,
    EYE_COMBINED,
    EYE_LEFT,
    EYE_RIGHT,
    FLAG_GAZE_VALID,
    FLAG_OPENNESS_VALID,
    GazeEye,
    GazeSharedMemory,
    direction_from_pitch_yaw,
    read,
)
from osc.osc import OSCManager
from osc.OSCMessage import OSCMessage, OSCMessageType
from tests import EyeInfoMock, SimpleUDPClientMock

HEADER_PATH = os.path.join(os.path.dirname(__file__), "..", "sdk", "eyetrackvr_gaze.h")


@pytest.fixture(autouse=True)
def private_names(monkeypatch):
    """Never touch the block a running EyeTrackVR publishes."""
    tag = uuid.uuid4().hex
    monkeypatch.setattr(shm_module, "WIN32_NAME", f"Local\\EyeTrackVR.Gaze.test.{tag}")
    monkeypatch.setattr(shm_module, "POSIX_PATH", f"/dev/shm/eyetrackvr_gaze_test_{tag}")


def _reader_view():
    """A second, reader-side mapping of the block, as another process would open it."""
    if sys.platform == "win32":
        return mmap.mmap(-1, shm_module.SIZE, tagname=shm_module.WIN32_NAME, access=mmap.ACCESS_READ)
    fd = os.open(shm_module.POSIX_PATH, os.O_RDONLY)
    try:
        return mmap.mmap(fd, shm_module.SIZE, access=mmap.ACCESS_READ)
    finally:
        os.close(fd)


def _eye(pitch, yaw, openness=1.0):
    return GazeEye(direction_from_pitch_yaw(pitch, yaw), openness, 1.0, FLAG_GAZE_VALID | FLAG_OPENNESS_VALID)


# ---------------------------------------------------------------- layout


def test_layout_matches_c_header():
    """Offsets in the Python writer agree with the struct in the C header."""
    with open(HEADER_PATH, encoding="utf-8") as f:
        header = f.read()
    defines = {
        m.group(1): int(m.group(2), 0)
        for m in re.finditer(r"^#define (ETVR_GAZE_\w+) (0x[0-9A-Fa-f]+|\d+)(?:u|LL)?\b", header, re.M)
    }
    for name, value in [
        ("ETVR_GAZE_VERSION", shm_module.VERSION),
        ("ETVR_GAZE_SIZE", shm_module.SIZE),
        ("ETVR_GAZE_CRC_START", shm_module.CRC_START),
        ("ETVR_GAZE_CLOCK_QPC_NS", CLOCK_QPC_NS),
        ("ETVR_GAZE_CLOCK_MONOTONIC_NS", CLOCK_MONOTONIC_NS),
        ("ETVR_GAZE_FLAG_GAZE_VALID", FLAG_GAZE_VALID),
        ("ETVR_GAZE_FLAG_OPENNESS_VALID", FLAG_OPENNESS_VALID),
    ]:
        assert defines[name] == value, name
    assert 'ETVR_GAZE_MAGIC "ETVG"' in header
    assert 'L"Local\\\\EyeTrackVR.Gaze.v1"' in header
    assert '"/eyetrackvr_gaze_v1"' in header
    assert shm_module.POSIX_PATH != "/dev/shm/eyetrackvr_gaze_v1"  # fixture is active
    # header 16 + body 32 + 3 eyes * 32 + fov 12 + reserved 100
    assert 16 + 32 + 3 * 32 + 12 + 100 == shm_module.SIZE


def test_direction_convention():
    assert direction_from_pitch_yaw(0, 0) == pytest.approx((0, 0, -1))
    x, y, z = direction_from_pitch_yaw(-10, 0)  # VRChat pitch negative = looking up
    assert y > 0 and z < 0 and x == pytest.approx(0)
    x, y, z = direction_from_pitch_yaw(0, 20)
    assert x > 0 and z < 0 and y == pytest.approx(0)
    assert math.dist((0, 0, 0), direction_from_pitch_yaw(13, -27)) == pytest.approx(1)


# ------------------------------------------------------------ writer/reader


@pytest.mark.skipif(shm_module.clock_id() is None, reason="no shared memory on this OS")
def test_roundtrip_through_a_second_mapping():
    writer = GazeSharedMemory()
    writer.fov = (40.0, 15.0, 40.0)
    assert writer.open()
    try:
        view = _reader_view()
        assert read(view) is None  # header only: no sample yet, so the CRC can't match
        before = time.perf_counter_ns()
        writer.publish(_eye(-5, -10), _eye(5, 10), sample_time_ns=123456789)
        sample = read(view)
        assert sample is not None
        assert sample["clock"] == shm_module.clock_id()
        assert sample["sample_count"] == 1
        assert sample["pid"] == os.getpid()
        assert sample["sample_time_ns"] == 123456789
        assert before <= sample["publish_time_ns"] <= time.perf_counter_ns()
        assert sample["fov"] == pytest.approx((40.0, 15.0, 40.0))
        left, right, combined = (sample["eyes"][i] for i in (EYE_LEFT, EYE_RIGHT, EYE_COMBINED))
        assert left.direction == pytest.approx(direction_from_pitch_yaw(-5, -10), abs=1e-6)
        assert right.direction == pytest.approx(direction_from_pitch_yaw(5, 10), abs=1e-6)
        # Symmetric eyes: combined looks straight ahead.
        assert combined.direction == pytest.approx((0, 0, -1), abs=1e-6)
        assert combined.flags == FLAG_GAZE_VALID | FLAG_OPENNESS_VALID

        writer.publish(_eye(0, 0), GazeEye(openness=0.1, flags=FLAG_OPENNESS_VALID))
        sample = read(view)
        assert sample["sample_count"] == 2
        assert not sample["eyes"][EYE_RIGHT].flags & FLAG_GAZE_VALID
        # One eye closed: combined follows the open eye.
        assert sample["eyes"][EYE_COMBINED].direction == pytest.approx((0, 0, -1), abs=1e-6)
        assert sample["eyes"][EYE_COMBINED].openness == pytest.approx(0.55)
        view.close()
    finally:
        writer.close()


@pytest.mark.skipif(shm_module.clock_id() is None, reason="no shared memory on this OS")
def test_reader_rejects_mid_update_and_torn_samples():
    writer = GazeSharedMemory()
    assert writer.open()
    try:
        writer.publish(_eye(1, 2), _eye(1, 2))
        good = bytearray(writer._map[:])
        assert read(good) is not None

        mid_update = bytearray(good)
        struct.pack_into("<I", mid_update, 8, struct.unpack_from("<I", good, 8)[0] + 1)
        assert read(mid_update) is None

        torn = bytearray(good)
        torn[60] ^= 0xFF  # inside the left eye's direction
        assert read(torn) is None

        wrong_version = bytearray(good)
        struct.pack_into("<H", wrong_version, 4, 2)
        assert read(wrong_version) is None
    finally:
        writer.close()


@pytest.mark.skipif(shm_module.clock_id() is None, reason="no shared memory on this OS")
def test_close_tells_readers_there_is_no_gaze():
    writer = GazeSharedMemory()
    assert writer.open()
    view = _reader_view()
    try:
        writer.publish(_eye(0, 0), _eye(0, 0))
        assert read(view)["eyes"][EYE_COMBINED].flags & FLAG_GAZE_VALID
        writer.close()
        # A reader still holding the mapping sees an invalid sample, not the last gaze.
        sample = read(view)
        assert sample is not None
        assert not any(e.flags & FLAG_GAZE_VALID for e in sample["eyes"])
    finally:
        view.close()
        writer.close()
    if sys.platform != "win32":
        assert not os.path.exists(shm_module.POSIX_PATH)


@pytest.mark.skipif(shm_module.clock_id() is None, reason="no shared memory on this OS")
def test_reopen_keeps_seq_even_for_existing_readers():
    writer = GazeSharedMemory()
    assert writer.open()
    view = _reader_view()  # keeps a Windows mapping alive across the writer's close
    try:
        writer.publish(_eye(0, 0), _eye(0, 0))
        struct.pack_into("<I", writer._map, 8, 7)  # as if a writer died mid-update
        writer._close_handles()
        again = GazeSharedMemory()
        assert again.open()
        assert struct.unpack_from("<I", view, 8)[0] % 2 == 0
        again.publish(_eye(0, 0), _eye(0, 0))
        assert read(view) is not None
        again.close()
    finally:
        view.close()
        writer.close()


# ------------------------------------------------------ foveation sender wiring


def _wait_until_sent(msg_queue, timeout=5.0):
    deadline = monotonic() + timeout
    while msg_queue.unfinished_tasks and monotonic() < deadline:
        sleep(0.005)
    assert msg_queue.unfinished_tasks == 0, "sender stopped consuming the queue"


@pytest.mark.skipif(shm_module.clock_id() is None, reason="no shared memory on this OS")
def test_foveation_output_publishes_capture_time_and_direction(main_config_v2_params):
    s = main_config_v2_params.settings
    s.gui_foveation_gaze = True
    main_config_v2_params.eye_display_id = EyeId.BOTH
    capture = time.perf_counter()
    info = EyeInfoMock(x=0.5, y=0.5, blink=1.0, pupil_dilation=0.0, avg_velocity=0.0)
    info.capture_ts = capture
    msg_queue = Queue()
    with mock.patch("osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        manager = OSCManager(config=main_config_v2_params, osc_message_in_queue=msg_queue)
        manager.start()
        try:
            msg_queue.put(OSCMessage(type=OSCMessageType.EYE_INFO, data=(EyeId.LEFT, info)))
            _wait_until_sent(msg_queue)
            view = _reader_view()
            sample = read(view)
        finally:
            manager.shutdown()
    assert sample["sample_time_ns"] == int(capture * 1e9)
    yaw = math.degrees(math.atan(0.5 * math.tan(math.radians(s.gui_gaze_yaw_max_deg))))
    pitch = -math.degrees(math.atan(0.5 * math.tan(math.radians(s.gui_gaze_pitch_up_deg))))
    left = sample["eyes"][EYE_LEFT]
    assert left.flags == FLAG_GAZE_VALID | FLAG_OPENNESS_VALID
    assert left.direction == pytest.approx(direction_from_pitch_yaw(pitch, yaw), abs=1e-6)
    assert left.direction[0] > 0 and left.direction[1] > 0  # right and up
    # The right eye has not reported yet; combined is the left eye alone.
    assert not sample["eyes"][EYE_RIGHT].flags & FLAG_GAZE_VALID
    assert sample["eyes"][EYE_COMBINED].direction == pytest.approx(left.direction, abs=1e-6)
    # After shutdown the block says "no gaze".
    after = read(view)
    view.close()
    assert not after["eyes"][EYE_COMBINED].flags & FLAG_GAZE_VALID
