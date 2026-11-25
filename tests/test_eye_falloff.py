"""Eye falloff / dominance (utils.eye_falloff.velocity_falloff): when the two
eyes' calibrated outputs disagree, both report the steadier eye (or the eye the
user chose), a closed eye mirrors the open one, and a latch with hysteresis
keeps the choice from flickering."""

from types import SimpleNamespace

import pytest

from eye import EyeId
from utils import eye_falloff

THRESH = 0.3


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """The latch and noise map are shared by both eye threads: start empty."""
    monkeypatch.setattr(eye_falloff, "_latched_eye", None)
    monkeypatch.setattr(eye_falloff, "_noise", {})
    monkeypatch.setattr(eye_falloff, "_counts", {})
    monkeypatch.setattr(eye_falloff, "_last_stash", {})


def _settings(outer=False, left=False, right=False):
    return SimpleNamespace(
        gui_outer_side_falloff=outer,
        gui_left_eye_dominant=left,
        gui_right_eye_dominant=right,
        gui_eye_dominant_diff_thresh=THRESH,
    )


def _var(l_vel=0.1, r_vel=0.9, l_open=1.0, r_open=1.0):
    return SimpleNamespace(
        l_eye_x=0.0,
        left_y=0.0,
        r_eye_x=0.0,
        right_y=0.0,
        l_eye_velocity=l_vel,
        r_eye_velocity=r_vel,
        l_eye_openness=l_open,
        r_eye_openness=r_open,
    )


def _out(settings, var, eye, x, y=0.0):
    return eye_falloff.velocity_falloff(SimpleNamespace(settings=settings, eye_id=eye), var, x, y)


def test_without_a_mode_each_eye_keeps_its_own_output():
    var = _var()
    _out(_settings(), var, EyeId.LEFT, 0.0)
    assert _out(_settings(), var, EyeId.RIGHT, 0.9) == (0.9, 0.0)


def test_a_single_eye_is_never_mirrored_to_a_stale_partner():
    # Only the left camera runs: nothing fresh to compare against.
    assert _out(_settings(outer=True), _var(), EyeId.LEFT, 0.8) == (0.8, 0.0)


def test_eyes_that_agree_track_independently():
    settings, var = _settings(outer=True), _var()
    _out(settings, var, EyeId.LEFT, 0.0)
    assert _out(settings, var, EyeId.RIGHT, 0.2) == (0.2, 0.0)


@pytest.mark.parametrize("left, right, chosen", [(True, False, 0.0), (False, True, 0.6)])
def test_a_dominant_eye_drives_both_once_they_disagree(left, right, chosen):
    settings, var = _settings(left=left, right=right), _var()
    _out(settings, var, EyeId.LEFT, 0.0)
    assert _out(settings, var, EyeId.RIGHT, 0.6) == (chosen, 0.0)
    assert _out(settings, var, EyeId.LEFT, 0.0) == (chosen, 0.0)


def test_a_closed_eye_mirrors_the_open_one():
    settings, var = _settings(outer=True), _var()
    _out(settings, var, EyeId.RIGHT, 0.4, 0.1)
    var.l_eye_openness = 0.1  # left lid shut: its own reading is meaningless
    assert _out(settings, var, EyeId.LEFT, -0.7, 0.9) == (0.4, 0.1)
    # ...and reads as unsteady, so it is not elected once both are open again.
    assert var.l_eye_velocity > var.r_eye_velocity


def test_outer_side_falloff_latches_the_steadier_eye_with_hysteresis():
    settings, var = _settings(outer=True), _var(l_vel=0.1, r_vel=0.9)
    _out(settings, var, EyeId.LEFT, 0.0)

    # Diverged: the steadier left eye is elected and mirrored to both.
    assert _out(settings, var, EyeId.RIGHT, 0.5) == (0.0, 0.0)
    assert _out(settings, var, EyeId.LEFT, 0.05) == (0.05, 0.0)
    # The right eye calming down mid-event does not flip the choice.
    var.l_eye_velocity, var.r_eye_velocity = 0.9, 0.1
    assert _out(settings, var, EyeId.RIGHT, 0.45) == (0.05, 0.0)
    # Back under the threshold but not by enough: still mirrored.
    assert _out(settings, var, EyeId.RIGHT, 0.05 + 0.8 * THRESH) == (0.05, 0.0)
    # Well under it: independent again.
    assert _out(settings, var, EyeId.RIGHT, 0.15) == (0.15, 0.0)
    assert eye_falloff._latched_eye is None
