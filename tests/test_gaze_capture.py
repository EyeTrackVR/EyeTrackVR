from types import SimpleNamespace

from gaze_capture import GazeTrace


def test_an_eye_without_frames_does_not_hold_up_the_others():
    steady, stalled = SimpleNamespace(), SimpleNamespace()
    trace = GazeTrace([steady, stalled])
    steady._next_smartcal_trace.extend((t / 100, 0.1, 0.2, 1.0, 0.0) for t in range(10))
    assert trace.scatter(0.0, 1.0) == 0.0
