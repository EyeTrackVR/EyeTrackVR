"""Per-eye NEXT gaze modes (next_eye_gaze; strabismus / amblyopia): fused
stays untouched, independent and dominant follow the Hybrid's monocular gaze
[8:12], a missing or closed eye is rebuilt from the other, Smart Calib keeps a
real deviation between the eyes, and the squint Y hold. The processor side
(routing, recenter) is in test_next_processing."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from eye import EyeId
from next_eye_gaze import (
    GAZE_MODE_DOMINANT,
    GAZE_MODE_FUSED,
    GAZE_MODE_INDEPENDENT,
    LID_CLOSED,
    PerEyeGaze,
    SQUINT_HOLD_BELOW,
    SQUINT_TRUST_ABOVE,
    SquintYHold,
    dominant_eye_from_settings,
    gaze_mode_from_settings,
    select_eye_gaze,
)
from next_smartcal import (
    NEXT_SMARTCAL_DOTS,
    _SMARTCAL_ANGLE_REF,
    _SMARTCAL_MAX_GAIN,
    _fit_next_smartcal,
    clamp_next_smartcal_transform,
    next_smartcal_apply,
    next_smartcal_dot_tangents,
)

STEP_S = 1.0 / 60.0
# Esotropia-like right eye: points 0.2 further toward +x than the left.
DEVIATION = np.array([0.2, 0.0])


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


# ── Smart Calib ──────────────────────────────────────────────────────────────


def _calib_processor(eye, deviation, gain=0.6):
    """Samples of an eye that under-reads by ``gain`` and points ``deviation``
    away from every dot (a real strabismus, not a tracking error)."""
    targets = next_smartcal_dot_tangents()
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
    # In output-normalised units, which is what the gain bound is in.
    w = np.array(ep._next_smartcal_w[:4]) / _SMARTCAL_ANGLE_REF
    return float(np.linalg.svd(w.reshape(2, 2), compute_uv=False)[0])


def test_smart_calib_clamps_a_moderately_under_reading_model():
    # A tiny model reading 0.25x needs 4x: clamped to the gain bound, not dropped.
    ep = _calib_processor(EyeId.LEFT, (0.0, 0.0), gain=0.25 * _SMARTCAL_ANGLE_REF)
    assert _fit_next_smartcal([ep], Mock(), _settings(gui_NEXT_calib_lids_brows=False))
    assert _max_gain(ep) == pytest.approx(_SMARTCAL_MAX_GAIN)


def test_smart_calib_still_rejects_a_wildly_over_gained_fit():
    # 0.12x needs ~8x, past the clamp factor: treated as degenerate.
    ep = _calib_processor(EyeId.LEFT, (0.0, 0.0), gain=0.12 * _SMARTCAL_ANGLE_REF)
    assert not _fit_next_smartcal([ep], Mock(), _settings(gui_NEXT_calib_lids_brows=False))
    assert ep._next_smartcal_w is None


def test_clamp_keeps_in_bound_and_mirrored_fits_unchanged():
    assert clamp_next_smartcal_transform([1.5, 0.0, 0.0, 2.0], [0.1, 0.0])[2] is False
    assert clamp_next_smartcal_transform([4.0, 0.0, 0.0, -4.0], [0.0, 0.0])[2] is False
    w, b, clamped = clamp_next_smartcal_transform([1.2, 0.0, 0.0, 4.0], [0.0, 0.4])
    assert clamped and w == pytest.approx([1.2, 0.0, 0.0, _SMARTCAL_MAX_GAIN]) and b == pytest.approx([0.0, 0.3])


# ── Squint Y hold ─────────────────────────────────────────────────────────────


def test_squint_hold_passes_gaze_through_while_the_eye_is_open():
    hold = SquintYHold()
    assert hold.apply(0.4, 0.75, 0.0) == 0.4
    assert hold.apply(-0.2, SQUINT_TRUST_ABOVE, 0.01) == -0.2


def test_squint_hold_keeps_the_last_trusted_gaze_while_closed():
    hold = SquintYHold()
    hold.apply(0.3, 0.75, 0.0)
    # A blink is far shorter than the release: the lid's pull never shows.
    assert hold.apply(-0.9, 0.0, 0.05) == pytest.approx(0.3, abs=0.05)


def test_squint_hold_fades_between_trusted_and_held():
    hold = SquintYHold()
    hold.apply(0.0, 0.75, 0.0)
    middle = 0.5 * (SQUINT_HOLD_BELOW + SQUINT_TRUST_ABOVE)
    assert 0.3 < hold.apply(1.0, middle, 0.0) < 0.7


def test_long_squint_still_follows_slowly():
    hold = SquintYHold()
    hold.apply(0.0, 0.75, 0.0)
    y = 0.0
    for step in range(1, 1001):
        y = hold.apply(1.0, 0.0, step * 0.01)
    assert y == pytest.approx(1.0, abs=0.01)


def test_squint_hold_does_not_prefer_a_direction():
    up, down = SquintYHold(), SquintYHold()
    up.apply(0.5, 0.75, 0.0)
    down.apply(-0.5, 0.75, 0.0)
    assert up.apply(0.0, 0.0, 0.01) == pytest.approx(0.5, abs=0.01)
    assert down.apply(0.0, 0.0, 0.01) == pytest.approx(-0.5, abs=0.01)
