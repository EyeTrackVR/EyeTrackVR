"""CameraWidget stop/start when a capture worker outlives its join: the next
start waits for it instead of un-cancelling it, and a stop cancels that
deferred start."""

import threading
import types

import pytest

import camera_widget
from camera_widget import CameraWidget


class _BlockingCamera:
    """A Camera.run stand-in that blocks in an un-interruptible 'open' first,
    then runs until the shared cancellation_event is set, like the real one."""

    def __init__(self, widget):
        self.widget = widget
        self.release = threading.Event()
        self.saw_cancel_on_open = []  # per run: was it already cancelled when the open returned?
        self.ended_by_cancel = []
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
            self.saw_cancel_on_open.append(ev.is_set())
            self.ended_by_cancel.append(ev.wait(5))
        finally:
            with self._lock:
                self.running -= 1


@pytest.fixture
def widget(monkeypatch):
    """A widget whose camera worker blocks; ``widget.helpers`` lists every
    thread camera_widget starts, so a test can wait for a deferred start."""
    helpers = []

    class _Recorded(threading.Thread):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("daemon", True)
            super().__init__(*args, **kwargs)
            helpers.append(self)

    monkeypatch.setattr(camera_widget, "Thread", _Recorded)
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
    w.helpers = helpers
    yield w
    w.camera.release.set()
    w.request_stop()
    for thread in helpers:
        thread.join(timeout=5)


def _deferred_starter(w, before):
    (starter,) = [t for t in w.helpers[before:] if t not in (w.camera_thread, w.tracking_thread)]
    return starter


def test_restart_waits_for_worker_stuck_past_stop_timeout(widget):
    w, cam = widget, widget.camera
    w.start()
    old_thread = w.camera_thread
    w.stop(join_timeout=0.05, warn_if_alive=False)
    assert old_thread.is_alive()

    before = len(w.helpers)
    w.start()
    starter = _deferred_starter(w, before)
    # The old worker must keep seeing the cancel; nothing new runs yet.
    assert w.cancellation_event.is_set()
    assert not w.started()
    assert cam.running == 1

    cam.release.set()  # the blocking open returns
    old_thread.join(5)
    assert not old_thread.is_alive()
    assert cam.saw_cancel_on_open[0]  # saw the cancel at once, didn't keep running

    starter.join(5)
    assert w.started()
    assert cam.max_running == 1  # never two run() loops at once
    w.stop(join_timeout=5)
    assert cam.ended_by_cancel[-1]


def test_stop_cancels_a_deferred_start(widget):
    w, cam = widget, widget.camera
    w.start()
    old_thread = w.camera_thread
    w.stop(join_timeout=0.05, warn_if_alive=False)
    before = len(w.helpers)
    w.start()  # deferred behind the stuck worker
    starter = _deferred_starter(w, before)
    w.stop(join_timeout=0.05, warn_if_alive=False)

    cam.release.set()
    old_thread.join(5)
    starter.join(5)

    assert not starter.is_alive()  # the deferred start has run its course...
    assert not w.started()  # ...and did not start anything
    assert w.camera_thread is None
    assert len(cam.saw_cancel_on_open) == 1
