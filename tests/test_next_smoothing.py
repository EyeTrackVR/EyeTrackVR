"""Smoothing of the shared NEXT model's output.

The VRChat gaze goes through next_smooth.Smoother, scaled by the smoothing
slider: a still eye is steadied, a real move is followed within a couple of
passes, a blink does not move gaze, a wink does not freeze it, and a lost
camera is not taken for an eye move. Foveated rendering keeps a fixed median +
One-Euro chain that steps in fixed time, so it responds the same whatever the
inference pass rate (one camera gives a pass per frame, two cameras a pass per
frame of either eye; per-pass filters made one eye visibly lag behind two)."""

from collections import deque

import numpy as np
import pytest

import one_euro_filter
from eye import EyeId
from next_model import NEXT_FILTER_STEP_S, TimedMedian
from next_smooth import GAZE_BAND, Smoother
from next_stereo_model import GAZE_SPACE_TAN, NEXT_Stereo_cls
from tests.next_stubs import stereo_runner

BOTH = {EyeId.LEFT: True, EyeId.RIGHT: True}
ONE_EYE = {EyeId.LEFT: True, EyeId.RIGHT: False}
FPS = 60.0
# Default smoothing slider values (config.py gui_min_cutoff / gui_speed_coefficient).
BASE_CUTOFF, BASE_BETA = 0.003162, 1.525


def _raw(gaze=(0.0, 0.0), lids=(0.85, 0.85), mono_l=None, mono_r=None):
    raw = np.zeros(12, dtype=np.float64)
    raw[1], raw[4] = lids
    raw[6:8] = gaze
    raw[8:10] = gaze if mono_l is None else mono_l
    raw[10:12] = gaze if mono_r is None else mono_r
    return raw


# ── Smoother ─────────────────────────────────────────────────────────────────


def _run(frames, fps=FPS):
    f, out = Smoother(), []
    for i, (raw, valid) in enumerate(frames):
        out.append(f(i / fps, raw, *valid)[6:8].copy())
    return np.array(out)


def test_still_eye_is_steadied_and_a_step_is_followed():
    rng = np.random.default_rng(0)
    frames = []
    for i in range(240):
        gaze = np.array([0.5 if i >= 120 else 0.0, 0.0]) + rng.normal(0, 0.008, 2)
        frames.append((_raw(gaze), (True, True)))
    out = _run(frames)
    assert out[60:118, 0].std() < 0.004  # raw noise is 0.008
    assert out[123, 0] > 0.45  # 90% of the move within 3 frames
    assert out[180:, 0].std() < 0.004


def test_blink_holds_gaze():
    frames = []
    for i in range(200):
        blink = 100 <= i < 106
        lids = (0.05, 0.05) if blink else (0.5, 0.5) if 106 <= i < 109 else (0.85, 0.85)
        frames.append((_raw((0.0, -0.4) if 99 <= i < 110 else (0.0, 0.0), lids), (True, True)))
    out = _run(frames)
    assert out[95:130, 1].min() > -0.08  # raw swings to -0.4


def test_wink_follows_the_open_eye():
    frames = []
    for i in range(300):
        winking = 60 <= i < 240
        x = 0.5 if i >= 150 else 0.0
        # The two-eye head is thrown off by the shut eye; the open eye is not.
        fused = (x, -0.3) if winking else (x, 0.0)
        frames.append((_raw(fused, (0.05 if winking else 0.85, 0.85), mono_l=fused, mono_r=(x, 0.0)), (True, True)))
    out = _run(frames)
    assert out[165, 0] > 0.45  # gaze still moves during the wink
    assert abs(out[140, 1]) < 0.05  # and does not take the shut eye's reading


def test_one_bad_camera_frame_at_two_passes_per_frame_is_not_a_move():
    frames = [(_raw((0.4, 0.0) if 200 <= i < 202 else (0.0, 0.0)), (True, True)) for i in range(300)]
    assert _run(frames, fps=120.0)[195:215, 0].max() < 0.1


def test_losing_a_camera_is_not_an_eye_move():
    frames = []
    for i in range(240):
        gap = 120 <= i < 125
        # The remaining eye's own head sits 0.15 away from the two-eye gaze.
        frames.append((_raw((0.0, 0.0), mono_l=(0.15, 0.0), mono_r=(0.0, 0.0)), (True, not gap)))
    out = _run(frames)
    assert np.abs(out[118:135, 0]).max() < 0.03


# ── through the shared runner ────────────────────────────────────────────────


def test_runner_routes_fused_and_per_eye_gaze_through_the_smoother(monkeypatch):
    clock = [0.0]
    model = stereo_runner(monkeypatch, clock)
    for i in range(180):
        clock[0] = i / FPS
        x = 0.5 if i >= 90 else 0.0
        raw = _raw((x, 0.1), mono_l=(x + 0.05, 0.1), mono_r=(x - 0.05, 0.1)).astype(np.float32)
        out = model.postprocess(raw, BOTH, BASE_CUTOFF, BASE_BETA)
        if i == 93:
            assert out[6] > 0.45  # the old chain needs over ten frames for this
    assert out[6] == np.float32(out[6]) and abs(out[6] - 0.5) < 0.01
    np.testing.assert_allclose(model.last_eye_gaze, [0.55, 0.1, 0.45, 0.1], atol=0.01)
    assert model.last_raw_gaze == (0.5, np.float32(0.1))


def test_dfr_gaze_keeps_the_fixed_chain_whatever_the_slider(monkeypatch):
    results = []
    for cutoff in (0.003162, 0.00002):
        clock = [0.0]
        model = stereo_runner(monkeypatch, clock)
        for i in range(96):
            clock[0] = i / FPS
            model.postprocess(_raw((0.5 if i >= 90 else 0.0, 0.0)).astype(np.float32), BOTH, cutoff, BASE_BETA)
        results.append(model.last_dfr_gaze[0])
    assert results[0] < 0.45  # six frames after the step the One-Euro chain is still on its way
    assert results[0] == results[1]


def test_slider_scales_the_vrchat_gaze_only(monkeypatch):
    def settle(cutoff):
        clock = [0.0]
        model = stereo_runner(monkeypatch, clock)
        rng = np.random.default_rng(0)
        outs = []
        for i in range(240):
            clock[0] = i / FPS
            gaze = (rng.normal(0, 0.008), 0.0)
            outs.append(model.postprocess(_raw(gaze).astype(np.float32), BOTH, cutoff, BASE_BETA)[6])
        return np.std(outs[60:])

    assert settle(0.003162) < settle(0.5)  # lighter smoothing passes more jitter
    assert settle(0.00002) < settle(0.003162)


def test_smoother_bands_follow_the_model_units():
    runner = NEXT_Stereo_cls.__new__(NEXT_Stereo_cls)
    runner.init_eye_gaze_state()
    runner._set_smoother_scale(1.0)
    snap = runner._gaze_smoother.g["both"]
    assert (snap.tau, snap.d0, snap.d1) == pytest.approx(GAZE_BAND)
    runner.gaze_space = GAZE_SPACE_TAN
    runner._set_smoother_scale(1.0)
    assert snap.tau == pytest.approx(GAZE_BAND[0])  # time is not a gaze unit
    assert snap.d0 == pytest.approx(GAZE_BAND[1] * 0.5774) and snap.d1 == pytest.approx(GAZE_BAND[2] * 0.5774)
    assert runner._eye_gaze_snaps[0].d1 == pytest.approx(snap.d1)
    # The smoothing slider still scales time and band together.
    runner._set_smoother_scale(2.0)
    assert snap.tau == pytest.approx(2 * GAZE_BAND[0]) and snap.d1 == pytest.approx(2 * GAZE_BAND[2] * 0.5774)


# ── the fixed-step foveation chain ───────────────────────────────────────────


def _settle_times(monkeypatch, passes_per_s, valid, step_s):
    """ms until the DFR gaze X (median + One-Euro chain) reaches 50% / 90% of a 0 -> 0.5 saccade."""
    clock = [0.0]
    model = stereo_runner(monkeypatch, clock, step_s=step_s)
    hits = {}
    for i in range(int(3.0 * passes_per_s)):
        t = i / passes_per_s
        clock[0] = t
        raw = np.zeros(12, dtype=np.float32)
        raw[6] = raw[8] = raw[10] = 0.5 if t >= 1.0 else 0.0
        model.postprocess(raw, valid, BASE_CUTOFF, BASE_BETA)
        gaze_x = model.last_dfr_gaze[0]
        # Per-eye gaze modes get the shared gaze's exact (fixed-step) smoothing.
        if step_s is not None:
            np.testing.assert_allclose(model.last_dfr_eye_gaze[[0, 2]], gaze_x, atol=1e-6)
        for frac in (0.5, 0.9):
            if t >= 1.0 and frac not in hits and gaze_x >= 0.5 * frac:
                hits[frac] = (t - 1.0) * 1000.0
    return hits


def test_one_eye_settles_like_two_eyes(monkeypatch):
    one = _settle_times(monkeypatch, 60, ONE_EYE, NEXT_FILTER_STEP_S)
    both = _settle_times(monkeypatch, 120, BOTH, NEXT_FILTER_STEP_S)
    # Within one 60 fps frame: the slower stream can only report on its frames.
    for frac in (0.5, 0.9):
        assert abs(one[frac] - both[frac]) <= 1000.0 / 60 + 1e-6


def test_per_pass_filter_was_rate_dependent(monkeypatch):
    # The regression this fixes: per-pass stepping made one eye far slower.
    one = _settle_times(monkeypatch, 60, ONE_EYE, None)
    both = _settle_times(monkeypatch, 120, BOTH, None)
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
