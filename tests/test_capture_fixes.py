"""Regression tests for capture-path fixes: data-collection queue cleanup and
output-folder removal, Linux V4L2 metadata-node filtering, the serial Scan
probe, and CameraWidget stop/start with a worker that outlives its join."""

import os
import queue
import sys
import threading
import time
import types

import numpy as np
import pytest

import camera_enum
import data_collection
from camera_widget import CameraWidget


# ---------------------------------------------------------------- data collection


class FakeCamera:
    def __init__(self):
        self.extra = []

    def add_extra_output_queue(self, q):
        self.extra.append(q)

    def remove_extra_output_queue(self, q):
        if q in self.extra:
            self.extra.remove(q)


class FakeEye:
    def __init__(self, side, started, camera):
        self.eye_id = types.SimpleNamespace(name=side)
        self.settings = types.SimpleNamespace(gui_setup_mode="etvr")
        self.config = types.SimpleNamespace(rotation_angle=0)
        self._started = started
        self._camera = camera

    def started(self):
        return self._started

    def _effective_camera(self):
        return self._camera


class _Widget:
    def configure(self, **_kw):
        pass


class _Var:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _make_window(eyes):
    w = data_collection.DataCollectionWindow.__new__(data_collection.DataCollectionWindow)
    w.parent = None
    w.eyes = eyes
    w.session_running = False
    w.session_cancel = threading.Event()
    w.gui_queue = queue.Queue()
    w.active_queues = []
    w.active_eyes = []
    w._attached_queues = []
    w.active_eye_labels = []
    w._session_output_dir = None
    w._video_writer_sizes = []
    w._latest_capture = None
    w.use_overlay_var = _Var(False)
    w._contributions = types.SimpleNamespace(
        busy=False, clear_capture=lambda: None, capture_started=lambda: None
    )
    w._status_var = _Var("")
    w._start_btn = _Widget()
    w._stop_btn = _Widget()
    return w


@pytest.fixture
def no_worker(monkeypatch):
    """Keep _start_collection from launching the capture worker."""
    class _NoThread:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            pass

    # Swap the module's threading reference only; patching threading.Thread
    # itself would leak into pytest and anything else running meanwhile.
    fake_threading = types.SimpleNamespace(Thread=_NoThread, Event=threading.Event)
    monkeypatch.setattr(data_collection, "threading", fake_threading)
    monkeypatch.setattr(data_collection, "tr", lambda key, **kw: key)


def test_single_left_eye_cleanup_detaches_its_queue(no_worker):
    right_cam, left_cam = FakeCamera(), FakeCamera()
    eyes = [FakeEye("RIGHT", False, right_cam), FakeEye("LEFT", True, left_cam)]
    w = _make_window(eyes)

    for _ in range(3):  # each recording must not leave another orphan queue
        w._start_collection()
        assert len(left_cam.extra) == 1
        assert w.active_eyes == [eyes[1]]
        w._cleanup_session()
        assert left_cam.extra == []
        assert right_cam.extra == []
        w.session_running = False  # what _poll_gui_queue does on session_done


def test_cleanup_detaches_from_camera_used_at_start(no_worker):
    cam_at_start, cam_later = FakeCamera(), FakeCamera()
    eye = FakeEye("LEFT", True, cam_at_start)
    w = _make_window([FakeEye("RIGHT", False, FakeCamera()), eye])
    w._start_collection()
    eye._camera = cam_later  # e.g. shared-capture source changed mid-session
    w._cleanup_session()
    assert cam_at_start.extra == []


def _run_session(monkeypatch, tmp_path, make_say):
    """Run _run_collection to its end with make_say(window) as the TTS hook."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(data_collection, "tr", lambda key, **kw: key)
    monkeypatch.setattr(data_collection, "prompt_text", lambda key: key)
    monkeypatch.setattr(
        data_collection, "get_best_codec",
        lambda: (data_collection.cv2.VideoWriter_fourcc(*"MJPG"), "MJPG", "avi"),
    )

    # Leftovers from other sessions must survive.
    version = data_collection.DATA_COLLECTION_VERSION
    other_dir = tmp_path / f"{version}_other_ETVR_Output"
    other_dir.mkdir()
    (other_dir / "keep.txt").write_text("x")
    other_zip = tmp_path / f"{version}_other_ETVR_User_Data_Output.zip"
    other_zip.write_bytes(b"zip")

    cam = FakeCamera()
    eye = FakeEye("LEFT", True, cam)
    w = _make_window([FakeEye("RIGHT", False, FakeCamera()), eye])
    monkeypatch.setattr(data_collection, "say", make_say(w))
    w._use_overlay = False
    q = queue.Queue()
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    for n in range(5):
        q.put((frame, n))
    cam.add_extra_output_queue(q)
    w.active_queues = [q]
    w.active_eyes = [eye]
    w._attached_queues = [(cam, q)]
    w.active_eye_labels = ["Left"]

    created = []
    real_makedirs = os.makedirs

    def spy_makedirs(path, *a, **kw):
        created.append(path)
        return real_makedirs(path, *a, **kw)

    monkeypatch.setattr(data_collection.os, "makedirs", spy_makedirs)
    w._run_collection()

    assert len(created) == 1
    assert not os.path.exists(created[0])
    assert (other_dir / "keep.txt").exists()
    assert list(tmp_path.glob("*_ETVR_User_Data_Output.zip")) == [other_zip]
    assert other_zip.read_bytes() == b"zip"
    assert cam.extra == []
    msgs = []
    while not w.gui_queue.empty():
        msgs.append(w.gui_queue.get_nowait())
    assert ("session_done", None) in msgs
    assert not any(kind == "capture_ready" for kind, _ in msgs)


def test_cancelled_session_removes_only_its_output_dir(monkeypatch, tmp_path):
    def make_say(w):
        def say_and_cancel(_key):
            w.session_cancel.set()  # user pressed Stop during the first prompt
            ev = threading.Event()
            ev.set()
            return ev
        return say_and_cancel

    _run_session(monkeypatch, tmp_path, make_say)


def test_failed_session_removes_its_output_dir(monkeypatch, tmp_path):
    def make_say(_w):
        def say_boom(_key):
            raise RuntimeError("tts exploded")
        return say_boom

    _run_session(monkeypatch, tmp_path, make_say)


def test_cancel_during_warmup_removes_its_output_dir(monkeypatch, tmp_path):
    def make_say(w):
        w.session_cancel.set()  # cancelled before any frame was read
        return lambda _key: pytest.fail("prompts must not run")

    _run_session(monkeypatch, tmp_path, make_say)


# ---------------------------------------------------------------- camera_enum


def _fake_linux_dev(monkeypatch, tmp_path, entries, sysfs):
    sysroot = tmp_path / "sysfs"
    sysroot.mkdir()
    for dev, attrs in sysfs.items():
        d = sysroot / dev
        d.mkdir()
        for k, v in attrs.items():
            (d / k).write_text(v)
    monkeypatch.setattr(camera_enum, "_V4L2_SYSFS_DIR", str(sysroot))

    real_listdir = os.listdir
    real_isdir = os.path.isdir
    monkeypatch.setattr(
        camera_enum.os, "listdir",
        lambda p: list(entries) if p == "/dev" else real_listdir(p),
    )
    monkeypatch.setattr(
        camera_enum.os.path, "isdir",
        lambda p: False if p == "/dev/v4l/by-id" else real_isdir(p),
    )


def test_linux_listing_drops_uvc_metadata_nodes(monkeypatch, tmp_path):
    _fake_linux_dev(
        monkeypatch, tmp_path,
        ["null", "video0", "video1", "video2", "video3", "video4"],
        {
            "video0": {"index": "0\n", "name": "Cam\n"},
            "video1": {"index": "1\n", "name": "Cam\n"},  # metadata node
            "video2": {"index": "0\n", "name": "Cam\n"},
            "video3": {"index": "1\n", "name": "Cam\n"},  # metadata node
            # video4: no sysfs entry at all -> kept
        },
    )
    assert camera_enum._linux_camera_metadata() == [
        (0, "Cam", "/dev/video0"),
        (2, "Cam", "/dev/video2"),
        (4, "Camera", "/dev/video4"),
    ]

    monkeypatch.setattr(camera_enum.sys, "platform", "linux")
    cams = camera_enum._list_uvc_cameras_uncached()
    # The cv2 index is the node number, not the list position.
    assert [c["index"] for c in cams] == [0, 2, 4]


def test_linux_listing_keeps_nodes_when_sysfs_missing(monkeypatch, tmp_path):
    _fake_linux_dev(monkeypatch, tmp_path, ["video0", "video1"], {})
    monkeypatch.setattr(camera_enum, "_V4L2_SYSFS_DIR", str(tmp_path / "nope"))
    assert [i for i, _, _ in camera_enum._linux_camera_metadata()] == [0, 1]


def test_serial_scan_skips_configured_ports(monkeypatch):
    list_ports = pytest.importorskip("serial.tools.list_ports")
    live = "COM5" if sys.platform.startswith("win") else "/dev/ttyUSB0"
    spare = "COM7" if sys.platform.startswith("win") else "/dev/ttyUSB1"
    ports = [
        types.SimpleNamespace(device=live, description="ETVR", vid=0x303A),
        types.SimpleNamespace(device=spare, description="ETVR", vid=0x303A),
    ]
    monkeypatch.setattr(list_ports, "comports", lambda: ports)
    probed = []

    def fake_probe(device, baud, timeout_s):
        probed.append(device)
        return True

    monkeypatch.setattr(camera_enum, "_probe_serial_for_jpeg", fake_probe)
    found = camera_enum.discover_etvr_serial_cameras(
        timeout_s=0.01, skip_devices=(live, 0, None, ""),
    )
    assert probed == [spare]
    assert [dev for _, dev in found] == [spare]


def test_serial_probe_opens_exclusively(monkeypatch):
    serial = pytest.importorskip("serial")
    opened = {}

    class FakeSerial:
        def __init__(self, **kw):
            opened.update(kw)

        def reset_input_buffer(self):
            pass

        def read(self, _n):
            return b"\x00\xff\xd8\xff"

        def close(self):
            pass

    monkeypatch.setattr(serial, "Serial", FakeSerial)
    assert camera_enum._probe_serial_for_jpeg("COM9", 115200, 0.5)
    assert opened.get("exclusive") is True


# ---------------------------------------------------------------- camera widget


class _BlockingCamera:
    """A Camera.run stand-in that blocks in an un-interruptible 'open' first,
    then loops on the shared cancellation_event like the real one."""

    def __init__(self, widget):
        self.widget = widget
        self.release = threading.Event()
        self.loops = []
        self.running = 0
        self.max_running = 0
        self._lock = threading.Lock()

    def set_extra_output_queues(self, _qs):
        pass

    def run(self):
        with self._lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        try:
            self.release.wait(5)  # stuck in cam.open
            ev = self.widget.cancellation_event
            n = 0
            while not ev.is_set() and n < 200:
                n += 1
                time.sleep(0.005)
            self.loops.append(n)
        finally:
            with self._lock:
                self.running -= 1


def _make_widget():
    w = CameraWidget.__new__(CameraWidget)
    w.eye_id = "LEFT"
    w.cancellation_event = threading.Event()
    w.cancellation_event.set()
    w.capture_event = threading.Event()
    w.uses_shared_capture_event = False
    w._shared_capture_source = None
    w.camera_thread = None
    w.tracking_thread = None
    w._stale_threads = []
    w._start_lock = threading.Lock()
    w._start_generation = 0
    w.ransac = types.SimpleNamespace(run=lambda: w.cancellation_event.wait(5))
    w.camera = _BlockingCamera(w)
    return w


def test_restart_waits_for_worker_stuck_past_stop_timeout():
    w = _make_widget()
    cam = w.camera
    w.start()
    old_thread = w.camera_thread
    w.stop(join_timeout=0.05, warn_if_alive=False)
    assert old_thread.is_alive()

    w.start()
    # The old worker must keep seeing the cancel; nothing new runs yet.
    assert w.cancellation_event.is_set()
    assert not w.started()
    assert cam.running == 1

    cam.release.set()  # the blocking open returns
    old_thread.join(2)
    assert not old_thread.is_alive()
    assert cam.loops[0] == 0  # saw the cancel immediately, didn't keep running

    deadline = time.monotonic() + 2
    while not w.started() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert w.started()
    assert cam.max_running == 1  # never two run() loops at once
    w.stop(join_timeout=2)
    assert cam.loops[-1] < 200


def test_stop_cancels_a_deferred_start():
    w = _make_widget()
    cam = w.camera
    w.start()
    old_thread = w.camera_thread
    w.stop(join_timeout=0.05, warn_if_alive=False)
    w.start()  # deferred behind the stuck worker
    w.stop(join_timeout=0.05, warn_if_alive=False)
    cam.release.set()
    old_thread.join(2)
    time.sleep(0.1)
    assert not w.started()
    assert w.camera_thread is None
