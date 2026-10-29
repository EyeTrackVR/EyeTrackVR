"""NEXT smoothing responds the same in time whatever the inference pass rate.

One camera gives one shared-model pass per frame; two cameras give a pass per
frame of either eye. The filters used to advance per pass, so one eye (or
slower cameras) visibly lagged behind two."""

from collections import deque

import numpy as np
import pytest

import one_euro_filter
from eye import EyeId
from next_model import NEXT_FILTER_STEP_S, TimedMedian
from next_stereo_model import NEXT_Stereo_cls

# Default smoothing slider values (config.py gui_min_cutoff / gui_speed_coefficient).
BASE_CUTOFF, BASE_BETA = 0.003162, 1.525


def _settle_times(monkeypatch, passes_per_s, valid, step_s):
    """ms until shared gaze X reaches 50% / 90% of a 0 -> 0.5 saccade."""
    clock = [0.0]
    monkeypatch.setattr(one_euro_filter, "perf_counter", lambda: clock[0])
    monkeypatch.setattr("next_stereo_model.time.perf_counter", lambda: clock[0])
    model = NEXT_Stereo_cls.__new__(NEXT_Stereo_cls)
    model.gaze_y_sign = 1.0
    model.one_euro_filter = one_euro_filter.OneEuroFilter(np.zeros(8, dtype=np.float32), step_s=step_s)
    model._brow_l_window = TimedMedian(5)
    model._brow_r_window = TimedMedian(5)
    model._gaze_x_window = TimedMedian(3)
    model._gaze_y_window = TimedMedian(3)
    model._last_expr = {EyeId.LEFT: None, EyeId.RIGHT: None}
    hits = {}
    for i in range(int(3.0 * passes_per_s)):
        t = i / passes_per_s
        clock[0] = t
        raw = np.zeros(12, dtype=np.float32)
        raw[6] = 0.5 if t >= 1.0 else 0.0
        out = model.postprocess(raw, valid, BASE_CUTOFF, BASE_BETA)
        for frac in (0.5, 0.9):
            if t >= 1.0 and frac not in hits and out[6] >= 0.5 * frac:
                hits[frac] = (t - 1.0) * 1000.0
    return hits


ONE_EYE = {EyeId.LEFT: True, EyeId.RIGHT: False}
BOTH_EYES = {EyeId.LEFT: True, EyeId.RIGHT: True}


def test_one_eye_settles_like_two_eyes(monkeypatch):
    one = _settle_times(monkeypatch, 60, ONE_EYE, NEXT_FILTER_STEP_S)
    both = _settle_times(monkeypatch, 120, BOTH_EYES, NEXT_FILTER_STEP_S)
    # Within one 60 fps frame: the slower stream can only report on its frames.
    for frac in (0.5, 0.9):
        assert abs(one[frac] - both[frac]) <= 1000.0 / 60 + 1e-6


def test_per_pass_filter_was_rate_dependent(monkeypatch):
    # The regression this fixes: per-pass stepping made one eye far slower.
    one = _settle_times(monkeypatch, 60, ONE_EYE, None)
    both = _settle_times(monkeypatch, 120, BOTH_EYES, None)
    assert one[0.9] - both[0.9] > 50.0


@pytest.mark.parametrize("rate", [30, 60, 90, 144, 240])
def test_fixed_step_filter_state_is_rate_independent(monkeypatch, rate):
    clock = [0.0]
    monkeypatch.setattr(one_euro_filter, "perf_counter", lambda: clock[0])
    reference = one_euro_filter.OneEuroFilter(np.zeros(1), min_cutoff=0.5, beta=0.3, step_s=NEXT_FILTER_STEP_S)
    filt = one_euro_filter.OneEuroFilter(np.zeros(1), min_cutoff=0.5, beta=0.3, step_s=NEXT_FILTER_STEP_S)
    # Hold a constant input: then the elapsed time, not the call pattern, must
    # decide the state. Compare at a time both call patterns land on.
    x = np.array([1.0])
    for i in range(1, 121):
        clock[0] = i * NEXT_FILTER_STEP_S
        expected = reference(x)
    clock[0] = 0.0
    filt.t_prev = 0.0
    for i in range(1, rate + 1):
        clock[0] = i / rate
        actual = filt(x)
    np.testing.assert_allclose(actual, expected, rtol=1e-6)


def test_fixed_step_filter_bounds_catch_up_after_a_stall(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(one_euro_filter, "perf_counter", lambda: clock[0])
    filt = one_euro_filter.OneEuroFilter(np.zeros(1), step_s=NEXT_FILTER_STEP_S)
    clock[0] = 3600.0
    out = filt(np.array([1.0]))
    assert np.isfinite(out).all()
    assert filt._pending_s < NEXT_FILTER_STEP_S


def test_timed_median_spans_time_but_keeps_three_samples():
    brow = TimedMedian(5)
    # At 120 passes/s (the reference) it is the old 5-sample window.
    values = [0.0, 0.0, 9.0, 1.0, 1.0]
    out = [brow(v, i * NEXT_FILTER_STEP_S) for i, v in enumerate(values)]
    assert out[-1] == float(np.median(values))
    assert len(brow._items) == 5
    # At 60 fps the same span holds three samples: less lag, spikes still rejected.
    slow = TimedMedian(5)
    for i, v in enumerate([0.0, 0.0, 0.0, 9.0, 1.0, 1.0]):
        last = slow(v, i / 60)
    assert len(slow._items) == 3
    assert last == 1.0
    # A constant clock (as some tests patch in) degrades to the old count window.
    frozen = TimedMedian(3)
    for v in (1.0, 2.0, 3.0, 4.0):
        frozen(v, 5.0)
    assert [v for _, v in frozen._items] == list(deque([2.0, 3.0, 4.0]))
