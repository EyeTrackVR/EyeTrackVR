"""Velocity-based eye falloff: when the two eyes disagree on where the user is
looking (by more than ``gui_eye_dominant_diff_thresh``), mirror the *cleaner*
eye's position to both sides instead of letting a jittery off-axis eye drag
the OSC output around.

Two signals drive the mirror decision:

  1. Per-frame velocity. The eye with the LOWER smoothed velocity is the one
     holding gaze; the higher-velocity one is the one whose tracker is
     thrashing. Picking the lower-velocity eye is the historical intent — the
     previous implementation had the comparison inverted (and the velocities
     it compared were always 0.0, see osc_calibrate_filter.py).

  2. A per-eye, per-region noise map. Some camera placements consistently
     fail in certain gaze zones (e.g. the right eye goes blind when looking
     far left because the iris hits the eyelid). We accumulate an EMA of the
     instantaneous velocity per gaze-bin per eye. When the two eyes diverge,
     if one eye has a meaningfully higher noise in the current bin we trust
     the other eye. The bin lookup is O(1) and the update is two scalar EMA
     writes per frame — negligible.

The noise map is intentionally coarse (an 11x11 grid over [-1, 1]^2) so it
fills in within a few minutes of normal use; finer grids would take longer
to populate and add no precision the downstream OSC pipeline can use.
"""

from __future__ import annotations

import math

from eye import EyeId

# Grid resolution over normalized gaze in [-1, 1]^2.
_GRID = 11
_INV_CELL = _GRID / 2.0  # multiplier for (gaze + 1) -> cell index
# EMA weight per sample. Slow enough to filter out single saccades but fast
# enough that a user's first few minutes establish the map.
_EMA_ALPHA = 0.03
# How many samples we need in a bin before we trust its noise estimate.
_MIN_SAMPLES = 8
# An eye's noise must exceed the other's by this factor (and the absolute
# floor below) before we mirror on the basis of the noise map alone.
_NOISE_RATIO = 1.8
_NOISE_ABS_FLOOR = 0.05

# Per-eye state: noise[eye] -> 2D list of EMA values, counts[eye] -> 2D list
# of sample counts. Module-level so both eye threads update the same map
# (the whole point is cross-eye comparison). Concurrent updates race but the
# EMA is robust to occasional lost writes and we only need a slow-moving
# estimate.
_noise: dict = {}
_counts: dict = {}


def _bin(value: float) -> int:
    # Clamp to grid; gaze occasionally overshoots [-1, 1] after recenter math.
    idx = int((value + 1.0) * _INV_CELL)
    if idx < 0:
        return 0
    if idx >= _GRID:
        return _GRID - 1
    return idx


def _ensure_eye(eye_id):
    if eye_id not in _noise:
        _noise[eye_id] = [[0.0] * _GRID for _ in range(_GRID)]
        _counts[eye_id] = [[0] * _GRID for _ in range(_GRID)]


def _update_noise(eye_id, out_x, out_y, inst_velocity):
    _ensure_eye(eye_id)
    bx, by = _bin(out_x), _bin(out_y)
    cell = _noise[eye_id][bx][by]
    _noise[eye_id][bx][by] = cell + _EMA_ALPHA * (inst_velocity - cell)
    if _counts[eye_id][bx][by] < _MIN_SAMPLES * 4:
        _counts[eye_id][bx][by] += 1


def _noise_at(eye_id, x, y):
    if eye_id not in _noise:
        return 0.0, 0
    bx, by = _bin(x), _bin(y)
    return _noise[eye_id][bx][by], _counts[eye_id][bx][by]


def velocity_falloff(self, var, out_x, out_y, inst_velocity: float = 0.0):
    settings = self.settings
    if not (
        settings.gui_right_eye_dominant
        or settings.gui_left_eye_dominant
        or settings.gui_outer_side_falloff
    ):
        return out_x, out_y

    eye_id = self.eye_id

    # Stash this eye's output for the OTHER eye's next call to consume. Done
    # before any mirror logic so the cross-eye comparison uses the most
    # recent paired sample.
    if eye_id == EyeId.LEFT:
        var.l_eye_x = out_x
        var.left_y = out_y
    elif eye_id == EyeId.RIGHT:
        var.r_eye_x = out_x
        var.right_y = out_y

    # Update the noise map only when both eyes appear to disagree — that's
    # when one of them is probably the noisy/clamped one. Training on every
    # frame would mix in normal saccades and wash out the asymmetry.
    # We bin by the cross-eye MIDPOINT (the user's actual gaze, roughly) so
    # both eyes' noise grids share the same region key — otherwise the
    # jittery eye's samples get smeared across many cells based on its own
    # spurious position, and the comparison at query time picks a bin where
    # one side has data and the other doesn't.
    dx = var.l_eye_x - var.r_eye_x
    dy = var.left_y - var.right_y
    dist = math.sqrt(dx * dx + dy * dy)
    if dist > settings.gui_eye_dominant_diff_thresh:
        mid_x = (var.l_eye_x + var.r_eye_x) * 0.5
        mid_y = (var.left_y + var.right_y) * 0.5
        _update_noise(eye_id, mid_x, mid_y, inst_velocity)

    if dist <= settings.gui_eye_dominant_diff_thresh:
        return out_x, out_y

    # Hard overrides win. They're explicit user intent.
    if settings.gui_right_eye_dominant:
        return var.r_eye_x, var.right_y
    if settings.gui_left_eye_dominant:
        return var.l_eye_x, var.left_y

    # Noise map preference: query both eyes' noise at the cross-eye midpoint
    # (same key used during training). If one side is reliably noisier in
    # this gaze region, mirror the other.
    mid_x = (var.l_eye_x + var.r_eye_x) * 0.5
    mid_y = (var.left_y + var.right_y) * 0.5
    l_noise, l_n = _noise_at(EyeId.LEFT, mid_x, mid_y)
    r_noise, r_n = _noise_at(EyeId.RIGHT, mid_x, mid_y)
    if l_n >= _MIN_SAMPLES and r_n >= _MIN_SAMPLES:
        if (
            l_noise > _NOISE_ABS_FLOOR
            and l_noise > r_noise * _NOISE_RATIO
        ):
            return var.r_eye_x, var.right_y
        if (
            r_noise > _NOISE_ABS_FLOOR
            and r_noise > l_noise * _NOISE_RATIO
        ):
            return var.l_eye_x, var.left_y

    # Fallback: pick the eye with the LOWER smoothed velocity. The
    # higher-velocity eye is the one currently jittering / chasing noise; the
    # lower-velocity eye is holding gaze. (The previous version compared the
    # wrong direction and used velocities that were never written — both
    # bugs masked each other into the feature being roughly inert.)
    if var.l_eye_velocity < var.r_eye_velocity:
        return var.l_eye_x, var.left_y
    return var.r_eye_x, var.right_y
