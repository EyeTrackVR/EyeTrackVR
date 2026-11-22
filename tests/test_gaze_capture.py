from types import SimpleNamespace

import math

from gaze_capture import GazeTrace, open_lid


def test_an_eye_without_frames_does_not_hold_up_the_others():
    steady, stalled = SimpleNamespace(), SimpleNamespace()
    trace = GazeTrace([steady, stalled])
    steady._next_smartcal_trace.extend((t / 100, 0.1, 0.2, 1.0, 0.0) for t in range(10))
    assert trace.scatter(0.0, 1.0) == 0.0


def test_blinks_are_judged_against_the_usual_lid_of_the_run():
    # An eye whose open lid reads low is not blinking all the time.
    assert open_lid([0.2] * 50 + [0.01] * 5) == 0.1
    # A high-reading eye keeps the fixed level, and shut eyes are never open.
    assert open_lid([0.9] * 50) == 0.3 and open_lid([]) == 0.3
    assert open_lid([0.0] * 50) == 0.05


def test_an_eye_with_a_low_resting_lid_still_rests():
    eye = SimpleNamespace()
    trace = GazeTrace([eye])
    eye._next_smartcal_trace.extend((t / 100, 0.1, 0.2, 0.2, 0.0) for t in range(10))
    assert trace.scatter(0.0, 1.0) == 0.0
    # Its blinks, with the gaze thrown off, do not count.
    eye._next_smartcal_trace.extend((0.2 + t / 100, 0.9, 0.9, 0.02, 0.0) for t in range(3))
    assert trace.scatter(0.0, 1.0) == 0.0
    assert math.isinf(trace.scatter(0.2, 1.0))
