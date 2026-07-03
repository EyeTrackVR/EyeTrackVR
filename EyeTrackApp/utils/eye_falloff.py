"""Velocity-based eye falloff: when the two calibrated eye outputs diverge
beyond ``gui_eye_dominant_diff_thresh``, mirror the more stable eye's gaze
to both sides instead of letting a jittery off-axis eye drag the OSC output.

Divergence is measured as the Euclidean distance between the two calibrated
eye outputs in normalised gaze space ([-1, 1]^2).  When divergence exceeds
the configured threshold, the eye with the lower smoothed velocity is elected
the "stable" eye and its gaze is mirrored to both outputs.

A latch with hysteresis prevents rapid toggling near the threshold:
  • Enter mirror mode when dist > thresh.
  • The elected stable eye is committed for the full divergence event.
  • Exit mirror mode only when dist drops back below thresh × HYSTERESIS_RECOVER.

A per-eye per-region EMA noise map (11×11 grid) breaks velocity ties in
areas where one camera placement is consistently noisier; it fills in within
a few minutes of normal use.
"""

from __future__ import annotations

import math
import time

from eye import EyeId

_GRID = 11
_INV_CELL = _GRID / 2.0
_EMA_ALPHA = 0.03
_MIN_SAMPLES = 8
_NOISE_RATIO = 1.8
_NOISE_ABS_FLOOR = 0.05

# Exit mirror mode only once divergence drops to this fraction of the threshold.
_HYSTERESIS_RECOVER = 0.7

_noise: dict = {}
_counts: dict = {}
_last_stash: dict = {}

# Shared latch across both eye threads.
# None  = independent mode.
# EyeId = this eye's output is being mirrored to both sides.
_latched_eye: EyeId | None = None


def _bin(value: float) -> int:
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


def _pick_stable_eye(var, mid_x: float, mid_y: float) -> EyeId:
    """Return whichever eye has lower recent instability at the gaze midpoint.

    Instability score = smoothed calibrated-output velocity
                      + normalised raw keypoint jitter.

    The keypoint jitter term is self-computed confidence: jittery pupil
    detection (high frame-to-frame displacement of the raw cx/cy keypoint
    relative to the ROI size) signals an unreliable tracker even if the
    calibrated output hasn't diverged much yet.  The noise-map check runs
    first and overrides when one region is consistently noisier.
    """
    l_noise, l_n = _noise_at(EyeId.LEFT, mid_x, mid_y)
    r_noise, r_n = _noise_at(EyeId.RIGHT, mid_x, mid_y)
    if l_n >= _MIN_SAMPLES and r_n >= _MIN_SAMPLES:
        if l_noise > _NOISE_ABS_FLOOR and l_noise > r_noise * _NOISE_RATIO:
            return EyeId.RIGHT
        if r_noise > _NOISE_ABS_FLOOR and r_noise > l_noise * _NOISE_RATIO:
            return EyeId.LEFT
    l_score = var.l_eye_velocity + getattr(var, "l_keypoint_noise", 0.0)
    r_score = var.r_eye_velocity + getattr(var, "r_keypoint_noise", 0.0)
    return EyeId.LEFT if l_score <= r_score else EyeId.RIGHT


def _mirror(stable_eye: EyeId, var):
    if stable_eye == EyeId.LEFT:
        return var.l_eye_x, var.left_y
    return var.r_eye_x, var.right_y


def velocity_falloff(self, var, out_x, out_y, inst_velocity: float = 0.0):
    global _latched_eye

    settings = self.settings
    if not (
        settings.gui_right_eye_dominant
        or settings.gui_left_eye_dominant
        or settings.gui_outer_side_falloff
    ):
        return out_x, out_y

    eye_id = self.eye_id
    now = time.monotonic()

    _CLOSED = 0.25
    l_open = getattr(var, "l_eye_openness", 1.0)
    r_open = getattr(var, "r_eye_openness", 1.0)
    this_open = l_open if eye_id == EyeId.LEFT else r_open
    other_open = r_open if eye_id == EyeId.LEFT else l_open

    # Stash this eye's last valid (open) position so cross-eye comparisons
    # use real gaze rather than a blink-distorted snapshot.
    if this_open >= _CLOSED:
        if eye_id == EyeId.LEFT:
            var.l_eye_x = out_x
            var.left_y = out_y
        elif eye_id == EyeId.RIGHT:
            var.r_eye_x = out_x
            var.right_y = out_y
    _last_stash[eye_id] = now

    # Single-eye mode guard: if the other eye hasn't updated in 0.5 s its
    # stash is stale and comparing against it would be meaningless.
    other_id = EyeId.RIGHT if eye_id == EyeId.LEFT else EyeId.LEFT
    if now - _last_stash.get(other_id, 0.0) > 0.5:
        return out_x, out_y

    # Blink fallback: one eye closed, other open → mirror the open eye.
    if this_open < _CLOSED and other_open >= _CLOSED:
        if eye_id == EyeId.LEFT:
            var.l_eye_velocity = max(var.l_eye_velocity, var.r_eye_velocity * 2.0 + 0.5)
            return var.r_eye_x, var.right_y
        else:
            var.r_eye_velocity = max(var.r_eye_velocity, var.l_eye_velocity * 2.0 + 0.5)
            return var.l_eye_x, var.left_y

    dx = var.l_eye_x - var.r_eye_x
    dy = var.left_y - var.right_y
    dist = math.sqrt(dx * dx + dy * dy)
    thresh = settings.gui_eye_dominant_diff_thresh

    # Both eyes agree and no active latch → independent tracking, no work to do.
    if dist <= thresh and _latched_eye is None:
        return out_x, out_y

    # Hard overrides: explicit user intent, wins over adaptive logic.
    if settings.gui_right_eye_dominant:
        _latched_eye = None
        return var.r_eye_x, var.right_y
    if settings.gui_left_eye_dominant:
        _latched_eye = None
        return var.l_eye_x, var.left_y

    # ── Outer-side falloff ────────────────────────────────────────────────────
    mid_x = (var.l_eye_x + var.r_eye_x) * 0.5
    mid_y = (var.left_y + var.right_y) * 0.5

    if dist > thresh:
        _update_noise(eye_id, mid_x, mid_y, inst_velocity)

        # Elect the stable eye once per divergence event and commit to it.
        if _latched_eye is None:
            _latched_eye = _pick_stable_eye(var, mid_x, mid_y)

        return _mirror(_latched_eye, var)

    # dist <= thresh but latch is active: convergence with hysteresis.
    if dist < thresh * _HYSTERESIS_RECOVER:
        # Divergence has fully recovered; return to independent tracking.
        _latched_eye = None
        return out_x, out_y

    # Hysteresis zone: continue mirroring until distance drops cleanly.
    return _mirror(_latched_eye, var)
