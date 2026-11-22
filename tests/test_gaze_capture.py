from types import SimpleNamespace

import math
import random
import time

import pytest

import gaze_capture
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


def _traced(gaze_at, seconds=1.0, fps=100):
    """A trace that already holds the frames of the next ``seconds``, so a
    wait reads what a camera would deliver without a thread to time it."""
    eye = SimpleNamespace()
    trace = GazeTrace([eye])
    start = time.monotonic() - 0.05
    eye._next_smartcal_trace.extend(
        (start + i / fps, *gaze_at(i / fps), 0.8, 0.5) for i in range(int((seconds + 0.05) * fps))
    )
    return trace


def _noisy(sigma, seed=1):
    noise = random.Random(seed)
    return lambda _at: (0.3 + noise.gauss(0.0, sigma), -0.2 + noise.gauss(0.0, sigma))


def test_one_stray_frame_does_not_make_a_resting_gaze_a_moving_one():
    eye = SimpleNamespace()
    trace = GazeTrace([eye])
    eye._next_smartcal_trace.extend((t / 100, 0.1, 0.2, 1.0, 0.0) for t in range(20))
    eye._next_smartcal_trace[7] = (0.07, 0.4, 0.2, 1.0, 0.0)
    assert trace.scatter(0.0, 1.0) == 0.0
    # A gaze on its way spreads every frame.
    eye._next_smartcal_trace[:] = [(t / 100, 0.1 + 0.02 * t, 0.2, 1.0, 0.0) for t in range(20)]
    assert trace.scatter(0.0, 1.0) > gaze_capture.CEILING


def test_a_gaze_resting_in_a_noisy_image_still_rests():
    trace = _traced(_noisy(0.025), fps=200)
    # Its farthest frame is well past the ceiling, most of them are not.
    ((_, frames),) = trace.frames(0.0)
    assert max(math.hypot(x - 0.3, y + 0.2) for _, x, y, _, _ in frames[:40]) > 1.2 * gaze_capture.CEILING
    assert trace.scatter(frames[0][0], frames[39][0]) < gaze_capture.CEILING
    assert _traced(_noisy(0.02)).wait_until_resting(0.8)


def test_the_steadiest_stretch_stands_in_when_the_noise_is_too_much_to_rest():
    trace = _traced(_noisy(0.045))
    started = time.monotonic()
    assert not trace.wait_until_resting(0.5)
    start, end = trace.steadiest_stretch()
    assert started <= start < end <= time.monotonic()
    assert end - start == pytest.approx(gaze_capture.SETTLE_S)
    ((_, frames),) = trace.frames(start, end)
    assert len(frames) >= 15


def test_a_gaze_that_keeps_moving_has_no_stretch_to_stand_in():
    trace = _traced(lambda at: (0.4 if int(at / 0.03) % 2 else -0.4, 0.0))
    assert not trace.wait_until_resting(0.4)
    assert trace.steadiest_stretch() is None
    # Nor has an eye that delivered nothing.
    idle = GazeTrace([SimpleNamespace()])
    assert not idle.wait_until_resting(0.25) and idle.steadiest_stretch() is None
