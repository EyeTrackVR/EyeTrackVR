"""Steam Frame built-in eye cameras (EyeTrackApp/frame_eye.py)."""

import logging
import os
import socket
import struct
import sys
import threading
import time
import uuid

import numpy as np
import pytest

import frame_eye as fe

LAYOUT = fe.Layout(ctrl_base=0x234000)


def control_block(fps=15.0, idx=(1, 2), enables=(0, 0)):
    """A 16 MB region holding a plausible control block at LAYOUT.ctrl_base."""
    buf = bytearray(fe.REGION_BYTES)
    base = LAYOUT.ctrl_base

    def put(off, value):
        struct.pack_into("<I", buf, base + off, value)

    struct.pack_into("<f", buf, base + LAYOUT.fps, fps)
    put(LAYOUT.idx_l, idx[0])
    put(LAYOUT.idx_r, idx[1])
    put(LAYOUT.enables, enables[0])
    put(LAYOUT.enables + 4, enables[1])
    for i, v in enumerate((1, 4, 4, 1, 0, 0, 0, 0)):
        put(LAYOUT.locks_l + 4 * i, v)
        put(LAYOUT.locks_r + 4 * i, v)
    return buf


def test_validate_accepts_a_real_layout():
    assert fe.validate_layout(memoryview(control_block()).cast("I"), LAYOUT) is None


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"fps": 0.0}, "fps"),
        ({"fps": float("nan")}, "fps"),
        ({"idx": (9, 1)}, "index"),
        ({"enables": (7, 0)}, "enable"),
    ],
)
def test_validate_rejects_a_wrong_base(kwargs, reason):
    assert reason in fe.validate_layout(memoryview(control_block(**kwargs)).cast("I"), LAYOUT)


def test_validate_rejects_garbage_at_another_candidate():
    words = memoryview(control_block()).cast("I")
    assert fe.validate_layout(words, fe.Layout(ctrl_base=0x124000)) is not None


def test_not_ready_index_is_valid():
    buf = control_block(idx=(fe.NOT_READY, fe.NOT_READY))
    assert fe.validate_layout(memoryview(buf).cast("I"), LAYOUT) is None


def test_frame_sources():
    assert fe.frame_source_eye("frame://left") == "left"
    assert fe.frame_source_eye(" FRAME://right/ ") == "right"
    assert fe.frame_source_eye("frame://middle") is None
    assert fe.frame_source_eye("http://etvr-left.local/") is None
    assert fe.frame_source_eye(0) is None
    assert fe.is_frame_capture_source(fe.FRAME_LEFT_SOURCE)
    assert not fe.is_frame_capture_source("COM5")


class FakeClient:
    """Stands in for DspClient: frames whose pixels encode (eye, slot)."""

    instances = []
    start_idx = {"left": fe.NOT_READY, "right": fe.NOT_READY}

    def __init__(self):
        self.layout = LAYOUT
        self.idx = dict(FakeClient.start_idx)
        self.started = False
        self.closed = False
        self.gone = False
        FakeClient.instances.append(self)

    def connect(self):
        self.started = True

    def read_fps(self):
        return 90.0

    def drain(self):
        if self.gone:
            raise ConnectionError("dsp_service closed the connection")
        return 0

    def read_index(self, eye):
        return self.idx[eye]

    def copy_frame(self, eye, idx):
        # Like the DSP: a 400x400 image at (64, 0), zero-filled around it, with
        # metadata bytes at the start of row 0. The image's top-left pixel is 1
        # and the rest is (eye, slot), so a rotation shows.
        frame = np.zeros((512, 512), dtype=np.uint8)
        frame[0:400, 64:464] = (100 if eye == "left" else 200) + idx
        frame[0, 64] = 1
        frame[0, :6] = (162, 79, 243, 137, 93, 47)
        return frame.tobytes()

    def close(self):
        self.closed = True


@pytest.fixture
def service(monkeypatch):
    FakeClient.instances.clear()
    monkeypatch.setattr(FakeClient, "start_idx", {"left": fe.NOT_READY, "right": fe.NOT_READY})
    monkeypatch.setattr(fe.FrameEyeService, "RETRY_MIN", 0.01)
    monkeypatch.setattr(fe.FrameEyeService, "CHECK_INTERVAL", 0.01)
    svc = fe.FrameEyeService(client_factory=FakeClient)
    yield svc
    while svc._subscribers:
        svc.unsubscribe()


def wait_for(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


def started_client():
    assert wait_for(lambda: FakeClient.instances and FakeClient.instances[-1].started)
    return FakeClient.instances[-1]


def test_service_publishes_cropped_upright_frames(service):
    service.subscribe()
    client = started_client()
    client.idx["left"] = 3
    img, seq, _ts = service.latest("left", 0, timeout=1.0)
    # Cropped to the camera image, and the left camera's image turned 180 degrees.
    assert img.shape == (400, 400) and img.flags.c_contiguous and seq == 1
    assert int(img[399, 399]) == 1 and int(img[0, 0]) == 103
    # Nothing new for the left eye until its index moves again.
    assert service.latest("left", seq, timeout=0.05) is None
    client.idx["left"] = 4
    client.idx["right"] = 0
    img, seq2, _ = service.latest("left", seq, timeout=1.0)
    assert int(img[0, 0]) == 104 and seq2 == 2
    img, _, _ = service.latest("right", 0, timeout=1.0)
    assert img.shape == (400, 400) and int(img[0, 0]) == 1 and int(img[399, 399]) == 200
    assert service.camera_fps == 90.0 and service.streaming


def test_find_image_box():
    img = np.zeros((512, 512), dtype=np.uint8)
    assert fe.find_image_box(img) is None
    img[0, :6] = 200  # metadata only
    assert fe.find_image_box(img) is None
    img[0:400, 64:464] = 5
    assert fe.find_image_box(img) == (64, 0, 400, 400)
    img[:] = 0
    img[56:456, 16:416] = 5
    assert fe.find_image_box(img) == (16, 56, 400, 400)
    img[:] = 0
    img[10:40, 10:40] = 5  # too small to be the camera image
    assert fe.find_image_box(img) is None


def test_frames_already_in_the_ring_at_connect_are_skipped(service, monkeypatch):
    monkeypatch.setattr(FakeClient, "start_idx", {"left": 2, "right": 5})
    service.subscribe()
    client = started_client()
    assert service.latest("left", 0, timeout=0.1) is None
    assert service.latest("right", 0, timeout=0.01) is None
    client.idx["left"] = 3
    img, _, _ = service.latest("left", 0, timeout=1.0)
    assert int(img[0, 64]) == 103


def test_a_gap_in_frames_waits_instead_of_reconnecting(service, monkeypatch, caplog):
    monkeypatch.setattr(fe.FrameEyeService, "WAITING_AFTER", 0.02)
    monkeypatch.setattr(fe.FrameEyeService, "WAIT_LOG_AFTER", 0.05)
    monkeypatch.setattr(fe.FrameEyeService, "IDLE_POLL", 0.005)
    caplog.set_level(logging.INFO, logger="frame_eye")
    service.subscribe()
    client = started_client()
    assert wait_for(lambda: service.waiting)
    assert wait_for(lambda: "headset not worn" in caplog.text)
    assert len(FakeClient.instances) == 1 and not client.closed and service.streaming
    # Frames coming back clear the waiting state on the same connection.
    client.idx["right"] = 1
    assert service.latest("right", 0, timeout=1.0) is not None
    assert wait_for(lambda: not service.waiting)
    assert len(FakeClient.instances) == 1


def test_reconnects_when_dsp_service_goes_away(service):
    service.subscribe()
    client = started_client()
    client.gone = True
    assert wait_for(lambda: len(FakeClient.instances) >= 2)
    assert client.closed
    assert "closed the connection" in service.last_error or service.streaming


def test_reconnects_after_repeated_out_of_range_indices(service):
    service.subscribe()
    client = started_client()
    client.idx["left"] = 9
    assert wait_for(lambda: len(FakeClient.instances) >= 2)
    assert client.closed


def test_service_stops_and_closes_with_the_last_subscriber(service):
    service.subscribe()
    service.subscribe()
    client = started_client()
    service.unsubscribe()
    assert not client.closed
    service.unsubscribe()
    assert client.closed
    assert not service.streaming


def test_service_reports_and_retries_connection_errors(monkeypatch):
    attempts = []

    class Failing(FakeClient):
        def connect(self):
            attempts.append(1)
            raise ConnectionRefusedError("no dsp_service here")

    monkeypatch.setattr(fe.FrameEyeService, "RETRY_MIN", 0.01)
    svc = fe.FrameEyeService(client_factory=Failing)
    svc.subscribe()
    try:
        assert wait_for(lambda: len(attempts) >= 2)
        assert "no dsp_service" in svc.last_error and not svc.streaming
        assert svc.latest("left", 0, timeout=0.01) is None
    finally:
        svc.unsubscribe()


def test_steamvr_eye_tracking_setting(tmp_path):
    f = tmp_path / "steamvr.vrsettings"
    f.write_text('{"steamvr": {"allowEyeTracking": false, "analogGain": 0.1}}', encoding="utf-8")
    assert fe.steamvr_eye_tracking_allowed(str(f)) is False
    f.write_text('{"steamvr": {"allowEyeTracking": true}}', encoding="utf-8")
    assert fe.steamvr_eye_tracking_allowed(str(f)) is True
    f.write_text('{"steamvr": {}}', encoding="utf-8")
    assert fe.steamvr_eye_tracking_allowed(str(f)) is None
    assert fe.steamvr_eye_tracking_allowed(str(tmp_path / "missing")) is None


def test_not_ready_retries_quickly_then_streams(monkeypatch):
    state = {"ready": False, "attempts": 0}

    class Gated(FakeClient):
        def connect(self):
            state["attempts"] += 1
            if not state["ready"]:
                raise fe.EyeCamerasNotReady("eye tracking is turned off in SteamVR settings")

    FakeClient.instances.clear()
    monkeypatch.setattr(fe.FrameEyeService, "RETRY_MIN", 30.0)  # a fault backoff would stall the test
    monkeypatch.setattr(fe.FrameEyeService, "NOT_READY_RETRY", 0.01)
    svc = fe.FrameEyeService(client_factory=Gated)
    svc.subscribe()
    try:
        assert wait_for(lambda: state["attempts"] >= 3)
        assert svc.not_ready and svc.eye_tracking_off and not svc.streaming
        state["ready"] = True
        assert wait_for(lambda: svc.streaming)
        assert not svc.not_ready and not svc.eye_tracking_off
    finally:
        svc.unsubscribe()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="abstract unix sockets and memfd are Linux-only")
def test_dsp_client_against_a_fake_service():
    """End to end over a real abstract socket and shared memfd, like dsp_service."""
    name = f"etvr-test-{uuid.uuid4().hex}".encode()
    mem = os.memfd_create("dsp")
    os.ftruncate(mem, fe.REGION_BYTES)
    block = bytes(control_block(idx=(5, 2)))
    os.pwrite(mem, block, 0)
    left_off = LAYOUT.ctrl_base + LAYOUT.ring_r + 2 * LAYOUT.slot_stride  # wearer's left = ring_r
    os.pwrite(mem, bytes([7]) * LAYOUT.frame_bytes, left_off)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(b"\0" + name)
    server.listen(1)
    requests = []
    hang_up = threading.Event()

    def serve():
        conn, _ = server.accept()
        with conn:
            socket.send_fds(conn, [b"x"], [mem])
            requests.append(conn.recv(4))
            hang_up.wait(5)  # then close, like dsp_service exiting

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    client = fe.DspClient(name=name)
    try:
        client.connect()
        assert client.layout.ctrl_base == LAYOUT.ctrl_base
        assert client.read_fps() == 15.0
        assert client.read_index("left") == 2 and client.read_index("right") == 5
        assert client.copy_frame("left", 2)[:3] == bytes([7, 7, 7])
        assert client.drain() == 0
        hang_up.set()
        t.join(timeout=2)
        with pytest.raises(ConnectionError):
            client.drain()
    finally:
        client.close()
    assert requests == [struct.pack("<I", 0)]
    # The control block is untouched: SteamVR's tracker owns the slots.
    ctrl_words = LAYOUT.locks_r + 4 * LAYOUT.slots
    assert os.pread(mem, ctrl_words, LAYOUT.ctrl_base) == block[LAYOUT.ctrl_base : LAYOUT.ctrl_base + ctrl_words]
    t.join(timeout=2)
    server.close()
    os.close(mem)


def test_both_eyes_of_a_pair_share_a_capture_time():
    svc = fe.FrameEyeService(client_factory=FakeClient)
    left = svc._capture_ts("left")
    assert svc._capture_ts("right") == left  # the pair's other half
    assert svc._capture_ts("left") > left  # the next pair starts
    time.sleep(0.02)
    first = svc._capture_ts("right")
    assert first > left and svc._capture_ts("left") == first
