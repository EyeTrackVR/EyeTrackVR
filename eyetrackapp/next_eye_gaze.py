"""
NEXT per-eye gaze modes (for strabismus / amblyopia).

The shared Hybrid model outputs one fused gaze [6:8] plus a monocular gaze per
eye [8:12] (gaze_x_l, gaze_y_l, gaze_x_r, gaze_y_r). Each monocular value is a
pure function of that eye's own image, measured on held-out people: pairing a
left image with a right image of a different fixation leaves each per-eye
output bit-identical, with no pull toward the other eye's target. The fused
gaze, by contrast, averages the two eyes (about half of each), so an eye that
does not point at the target drags the fused gaze halfway with it.

gui_NEXT_gaze_mode picks what the avatar eyes get:

    fused        both eyes get the fused gaze (default, the original behaviour)
    independent  each avatar eye follows its own monocular gaze, so a real
                 deviation (cross-eyed, lazy eye) shows on the avatar
    dominant     both avatar eyes follow the monocular gaze of
                 gui_NEXT_dominant_eye, for users who want accurate gaze
                 instead of a mirrored deviation

The monocular gaze of an eye that is unusable in a pass (black-frame sentinel,
or clearly closed while the other is open) is rebuilt from the other eye plus
the left/right offset last seen while both eyes were open, so the sentinel's
zeros never reach the filters and a wink or a camera hiccup keeps the user's
deviation instead of snapping the eyes together. In a normal pass with both
eyes open the per-eye values pass through untouched.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import math

import numpy as np

from eye import EyeId

GAZE_MODE_FUSED = "fused"
GAZE_MODE_INDEPENDENT = "independent"
GAZE_MODE_DOMINANT = "dominant"
GAZE_MODES = (GAZE_MODE_FUSED, GAZE_MODE_INDEPENDENT, GAZE_MODE_DOMINANT)
DOMINANT_EYES = ("left", "right")

# Eyelid aperture (raw model eyelid) over which an eye's own gaze hands over to
# the rebuilt one: below CLOSED it is fully rebuilt from the open eye, above
# OPEN it is its own. Only the less open eye is ever rebuilt; a bilateral
# blink keeps both own values, which is what the model is trained to do.
LID_CLOSED = 0.15
LID_OPEN = 0.40
# Time constant of the left/right offset kept for rebuilding. Long enough to
# average out per-frame monocular noise, short enough to follow a deviation
# that changes with gaze direction.
OFFSET_TAU_S = 0.3
# Output openness over which vertical gaze stops being trusted (SquintYHold):
# below HOLD_BELOW it is held, above TRUST_ABOVE it passes through untouched.
SQUINT_HOLD_BELOW = 0.20
SQUINT_TRUST_ABOVE = 0.50
# How fast the held value follows the gaze anyway: a blink barely moves it, a
# long squint or naturally narrow eyes can't freeze the avatar's eyes for good.
SQUINT_RELEASE_TAU_S = 1.5


def gaze_mode_from_settings(settings) -> str:
    mode = str(getattr(settings, "gui_NEXT_gaze_mode", GAZE_MODE_FUSED) or GAZE_MODE_FUSED).lower()
    return mode if mode in GAZE_MODES else GAZE_MODE_FUSED


def dominant_eye_from_settings(settings):
    side = str(getattr(settings, "gui_NEXT_dominant_eye", "left") or "left").lower()
    return EyeId.RIGHT if side == "right" else EyeId.LEFT


def select_eye_gaze(eye_gaze, eye_id, mode: str, dominant):
    """(gaze_x, gaze_y) one avatar eye gets from a per-eye 4-vector
    [x_l, y_l, x_r, y_r] under a non-fused mode."""
    source = dominant if mode == GAZE_MODE_DOMINANT else eye_id
    base = 2 if source == EyeId.RIGHT else 0
    return float(eye_gaze[base]), float(eye_gaze[base + 1])


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


class SquintYHold:
    """Holds vertical gaze while the lids cover the pupil. The upper lid hides
    what vertical gaze is read from first, so the output can follow the lid
    instead of the eye. Gaze fades towards its last trusted value as the eye
    closes rather than towards a limit: looking up while squinting is real, and
    a lid dragging gaze down isn't stopped by a ceiling. Horizontal gaze stays
    readable from the visible iris and is left alone."""

    def __init__(self):
        self._held = None
        self._last_t = None

    def apply(self, y: float, openness: float, now: float) -> float:
        trust = _smoothstep(SQUINT_HOLD_BELOW, SQUINT_TRUST_ABOVE, openness)
        dt = 0.0 if self._last_t is None else max(0.0, now - self._last_t)
        self._last_t = now
        if self._held is None or trust >= 1.0:
            self._held = y
            return y
        self._held += (y - self._held) * (1.0 - math.exp(-dt / SQUINT_RELEASE_TAU_S))
        return self._held + trust * (y - self._held)


class PerEyeGaze:
    """Rebuilds unusable eyes in the per-eye gaze channels of one shared
    model. One instance per model session, stepped once per pass."""

    def __init__(self):
        self.offset = None  # smoothed (left - right), np.ndarray(2)
        self.last = None  # last returned 4-vector
        self._last_ts = None

    def reset(self) -> None:
        self.offset = None
        self.last = None
        self._last_ts = None

    def update(self, eye_gaze, valid_l: bool, valid_r: bool, lid_l: float, lid_r: float, now: float) -> np.ndarray:
        """Per-eye gaze [x_l, y_l, x_r, y_r] for one pass, in the app's axes."""
        g = np.asarray(eye_gaze, dtype=np.float64)
        left, right = g[0:2].copy(), g[2:4].copy()
        dt = 0.0 if self._last_ts is None else min(1.0, max(0.0, now - self._last_ts))
        self._last_ts = now

        if not (valid_l or valid_r):
            if self.last is None:
                self.last = np.zeros(4, dtype=np.float32)
            return self.last.copy()

        rel_l = _smoothstep(LID_CLOSED, LID_OPEN, float(lid_l)) if valid_l else 0.0
        rel_r = _smoothstep(LID_CLOSED, LID_OPEN, float(lid_r)) if valid_r else 0.0
        if valid_l and valid_r and rel_l >= 1.0 and rel_r >= 1.0:
            diff = left - right
            if self.offset is None:
                self.offset = diff
            else:
                self.offset = self.offset + (diff - self.offset) * (1.0 - math.exp(-dt / OFFSET_TAU_S))

        # The more open (or only) eye keeps its own gaze; the other blends
        # toward the rebuilt one by how closed it is. Every present eye closed:
        # own values (a missing eye is still rebuilt from the present one).
        top = max(rel_l, rel_r)
        if top > 0.0:
            rel_l, rel_r = rel_l / top, rel_r / top
        else:
            rel_l, rel_r = float(valid_l), float(valid_r)
        offset = self.offset if self.offset is not None else np.zeros(2)
        out_l = rel_l * left + (1.0 - rel_l) * (right + offset)
        out_r = rel_r * right + (1.0 - rel_r) * (left - offset)
        self.last = np.clip(np.concatenate((out_l, out_r)), -1.0, 1.0).astype(np.float32)
        return self.last.copy()
