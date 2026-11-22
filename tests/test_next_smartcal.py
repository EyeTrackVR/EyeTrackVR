"""NEXT Smart Calib gaze fit: raw model gaze -> true gaze angle -> output gaze
as a fraction of the configured gaze limits."""

import math
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from eye import EyeId
from next_smartcal import (
    NEXT_SMARTCAL_DOTS,
    SMARTCAL_KEPT,
    SMARTCAL_NOT_BETTER,
    SMARTCAL_REJECTED,
    SMARTCAL_SPACE_ANGLE,
    _fit_errors_deg,
    _choose_saturation,
    _clamp_angle_transform,
    _curve_stays_in_bounds,
    _desaturate,
    _dot_medians,
    _drop_inconsistent_dots,
    _heldout_errors_deg,
    _fit_next_smartcal,
    gaze_fit_applied,
    next_smartcal_apply,
    next_smartcal_dot_tangents,
    next_smartcal_gaze,
    next_smartcal_transform_is_sane,
    parse_overlay_gaze_range,
    smartcal_tangents_to_gaze,
)
from utils.overlay_launch import OverlaySession

GAZE_RANGE_LINE = (
    "[INFO] Gaze range: centre=(0, 0) m (0° elev)  ±1.73205 m (±30°) x +0.803848/-2.5173 m "
    "(15°..-40° elev)  coverage=0.7  cap=30° lat/15° up/40° down  lens-polygons=yes  ellipse-scale=1"
)
NARROW_LINE = (
    "[INFO] Gaze range: centre=(0, 0) m (0° elev)  ±1.4 m (±25.0169°) x +0.75/-1.9 m "
    "(14.0362°..-32.3474° elev)  coverage=0.7  cap=30° lat/15° up/40° down"
)
# The overlay's old finetune table, which Smart Calib showed before the app
# placed its own dots. The recorded captures below follow it.
FINETUNE_DOTS = (
    (0.0, 0.8),
    (0.760845, 0.247214),
    (0.470228, -0.647214),
    (-0.470228, -0.647214),
    (-0.760845, 0.247214),
    (0.246870, 0.339787),
    (0.399444, -0.129787),
    (0.0, -0.42),
    (-0.399444, -0.129787),
    (-0.246870, 0.339787),
    (0.0, 0.0),
)
SETTINGS = SimpleNamespace(
    gui_NEXT_gaze_mode="fused",
    gui_NEXT_calib_lids_brows=False,
    gui_gaze_yaw_max_deg=40.0,
    gui_gaze_pitch_up_deg=15.0,
    gui_gaze_pitch_down_deg=40.0,
)

# Per-dot raw medians of two real Smart Calib runs (Quest 3, one person):
# the fused gaze, and the left eye's monocular gaze.
FUSED_CAPTURE = [
    (-0.029, 0.328),
    (0.606, 0.019),
    (0.384, -0.492),
    (-0.443, -0.508),
    (-0.611, 0.114),
    (0.183, 0.065),
    (0.367, -0.127),
    (-0.017, -0.298),
    (-0.359, -0.149),
    (-0.244, 0.209),
    (0.007, -0.003),
]
MONOCULAR_CAPTURE = [
    (0.091, 0.099),
    (0.695, -0.020),
    (0.530, -0.542),
    (-0.214, -0.505),
    (-0.525, -0.025),
    (0.320, 0.074),
    (0.408, -0.209),
    (0.009, -0.292),
    (-0.333, -0.152),
    (-0.064, 0.027),
    (0.031, 0.014),
]


def _processor(raw_by_dot, eye=EyeId.LEFT):
    return SimpleNamespace(
        eye_id=eye,
        _next_smartcal_samples={dot: [(x, y, 0.75, 0.5)] * 8 for dot, (x, y) in raw_by_dot.items()},
        config=SimpleNamespace(),
        _next_smartcal_w=None,
        _next_smartcal_b=None,
        _next_smartcal_warp=None,
    )


def _model(tan_x, tan_y, up=1.4, down=0.8, offset=(0.02, -0.03)):
    """A stand-in model: linear in the gaze tangent, but reading upward gaze
    with a different gain than downward (as the real one does)."""
    return 1.3 * tan_x + offset[0], (up if tan_y >= 0.0 else down) * tan_y + offset[1]


def _fit(raw_by_dot, gaze_range=None, settings=SETTINGS, layout=FINETUNE_DOTS):
    ep = _processor(raw_by_dot)
    assert _fit_next_smartcal([ep], Mock(), settings, gaze_range, layout)
    return ep


def _gaze(ep, raw, settings=SETTINGS):
    return next_smartcal_gaze(ep._next_smartcal_w, ep._next_smartcal_b, ep._next_smartcal_warp, *raw, settings)


def _angles(ep, raw):
    tangents = next_smartcal_apply(ep._next_smartcal_w, ep._next_smartcal_b, ep._next_smartcal_warp, *raw)
    return [math.degrees(math.atan(t)) for t in tangents]


# ── overlay geometry ─────────────────────────────────────────────────────────


def test_gaze_range_is_read_from_the_overlay_log():
    log = "EyeTrackVR Calibration Overlay 0.4.0\n" + GAZE_RANGE_LINE + "\n[INFO] Done\n"
    assert parse_overlay_gaze_range(log) == pytest.approx((30.0, 15.0, -40.0, 0.0))


def test_the_last_reported_gaze_range_wins():
    # The overlay starts on a fallback and logs again once the headset answers.
    assert parse_overlay_gaze_range(GAZE_RANGE_LINE + "\n" + NARROW_LINE)[0] == pytest.approx(25.0169)


def test_gaze_range_survives_a_mangled_degree_sign():
    mangled = GAZE_RANGE_LINE.encode("utf-8").decode("cp1252")
    assert parse_overlay_gaze_range(mangled) == pytest.approx((30.0, 15.0, -40.0, 0.0))


@pytest.mark.parametrize("log", ["", None, "[INFO] Done", GAZE_RANGE_LINE.replace("±30°", "±300°")])
def test_an_unusable_gaze_range_is_ignored(log):
    assert parse_overlay_gaze_range(log) is None


def test_dot_tangents_follow_the_overlay_range():
    default = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    assert default[0] == pytest.approx((0.0, 0.8 * math.tan(math.radians(15.0))))
    assert default[7] == pytest.approx((0.0, -0.42 * math.tan(math.radians(40.0))))
    assert default[10] == (0.0, 0.0)
    narrow = next_smartcal_dot_tangents(parse_overlay_gaze_range(NARROW_LINE), FINETUNE_DOTS)
    assert narrow[1][0] == pytest.approx(0.760845 * 1.4 / 3.0, rel=1e-4)
    assert narrow[7][1] == pytest.approx(-0.42 * 1.9 / 3.0, rel=1e-4)


def test_overlay_session_log_text_reads_the_run_log(tmp_path):
    session = OverlaySession("finetune")
    log = tmp_path / "calibration-overlay.log"
    log.write_text(GAZE_RANGE_LINE, encoding="utf-8")
    with open(log, encoding="utf-8") as handle:
        session._log = handle
        assert parse_overlay_gaze_range(session.log_text()) is not None
        session._started_wall = log.stat().st_mtime + 60.0  # a log from before this run
        assert session.log_text() == ""


# ── the fit ──────────────────────────────────────────────────────────────────


def test_fit_recovers_true_angles_from_a_model_with_unequal_up_and_down_gain():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    ep = _fit({dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))})
    assert ep._next_smartcal_warp == SMARTCAL_SPACE_ANGLE == ep.config.next_smartcal_warp
    for yaw, pitch in [(0.0, 0.0), (20.0, 10.0), (-25.0, -30.0), (5.0, -3.0), (-12.0, 14.0)]:
        raw = _model(math.tan(math.radians(yaw)), math.tan(math.radians(pitch)))
        assert _angles(ep, raw) == pytest.approx([yaw, pitch], abs=1e-6)


def test_output_gaze_is_the_angle_as_a_fraction_of_the_limits():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    ep = _fit({dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))})

    def looking(yaw, pitch, settings=SETTINGS):
        return _gaze(ep, _model(math.tan(math.radians(yaw)), math.tan(math.radians(pitch))), settings)

    assert looking(40.0, 15.0) == pytest.approx((1.0, 1.0))
    assert looking(-40.0, -40.0) == pytest.approx((-1.0, -1.0))
    assert looking(20.0, -10.0) == pytest.approx(
        (
            math.tan(math.radians(20.0)) / math.tan(math.radians(40.0)),
            -math.tan(math.radians(10.0)) / math.tan(math.radians(40.0)),
        )
    )
    # Past the limit is reported as such (foveation follows it); callers clip.
    assert looking(0.0, 25.0)[1] > 1.5
    # Another limit rescales the output of the same fit: no recalibration.
    wide = SimpleNamespace(**{**vars(SETTINGS), "gui_gaze_yaw_max_deg": 45.0, "gui_gaze_pitch_up_deg": 25.0})
    assert looking(45.0, 25.0, wide) == pytest.approx((1.0, 1.0))


def test_fit_uses_the_range_the_overlay_really_drew():
    # On a narrow headset the same dots sit at smaller angles.
    gaze_range = parse_overlay_gaze_range(NARROW_LINE)
    tangents = next_smartcal_dot_tangents(gaze_range, FINETUNE_DOTS)
    raw = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    looking_right = _model(math.tan(math.radians(20.0)), 0.0)
    assert _angles(_fit(raw, gaze_range), looking_right) == pytest.approx([20.0, 0.0], abs=1e-6)
    assert _angles(_fit(raw), looking_right)[0] > 23.0  # assuming the default range overshoots


def test_fit_takes_any_layout_and_shares_the_centre_weight_between_centre_visits():
    layout = ((0.0, 0.0), (-0.5, 0.0), (0.0, 0.5), (0.5, 0.0), (0.0, -0.5), (-0.9, 0.0), (0.0, 0.9), (0.9, 0.0))
    layout += ((0.0, -0.9), (0.4, 0.4), (-0.4, -0.4), (0.0, 0.0))
    tangents = next_smartcal_dot_tangents(layout=layout)
    raw = {dot: _model(*tangents[dot]) for dot in range(len(layout))}
    ep = _fit(raw, layout=layout)
    for yaw, pitch in [(0.0, 0.0), (20.0, 10.0), (-25.0, -30.0)]:
        looking = _model(math.tan(math.radians(yaw)), math.tan(math.radians(pitch)))
        assert _angles(ep, looking) == pytest.approx([yaw, pitch], abs=1e-6)


def test_without_the_centre_dot_one_vertical_gain_serves_both_directions():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    raw = {dot: (1.3 * tangents[dot][0], 0.9 * tangents[dot][1]) for dot in range(len(FINETUNE_DOTS) - 1)}
    ep = _fit(raw)
    assert ep._next_smartcal_w[5] == ep._next_smartcal_w[3]
    assert _angles(ep, (0.0, 0.0)) == pytest.approx([0.0, 0.0], abs=1e-6)


def test_real_fused_capture_lands_on_its_dots():
    ep = _fit(dict(enumerate(FUSED_CAPTURE)))
    errors = _fit_errors_deg(
        ep._next_smartcal_w,
        ep._next_smartcal_b,
        _dot_medians(ep, len(FINETUNE_DOTS)),
        next_smartcal_dot_tangents(layout=FINETUNE_DOTS),
    )
    yaw_rms, pitch_rms = np.sqrt((errors**2).mean(axis=0))
    # A single vertical gain left 2.0 deg pitch rms and the centre 1.3 deg up.
    assert yaw_rms < 1.2 and pitch_rms < 1.7
    assert np.hypot(*errors[10]) < 1.0
    assert abs(errors[0][1]) < 1.5  # top dot, was 2.8 deg low


def test_real_monocular_capture_still_fits():
    ep = _fit(dict(enumerate(MONOCULAR_CAPTURE)))
    assert next_smartcal_transform_is_sane(ep._next_smartcal_w, ep._next_smartcal_b, ep._next_smartcal_warp)
    assert 0.0 < ep._next_smartcal_w[5]


def test_held_out_error_is_honest_about_noise():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    exact = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    assert np.abs(_heldout_errors_deg(exact, tangents, FINETUNE_DOTS)).max() < 1e-6

    ep = _fit(dict(enumerate(FUSED_CAPTURE)))
    medians = _dot_medians(ep, len(FINETUNE_DOTS))
    fit = np.hypot(*_fit_errors_deg(ep._next_smartcal_w, ep._next_smartcal_b, medians, tangents).T)
    heldout = np.hypot(*_heldout_errors_deg(medians, tangents, FINETUNE_DOTS).T)
    # A fit bends towards its own dots, so it misses them by less than a fit
    # that never saw them.
    assert heldout.mean() > fit.mean()
    assert np.isfinite(heldout).all()


def test_a_dot_the_user_did_not_look_at_is_dropped():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    raw = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    raw[2] = (raw[2][0] + 0.35, raw[2][1] + 0.25)  # looked somewhere else
    kept, dropped = _drop_inconsistent_dots(raw, tangents, FINETUNE_DOTS)
    assert [dot for dot, _ in dropped] == [2] and 2 not in kept

    ep = _fit(raw)
    looking = _model(math.tan(math.radians(20.0)), math.tan(math.radians(-25.0)))
    assert _angles(ep, looking) == pytest.approx([20.0, -25.0], abs=1e-6)


def test_the_centre_dot_and_consistent_captures_are_kept():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    raw = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    raw[10] = (raw[10][0] + 0.3, raw[10][1])
    assert 10 in _drop_inconsistent_dots(raw, tangents, FINETUNE_DOTS)[0]
    for capture in (FUSED_CAPTURE, MONOCULAR_CAPTURE):
        assert not _drop_inconsistent_dots(dict(enumerate(capture)), tangents, FINETUNE_DOTS)[1]


def test_one_of_two_centre_visits_can_be_dropped():
    # The first centre capture caught the gaze still on the instruction text.
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    raw[0] = (raw[0][0], raw[0][1] - 0.35)
    kept, dropped = _drop_inconsistent_dots(raw, tangents, NEXT_SMARTCAL_DOTS)
    assert [dot for dot, _ in dropped] == [0] and len(NEXT_SMARTCAL_DOTS) - 1 in kept


def test_a_dot_without_a_gaze_reading_is_left_out_instead_of_sinking_the_fit():
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    raw[9] = (math.nan, 0.1)
    results = []
    ep = _processor(raw)
    assert _fit_next_smartcal([ep], Mock(), SETTINGS, None, NEXT_SMARTCAL_DOTS, results)
    assert 9 not in _dot_medians(ep) and results[0].dots_used == len(NEXT_SMARTCAL_DOTS) - 1
    assert _angles(ep, _model(0.3, -0.2)) == pytest.approx(np.degrees(np.arctan([0.3, -0.2])), abs=1e-6)
    # Such dots count as not captured: too few of the rest is no fit.
    few = {dot: (math.nan, math.nan) if dot > 4 else raw[dot] for dot in raw}
    results = []
    assert not _fit_next_smartcal([_processor(few)], Mock(), SETTINGS, None, NEXT_SMARTCAL_DOTS, results)
    assert results[0].reason == "too_few_dots"


def test_dropping_stops_at_the_minimum_number_of_dots():
    layout = ((0.0, 0.0), (-0.5, 0.0), (0.0, 0.5), (0.5, 0.0), (0.0, -0.5), (-0.9, 0.3), (0.9, 0.6), (0.4, -0.9))
    tangents = next_smartcal_dot_tangents(layout=layout)
    raw = {dot: _model(*tangents[dot]) for dot in range(len(layout))}
    raw[1] = (raw[1][0] + 0.35, raw[1][1] + 0.25)
    raw[6] = (raw[6][0] - 0.3, raw[6][1] + 0.3)
    kept, dropped = _drop_inconsistent_dots(raw, tangents, layout)
    # Six dots are left. Of those, dot 2 fits worst and would go next.
    assert [dot for dot, _ in dropped] == [1, 6] and sorted(kept) == [0, 2, 3, 4, 5, 7]
    errors = np.hypot(*_heldout_errors_deg(kept, tangents, layout).T)
    assert errors[1] == errors.max() > max(5.0, 3.0 * np.median(np.delete(errors, 1)))


def _noisy(raw, seed, sigma=0.02):
    rng = np.random.default_rng(seed)
    return {dot: (x + rng.normal(0, sigma), y + rng.normal(0, sigma)) for dot, (x, y) in raw.items()}


def test_a_better_current_calibration_is_kept():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    exact = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    ep = _fit(exact)
    w, b = list(ep._next_smartcal_w), list(ep._next_smartcal_b)
    ep._next_smartcal_samples = {dot: [(x, y, 0.75, 0.5)] * 8 for dot, (x, y) in _noisy(exact, 1).items()}
    assert not _fit_next_smartcal([ep], Mock(), SETTINGS, layout=FINETUNE_DOTS)
    assert (ep._next_smartcal_w, ep._next_smartcal_b) == (w, b)


def test_a_first_run_worse_than_the_uncalibrated_gaze_does_not_claim_a_previous_calibration():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    # A model that already reads the gaze right: a fit can only add its noise.
    exact = {dot: smartcal_tangents_to_gaze(*tangents[dot], SETTINGS) for dot in range(len(FINETUNE_DOTS))}
    ep = _processor(_noisy(exact, 1))
    results = []
    assert not _fit_next_smartcal([ep], Mock(), SETTINGS, layout=FINETUNE_DOTS, results=results)
    assert ep._next_smartcal_w is None
    assert results[0].outcome == SMARTCAL_NOT_BETTER and not gaze_fit_applied(results)
    assert results[0].heldout_mean > results[0].current_mean


def test_a_low_resting_lid_is_not_taken_for_blinks():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    exact = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    ep = _processor(exact)
    # The open eye reads 0.2 here; the blink in each capture reads far lower.
    ep._next_smartcal_samples = {
        dot: [(x, y, 0.2, 0.5)] * 8 + [(x + 0.5, y - 0.5, 0.03, 0.5)] * 2 for dot, (x, y) in exact.items()
    }
    assert _dot_medians(ep, len(FINETUNE_DOTS)) == pytest.approx(exact)
    assert _fit_next_smartcal([ep], Mock(), SETTINGS, layout=FINETUNE_DOTS)


def test_saving_only_lids_and_brows_does_not_count_as_a_gaze_fit():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    exact = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    ep = _fit(exact)
    w = list(ep._next_smartcal_w)
    ep._next_smartcal_samples = {dot: [(x, y, 0.6, 0.4)] * 8 for dot, (x, y) in _noisy(exact, 1).items()}
    settings = SimpleNamespace(**{**vars(SETTINGS), "gui_NEXT_calib_lids_brows": True})
    results = []
    # The lid/brow anchors are saved, so something was.
    assert _fit_next_smartcal([ep], Mock(), settings, layout=FINETUNE_DOTS, results=results)
    assert ep._next_smartcal_lid_neutral == pytest.approx(0.6) and ep._next_smartcal_w == w
    assert results[0].outcome == SMARTCAL_KEPT and not gaze_fit_applied(results)


def test_a_worse_current_calibration_is_replaced():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    exact = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    ep = _processor(_noisy(exact, 1))
    ep._next_smartcal_w, ep._next_smartcal_b = [0.7, 0.0, 0.0, 0.9, 0.0, 0.9], [0.05, -0.08]
    ep._next_smartcal_warp = SMARTCAL_SPACE_ANGLE
    assert _fit_next_smartcal([ep], Mock(), SETTINGS, layout=FINETUNE_DOTS)
    assert ep._next_smartcal_b != [0.05, -0.08]


def test_a_fit_that_cannot_be_scored_is_not_applied(monkeypatch):
    import next_smartcal

    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    exact = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    monkeypatch.setattr(next_smartcal, "_heldout_errors_deg", lambda medians, *args: np.full((len(medians), 2), np.nan))
    for fitted in (False, True):
        ep = _processor(exact)
        if fitted:
            ep._next_smartcal_w, ep._next_smartcal_b = [0.7, 0.0, 0.0, 0.9, 0.0, 0.9], [0.05, -0.08]
            ep._next_smartcal_warp = SMARTCAL_SPACE_ANGLE
        before = (ep._next_smartcal_w, ep._next_smartcal_b)
        results = []
        assert not _fit_next_smartcal([ep], Mock(), SETTINGS, layout=FINETUNE_DOTS, results=results)
        assert (ep._next_smartcal_w, ep._next_smartcal_b) == before
        assert (results[0].outcome, results[0].reason) == (SMARTCAL_REJECTED, "degenerate")
        assert results[0].heldout_mean is None and not gaze_fit_applied(results)


def test_a_current_calibration_that_reads_nothing_is_replaced():
    tangents = next_smartcal_dot_tangents(layout=FINETUNE_DOTS)
    exact = {dot: _model(*tangents[dot]) for dot in range(len(FINETUNE_DOTS))}
    ep = _processor(_noisy(exact, 1))
    ep._next_smartcal_w, ep._next_smartcal_b = [math.nan, 0.0, 0.0, 0.9, 0.0, 0.9], [0.0, 0.0]
    ep._next_smartcal_warp = SMARTCAL_SPACE_ANGLE
    results = []
    assert _fit_next_smartcal([ep], Mock(), SETTINGS, layout=FINETUNE_DOTS, results=results)
    assert gaze_fit_applied(results) and results[0].current_mean is None
    assert next_smartcal_transform_is_sane(ep._next_smartcal_w, ep._next_smartcal_b, ep._next_smartcal_warp)


def test_the_layout_shows_a_central_core_before_the_extremes():
    layout = NEXT_SMARTCAL_DOTS
    assert layout[0] == layout[-1] == (0.0, 0.0)
    radius = [math.hypot(*dot) for dot in layout]
    assert max(radius[1:9]) < 0.5 < 0.9 < min(radius[9:17]) <= max(radius[9:17]) <= 1.0
    # Symmetric, so no direction is fit on more dots than its opposite.
    assert sorted(layout) == sorted((-x, -y) for x, y in layout)


def test_the_layout_fits_without_its_extremes():
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS)) if not 9 <= dot <= 16}
    ep = _fit(raw, layout=NEXT_SMARTCAL_DOTS)
    looking = _model(math.tan(math.radians(25.0)), math.tan(math.radians(-30.0)))
    assert _angles(ep, looking) == pytest.approx([25.0, -30.0], abs=1e-6)


def _saturating(tan_x, tan_y, ceiling=0.9, gain=1.6):
    """A model whose raw output flattens towards +-ceiling, as NEXT's does."""
    return tuple(ceiling * math.tanh(gain * v / ceiling) for v in (tan_x, tan_y))


def test_a_saturating_model_is_fit_with_its_saturation_undone():
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _saturating(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    assert _choose_saturation(raw, tangents, NEXT_SMARTCAL_DOTS) == (0.9, 0.9)
    ep = _fit(raw, layout=NEXT_SMARTCAL_DOTS)
    assert ep._next_smartcal_w[6:] == [0.9, 0.9]
    # The lowest dots are just past where the undo stops following the curve
    # (test_the_saturation_undo_never_gets_steeper_than_its_limit), which
    # costs a few hundredths of a degree.
    for yaw, pitch in [(25.0, 10.0), (-28.0, -35.0), (0.0, 14.0)]:
        looking = _saturating(math.tan(math.radians(yaw)), math.tan(math.radians(pitch)))
        assert _angles(ep, looking) == pytest.approx([yaw, pitch], abs=0.1)


def test_each_axis_gets_its_own_saturation():
    tangents = next_smartcal_dot_tangents()
    raw = {
        dot: (_saturating(*tangents[dot], ceiling=0.8)[0], _saturating(*tangents[dot], ceiling=1.2)[1])
        for dot in range(len(NEXT_SMARTCAL_DOTS))
    }
    assert _choose_saturation(raw, tangents, NEXT_SMARTCAL_DOTS) == (0.8, 1.2)


def test_a_linear_model_keeps_the_straight_fit():
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    assert _choose_saturation(raw, tangents, NEXT_SMARTCAL_DOTS) == (0.0, 0.0)
    assert len(_fit(raw, layout=NEXT_SMARTCAL_DOTS)._next_smartcal_w) == 6


def test_the_saturation_undo_never_gets_steeper_than_its_limit():
    import next_smartcal

    ceiling, limit = 0.8, next_smartcal._SMARTCAL_UNDO_MAX_SLOPE
    # The plain inverse up to the knee, and the same either side of zero.
    assert _desaturate(0.4, ceiling) == pytest.approx(math.atanh(0.5))
    assert _desaturate(-0.76, ceiling) == -_desaturate(0.76, ceiling)
    assert _desaturate(0.3, 0.0) == 0.3
    # From there on a raw step never counts more than ``limit`` times what it
    # does at the centre, where the inverse was ten times as steep at 95 % of
    # the ceiling and far more beyond.
    centre = _desaturate(0.001, ceiling) / 0.001
    raws = np.linspace(0.0, 1.2, 241)
    undone = np.array([_desaturate(raw, ceiling) for raw in raws])
    slopes = np.diff(undone) / np.diff(raws)
    assert slopes.max() == pytest.approx(limit * centre, rel=1e-3)
    assert slopes[int(0.95 * ceiling / 0.005)] == pytest.approx(limit * centre, rel=1e-3)
    # No jump at the knee, and a raw gaze at or past the ceiling is still told
    # apart from one just under it.
    assert np.all(slopes > 0.0) and np.abs(np.diff(slopes)).max() < 0.2 * centre
    assert _desaturate(0.8, ceiling) < _desaturate(0.85, ceiling) < _desaturate(1.0, ceiling) < math.inf


def test_a_curve_is_checked_over_the_whole_raw_range():
    ref = math.tan(math.radians(40.0))
    gain = 1.6 * ref
    b = [0.0, 0.0]
    steep = [gain, 0.0, 0.0, gain, 0.0, gain, 0.8, 0.8]
    # Near the centre, where a curve is nearly straight, it looks like the
    # straight fit of the same gain, which is fine.
    assert next_smartcal_transform_is_sane(steep, b, SMARTCAL_SPACE_ANGLE)
    assert _curve_stays_in_bounds(steep[:6], b)
    # Further out it carries the raw gaze past anything a straight fit may.
    assert not _curve_stays_in_bounds(steep, b)
    assert _curve_stays_in_bounds([0.7, 0.0, 0.0, 1.1, 0.0, 0.6, 0.85, 1.0], [0.0, 0.01])

    # Such a curve is not among those a fit chooses from, however well it
    # would predict the dots: this model is steep and flattens early.
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _saturating(*tangents[dot], ceiling=0.8, gain=0.45) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    ep = _fit(raw, layout=NEXT_SMARTCAL_DOTS)
    assert _curve_stays_in_bounds(ep._next_smartcal_w, ep._next_smartcal_b)


def test_a_saturating_fit_is_stored_clamped_and_checked_like_a_straight_one():
    ref = math.tan(math.radians(40.0))
    w, b = [0.7, 0.0, 0.0, 1.1, 0.0, 0.6, 0.85, 1.0], [0.0, 0.01]
    assert next_smartcal_transform_is_sane(w, b, SMARTCAL_SPACE_ANGLE)
    # The straight fit is the same transform without the saturation.
    assert next_smartcal_apply(w[:6], b, SMARTCAL_SPACE_ANGLE, 0.0, 0.0) == pytest.approx(
        next_smartcal_apply(w, b, SMARTCAL_SPACE_ANGLE, 0.0, 0.0)
    )
    over = [4.0 * ref, 0.0, 0.0, 1.1, 0.0, 0.6, 0.85, 1.0]
    clamped, _, was = _clamp_angle_transform(over, b)
    assert was and clamped[6:] == [0.85, 1.0]


def test_inconsistent_captures_are_rejected():
    rng = np.random.default_rng(3)
    ep = _processor({dot: tuple(rng.uniform(-0.6, 0.6, 2)) for dot in range(len(FINETUNE_DOTS))})
    assert not _fit_next_smartcal([ep], Mock(), SETTINGS, layout=FINETUNE_DOTS)
    assert ep._next_smartcal_w is None


# ── stored transforms ────────────────────────────────────────────────────────


def test_legacy_fit_still_maps_straight_to_output_gaze():
    assert next_smartcal_gaze([2.0, 0.0, 0.0, 1.0], [0.1, -0.2], None, 0.3, 0.4, SETTINGS) == pytest.approx((0.7, 0.2))


def test_angle_fit_sanity():
    ref = math.tan(math.radians(40.0))
    assert next_smartcal_transform_is_sane([0.7, 0.0, 0.0, 1.1, 0.0, 0.6], [0.0, 0.01], SMARTCAL_SPACE_ANGLE)
    # Upward gain alone out of bounds, mirrored upward gain, wrong shape.
    assert not next_smartcal_transform_is_sane([0.7, 0.0, 0.0, 1.1, 0.0, 9.0 * ref], [0.0, 0.0], SMARTCAL_SPACE_ANGLE)
    assert not next_smartcal_transform_is_sane([0.7, 0.0, 0.0, 1.1, 0.0, -0.5], [0.0, 0.0], SMARTCAL_SPACE_ANGLE)
    assert not next_smartcal_transform_is_sane([0.7, 0.0, 0.0, 1.1], [0.0, 0.0], SMARTCAL_SPACE_ANGLE)


def test_tangents_to_gaze_defaults_without_settings():
    x, y = smartcal_tangents_to_gaze(math.tan(math.radians(40.0)), -math.tan(math.radians(40.0)), SimpleNamespace())
    assert (x, y) == pytest.approx((1.0, -1.0))
