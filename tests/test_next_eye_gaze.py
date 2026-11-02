"""Per-eye NEXT gaze modes (strabismus / amblyopia): fused stays untouched,
independent and dominant follow the Hybrid's monocular gaze [8:12], and Smart
Calib / recenter keep a real deviation between the eyes."""

import os
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from eye import EyeId
from eye_processor import EyeProcessor
from next_eye_gaze import (
    GAZE_MODE_DOMINANT,
    GAZE_MODE_FUSED,
    GAZE_MODE_INDEPENDENT,
    LID_CLOSED,
    PerEyeGaze,
    dominant_eye_from_settings,
    gaze_mode_from_settings,
    select_eye_gaze,
)
from next_stereo_model import NEXT_Stereo_cls, SharedPass, stereo_model_file
from osc_calibrate_filter import (
    NEXT_SMARTCAL_DOTS,
    _SMARTCAL_MAX_GAIN,
    _fit_next_smartcal,
    clamp_next_smartcal_transform,
    next_smartcal_apply,
    next_smartcal_targets,
)
from utils.misc_utils import resource_path

STEP_S = 1.0 / 60.0
# Esotropia-like right eye: points 0.2 further toward +x than the left.
DEVIATION = np.array([0.2, 0.0])


class _IdentityFilter:
    def __init__(self, size):
        self.min_cutoff = np.zeros(size, dtype=np.float32)
        self.beta = np.zeros(size, dtype=np.float32)

    def __call__(self, values):
        return np.asarray(values, dtype=np.float32)


def _settings(mode=GAZE_MODE_FUSED, dominant="left", **extra):
    return SimpleNamespace(gui_NEXT_gaze_mode=mode, gui_NEXT_dominant_eye=dominant, **extra)


# ── settings + selection ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stored,expected",
    [
        (None, GAZE_MODE_FUSED),
        ("bogus", GAZE_MODE_FUSED),
        ("Independent", GAZE_MODE_INDEPENDENT),
        ("dominant", GAZE_MODE_DOMINANT),
    ],
)
def test_gaze_mode_defaults_to_fused(stored, expected):
    settings = SimpleNamespace() if stored is None else SimpleNamespace(gui_NEXT_gaze_mode=stored)
    assert gaze_mode_from_settings(settings) == expected


def test_dominant_eye_defaults_to_left():
    assert dominant_eye_from_settings(SimpleNamespace()) == EyeId.LEFT
    assert dominant_eye_from_settings(_settings(dominant="right")) == EyeId.RIGHT


def test_select_eye_gaze_routes_each_mode():
    eye = [0.1, 0.2, 0.3, 0.4]
    assert select_eye_gaze(eye, EyeId.LEFT, GAZE_MODE_INDEPENDENT, EyeId.LEFT) == pytest.approx((0.1, 0.2))
    assert select_eye_gaze(eye, EyeId.RIGHT, GAZE_MODE_INDEPENDENT, EyeId.LEFT) == pytest.approx((0.3, 0.4))
    for eye_id in (EyeId.LEFT, EyeId.RIGHT):
        assert select_eye_gaze(eye, eye_id, GAZE_MODE_DOMINANT, EyeId.RIGHT) == pytest.approx((0.3, 0.4))
        assert select_eye_gaze(eye, eye_id, GAZE_MODE_DOMINANT, EyeId.LEFT) == pytest.approx((0.1, 0.2))


# ── missing / closed eye rebuild ─────────────────────────────────────────────


def _settle(tracker, left, right, passes=120):
    ts = 0.0
    for _ in range(passes):
        ts += STEP_S
        out = tracker.update([*left, *right], True, True, 0.8, 0.8, ts)
    return out, ts


def test_both_eyes_open_pass_through_untouched():
    tracker = PerEyeGaze()
    left, right = np.array([0.1, -0.2]), np.array([0.1, -0.2]) + DEVIATION
    out, _ = _settle(tracker, left, right)
    np.testing.assert_allclose(out, [*left, *right], atol=1e-6)


@pytest.mark.parametrize("missing", [EyeId.LEFT, EyeId.RIGHT])
def test_black_sentinel_eye_keeps_the_deviation(missing):
    tracker = PerEyeGaze()
    left, right = np.array([0.0, 0.0]), DEVIATION.copy()
    _, ts = _settle(tracker, left, right)
    # The present eye moves on; the sentinel's zeros must not reach the output.
    moved = np.array([-0.3, 0.25])
    if missing == EyeId.RIGHT:
        out = tracker.update([*moved, 0.0, 0.0], True, False, 0.8, 0.0, ts + STEP_S)
        np.testing.assert_allclose(out, [*moved, *(moved + DEVIATION)], atol=1e-5)
    else:
        out = tracker.update([0.0, 0.0, *(moved + DEVIATION)], False, True, 0.0, 0.8, ts + STEP_S)
        np.testing.assert_allclose(out, [*moved, *(moved + DEVIATION)], atol=1e-5)


def test_wink_hands_the_closed_eye_to_the_open_one():
    tracker = PerEyeGaze()
    left, right = np.array([0.0, 0.0]), DEVIATION.copy()
    _, ts = _settle(tracker, left, right)
    # Right eye closed: its own (unreliable) value is replaced; left untouched.
    out = tracker.update([0.1, 0.1, 0.9, -0.9], True, True, 0.8, LID_CLOSED * 0.5, ts + STEP_S)
    np.testing.assert_allclose(out, [0.1, 0.1, 0.3, 0.1], atol=1e-5)


def test_bilateral_blink_keeps_own_values():
    tracker = PerEyeGaze()
    _, ts = _settle(tracker, np.zeros(2), DEVIATION)
    out = tracker.update([0.05, 0.0, 0.25, 0.0], True, True, 0.02, 0.03, ts + STEP_S)
    np.testing.assert_allclose(out, [0.05, 0.0, 0.25, 0.0], atol=1e-6)


def test_no_eye_holds_the_last_value():
    tracker = PerEyeGaze()
    out, ts = _settle(tracker, np.array([0.1, 0.1]), np.array([0.3, 0.1]))
    held = tracker.update([0.0, 0.0, 0.0, 0.0], False, False, 0.0, 0.0, ts + STEP_S)
    np.testing.assert_allclose(held, out)


# ── model postprocess ────────────────────────────────────────────────────────

HYBRID_PATH = stereo_model_file("ETVR")
needs_hybrid = pytest.mark.skipif(
    HYBRID_PATH is None or not os.path.exists(resource_path(HYBRID_PATH)),
    reason="shipped Hybrid export not present",
)


@pytest.fixture
def hybrid():
    return NEXT_Stereo_cls(HYBRID_PATH)


def _raw12(rng):
    raw = rng.uniform(0.2, 0.9, 12).astype(np.float32)
    raw[6:] = rng.uniform(-0.6, 0.6, 6)
    return raw


@needs_hybrid
def test_fused_outputs_ignore_the_per_eye_channels(hybrid):
    # Same [0:8] stream through two fresh runners, one with wildly different
    # per-eye channels and one with none at all: the fused result is identical.
    other = NEXT_Stereo_cls(HYBRID_PATH)
    legacy = NEXT_Stereo_cls(HYBRID_PATH)
    # The One-Euro step depends on wall-clock spacing between calls; identity
    # filters keep the comparison exact (medians and the hold still run).
    for runner in (hybrid, other, legacy):
        runner.one_euro_filter = _IdentityFilter(8)
    rng = np.random.default_rng(3)
    valid = {EyeId.LEFT: True, EyeId.RIGHT: True}
    for _ in range(30):
        raw = _raw12(rng)
        alt = raw.copy()
        alt[8:12] = rng.uniform(-1.0, 1.0, 4)
        a = hybrid.postprocess(raw, valid, 0.5, 0.2)
        b = other.postprocess(alt, valid, 0.5, 0.2)
        c = legacy.postprocess(raw[:8].copy(), valid, 0.5, 0.2)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(a, c)
    assert legacy.last_eye_gaze is None
    assert hybrid.last_eye_gaze is not None


@needs_hybrid
def test_per_eye_y_uses_the_shared_gaze_y_sign(hybrid):
    # The exporter negates channels 7, 9 and 11 together, so all three take
    # the app's one Y sign.
    hybrid.one_euro_filter = _IdentityFilter(8)
    hybrid.eye_gaze_filter = _IdentityFilter(4)
    raw = np.array([0.5, 0.8, 0.0, 0.5, 0.8, 0.0, 0.1, 0.2, 0.11, 0.21, 0.31, 0.41], dtype=np.float32)
    out = hybrid.postprocess(raw.copy(), {EyeId.LEFT: True, EyeId.RIGHT: True}, 0.0, 0.0)
    s = hybrid.gaze_y_sign
    assert out[7] == pytest.approx(0.2 * s)
    np.testing.assert_allclose(hybrid.last_eye_gaze, [0.11, 0.21 * s, 0.31, 0.41 * s], atol=1e-6)
    np.testing.assert_allclose(hybrid.last_raw_eye_gaze, [0.11, 0.21 * s, 0.31, 0.41 * s], atol=1e-6)


@needs_hybrid
def test_black_eye_never_reaches_the_per_eye_filter(hybrid):
    hybrid.eye_gaze_filter = _IdentityFilter(4)
    both = {EyeId.LEFT: True, EyeId.RIGHT: True}
    s = hybrid.gaze_y_sign
    for _ in range(60):
        raw = np.array([0.5, 0.8, 0.0, 0.5, 0.8, 0.0, 0.1, 0.0, 0.0, 0.0, 0.2, 0.0], dtype=np.float32)
        hybrid.postprocess(raw, both, 0.0, 0.0)
    # Right camera blacked out: the model zeroes its expressions and gaze.
    raw = np.array([0.5, 0.8, 0.0, 0.0, 0.0, 0.0, -0.3, 0.1, -0.3, 0.1, 0.0, 0.0], dtype=np.float32)
    for _ in range(5):
        hybrid.postprocess(raw.copy(), {EyeId.LEFT: True, EyeId.RIGHT: False}, 0.0, 0.0)
    np.testing.assert_allclose(hybrid.last_eye_gaze, [-0.3, 0.1 * s, -0.1, 0.1 * s], atol=1e-5)


# ── eye processor routing ────────────────────────────────────────────────────


def _routing_processor(eye, mode, dominant="left"):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = eye
    processor.current_raw_frame = np.zeros((64, 80, 3), dtype=np.uint8)
    processor.current_image_gray = np.zeros((64, 80), dtype=np.uint8)
    processor.current_capture_ts = 1000.0
    processor.settings = _settings(
        mode,
        dominant,
        gui_min_cutoff=0.0004,
        gui_speed_coefficient=0.9,
        gui_setup_mode="standard",
        gui_model_variant="ETVR",
        gui_use_gpu=False,
    )
    processor._next_apply = Mock()
    processor._next_mode_changed = Mock()
    return processor


def _coord(served):
    coord = SimpleNamespace(
        supports_single_eye=True,
        submit=Mock(),
        run=Mock(return_value=(0.05, 0.06, 0.3, 0.4, 0.5)),
        peer_active=Mock(),
        raw_gaze=Mock(return_value=(0.07, 0.08)),
        expression_coupler=Mock(),
        served_pass=Mock(return_value=served),
    )
    return coord


def _served():
    result = np.zeros(8, dtype=np.float32)
    return SharedPass(
        1,
        result,
        True,
        1.0,
        np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        np.array([0.11, 0.21, 0.31, 0.41], dtype=np.float32),
    )


@pytest.mark.parametrize("eye", [EyeId.LEFT, EyeId.RIGHT])
def test_fused_mode_routes_the_shared_gaze_unchanged(monkeypatch, eye):
    processor = _routing_processor(eye, GAZE_MODE_FUSED)
    served = _served()
    coord = _coord(served)
    monkeypatch.setattr("eye_processor.get_stereo_coordinator", lambda *args: coord)
    processor.NEXTM()
    processor._next_apply.assert_called_once_with(
        0.05, 0.06, 0.3, 0.4, 0.5, raw_gaze=(0.07, 0.08), shared=(coord.expression_coupler, served)
    )


@pytest.mark.parametrize(
    "mode,dominant,eye,gaze,raw",
    [
        (GAZE_MODE_INDEPENDENT, "left", EyeId.LEFT, (0.1, 0.2), (0.11, 0.21)),
        (GAZE_MODE_INDEPENDENT, "left", EyeId.RIGHT, (0.3, 0.4), (0.31, 0.41)),
        (GAZE_MODE_DOMINANT, "right", EyeId.LEFT, (0.3, 0.4), (0.31, 0.41)),
        (GAZE_MODE_DOMINANT, "left", EyeId.RIGHT, (0.1, 0.2), (0.11, 0.21)),
    ],
)
def test_per_eye_modes_route_the_monocular_gaze(monkeypatch, mode, dominant, eye, gaze, raw):
    processor = _routing_processor(eye, mode, dominant)
    served = _served()
    coord = _coord(served)
    monkeypatch.setattr("eye_processor.get_stereo_coordinator", lambda *args: coord)
    processor.NEXTM()
    args, kwargs = processor._next_apply.call_args
    assert args[:2] == pytest.approx(gaze)
    assert args[2:] == (0.3, 0.4, 0.5)
    assert kwargs["raw_gaze"] == pytest.approx(raw)
    reference = (0.3, 0.4) if dominant == "right" else (0.1, 0.2)
    assert kwargs["recenter_gaze"] == pytest.approx(reference)
    assert kwargs["shared"] == (coord.expression_coupler, served)


def test_per_eye_mode_without_per_eye_channels_stays_fused(monkeypatch):
    # Legacy 8-output stereo: nothing to route, so the fused gaze is kept.
    processor = _routing_processor(EyeId.RIGHT, GAZE_MODE_INDEPENDENT)
    served = SharedPass(1, np.zeros(8, dtype=np.float32), True, 1.0)
    coord = _coord(served)
    monkeypatch.setattr("eye_processor.get_stereo_coordinator", lambda *args: coord)
    processor.NEXTM()
    processor._next_apply.assert_called_once_with(
        0.05, 0.06, 0.3, 0.4, 0.5, raw_gaze=(0.07, 0.08), shared=(coord.expression_coupler, served)
    )


# ── recenter ─────────────────────────────────────────────────────────────────


def _apply_processor(eye):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = eye
    processor.settings = SimpleNamespace(
        gui_NEXT_calib_lids_brows=False,
        gui_NEXT_lid_sync=0,
        gui_NEXT_brow_sync=0,
        gui_flip_x_axis_left=False,
        gui_flip_x_axis_right=False,
        gui_flip_y_axis=False,
        gui_recenter_eyes=True,
        leap_lid_close_threshold_left=0.1,
        leap_lid_widen_threshold_left=0.9,
        leap_lid_close_threshold_right=0.1,
        leap_lid_widen_threshold_right=0.9,
    )
    processor._next_smartcal_active_dot = None
    processor._next_smartcal_w = None
    processor._next_smartcal_b = None
    processor._next_smartcal_warp = None
    processor._next_smartcal_lid_neutral = None
    processor._next_smartcal_brow_neutral = None
    processor._next_recenter_offset_x = 0.0
    processor._next_recenter_offset_y = 0.0
    processor._next_recenter_armed_at = None
    processor._recenter_delay_s = 0.2
    processor.out_x = 0.0
    processor.out_y = 0.0
    processor.osc_queue = Queue()
    return processor


def test_recenter_keeps_the_deviation_in_independent_mode():
    left_gaze, right_gaze = (0.05, -0.02), (0.25, -0.02)
    left, right = _apply_processor(EyeId.LEFT), _apply_processor(EyeId.RIGHT)
    left._next_apply(*left_gaze, 0.5, 0.8, 0.0, recenter_gaze=left_gaze)
    right._next_apply(*right_gaze, 0.5, 0.8, 0.0, recenter_gaze=left_gaze)
    assert (left.out_x, left.out_y) == pytest.approx((0.0, 0.0))
    assert (right.out_x, right.out_y) == pytest.approx(tuple(DEVIATION))


def test_recenter_without_reference_zeroes_each_eye():
    processor = _apply_processor(EyeId.RIGHT)
    processor._next_apply(0.25, -0.02, 0.5, 0.8, 0.0)
    assert (processor.out_x, processor.out_y) == pytest.approx((0.0, 0.0))


# ── Smart Calib ──────────────────────────────────────────────────────────────


def _calib_processor(eye, deviation, gain=0.6):
    """Samples of an eye that under-reads by ``gain`` and points ``deviation``
    away from every dot (a real strabismus, not a tracking error)."""
    targets = next_smartcal_targets(SimpleNamespace())
    samples = {}
    for dot in range(len(NEXT_SMARTCAL_DOTS)):
        tx, ty = targets[dot]
        x, y = gain * tx + deviation[0], gain * ty + deviation[1]
        samples[dot] = [(x, y, 0.75, 0.5)] * 8
    return SimpleNamespace(
        eye_id=eye,
        _next_smartcal_samples=samples,
        config=SimpleNamespace(),
        _next_smartcal_w=None,
        _next_smartcal_b=None,
        _next_smartcal_warp=None,
    )


def _calibrated(ep, gaze):
    return np.array(next_smartcal_apply(ep._next_smartcal_w, ep._next_smartcal_b, ep._next_smartcal_warp, *gaze))


def _fit(mode, dominant="left"):
    eps = [_calib_processor(EyeId.LEFT, (0.0, 0.0)), _calib_processor(EyeId.RIGHT, 0.6 * DEVIATION)]
    settings = _settings(mode, dominant, gui_NEXT_calib_lids_brows=False)
    assert _fit_next_smartcal(eps, Mock(), settings)
    return eps


def test_fused_smart_calib_still_fits_each_eye():
    left, right = _fit(GAZE_MODE_FUSED)
    # Each eye is pulled onto the dots: right's deviation becomes its bias.
    assert right._next_smartcal_b != pytest.approx(left._next_smartcal_b)
    straight = _calibrated(right, 0.6 * DEVIATION)
    np.testing.assert_allclose(straight, [0.0, 0.0], atol=1e-6)


@pytest.mark.parametrize("mode", [GAZE_MODE_INDEPENDENT, GAZE_MODE_DOMINANT])
def test_per_eye_smart_calib_fits_the_dominant_eye_for_both(mode):
    left, right = _fit(mode)
    assert right._next_smartcal_w == left._next_smartcal_w
    assert right._next_smartcal_b == left._next_smartcal_b
    assert right.config.next_smartcal_w == left.config.next_smartcal_w
    # Looking at the centre dot: the left eye reads centre, the deviated right
    # eye keeps its full deviation (the gain is corrected, not erased).
    np.testing.assert_allclose(_calibrated(left, (0.0, 0.0)), [0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(_calibrated(right, 0.6 * DEVIATION), DEVIATION, atol=1e-6)


def test_per_eye_smart_calib_follows_the_chosen_dominant_eye():
    left, right = _fit(GAZE_MODE_INDEPENDENT, dominant="right")
    np.testing.assert_allclose(_calibrated(right, 0.6 * DEVIATION), [0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(_calibrated(left, (0.0, 0.0)), -DEVIATION, atol=1e-6)


def _max_gain(ep):
    w = ep._next_smartcal_w
    return float(np.linalg.svd(np.array([[w[0], w[1]], [w[2], w[3]]]), compute_uv=False)[0])


def test_smart_calib_clamps_a_moderately_under_reading_model():
    # A tiny model reading 0.25x needs 4x: clamped to the gain bound, not dropped.
    ep = _calib_processor(EyeId.LEFT, (0.0, 0.0), gain=0.25)
    assert _fit_next_smartcal([ep], Mock(), _settings(gui_NEXT_calib_lids_brows=False))
    assert _max_gain(ep) == pytest.approx(_SMARTCAL_MAX_GAIN)


def test_smart_calib_still_rejects_a_wildly_over_gained_fit():
    # 0.12x needs ~8x, past the clamp factor: treated as degenerate.
    ep = _calib_processor(EyeId.LEFT, (0.0, 0.0), gain=0.12)
    assert not _fit_next_smartcal([ep], Mock(), _settings(gui_NEXT_calib_lids_brows=False))
    assert ep._next_smartcal_w is None


def test_clamp_keeps_in_bound_and_mirrored_fits_unchanged():
    assert clamp_next_smartcal_transform([1.5, 0.0, 0.0, 2.0], [0.1, 0.0])[2] is False
    assert clamp_next_smartcal_transform([4.0, 0.0, 0.0, -4.0], [0.0, 0.0])[2] is False
    w, b, clamped = clamp_next_smartcal_transform([1.2, 0.0, 0.0, 4.0], [0.0, 0.4])
    assert clamped and w == pytest.approx([1.2, 0.0, 0.0, _SMARTCAL_MAX_GAIN]) and b == pytest.approx([0.0, 0.3])
