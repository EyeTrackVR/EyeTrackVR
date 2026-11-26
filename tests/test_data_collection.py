"""Data collection (data_collection, data_collection_tts): camera queues are
detached when a recording ends, an unfinished session leaves no output behind,
the recorder keeps every frame, codec choice, and the spoken prompts."""

import os
import queue
import threading
import types

import numpy as np
import pytest

import data_collection
import data_collection_tts
import data_collection as dc
import zipfile
from utils import user_data


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
    w._contributions = types.SimpleNamespace(busy=False, clear_capture=lambda: None, capture_started=lambda: None)
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


# ── camera queues ────────────────────────────────────────────────────────────


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


@pytest.mark.parametrize("on_frame", [True, False])
def test_recording_on_a_frame_pauses_tracking_until_it_ends(no_worker, monkeypatch, on_frame):
    monkeypatch.setattr(data_collection, "is_steam_frame", lambda: on_frame)
    paused = data_collection.models_paused_for_recording
    paused.clear()
    w = _make_window([FakeEye("RIGHT", True, FakeCamera()), FakeEye("LEFT", True, FakeCamera())])
    w._start_collection()
    assert paused.is_set() is on_frame
    w._cleanup_session()
    assert not paused.is_set()


def test_cleanup_detaches_from_camera_used_at_start(no_worker):
    cam_at_start, cam_later = FakeCamera(), FakeCamera()
    eye = FakeEye("LEFT", True, cam_at_start)
    w = _make_window([FakeEye("RIGHT", False, FakeCamera()), eye])
    w._start_collection()
    eye._camera = cam_later  # e.g. shared-capture source changed mid-session
    w._cleanup_session()
    assert cam_at_start.extra == []


# ── unfinished sessions ──────────────────────────────────────────────────────


def _say_and_cancel(w):
    def say(_key):
        w.session_cancel.set()  # user pressed Stop during the first prompt
        ev = threading.Event()
        ev.set()
        return ev

    return say


def _say_boom(_w):
    def say(_key):
        raise RuntimeError("tts exploded")

    return say


def _cancel_during_warmup(w):
    w.session_cancel.set()  # cancelled before any frame was read
    return lambda _key: pytest.fail("prompts must not run")


@pytest.mark.parametrize(
    "make_say",
    [_say_and_cancel, _say_boom, _cancel_during_warmup],
    ids=["cancelled", "failed", "cancelled-during-warmup"],
)
def test_an_unfinished_session_removes_only_its_output_dir(monkeypatch, tmp_path, make_say):
    monkeypatch.setattr(data_collection, "capture_dir", lambda: str(tmp_path))
    monkeypatch.setattr(data_collection, "tr", lambda key, **kw: key)
    monkeypatch.setattr(data_collection, "prompt_text", lambda key: key)
    monkeypatch.setattr(
        data_collection,
        "get_best_codec",
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


def test_captures_go_to_the_user_data_folder(isolated_user_data):
    assert os.path.dirname(data_collection.capture_dir()) == os.path.abspath(isolated_user_data)


# ── session recorder ─────────────────────────────────────────────────────────


def _put_dropping_oldest(q, item):
    """What Camera.push_image_to_queue does with a full queue."""
    try:
        q.put_nowait(item)
    except queue.Full:
        q.get_nowait()
        q.put_nowait(item)


def _frame(i):
    return (np.full((4, 4, 3), i % 256, np.uint8), i, 90.0, 0.0)


class _Written:
    """The recorder's write callback: records each frame's number and lets a
    test wait until a given count has been written."""

    def __init__(self):
        self.numbers = []
        self._cond = threading.Condition()

    def __call__(self, _j, frame):
        with self._cond:
            self.numbers.append(int(frame[0, 0, 0]))
            self._cond.notify_all()

    def wait_for(self, count, timeout=5.0):
        with self._cond:
            assert self._cond.wait_for(lambda: len(self.numbers) >= count, timeout), self.numbers


def test_recorder_keeps_every_frame_while_the_capture_loop_blocks():
    q = queue.Queue(maxsize=10)
    written = _Written()
    rec = data_collection._SessionRecorder([q], lambda j, f: f, written)
    rec.start()
    # The capture loop is meanwhile blocked on the overlay socket. 45 frames
    # overflow the 10-frame queue unless the recorder drains it concurrently;
    # without it this put times out and the test fails.
    for i in range(45):
        q.put(_frame(i), timeout=5.0)
    rec.stop()
    assert written.numbers == [i % 256 for i in range(45)]


def test_recorder_snapshot_is_the_next_frame_not_a_queued_one():
    q = queue.Queue(maxsize=10)
    written = _Written()
    rec = data_collection._SessionRecorder([q], lambda j, f: f, written)
    rec.start()
    try:
        for i in range(5):
            _put_dropping_oldest(q, _frame(i))
        written.wait_for(5)  # frames from before the snapshot was asked for
        got = []
        waiter = threading.Thread(target=lambda: got.append(rec.next_frame(0, timeout=5.0)))
        waiter.start()
        n = 100
        while waiter.is_alive() and n < 1000:  # the camera keeps delivering
            q.put(_frame(n), timeout=5.0)
            n += 1
            waiter.join(0.005)
        waiter.join()
        frame, number = got[0]
        # A frame from after the request (not one of the five queued before it).
        assert number >= 100 and int(frame[0, 0, 0]) == number % 256
        written.wait_for(5 + (n - 100))  # the recorder took everything delivered
        with pytest.raises(queue.Empty):
            rec.next_frame(0, timeout=0.05)
    finally:
        rec.stop()


def test_arm64_codec_probe_never_tries_h264(monkeypatch, tmp_path):
    tried = []

    class Writer:
        def __init__(self, path, fourcc, fps, size, color):
            tried.append(fourcc)

        def isOpened(self):
            return True

        def release(self):
            pass

    monkeypatch.setattr(data_collection.platform, "system", lambda: "Linux")
    monkeypatch.setattr(data_collection.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(data_collection.cv2, "VideoWriter", Writer)
    monkeypatch.setattr(data_collection, "capture_dir", lambda: str(tmp_path))
    _, codec, container = data_collection.get_best_codec()
    h264 = {data_collection.cv2.VideoWriter_fourcc(*c) for c in ("avc1", "H264")}
    assert (codec, container) == ("XVID", "avi") and not h264 & set(tried)


# ── spoken prompts ───────────────────────────────────────────────────────────


def test_prompt_without_a_tts_engine_waits_its_reading_time(monkeypatch):
    slept = []
    monkeypatch.setattr(data_collection_tts.platform, "system", lambda: "Linux")
    monkeypatch.setattr(data_collection_tts, "_run_tts_command", lambda *a, **k: False)
    monkeypatch.setattr(data_collection_tts, "time", types.SimpleNamespace(sleep=slept.append))

    assert data_collection_tts.speak("Look left and squint").wait(5.0)

    assert slept == [data_collection_tts._reading_seconds("Look left and squint")]


def test_bundled_espeak_speaks_first_with_its_own_libraries(monkeypatch, tmp_path):
    import utils.misc_utils

    tts = tmp_path / "tools" / "tts"
    tts.mkdir(parents=True)
    exe = tts / "espeak-ng"
    exe.write_text("")
    exe.chmod(0o755)
    monkeypatch.setattr(utils.misc_utils, "resource_path", lambda rel: str(tmp_path / rel))
    calls = []

    def run(command, timeout, stdin_text=None, env=None):
        calls.append((command, env))
        return command[2] == "en"  # German isn't installed here: English fallback

    monkeypatch.setattr(data_collection_tts, "_run_tts_command", run)
    assert data_collection_tts._speak_linux("Schau nach links", "de", "Look left")
    assert [c[0] for c in calls] == [
        [str(exe), "-v", "de", "Schau nach links"],
        [str(exe), "-v", "en", "Look left"],
    ]
    env = calls[0][1]
    assert env["ESPEAK_DATA_PATH"] == str(tts) and env["LD_LIBRARY_PATH"] == str(tts / "lib")


@pytest.mark.parametrize(
    "launch, expected",
    [
        ({"LD_LIBRARY_PATH_ORIG": "/opt/lib"}, "/opt/lib"),  # the user's own path survives
        ({}, None),  # launched without one: none at all
        ({"LD_LIBRARY_PATH_ORIG": "{b}:/opt/lib"}, "/opt/lib"),  # leap.py re-exec saved the bundle in ORIG
    ],
)
def test_frozen_linux_build_runs_system_tts_without_its_bundled_libraries(monkeypatch, tmp_path, launch, expected):
    """The bootloader puts the bundle's libraries first on LD_LIBRARY_PATH;
    a system espeak-ng/spd-say loading them instead of the host's can fail
    or play nothing (reported silent on Arch)."""
    import utils.misc_utils as misc_utils

    bundle = str(tmp_path / "_internal")
    monkeypatch.setattr(misc_utils, "is_linux", True)
    monkeypatch.setattr(misc_utils.sys, "frozen", True, raising=False)
    monkeypatch.setattr(misc_utils.sys, "_MEIPASS", bundle, raising=False)
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", f"{bundle}:{bundle}/lib")
    for name, value in launch.items():
        monkeypatch.setenv(name, value.format(b=bundle))
    monkeypatch.setattr(data_collection_tts.shutil, "which", lambda name: "/usr/bin/" + name)
    seen = []

    def run(command, **kwargs):
        seen.append(kwargs["env"])
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(data_collection_tts.subprocess, "run", run)

    assert data_collection_tts._run_tts_command(["espeak-ng", "hi"], timeout=1)
    assert seen[0].get("LD_LIBRARY_PATH") == expected and "LD_LIBRARY_PATH_ORIG" not in seen[0]


def test_reading_time_scales_with_the_prompt():
    reading = data_collection_tts._reading_seconds
    assert reading("Captured") < reading("Look up and to the left and squint") <= 8.0
    assert reading("向左看并眯眼睛") > reading("看")


# The plaintext recordings a session leaves: one ZIP beside its working folder in the
# private capture folder, deleted once sealed or abandoned, swept on the next start.


@pytest.fixture
def captures(monkeypatch, tmp_path):
    monkeypatch.setattr(user_data, "_USER_DATA_DIR", str(tmp_path / "data"))
    return dc.capture_dir()


def _session(captures, seed="1234"):
    output_dir = os.path.join(captures, f"{seed}{dc._OUTPUT_SUFFIX}")
    os.makedirs(os.path.join(output_dir, "snapshots"))
    with open(os.path.join(output_dir, "LEFT.avi"), "wb") as file:
        file.write(b"video")
    with open(os.path.join(output_dir, "snapshots", "center.png"), "wb") as file:
        file.write(b"png")
    return output_dir


@pytest.mark.skipif(os.name == "nt", reason="Windows gets an owner-only ACL (contributions.private_files)")
def test_capture_folder_is_private(captures):
    # Where it lives: test_data_collection.py::test_captures_go_to_the_user_data_folder.
    assert os.stat(captures).st_mode & 0o077 == 0


def test_a_session_is_zipped_beside_its_folder(captures):
    output_dir = _session(captures)
    zip_name = dc._zip_output("1234", output_dir)
    assert zip_name == os.path.join(captures, f"{dc.DATA_COLLECTION_VERSION}_1234{dc._ZIP_SUFFIX}")
    folder = os.path.basename(output_dir)
    with zipfile.ZipFile(zip_name) as archive:
        assert sorted(archive.namelist()) == [f"{folder}/LEFT.avi", f"{folder}/snapshots/center.png"]
        assert archive.read(f"{folder}/LEFT.avi") == b"video"


def test_only_the_apps_own_recordings_are_deleted(captures, tmp_path):
    ours = dc._zip_output("1", _session(captures, "1"))
    elsewhere = tmp_path / f"{dc.DATA_COLLECTION_VERSION}_2{dc._ZIP_SUFFIX}"  # a copy the user made
    elsewhere.write_bytes(b"zip")
    other_name = os.path.join(captures, "notes.zip")
    with open(other_name, "wb") as file:
        file.write(b"zip")

    for path in (ours, str(elsewhere), other_name, None, ""):
        dc.discard_capture(path)
    dc.discard_capture(ours)  # already gone: nothing to do

    assert not os.path.exists(ours)
    assert elsewhere.exists() and os.path.exists(other_name)


def test_next_start_sweeps_what_an_earlier_run_left(captures):
    left_zip = dc._zip_output("1", _session(captures, "1"))
    left_dir = _session(captures, "2")
    keep = os.path.join(captures, "readme.txt")
    with open(keep, "w", encoding="utf-8") as file:
        file.write("not ours")

    dc._sweep_captures()

    assert not os.path.exists(left_zip) and not os.path.exists(left_dir)
    assert os.listdir(captures) == ["readme.txt"]  # both working folders went too
