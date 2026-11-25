"""BLINK, the image-intensity blink estimator: a closed lid reads brighter
than the open eye once it has learned the brightness range, and its outlier
bounds are not re-sorted from the whole window every frame."""

from collections import deque
from types import SimpleNamespace

import numpy as np

import blink


def _processor(level=100, **state):
    proc = SimpleNamespace(
        current_image_gray_clean=np.full((10, 10), level, dtype=np.uint8),
        calibration_start_time=None,
        max_ints=[],
        max_int=0,
        min_int=float("inf"),
        frames=0,
    )
    for name, value in state.items():
        setattr(proc, name, value)
    return proc


def test_reads_open_until_the_closed_brightness_is_learned():
    proc = _processor(level=250)
    assert [blink.BLINK(proc) for _ in range(20)] == [0.8] * 20


def _learned(level):
    # A window spanning dark to bright frames, and two learned lid brightnesses.
    window = deque(np.linspace(0, 25500, 100), maxlen=300)
    return _processor(level, filterlist=window, max_ints=[10000, 12000], max_int=12000, frames=400)


def test_a_frame_brighter_than_the_learned_lid_reads_closed():
    assert blink.BLINK(_learned(150)) == 0.0  # sum 15000 > 10000


def test_a_frame_darker_than_the_learned_lid_reads_open():
    assert blink.BLINK(_learned(50)) == 0.8  # sum 5000


def test_a_calibration_restarts_the_window():
    proc = _learned(150)
    proc.calibration_start_time = 1.0
    blink.BLINK(proc)
    assert list(proc.filterlist) == [15000]


def test_blink_bounds_are_not_recomputed_every_frame(count_calls):
    calls = count_calls(blink.np, "percentile")
    proc = _processor()
    for _ in range(100):  # fill the window
        blink.BLINK(proc)
    calls.clear()

    for _ in range(30):
        blink.BLINK(proc)

    assert len(calls) <= 4
