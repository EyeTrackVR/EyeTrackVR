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
    SMARTCAL_SPACE_ANGLE,
    _fit_errors_deg,
    _dot_medians,
    _drop_inconsistent_dots,
    _heldout_errors_deg,
    _fit_next_smartcal,
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


def _fit(raw_by_dot, gaze_range=None, settings=SETTINGS, layout=NEXT_SMARTCAL_DOTS):
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
    default = next_smartcal_dot_tangents()
    assert default[0] == pytest.approx((0.0, 0.8 * math.tan(math.radians(15.0))))
    assert default[7] == pytest.approx((0.0, -0.42 * math.tan(math.radians(40.0))))
    assert default[10] == (0.0, 0.0)
    narrow = next_smartcal_dot_tangents(parse_overlay_gaze_range(NARROW_LINE))
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
    tangents = next_smartcal_dot_tangents()
    ep = _fit({dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))})
    assert ep._next_smartcal_warp == SMARTCAL_SPACE_ANGLE == ep.config.next_smartcal_warp
    for yaw, pitch in [(0.0, 0.0), (20.0, 10.0), (-25.0, -30.0), (5.0, -3.0), (-12.0, 14.0)]:
        raw = _model(math.tan(math.radians(yaw)), math.tan(math.radians(pitch)))
        assert _angles(ep, raw) == pytest.approx([yaw, pitch], abs=1e-6)


def test_output_gaze_is_the_angle_as_a_fraction_of_the_limits():
    tangents = next_smartcal_dot_tangents()
    ep = _fit({dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))})

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
    tangents = next_smartcal_dot_tangents(gaze_range)
    raw = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
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
    tangents = next_smartcal_dot_tangents()
    raw = {dot: (1.3 * tangents[dot][0], 0.9 * tangents[dot][1]) for dot in range(len(NEXT_SMARTCAL_DOTS) - 1)}
    ep = _fit(raw)
    assert ep._next_smartcal_w[5] == ep._next_smartcal_w[3]
    assert _angles(ep, (0.0, 0.0)) == pytest.approx([0.0, 0.0], abs=1e-6)


def test_real_fused_capture_lands_on_its_dots():
    ep = _fit(dict(enumerate(FUSED_CAPTURE)))
    errors = _fit_errors_deg(ep._next_smartcal_w, ep._next_smartcal_b, _dot_medians(ep), next_smartcal_dot_tangents())
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
    tangents = next_smartcal_dot_tangents()
    exact = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    assert np.abs(_heldout_errors_deg(exact, tangents, NEXT_SMARTCAL_DOTS)).max() < 1e-6

    ep = _fit(dict(enumerate(FUSED_CAPTURE)))
    medians = _dot_medians(ep)
    fit = np.hypot(*_fit_errors_deg(ep._next_smartcal_w, ep._next_smartcal_b, medians, tangents).T)
    heldout = np.hypot(*_heldout_errors_deg(medians, tangents, NEXT_SMARTCAL_DOTS).T)
    # A fit bends towards its own dots, so it misses them by less than a fit
    # that never saw them.
    assert heldout.mean() > fit.mean()
    assert np.isfinite(heldout).all()


def test_a_dot_the_user_did_not_look_at_is_dropped():
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    raw[2] = (raw[2][0] + 0.35, raw[2][1] + 0.25)  # looked somewhere else
    kept, dropped = _drop_inconsistent_dots(raw, tangents, NEXT_SMARTCAL_DOTS)
    assert [dot for dot, _ in dropped] == [2] and 2 not in kept

    ep = _fit(raw)
    looking = _model(math.tan(math.radians(20.0)), math.tan(math.radians(-25.0)))
    assert _angles(ep, looking) == pytest.approx([20.0, -25.0], abs=1e-6)


def test_the_centre_dot_and_consistent_captures_are_kept():
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    raw[10] = (raw[10][0] + 0.3, raw[10][1])
    assert 10 in _drop_inconsistent_dots(raw, tangents, NEXT_SMARTCAL_DOTS)[0]
    for capture in (FUSED_CAPTURE, MONOCULAR_CAPTURE):
        assert not _drop_inconsistent_dots(dict(enumerate(capture)), tangents, NEXT_SMARTCAL_DOTS)[1]


def test_dropping_stops_at_the_minimum_number_of_dots():
    rng = np.random.default_rng(3)
    raw = {dot: tuple(rng.uniform(-0.6, 0.6, 2)) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    kept, dropped = _drop_inconsistent_dots(raw, next_smartcal_dot_tangents(), NEXT_SMARTCAL_DOTS)
    assert len(dropped) <= 3 and len(kept) >= 6


def test_inconsistent_captures_are_rejected():
    rng = np.random.default_rng(3)
    ep = _processor({dot: tuple(rng.uniform(-0.6, 0.6, 2)) for dot in range(len(NEXT_SMARTCAL_DOTS))})
    assert not _fit_next_smartcal([ep], Mock(), SETTINGS)
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
