"""VRChat gaze of the shared model: next_smooth.Smoother, scaled by the smoothing slider.

A still eye is steadied, a real move is followed within a couple of passes, a
blink does not move gaze, a wink does not freeze it, and a lost camera is not
taken for an eye move.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "eyetrackapp"))

from eye import EyeId  # noqa: E402
from next_model import TimedMedian  # noqa: E402
from next_smooth import Smoother  # noqa: E402
from next_stereo_model import NEXT_Stereo_cls  # noqa: E402
import one_euro_filter  # noqa: E402

BOTH = {EyeId.LEFT: True, EyeId.RIGHT: True}
FPS = 60.0


def _raw(gaze=(0.0, 0.0), lids=(0.85, 0.85), mono_l=None, mono_r=None):
    raw = np.zeros(12, dtype=np.float64)
    raw[1], raw[4] = lids
    raw[6:8] = gaze
    raw[8:10] = gaze if mono_l is None else mono_l
    raw[10:12] = gaze if mono_r is None else mono_r
    return raw


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


def _runner(monkeypatch, clock):
    monkeypatch.setattr(one_euro_filter, "perf_counter", lambda: clock[0])
    monkeypatch.setattr("next_stereo_model.time.perf_counter", lambda: clock[0])
    model = NEXT_Stereo_cls.__new__(NEXT_Stereo_cls)
    model.gaze_y_sign = 1.0
    model.one_euro_filter = one_euro_filter.OneEuroFilter(np.zeros(8, dtype=np.float32), step_s=1 / 120)
    model._brow_l_window, model._brow_r_window = TimedMedian(5), TimedMedian(5)
    model._gaze_x_window, model._gaze_y_window = TimedMedian(3), TimedMedian(3)
    model._last_expr = {EyeId.LEFT: None, EyeId.RIGHT: None}
    model.init_eye_gaze_state()
    return model


def test_runner_routes_fused_and_per_eye_gaze_through_the_smoother(monkeypatch):
    clock = [0.0]
    model = _runner(monkeypatch, clock)
    for i in range(180):
        clock[0] = i / FPS
        x = 0.5 if i >= 90 else 0.0
        raw = _raw((x, 0.1), mono_l=(x + 0.05, 0.1), mono_r=(x - 0.05, 0.1)).astype(np.float32)
        out = model.postprocess(raw, BOTH, 0.003162, 1.525)
        if i == 93:
            assert out[6] > 0.45  # the old chain needs over ten frames for this
    assert out[6] == np.float32(out[6]) and abs(out[6] - 0.5) < 0.01
    np.testing.assert_allclose(model.last_eye_gaze, [0.55, 0.1, 0.45, 0.1], atol=0.01)
    assert model.last_raw_gaze == (0.5, np.float32(0.1))


def test_dfr_gaze_keeps_the_fixed_chain_whatever_the_slider(monkeypatch):
    results = []
    for cutoff in (0.003162, 0.00002):
        clock = [0.0]
        model = _runner(monkeypatch, clock)
        for i in range(96):
            clock[0] = i / FPS
            model.postprocess(_raw((0.5 if i >= 90 else 0.0, 0.0)).astype(np.float32), BOTH, cutoff, 1.525)
        results.append(model.last_dfr_gaze[0])
    assert results[0] < 0.45  # six frames after the step the One-Euro chain is still on its way
    assert results[0] == results[1]


def test_slider_scales_the_vrchat_gaze_only(monkeypatch):
    def settle(cutoff):
        clock = [0.0]
        model = _runner(monkeypatch, clock)
        rng = np.random.default_rng(0)
        outs = []
        for i in range(240):
            clock[0] = i / FPS
            gaze = (rng.normal(0, 0.008), 0.0)
            outs.append(model.postprocess(_raw(gaze).astype(np.float32), BOTH, cutoff, 1.525)[6])
        return np.std(outs[60:])

    assert settle(0.003162) < settle(0.5)  # lighter smoothing passes more jitter
    assert settle(0.00002) < settle(0.003162)
