"""NEXT Smart Calibration: the overlay dot sequence, fitting the per-eye gaze
transform from it, and applying that transform.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import json
import logging
import math
import re
import struct
import time
from dataclasses import asdict, dataclass, field

import numpy as np

from calibration_state import var
from next_eye_gaze import GAZE_MODE_FUSED, dominant_eye_from_settings, gaze_mode_from_settings
from utils.async_call import Async
from utils.misc_utils import PlaySound, SND_ASYNC, SND_FILENAME, resource_path
from gaze_capture import GazeTrace, open_lid
from utils.overlay_launch import (
    CMD_DOT,
    CMD_END_PASS,
    CMD_HIDE_TEXT,
    CMD_QUIT,
    CMD_START_PASS,
    CMD_TEXT,
    SIG_DOT_HELD,
    SIG_PASS_ENDED,
    SIG_PASS_RUNNING,
    SIG_READY,
    OverlaySession,
    OverlayStopped,
)

logger = logging.getLogger(__name__)


# ── NEXT Smart Calibration (overlay "interactive" mode) ──────────────────────
#
# The app shows each dot of NEXT_SMARTCAL_DOTS in turn and samples the gaze
# while the overlay holds it (see _show_dots):
#
#   0 centre, 1..8 inner ring, 9..12 the four extremes, 13..16 the top and
#   bottom edge, 17 centre again
#
# When the user fixates a dot their true gaze IS the dot's direction, so each
# dot's known angle is a regression target. We pair it with the median raw NEXT
# gaze captured while the dot was held and least-squares fit a per-eye transform
# from raw model output to TRUE GAZE ANGLE (as tangents: tan yaw, tan pitch in
# head space, +x right, +y up):
#     tan_yaw   = w11*xr + w12*yr + b1
#     tan_pitch = w21*xr + w22*yr + b2 + (w22_up - w22) * max(yr - y0, 0)
# W carries scale / roll / anisotropy, B the offset. The vertical gain has two
# values, one below and one above the centre capture y0: the model is trained
# on labels normalised to an asymmetric vertical range (a little up, a lot
# down), so its response per degree differs between up and down, and by a
# different ratio per person. One shared gain leaves the centre a degree or two
# off and the top dots several degrees off (measured on real captures: held-out
# pitch error 3.2 deg -> 2.2 deg, worst dot 7.6 deg -> 3.5 deg).
#
# Output gaze is then that angle as a fraction of the configured gaze limits
# (gui_gaze_yaw_max_deg / _pitch_up_deg / _pitch_down_deg, see
# smartcal_tangents_to_gaze): +-1 is the limit, which is exactly how the
# pyVRCFT native endpoint, the foveation outputs and the gaze preview turn
# gaze back into an angle. The stored fit is in angles, so changing a limit
# needs no recalibration.
#
# ``warp`` names the space a stored fit lives in:
#   "angle" -> the fit above. W holds [w11, w12, w21, w22, y0, w22_up], and
#              two more, the sideways and vertical saturation sx and sy, when
#              the fit first undoes the model's saturation (see
#              _SMARTCAL_SATURATIONS): xr = atanh(raw x / sx), likewise for y.
#   None    -> legacy: a plain affine straight onto output-normalised gaze
#              (W = [w11, w12, w21, w22]), saved by older builds. Still applied.
#   "atanh" -> legacy affine in arctanh(raw) space, for a model that saturates.

# arctanh blows up at +-1; clamp the raw magnitude just inside so a fully pinned
# sample maps to a large-but-finite warped value instead of inf.
_SMARTCAL_WARP_CLAMP = 0.999
SMARTCAL_SPACE_ANGLE = "angle"

# The overlay's default gaze range in degrees: lateral half-range, top and
# bottom elevation, elevation of the centre dot (fov.h max_deg / max_deg_up /
# max_deg_down / center_deg). It is what a wide-FOV headset gets; on a narrower
# one the overlay shrinks the range to what both eyes can see and says so in
# its log, which parse_overlay_gaze_range reads. These are the fallback.
_OVERLAY_GAZE_RANGE_DEFAULT = (30.0, 15.0, -40.0, 0.0)

_NUM = r"-?\d+(?:\.\d+)?(?:e[-+]?\d+)?"
_GAZE_RANGE_RE = re.compile(
    rf"Gaze range.*? m \((?P<centre>{_NUM})[^\s)]* elev\)"
    rf".*? m \([^\d)-]*(?P<yaw>{_NUM})[^\s)]*\) x "
    rf".*? m \((?P<top>{_NUM})[^\s.\d]*\.\.(?P<bottom>{_NUM})[^\s)]* elev\)"
)


def parse_overlay_gaze_range(log_text):
    """(yaw, top, bottom, centre) in degrees from the overlay's last
    "Gaze range" log line: the range the dots were really placed in on this
    headset. None when the log has no usable line."""
    found = None
    for found in _GAZE_RANGE_RE.finditer(log_text or ""):
        pass
    if found is None:
        return None
    yaw, top, bottom, centre = (float(found[k]) for k in ("yaw", "top", "bottom", "centre"))
    if not (5.0 <= yaw <= 89.0 and bottom < centre < top and -89.0 <= bottom and top <= 89.0):
        return None
    return yaw, top, bottom, centre


# The centre, a ring of eight around it at half the range, the four extremes
# at 0.95, four more along the top and bottom edge and the centre again. Normalised overlay coordinates (+-1 =
# edge of the overlay's gaze range); the angle each dot sits at comes from
# next_smartcal_dot_tangents().
#
# The inner ring comes first so that the run has a well-conditioned core
# before the extremes, where the lids can hide the pupil (looking down
# especially). A lost or inconsistent extreme is then left out of the fit
# (_drop_inconsistent_dots) instead of costing the run. The extremes reach
# further out than the old finetune table (0.95 against 0.65 to 0.8), so the
# fit measures the gain where users notice it. The top and bottom get two more
# each, so the vertical extremes are not fit from one dot alone. The second
# centre visit averages out drift over the run (see _solve_angle_fit).
NEXT_SMARTCAL_DOTS = (
    (0.0, 0.0),
    (-0.475, 0.0),
    (-0.35, 0.35),
    (0.0, 0.475),
    (0.35, 0.35),
    (0.475, 0.0),
    (0.35, -0.35),
    (0.0, -0.475),
    (-0.35, -0.35),
    (-0.95, 0.0),
    (0.0, 0.95),
    (0.95, 0.0),
    (0.0, -0.95),
    (-0.4, 0.9),
    (0.4, 0.9),
    (0.4, -0.9),
    (-0.4, -0.9),
    (0.0, 0.0),
)


def next_smartcal_dot_tangents(gaze_range=None, layout=NEXT_SMARTCAL_DOTS):
    """True direction of each overlay dot as (tan yaw, tan pitch) from straight
    ahead. The overlay places a dot linearly on a flat plane, so normalised n
    sits at tangent n * tan(range edge), with separate up and down edges about
    the centre dot's own elevation. ``gaze_range`` is parse_overlay_gaze_range's
    result; None uses the overlay defaults. ``layout`` holds the normalised dot
    positions."""
    yaw, top, bottom, centre = gaze_range or _OVERLAY_GAZE_RANGE_DEFAULT
    rx = math.tan(math.radians(yaw))
    cy = math.tan(math.radians(centre))
    ry_up = math.tan(math.radians(top)) - cy
    ry_down = cy - math.tan(math.radians(bottom))
    return [(nx * rx, cy + ny * (ry_up if ny >= 0.0 else ry_down)) for nx, ny in layout]


def _centre_dots(layout) -> list:
    """Indices of the straight-ahead dots in a layout."""
    return [dot for dot, (nx, ny) in enumerate(layout) if nx == 0.0 and ny == 0.0]


def _gaze_limit_tan(settings, name, default):
    return math.tan(math.radians(min(89.0, max(1.0, float(getattr(settings, name, default))))))


def smartcal_tangents_to_gaze(tan_x: float, tan_y: float, settings):
    """Output gaze for a true gaze direction: its tangent as a fraction of the
    configured limit on that side (not clipped). The inverse of how the
    outputs read gaze, atan(gaze * tan(limit))."""
    pitch = ("gui_gaze_pitch_up_deg", 15.0) if tan_y >= 0.0 else ("gui_gaze_pitch_down_deg", 40.0)
    return tan_x / _gaze_limit_tan(settings, "gui_gaze_yaw_max_deg", 40.0), tan_y / _gaze_limit_tan(settings, *pitch)


def smartcal_gaze_to_tangents(x: float, y: float, settings):
    """The gaze direction, as tangents, that an output gaze stands for. The
    inverse of smartcal_tangents_to_gaze."""
    pitch = ("gui_gaze_pitch_up_deg", 15.0) if y >= 0.0 else ("gui_gaze_pitch_down_deg", 40.0)
    return x * _gaze_limit_tan(settings, "gui_gaze_yaw_max_deg", 40.0), y * _gaze_limit_tan(settings, *pitch)


# Each dot is captured for this long once the gaze rests on it (see
# show_dot_and_capture). The dot stays up until then, so a slow saccade or a
# slow camera only delays the next dot instead of mixing two fixations.
NEXT_SMARTCAL_CAPTURE_WINDOW_S = 0.45
# A dot needs a few clean frames for its median to mean anything.
_SMARTCAL_MIN_SAMPLES_PER_DOT = 5
# Each output axis solves for 3 affine unknowns; require a comfortable margin
# over that minimum so a few missed dots (and ideally both rings) still leave a
# well-conditioned fit.
_SMARTCAL_MIN_DOTS = 6
# Straight-ahead is the semantic zero used by VRChat and recentering. Weight its
# per-dot median more strongly than one peripheral point so least squares cannot
# leave a visible centre offset merely to shave error off the ring.
_SMARTCAL_CENTER_WEIGHT = 6.0
# Sanity bounds for an accepted transform, in output-normalised units: an
# angle-space fit is checked as tangent / _SMARTCAL_ANGLE_REF, which is what
# +-1 meant for the fits these bounds were tuned on. The smart cal is a gentle
# per-user polish: singular values of W (direction-independent gains) must stay within
# [MIN, MAX] and orientation must be preserved (det > 0). In arctanh space a
# saturating model needs a small gain (arctanh expands the input), so the lower
# bound is looser than a raw-space affine would need. Smart calibration is only
# a per-user polish, so large gains or offsets are rejected rather than saved.
# MAX was 1.75, which rejected exactly the users who need calibration most: on
# people the shared hybrid did not train on, held-out BSB gaze_y comes out at
# ~0.39x the true movement (per-user 0.31-0.46x, consistent rather than noisy),
# so a correct fit needs ~2.2-3.2x and was thrown away for the raw, compressed
# gaze. Degenerate fits seen in the wild were 10-200x, still far above this.
_SMARTCAL_MAX_GAIN = 3.2
_SMARTCAL_MIN_GAIN = 0.08
_SMARTCAL_MAX_BIAS = 0.30
_SMARTCAL_ANGLE_REF = math.tan(math.radians(40.0))
# A consistent fit (residual guard passed) that only overshoots those bounds
# moderately is CLAMPED onto them instead of thrown away: the weak tiny models
# under-read so much (held-out ETVR micro gaze_y gain ~0.31) that ~1/3 of users
# needed > 3.2x and ran fully uncalibrated. Simulated on held-out people,
# clamping kept the per-frame error and lifted vertical gain 0.31 -> 0.71
# (ETVR micro) / 0.62 -> 0.73 (BSB micro); the full model was unaffected.
# Beyond this factor over the bound the fit is still treated as degenerate
# (the bad captures seen in the wild were 10-200x).
_SMARTCAL_CLAMP_FACTOR = 2.0
# The raw output of the NEXT models flattens towards the edges, by an amount
# that differs between models and users. A straight fit then misses the
# extremes by several degrees, and leaving them out (below) hides exactly the
# range that matters. So the fit also tries undoing a tanh-like saturation
# with each ceiling here and keeps the one whose dots it predicts best when
# held out, by the median so a single bad dot does not decide. A curve has to
# beat the straight fit by CURVE_MARGIN to be used. On four Bigscreen Beyond
# runs, fitting one run and scoring the other three, the straight fit missed
# by 3.6 deg on average and the curve it chose by 2.6 to 2.7 deg.
# Each axis gets its own ceiling: on a Bigscreen Beyond the raw gaze flattens
# more sideways than vertically, and separate ceilings cut the error on unseen
# runs from 3.0 to 2.1 deg.
_SMARTCAL_SATURATIONS = (1.2, 1.0, 0.9, 0.85, 0.8)
_SMARTCAL_CURVE_MARGIN = 0.95
# A dot whose held-out error is far above the others' was not fixated (a
# glance away, a blink the median could not reject, a slipped pupil fit). One
# such dot pulls the whole fit, and can push the mean error past the limit
# below so the run is thrown away. It is dropped when its held-out error, under
# the chosen fit, is over MIN_DEG and RATIO times the median of the rest, worst
# first, up to MAX_DROPPED dots and never below _SMARTCAL_MIN_DOTS. A centre
# visit is the recentering anchor and is only dropped while another remains.
_SMARTCAL_OUTLIER_MIN_DEG = 5.0
_SMARTCAL_OUTLIER_RATIO = 3.0
_SMARTCAL_MAX_DROPPED = 3
# Mean angular distance (degrees) between the fitted mapping of the captured
# points and the dots. A transform that can't get within this of its OWN
# fitting points is fitting noise.
_SMARTCAL_MAX_RESIDUAL_DEG = 8.0
# The per-dot raw medians must span at least this much in both axes; if the
# raw gaze barely moved across the well-separated dots, the samples are
# degenerate (tracking frozen, eye not following) and lstsq would explode.
_SMARTCAL_MIN_RAW_SPREAD = 0.10
# Behavioural guard against the exact "snaps to the extremes even when not
# looking there" failure: a modest raw gaze (radius EARLY_R) must NOT already
# map near the output edge. A degenerate over-gained fit pins small gaze to the
# corner; this catches it directly. (A warp+affine with det(W) > 0 is injective,
# so no fold back or monotonicity walk is needed because that was only for the old
# cubic.) The limit leaves headroom for a real per-user gain without allowing
# a small raw gaze to clip at the output edge. The ring radius scales with
# MAX_GAIN: at 0.50 it capped the effective gain near 1.7 on its own, and an
# under-driving model never reaches raw 0.5 for a user who needs a 2.5x fit
# (that would be 1.25 of real gaze). 0.25 keeps the same guard at that gain.
_SMARTCAL_SANITY_EARLY_R = 0.25
_SMARTCAL_SANITY_EARLY_MAX = 0.85

# ── Lid / brow half of the smart calibration ──────────────────────────────────
# The user holds a neutral face for the whole dot sequence (they are only moving
# their eyes), so every captured frame is a sample of "eyes normally open, brow
# at rest". Those two medians are anchored to the output values below.
NEXT_SMARTCAL_LID_TARGET = 0.75
NEXT_SMARTCAL_BROW_TARGET = 0.5
# A neutral outside these bounds is not a resting face (eyes held shut or
# forced wide, brow pinned): anchoring to it would either crush the closed
# range or leave no headroom above neutral. Rejected rather than saved.
_SMARTCAL_LID_NEUTRAL_MIN = 0.15
_SMARTCAL_LID_NEUTRAL_MAX = 0.98
_SMARTCAL_BROW_NEUTRAL_MIN = 0.05
_SMARTCAL_BROW_NEUTRAL_MAX = 0.95
# Total samples (across all dots) needed before a median means anything.
_SMARTCAL_MIN_NEUTRAL_SAMPLES = 30


def next_smartcal_neutral_apply(value: float, neutral, target: float) -> float:
    """Remap one expression channel so the user's neutral reads as ``target``.

    Piecewise-linear through (0, 0), (neutral, target) and (1, 1): the fully
    closed and fully open/raised ends stay where they are, only the resting
    point moves. A plain gain would clip the top of the range and a plain
    offset would stop a blink from ever reaching 0.

    ``neutral`` None (not calibrated) returns the value untouched."""
    if neutral is None:
        return value
    n = float(neutral)
    if not (0.0 < n < 1.0):
        return value
    v = max(0.0, min(1.0, float(value)))
    if v <= n:
        return target * (v / n)
    return target + (1.0 - target) * ((v - n) / (1.0 - n))


def _fit_next_smartcal_neutrals(eye_processors: list) -> bool:
    """Anchor each eye's neutral lid/brow reading to its target output.

    Uses the same per-dot captures as the gaze fit (fields 2 and 3 of each
    sample), pooled across every dot: the face is at rest for the whole
    sequence, so there is nothing per-dot about these two channels. The median
    over the pool rejects the blinks that inevitably happen during it."""
    saved_any = False
    for ep in eye_processors:
        eye = getattr(ep, "eye_id", "?")
        pooled = [s for pts in (getattr(ep, "_next_smartcal_samples", {}) or {}).values() for s in pts if len(s) >= 4]
        if len(pooled) < _SMARTCAL_MIN_NEUTRAL_SAMPLES:
            logger.warning(
                "NEXT smart cal (eye %s): only %d lid/brow samples (<%d); keeping previous lid/brow calibration.",
                eye,
                len(pooled),
                _SMARTCAL_MIN_NEUTRAL_SAMPLES,
            )
            continue
        arr = np.asarray(pooled, dtype=np.float64)
        lid = float(np.median(arr[:, 2]))
        brow = float(np.median(arr[:, 3]))
        logger.info(
            "NEXT smart cal (eye %s): neutral lid %.3f -> %.2f, brow %.3f -> %.2f (%d samples)",
            eye,
            lid,
            NEXT_SMARTCAL_LID_TARGET,
            brow,
            NEXT_SMARTCAL_BROW_TARGET,
            len(pooled),
        )
        if not _SMARTCAL_LID_NEUTRAL_MIN <= lid <= _SMARTCAL_LID_NEUTRAL_MAX:
            logger.warning(
                "NEXT smart cal (eye %s): neutral eyelid %.3f is outside "
                "[%.2f, %.2f] - were the eyes open and relaxed? Keeping the "
                "previous lid calibration.",
                eye,
                lid,
                _SMARTCAL_LID_NEUTRAL_MIN,
                _SMARTCAL_LID_NEUTRAL_MAX,
            )
        else:
            ep.config.next_smartcal_lid_neutral = lid
            ep._next_smartcal_lid_neutral = lid
            saved_any = True
        if not _SMARTCAL_BROW_NEUTRAL_MIN <= brow <= _SMARTCAL_BROW_NEUTRAL_MAX:
            logger.warning(
                "NEXT smart cal (eye %s): neutral eyebrow %.3f is outside "
                "[%.2f, %.2f]. Keeping the previous brow calibration.",
                eye,
                brow,
                _SMARTCAL_BROW_NEUTRAL_MIN,
                _SMARTCAL_BROW_NEUTRAL_MAX,
            )
        else:
            ep.config.next_smartcal_brow_neutral = brow
            ep._next_smartcal_brow_neutral = brow
            saved_any = True
    return saved_any


def _smartcal_warp_scalar(v: float, warp) -> float:
    """De-saturate one raw gaze component into the fit space selected by ``warp``.

    ``"atanh"`` inverts the model's output tanh so a saturating model becomes
    ~linear in true gaze; ``None`` (legacy) is the identity (raw-space affine)."""
    if warp == "atanh":
        v = max(-_SMARTCAL_WARP_CLAMP, min(_SMARTCAL_WARP_CLAMP, float(v)))
        return math.atanh(v)
    return float(v)


def _saturation(w) -> tuple:
    """The (sideways, vertical) saturation an angle fit undoes before its
    affine, 0 for an axis it fits straight."""
    return (float(w[6]), float(w[7])) if len(w) > 7 else (0.0, 0.0)


def _desaturate(v: float, saturation: float) -> float:
    """Undo a model output that flattens towards +-``saturation`` (a tanh
    curve with that ceiling), or nothing for saturation 0."""
    if saturation <= 0.0:
        return float(v)
    return math.atanh(max(-_SMARTCAL_WARP_CLAMP, min(_SMARTCAL_WARP_CLAMP, float(v) / saturation)))


def next_smartcal_apply(w, b, warp, x_raw, y_raw):
    """Map a raw NEXT gaze (x_raw, y_raw) through a stored transform, into the
    space that fit lives in: gaze tangents for "angle", output-normalised gaze
    for the legacy fits. next_smartcal_gaze is the one that returns output."""
    if warp == SMARTCAL_SPACE_ANGLE:
        sx, sy = _saturation(w)
        x, y = _desaturate(x_raw, sx), _desaturate(y_raw, sy)
        tan_x = w[0] * x + w[1] * y + b[0]
        tan_y = w[2] * x + w[3] * y + b[1] + (w[5] - w[3]) * max(y - w[4], 0.0)
        return tan_x, tan_y
    gx = _smartcal_warp_scalar(x_raw, warp)
    gy = _smartcal_warp_scalar(y_raw, warp)
    x_cal = w[0] * gx + w[1] * gy + b[0]
    y_cal = w[2] * gx + w[3] * gy + b[1]
    return x_cal, y_cal


def next_smartcal_gaze(w, b, warp, x_raw, y_raw, settings):
    """Calibrated output gaze (not clipped) for a raw NEXT gaze: an angle fit
    gives the true gaze angle, scaled here by the configured gaze limits."""
    x, y = next_smartcal_apply(w, b, warp, x_raw, y_raw)
    if warp == SMARTCAL_SPACE_ANGLE:
        return smartcal_tangents_to_gaze(x, y, settings)
    return x, y


def _angle_pieces(w, b):
    """An angle fit as its two plain affines (below, above the vertical hinge),
    in output-normalised units so the gain and bias bounds apply to it."""
    k = 1.0 / _SMARTCAL_ANGLE_REF
    w11, w12, w21, w22, y0, w22_up = (float(v) for v in w[:6])
    b1, b2 = float(b[0]), float(b[1])
    down = ([w11 * k, w12 * k, w21 * k, w22 * k], [b1 * k, b2 * k])
    up = ([w11 * k, w12 * k, w21 * k, w22_up * k], [b1 * k, (b2 - (w22_up - w22) * y0) * k])
    return down, up


def next_smartcal_transform_is_sane(w, b, warp=None) -> bool:
    """True if a stored smart-cal transform is plausibly a gentle per-user
    polish rather than a degenerate fit.

    Checked both when fitting (before save) and when loading from config, so
    garbage transforms persisted by older builds are ignored instead of
    pinning the gaze output to the clip bounds."""
    if warp == SMARTCAL_SPACE_ANGLE:
        try:
            if len(w) not in (6, 8) or any(s != 0.0 and not 0.5 <= s <= 2.0 for s in _saturation(w)):
                return False
            pieces = _angle_pieces(w, b)
        except (TypeError, ValueError, IndexError):
            return False
        if not all(_affine_is_sane(pw, pb, None) for pw, pb in pieces):
            return False
        # The pieces leave out the saturation, so check the whole map too.
        for ang in np.linspace(0.0, 2.0 * math.pi, 8, endpoint=False):
            r = _SMARTCAL_SANITY_EARLY_R
            tx, ty = next_smartcal_apply(w, b, warp, math.cos(ang) * r, math.sin(ang) * r)
            gx, gy = (max(-1.0, min(1.0, v / _SMARTCAL_ANGLE_REF)) for v in (tx, ty))
            if not math.isfinite(tx + ty) or math.hypot(gx, gy) > _SMARTCAL_SANITY_EARLY_MAX:
                return False
        return True
    return _affine_is_sane(w, b, warp)


def _affine_is_sane(w, b, warp) -> bool:
    """The bounds, on one affine (W row-major [w11,w12,w21,w22], B [b1,b2])
    onto output-normalised gaze."""
    try:
        W = np.array([[w[0], w[1]], [w[2], w[3]]], dtype=np.float64)
        B = np.asarray(b, dtype=np.float64).reshape(2)
    except (TypeError, ValueError, IndexError):
        return False
    if not (np.all(np.isfinite(W)) and np.all(np.isfinite(B))):
        return False
    if np.linalg.det(W) <= 0.0:  # mirror/collapse: never a valid polish
        return False
    svals = np.linalg.svd(W, compute_uv=False)
    if svals[0] > _SMARTCAL_MAX_GAIN or svals[-1] < _SMARTCAL_MIN_GAIN:
        return False
    if np.max(np.abs(B)) > _SMARTCAL_MAX_BIAS:
        return False

    # Behavioural guard: a modest gaze must not already be pinned near the edge.
    # Evaluate the full map on the clipped output (what actually reaches OSC)
    # around a small ring; if any direction is already slammed out, it's the
    # snap-to-extreme degeneracy.
    for ang in np.linspace(0.0, 2.0 * math.pi, 8, endpoint=False):
        cx, cy = next_smartcal_apply(
            w,
            b,
            warp,
            math.cos(ang) * _SMARTCAL_SANITY_EARLY_R,
            math.sin(ang) * _SMARTCAL_SANITY_EARLY_R,
        )
        if not (math.isfinite(cx) and math.isfinite(cy)):
            return False
        ocx = max(-1.0, min(1.0, cx))
        ocy = max(-1.0, min(1.0, cy))
        if math.hypot(ocx, ocy) > _SMARTCAL_SANITY_EARLY_MAX:
            return False
    return True


def clamp_next_smartcal_transform(w, b):
    """Pull a moderately over-bound affine onto the sanity bounds.

    Singular values of W above _SMARTCAL_MAX_GAIN are capped at it (direction
    and roll kept) and the bias is clipped to +-_SMARTCAL_MAX_BIAS, provided
    neither exceeds its bound by more than _SMARTCAL_CLAMP_FACTOR. Anything
    else (mirrored W, a wildly over-gained or offset fit) is returned
    unchanged so next_smartcal_transform_is_sane still rejects it.
    Returns (w, b, clamped)."""
    W = np.array([[w[0], w[1]], [w[2], w[3]]], dtype=np.float64)
    B = np.asarray(b, dtype=np.float64).reshape(2)
    if not (np.all(np.isfinite(W)) and np.all(np.isfinite(B))) or np.linalg.det(W) <= 0.0:
        return w, b, False
    U, s, Vt = np.linalg.svd(W)
    over_gain = s[0] > _SMARTCAL_MAX_GAIN
    over_bias = float(np.max(np.abs(B))) > _SMARTCAL_MAX_BIAS
    if not (over_gain or over_bias):
        return w, b, False
    if s[0] > _SMARTCAL_MAX_GAIN * _SMARTCAL_CLAMP_FACTOR:
        return w, b, False
    if float(np.max(np.abs(B))) > _SMARTCAL_MAX_BIAS * _SMARTCAL_CLAMP_FACTOR:
        return w, b, False
    Wc = U @ np.diag(np.minimum(s, _SMARTCAL_MAX_GAIN)) @ Vt
    Bc = np.clip(B, -_SMARTCAL_MAX_BIAS, _SMARTCAL_MAX_BIAS)
    return [float(Wc[0, 0]), float(Wc[0, 1]), float(Wc[1, 0]), float(Wc[1, 1])], [float(Bc[0]), float(Bc[1])], True


def _clamp_angle_transform(w, b):
    """clamp_next_smartcal_transform for an angle fit: the below-hinge affine
    as a whole, then the upward gain on its own. Returns (w, b, clamped)."""
    (down_w, down_b), _ = _angle_pieces(w, b)
    cw, cb, clamped = clamp_next_smartcal_transform(down_w, down_b)
    up = float(w[5]) / _SMARTCAL_ANGLE_REF
    if _SMARTCAL_MAX_GAIN < up <= _SMARTCAL_MAX_GAIN * _SMARTCAL_CLAMP_FACTOR:
        up, clamped = _SMARTCAL_MAX_GAIN, True
    if not clamped:
        return w, b, False
    r = _SMARTCAL_ANGLE_REF
    return [*(float(v) * r for v in cw), float(w[4]), up * r, *w[6:]], [float(v) * r for v in cb], clamped


def reset_next_smartcal(eye_processors: list, baseconfig) -> None:
    """Clear the fitted smart-cal transform (memory + config) for all eyes,
    lid/brow anchors included."""
    for ep in eye_processors:
        ep._next_smartcal_w = None
        ep._next_smartcal_b = None
        ep._next_smartcal_warp = None
        ep._next_smartcal_lid_neutral = None
        ep._next_smartcal_brow_neutral = None
        ep.config.next_smartcal_w = None
        ep.config.next_smartcal_b = None
        ep.config.next_smartcal_warp = None
        ep.config.next_smartcal_lid_neutral = None
        ep.config.next_smartcal_brow_neutral = None
    baseconfig.save()
    logger.info("NEXT smart cal: transforms cleared (raw model gaze, lid and brow restored).")


def _dot_medians(ep, dot_count: int = len(NEXT_SMARTCAL_DOTS)) -> dict:
    """{dot: (raw_x, raw_y)} for the dots this eye captured enough frames of.
    The median over the hold window rejects blinks / transient outliers."""
    samples = getattr(ep, "_next_smartcal_samples", {}) or {}
    min_lid = open_lid(s[2] for pts in samples.values() for s in pts if len(s) >= 3)
    medians = {}
    for dot in range(dot_count):
        # Gaze from blinks says nothing; lid and brow use every frame.
        pts = [s for s in samples.get(dot, []) if len(s) < 3 or s[2] >= min_lid]
        if len(pts) < _SMARTCAL_MIN_SAMPLES_PER_DOT:
            continue
        arr = np.asarray(pts, dtype=np.float64)
        medians[dot] = (float(np.median(arr[:, 0])), float(np.median(arr[:, 1])))
    return medians


def _fit_errors_deg(w, b, medians: dict, tangents) -> np.ndarray:
    """(yaw, pitch) error in degrees of an angle fit at each captured dot."""
    fitted = np.array([next_smartcal_apply(w, b, SMARTCAL_SPACE_ANGLE, *medians[d]) for d in sorted(medians)])
    truth = np.array([tangents[d] for d in sorted(medians)])
    return np.degrees(np.arctan(fitted) - np.arctan(truth))


def _solve_angle_fit(medians: dict, tangents, layout, hinge_y=None, saturation=(0.0, 0.0)):
    """Weighted least-squares angle fit (see the module header) of the captured
    dots, as (w, b). None when the solve fails. ``hinge_y`` is the raw vertical
    gaze to hinge on when no centre capture is among ``medians``. With a
    (sideways, vertical) ``saturation``, the fit is made on the raw gaze with
    that saturation undone and stores it as w[6] and w[7]."""
    dots = sorted(medians)
    R = np.asarray(
        [[_desaturate(medians[d][0], saturation[0]), _desaturate(medians[d][1], saturation[1])] for d in dots],
        dtype=np.float64,
    )  # N x 2 raw gaze, saturation undone
    T = np.asarray([tangents[d] for d in dots], dtype=np.float64)  # N x 2 dot tangents
    gx, gy = R[:, 0], R[:, 1]
    A = np.column_stack([gx, gy, np.ones(len(R))])  # N x 3  [gx, gy, 1]
    # The separate upward gain needs the centre capture to hinge on and a
    # couple of dots on each side of it; otherwise one gain serves both.
    centres = [d for d in _centre_dots(layout) if d in medians]
    above = sum(layout[d][1] > 0.0 for d in dots)
    below = sum(layout[d][1] < 0.0 for d in dots)
    hinge = (bool(centres) or hinge_y is not None) and above >= 2 and below >= 2
    if not hinge:
        y0 = 0.0
    elif centres:
        y0 = float(np.mean([R[dots.index(d), 1] for d in centres]))
    else:
        y0 = _desaturate(hinge_y, saturation[1])
    Ay = np.column_stack([A, np.maximum(gy - y0, 0.0)]) if hinge else A
    # Weighted least squares. Multiplying rows by sqrt(weight) makes the
    # centre anchor count more without duplicating or over-sampling frames.
    # A layout that visits the centre more than once shares the weight.
    centre_weight = _SMARTCAL_CENTER_WEIGHT / max(1, len(centres))
    sw = np.sqrt([centre_weight if d in centres else 1.0 for d in dots])
    try:
        sol_x, *_ = np.linalg.lstsq(A * sw[:, None], T[:, 0] * sw, rcond=None)  # [w11, w12, b1]
        sol_y, *_ = np.linalg.lstsq(Ay * sw[:, None], T[:, 1] * sw, rcond=None)  # [w21, w22, b2, up - w22]
    except np.linalg.LinAlgError as e:
        logger.warning("NEXT smart cal: solve failed: %s", e)
        return None
    w22 = float(sol_y[1])
    w22_up = w22 + float(sol_y[3]) if hinge else w22
    w = [float(sol_x[0]), float(sol_x[1]), float(sol_y[0]), w22, y0, w22_up]
    if any(s > 0.0 for s in saturation):
        w += [float(saturation[0]), float(saturation[1])]
    return w, [float(sol_x[2]), float(sol_y[2])]


def current_gaze_tangents(ep, raw_x: float, raw_y: float, settings):
    """The gaze direction, as tangents, that this eye's current mapping reads
    from a raw model gaze: its saved fit, or the raw model output without
    one. Before the output limits clip it."""
    w, b = getattr(ep, "_next_smartcal_w", None), getattr(ep, "_next_smartcal_b", None)
    if w is None or b is None:
        return smartcal_gaze_to_tangents(raw_x, raw_y, settings)
    warp = getattr(ep, "_next_smartcal_warp", None)
    if warp == SMARTCAL_SPACE_ANGLE:
        return next_smartcal_apply(w, b, warp, raw_x, raw_y)
    return smartcal_gaze_to_tangents(*next_smartcal_apply(w, b, warp, raw_x, raw_y), settings)


def _current_mapping_errors_deg(ep, medians: dict, tangents, settings) -> np.ndarray:
    """(yaw, pitch) error in degrees at each captured dot of the gaze mapping
    this eye uses now."""
    errors = [
        np.degrees(np.arctan(current_gaze_tangents(ep, *medians[dot], settings)) - np.arctan(tangents[dot]))
        for dot in sorted(medians)
    ]
    return np.asarray(errors, dtype=np.float64)


def _heldout_errors_deg(medians: dict, tangents, layout, saturation=(0.0, 0.0)) -> np.ndarray:
    """(yaw, pitch) error in degrees at each captured dot (in dot order) of a
    fit made without that dot, clamped like the saved fit.

    The error a fit makes on its own dots flatters it: with three or four
    unknowns per axis it partly bends to their noise. Leaving each dot out in
    turn measures how well the calibration predicts gaze it was not fit on,
    which is what the user gets. NaN where the remaining dots can't be fit."""
    errors = np.full((len(medians), 2), np.nan)
    centres = _centre_dots(layout)
    for i, dot in enumerate(sorted(medians)):
        others = {d: m for d, m in medians.items() if d != dot}
        # Leaving out the only centre capture would also drop the hinge and
        # score a different model. Hinge on its raw gaze, not its target.
        hinge_y = medians[dot][1] if dot in centres else None
        solved = _solve_angle_fit(others, tangents, layout, hinge_y, saturation)
        if solved is None:
            continue
        w, b, _ = _clamp_angle_transform(*solved)
        errors[i] = _fit_errors_deg(w, b, {dot: medians[dot]}, tangents)[0]
    return errors


SMARTCAL_APPLIED = "applied"
SMARTCAL_KEPT = "kept"
SMARTCAL_REJECTED = "rejected"


@dataclass
class SmartCalEyeResult:
    """How one eye's gaze fit went, for the calibration report.

    ``outcome`` is SMARTCAL_APPLIED, SMARTCAL_KEPT (the current calibration was
    more accurate) or SMARTCAL_REJECTED, with ``reason`` one of "too_few_dots",
    "no_spread", "inconsistent" or "degenerate". Errors are in degrees:
    ``heldout_*`` from fits that did not see the dot, ``current_mean`` for the
    calibration used before. ``dropped`` lists the dots left out of the fit as
    (dot, held-out error)."""

    eye: object
    dots_total: int
    outcome: str = SMARTCAL_REJECTED
    reason: str | None = None
    dots_used: int = 0
    dropped: list = field(default_factory=list)
    fit_error: float | None = None
    heldout_mean: float | None = None
    heldout_worst: float | None = None
    current_mean: float | None = None


def _choose_saturation(medians: dict, tangents, layout) -> tuple:
    """The (sideways, vertical) saturation (0: none) whose fit best predicts
    held-out dots. Only saturations whose fit of all dots would be accepted
    take part."""
    scores = {}
    ceilings = (0.0, *_SMARTCAL_SATURATIONS)
    for saturation in ((sx, sy) for sx in ceilings for sy in ceilings):
        solved = _solve_angle_fit(medians, tangents, layout, saturation=saturation)
        if solved is None or not next_smartcal_transform_is_sane(
            *_clamp_angle_transform(*solved)[:2], SMARTCAL_SPACE_ANGLE
        ):
            continue
        errors = np.hypot(*_heldout_errors_deg(medians, tangents, layout, saturation).T)
        if np.isfinite(errors).any():
            scores[saturation] = float(np.nanmedian(errors))
    if not scores:
        return (0.0, 0.0)
    straight = (0.0, 0.0)
    best = min(scores, key=scores.get)
    if best != straight and straight in scores and scores[best] > _SMARTCAL_CURVE_MARGIN * scores[straight]:
        best = straight
    logger.info(
        "NEXT smart cal: held-out median error %.1f deg with saturation %g sideways, %g vertical (straight fit %s)",
        scores[best],
        *best,
        f"{scores[straight]:.1f} deg" if straight in scores else "rejected",
    )
    return best


def _predicted_error_deg(kept: dict, dot, raw, tangents, layout, saturation) -> float:
    """How far a fit of ``kept`` misses ``dot`` (raw gaze ``raw``), clamped
    like the saved fit. Inf when ``kept`` can't be fit."""
    centres = _centre_dots(layout)
    solved = _solve_angle_fit(kept, tangents, layout, raw[1] if dot in centres else None, saturation)
    if solved is None:
        return math.inf
    w, b, _ = _clamp_angle_transform(*solved)
    return float(np.hypot(*_fit_errors_deg(w, b, {dot: raw}, tangents)[0]))


def _drop_inconsistent_dots(medians: dict, tangents, layout, saturation=(0.0, 0.0)):
    """The captures without the dots that don't fit with the rest (see
    _SMARTCAL_OUTLIER_MIN_DEG), and the dropped dots as (dot, held-out error
    in degrees) in the order they were dropped.

    One bad dot also bends the fit for the others (a bad centre visit moves
    the hinge), so a good dot can look worse than it and go first. After each
    drop, a dot dropped before comes back when the remaining dots now predict
    it within the limit."""
    kept = dict(medians)
    dropped = []
    centres = set(_centre_dots(layout))
    for _ in range(2 * _SMARTCAL_MAX_DROPPED + 2):
        if len(kept) <= _SMARTCAL_MIN_DOTS or len(dropped) >= _SMARTCAL_MAX_DROPPED:
            break
        dots = sorted(kept)
        errors = np.hypot(*_heldout_errors_deg(kept, tangents, layout, saturation).T)
        spare_centre = sum(d in centres for d in dots) > 1
        candidates = [i for i, d in enumerate(dots) if (spare_centre or d not in centres) and np.isfinite(errors[i])]
        if not candidates:
            break
        worst = max(candidates, key=lambda i: errors[i])
        rest = np.delete(errors, worst)
        rest = rest[np.isfinite(rest)]
        limit = max(_SMARTCAL_OUTLIER_MIN_DEG, _SMARTCAL_OUTLIER_RATIO * float(np.median(rest))) if rest.size else 0.0
        if not rest.size or errors[worst] <= limit:
            break
        dropped.append((dots[worst], float(errors[worst])))
        del kept[dots[worst]]
        for earlier, _ in dropped[:-1]:
            if _predicted_error_deg(kept, earlier, medians[earlier], tangents, layout, saturation) <= limit:
                kept[earlier] = medians[earlier]
                dropped = [(dot, error) for dot, error in dropped if dot != earlier]
    return kept, dropped


def _fit_next_smartcal(
    eye_processors: list, baseconfig, settings, gaze_range=None, layout=NEXT_SMARTCAL_DOTS, results=None
) -> bool:
    """Least-squares fit the per-eye transform from raw gaze to true gaze angle
    (see the module header) on the per-dot raw medians.

    ``gaze_range`` is the range the overlay really placed its dots in
    (parse_overlay_gaze_range); None assumes the overlay defaults. ``layout``
    holds the normalised positions of the dots that were shown.

    In the per-eye gaze modes (gui_NEXT_gaze_mode, see next_eye_gaze) the gaze
    transform is fit ONCE, on the dominant eye, and applied to both eyes. Each
    eye's own fit would pull it onto the dots and erase exactly the deviation
    independent mode exists to show; the dominant eye is the one that actually
    fixates them. Both eyes share one monocular head, so one user-level
    correction fits both. (Lid/brow anchors stay per eye.)

    Appends a SmartCalEyeResult per fitted eye to ``results`` when given.
    Returns True if anything was saved: a gaze transform, or only the lid/brow
    anchors (gaze_fit_applied tells the two apart)."""
    tangents = next_smartcal_dot_tangents(gaze_range, layout)
    saved_any = False
    sources = eye_processors
    shared_fit = False
    if gaze_mode_from_settings(settings) != GAZE_MODE_FUSED:
        dominant = dominant_eye_from_settings(settings)
        source = [ep for ep in eye_processors if getattr(ep, "eye_id", None) == dominant]
        if source:
            sources, shared_fit = source, True
    for ep in sources:
        eye = getattr(ep, "eye_id", "?")
        medians = _dot_medians(ep, len(layout))
        dots = sorted(medians)
        result = SmartCalEyeResult(eye=eye, dots_total=len(layout), dots_used=len(dots))
        if results is not None:
            results.append(result)
        if len(dots) < _SMARTCAL_MIN_DOTS:
            result.reason = "too_few_dots"
            logger.warning(
                "NEXT smart cal (eye %s): only %d/%d dots captured (<%d); skipping fit.",
                eye,
                len(dots),
                len(layout),
                _SMARTCAL_MIN_DOTS,
            )
            continue

        R = np.asarray([medians[d] for d in dots], dtype=np.float64)  # N x 2 raw gaze
        T = np.asarray([tangents[d] for d in dots], dtype=np.float64)  # N x 2 dot tangents

        # Degenerate-input guard: the dots span most of the gaze range, so the
        # raw medians must show real movement in both axes. A near-constant
        # cluster (frozen tracking, eye not following the dot) makes lstsq
        # amplify noise into gains of 100+.
        spread = R.max(axis=0) - R.min(axis=0)
        if float(spread.min()) < _SMARTCAL_MIN_RAW_SPREAD:
            logger.warning(
                "NEXT smart cal (eye %s): raw gaze spread %.3f/%.3f (x/y) is too "
                "small to fit - was the eye following the dots? Keeping previous "
                "calibration.",
                eye,
                float(spread[0]),
                float(spread[1]),
            )
            result.reason = "no_spread"
            continue

        # A bad dot can sway the choice of curve, so choose again on the dots
        # that are left, and drop under that choice.
        saturation = _choose_saturation(medians, tangents, layout)
        kept, dropped = _drop_inconsistent_dots(medians, tangents, layout, saturation)
        if dropped:
            saturation = _choose_saturation(kept, tangents, layout)
            medians, dropped = _drop_inconsistent_dots(medians, tangents, layout, saturation)
        else:
            medians = kept
        result.dropped, result.dots_used = dropped, len(medians)
        if dropped:
            logger.warning(
                "NEXT smart cal (eye %s): dropped %d dot(s) that do not fit with the others: %s",
                eye,
                len(dropped),
                ", ".join(f"{dot} ({error:.1f} deg held out)" for dot, error in dropped),
            )
            dots = sorted(medians)
            R = np.asarray([medians[d] for d in dots], dtype=np.float64)
            T = np.asarray([tangents[d] for d in dots], dtype=np.float64)

        solved = _solve_angle_fit(medians, tangents, layout, saturation=saturation)
        if solved is None:
            result.reason = "degenerate"
            continue
        w, b = solved

        # Diagnostic dump (INFO so it shows without debug config): each held
        # dot's raw median, where the dot really is, and how far the fit lands
        # from it. Rings that do not separate in raw mean the model output is
        # plateauing; a sign inverted against the dot means the capture is
        # flipped; wide scatter means a noisy follow.
        errors = _fit_errors_deg(w, b, medians, tangents)
        heldout = _heldout_errors_deg(medians, tangents, layout, saturation)
        heldout_deg = np.hypot(heldout[:, 0], heldout[:, 1])
        if np.isfinite(heldout_deg).any():
            result.heldout_mean = float(np.nanmean(heldout_deg))
            result.heldout_worst = float(np.nanmax(heldout_deg))
        truth = np.degrees(np.arctan(T))
        logger.info(
            "NEXT smart cal (eye %s) captures: dot raw -> dot angle (yaw, pitch deg), fit error and "
            "held-out error (deg):\n%s",
            eye,
            "\n".join(
                f"  {d:2d} ({R[i, 0]:+.3f}, {R[i, 1]:+.3f}) -> ({truth[i, 0]:+5.1f}, {truth[i, 1]:+5.1f})"
                f"  err ({errors[i, 0]:+.1f}, {errors[i, 1]:+.1f})"
                f"  held-out ({heldout[i, 0]:+.1f}, {heldout[i, 1]:+.1f})"
                for i, d in enumerate(dots)
            ),
        )

        # A usable fit must land close to its own fitting points AND look like
        # a gentle polish. Otherwise keep whatever the user had before.
        residual = float(np.mean(np.hypot(errors[:, 0], errors[:, 1])))
        result.fit_error = residual
        if residual > _SMARTCAL_MAX_RESIDUAL_DEG:
            logger.warning(
                "NEXT smart cal (eye %s): the fit misses its own dots by %.1f deg "
                "on average (limit %.0f; attempted W=%s B=%s): captures look "
                "inconsistent. Keeping previous calibration.",
                eye,
                residual,
                _SMARTCAL_MAX_RESIDUAL_DEG,
                [round(v, 4) for v in w],
                [round(v, 4) for v in b],
            )
            result.reason = "inconsistent"
            continue
        w_fit, b_fit = w, b
        w, b, clamped = _clamp_angle_transform(w, b)
        if clamped:
            logger.info(
                "NEXT smart cal (eye %s): fit W=%s B=%s exceeds gain %.1f / bias %.2f; "
                "clamped to W=%s B=%s (model under-reads this user).",
                eye,
                [round(v, 4) for v in w_fit],
                [round(v, 4) for v in b_fit],
                _SMARTCAL_MAX_GAIN,
                _SMARTCAL_MAX_BIAS,
                [round(v, 4) for v in w],
                [round(v, 4) for v in b],
            )
        if not next_smartcal_transform_is_sane(w, b, SMARTCAL_SPACE_ANGLE):
            logger.warning(
                "NEXT smart cal (eye %s): rejected degenerate transform W=%s B=%s "
                "(gain/bias/monotonicity out of bounds). Keeping previous "
                "calibration.",
                eye,
                [round(v, 4) for v in w],
                [round(v, 4) for v in b],
            )
            result.reason = "degenerate"
            continue

        # Replace the calibration only with a better one. The current mapping
        # was not fit on these captures, so its error on them is held out too.
        new_mean = result.heldout_mean
        if new_mean is None or not math.isfinite(new_mean):
            # No dot could be held out, so nothing says this fit is any good.
            logger.warning("NEXT smart cal (eye %s): the fit could not be scored. Keeping previous calibration.", eye)
            result.reason = "degenerate"
            continue
        current_mean = float(np.mean(np.hypot(*_current_mapping_errors_deg(ep, medians, tangents, settings).T)))
        # A current mapping that reads no gaze at all (a broken saved fit) is
        # worse than any fit that got this far.
        if not math.isfinite(current_mean):
            current_mean = math.inf
        else:
            result.current_mean = current_mean
        logger.info(
            "NEXT smart cal (eye %s): new fit %.1f deg held out, current calibration %.1f deg on the same dots.",
            eye,
            new_mean,
            current_mean,
        )
        if new_mean > current_mean:
            logger.warning(
                "NEXT smart cal (eye %s): the new fit is less accurate than the current calibration. Keeping it.",
                eye,
            )
            result.outcome = SMARTCAL_KEPT
            continue

        for dst in eye_processors if shared_fit else (ep,):
            dst.config.next_smartcal_w = list(w)
            dst.config.next_smartcal_b = list(b)
            dst.config.next_smartcal_warp = SMARTCAL_SPACE_ANGLE
            dst._next_smartcal_w = list(w)
            dst._next_smartcal_b = list(b)
            dst._next_smartcal_warp = SMARTCAL_SPACE_ANGLE
        result.outcome = SMARTCAL_APPLIED
        saved_any = True
        logger.info(
            "NEXT smart cal (eye %s%s): fit from %d dots: W=%s B=%s, mean error %.1f deg "
            "(worst %.1f), held-out %.1f deg (worst %.1f), vertical gain up/down %.2f",
            eye,
            ", dominant: applied to both eyes" if shared_fit else "",
            len(dots),
            [round(v, 4) for v in w],
            [round(v, 4) for v in b],
            residual,
            float(np.max(np.hypot(errors[:, 0], errors[:, 1]))),
            float(np.nanmean(heldout_deg)),
            float(np.nanmax(heldout_deg)),
            w[5] / w[3],
        )
        # How the other eye's own captures land under the fit it was handed: a
        # real deviation between the eyes shows here, and so does a model that
        # simply reads this eye differently, which the shared fit can't correct.
        for other in eye_processors if shared_fit else ():
            other_medians = _dot_medians(other, len(layout))
            if other is ep or len(other_medians) < _SMARTCAL_MIN_DOTS:
                continue
            off = _fit_errors_deg(w, b, other_medians, tangents)
            logger.info(
                "NEXT smart cal (eye %s under the fit of eye %s): mean error %.1f deg, "
                "mean offset (yaw %+.1f, pitch %+.1f)",
                getattr(other, "eye_id", "?"),
                eye,
                float(np.mean(np.hypot(off[:, 0], off[:, 1]))),
                float(np.mean(off[:, 0])),
                float(np.mean(off[:, 1])),
            )

    # The lid/brow anchors are fit independently of the gaze transform: they
    # need far less data, so a gaze fit that was rejected (or skipped for too
    # few dots) must not cost the user their lid/brow calibration.
    if getattr(settings, "gui_NEXT_calib_lids_brows", True):
        saved_any = _fit_next_smartcal_neutrals(eye_processors) or saved_any

    if saved_any:
        baseconfig.save()
    return saved_any


def gaze_fit_applied(results) -> bool:
    """Whether a run replaced the gaze calibration of any eye. A run that only
    saved the lid/brow anchors kept the gaze calibration the user had."""
    return any(result.outcome == SMARTCAL_APPLIED for result in results)


# Before the first dot is captured, the instruction and the centre dot stay up
# until the gaze has rested for READY_REST_S: longer than a reading fixation
# (about 0.25 s), so the user is looking at the dot and not reading. Then the
# text goes away for the rest of the run. After READY_TIMEOUT_S it starts
# anyway. Each dot then waits up to DOT_REST_TIMEOUT_S for the gaze to rest.
READY_REST_S = 0.8
READY_TIMEOUT_S = 15.0
DOT_REST_TIMEOUT_S = 1.5
# The gaze needs this long to react when the text goes away.
REACTION_S = 0.3
# How long the result stays in the headset after the dots.
_SMARTCAL_SUMMARY_S = 8.0


# The dots reach at most this fraction of the headset's binocular view, so the
# outermost dot and most of its converging ring stay on screen.
CALIBRATION_COVERAGE = 0.9


# The range the NEXT models' training data covers (sideways, up, down in
# degrees): data collection puts its dots at most this far out
# (data_collection.py). The calibration covers at least that much, so the fit
# does not extrapolate where the model still reads gaze, and raising a gaze
# limit up to it needs no new calibration.
MODEL_TRAINED_RANGE_DEG = (36.0, 20.0, 40.0)


def calibration_range_args(settings) -> list:
    """Overlay flags that spread the dots over the configured output gaze
    limits, or the range the model was trained on where that is wider, so the
    fit covers the range the outputs use instead of extrapolating to it. The
    overlay pulls them in to what both eyes can see on the headset and logs
    the range it used."""

    def extent(name, default, trained):
        return min(89.0, max(1.0, trained, float(getattr(settings, name, default))))

    yaw, up, down = MODEL_TRAINED_RANGE_DEG
    return [
        f"--coverage={CALIBRATION_COVERAGE:g}",
        f"--max-deg={extent('gui_gaze_yaw_max_deg', 40.0, yaw):g}",
        f"--max-deg-up={extent('gui_gaze_pitch_up_deg', 15.0, up):g}",
        f"--max-deg-down={extent('gui_gaze_pitch_down_deg', 40.0, down):g}",
    ]


def _calibrating() -> bool:
    return var.overlay_active


def start_when_ready(overlay, trace, events: list, keep_going) -> None:
    """Start a pass with the centre dot up and wait until the user rests
    their gaze on it, then hide the instruction (sent before). Appends
    (time, "ready", rested) to ``events``."""
    overlay.send(CMD_START_PASS)
    overlay.wait_for(SIG_PASS_RUNNING, keep_going)
    overlay.send(CMD_DOT, 0.0, 0.0)
    overlay.wait_for(SIG_DOT_HELD, keep_going)
    rested = trace.wait_until_resting(READY_TIMEOUT_S, READY_REST_S, keep_going)
    if not rested:
        logger.warning("Calibration overlay: the gaze did not rest on the first dot. Starting anyway.")
    overlay.send(CMD_HIDE_TEXT)
    events.append((time.monotonic(), "ready", rested))
    overlay.pause(REACTION_S, keep_going)


def show_dot_and_capture(overlay, trace, events: list, dot, position, keep_going) -> dict:
    """Show the dot at ``position`` (None: it is already up), wait until the
    gaze rests on it and capture it. Returns [(processor, frames)]."""
    if position is not None:
        overlay.send(CMD_DOT, *position)
        events.append((time.monotonic(), "show", dot))
        overlay.wait_for(SIG_DOT_HELD, keep_going)
    events.append((time.monotonic(), "held", dot))
    if not trace.wait_until_resting(DOT_REST_TIMEOUT_S, keep_going=keep_going):
        # A gaze that never came to rest is not a fixation of this dot.
        events.append((time.monotonic(), "unrested", dot))
        return [(ep, []) for ep in trace.processors]
    start = time.monotonic()
    overlay.pause(NEXT_SMARTCAL_CAPTURE_WINDOW_S, keep_going)
    end = time.monotonic()
    events.append((start, "capture", dot))
    events.append((end, "captured", dot))
    return trace.frames(start, end)


def _show_dots(overlay, trace, eye_processors: list, layout, events: list) -> None:
    """Show the dots of ``layout`` one after another and capture each once the
    gaze rests on it. Appends what happened when to ``events``, and (time,
    "end", None) once the last dot is done."""
    from localization import tr

    overlay.wait_for(SIG_READY, _calibrating)
    # Text sent before the pass starts replaces the overlay's own.
    overlay.send_text(CMD_TEXT, tr("smartcal.follow"))
    start_when_ready(overlay, trace, events, _calibrating)
    for dot, position in enumerate(layout):
        # The ready dot is the centre: a layout that starts there captures it.
        shown = None if dot == 0 and tuple(position) == (0.0, 0.0) else position
        captured = show_dot_and_capture(overlay, trace, events, dot, shown, _calibrating)
        logger.debug("NEXT smart cal: captured dot %d", dot)
        for ep, frames in captured:
            ep._next_smartcal_samples[dot] = [tuple(values) for _, *values in frames]
    overlay.send(CMD_END_PASS)
    overlay.wait_for(SIG_PASS_ENDED, _calibrating)
    events.append((time.monotonic(), "end", None))


def _show_summary(overlay, results) -> None:
    """Show the result in the headset for a few seconds, or until the overlay
    closes."""
    from smartcal_report import headset_report

    if not results:
        return
    overlay.send_text(CMD_TEXT, headset_report(results))
    deadline = time.monotonic() + _SMARTCAL_SUMMARY_S
    while time.monotonic() < deadline and var.overlay_active and overlay.process.poll() is None:
        time.sleep(0.1)


def _overlay_gaze_range(overlay):
    gaze_range = parse_overlay_gaze_range(overlay.log_text())
    if gaze_range is None:
        logger.warning("NEXT smart cal: the overlay did not report where it drew the dots. Not fitting.")
    else:
        logger.info("NEXT smart cal: overlay dots span +-%.1f deg yaw, %.1f..%.1f deg elevation.", *gaze_range[:3])
    return gaze_range


@Async
def next_smartcal_overlay(eye_processors: list, settings, baseconfig, layout=NEXT_SMARTCAL_DOTS) -> None:
    """Show the Smart Calib dots in the overlay's interactive mode and fit the
    NEXT smart-cal transform to what the eyes did."""
    if var.overlay_active:
        return
    var.overlay_active = True
    results = []
    events = []
    gaze_range = None
    trace = None
    finished = False
    started = time.monotonic()
    try:
        with OverlaySession("interactive", *calibration_range_args(settings)) as overlay:
            # Fresh sample state for this run.
            for ep in eye_processors:
                ep._next_smartcal_samples = {}
            trace = GazeTrace(eye_processors)
            try:
                _show_dots(overlay, trace, eye_processors, layout, events)
                gaze_range = _overlay_gaze_range(overlay)
                if gaze_range is not None:
                    _fit_next_smartcal(eye_processors, baseconfig, settings, gaze_range, layout, results)
                    # The chime says the gaze was recalibrated, not that only
                    # the lid/brow anchors were saved beside a kept gaze fit.
                    if gaze_fit_applied(results):
                        PlaySound(resource_path("assets/audio/completed.wav"), SND_FILENAME | SND_ASYNC)
                    finished = True
                    _show_summary(overlay, results)
            except OverlayStopped:
                logger.info("NEXT smart calibration stopped.")
            overlay.send(CMD_QUIT)
            overlay.finish()
    except TimeoutError:
        logger.warning("NEXT smart calibration timed out before completion.")
    except (OSError, struct.error) as e:
        logger.warning(
            "NEXT smart calibration overlay error (%s). Make sure SteamVR is running.",
            e,
        )
    finally:
        # Taken away first: the eye threads stop appending to it.
        traces = trace.close() if trace is not None else {}
        _save_recording_safely(traces, layout, gaze_range, settings, events, results, started)
        _publish_report(results, finished)
        var.overlay_active = False


# Each run's raw frames are kept in the log folder so that captures from any
# headset can be replayed against changes to the capture and the fit. The
# newest RECORDINGS_KEPT runs stay, at roughly 100 to 200 KB each.
RECORDING_FORMAT = 2
RECORDINGS_KEPT = 20


def _eye_key(eye) -> str:
    return str(getattr(eye, "name", eye)).lower()


def save_recording(traces: dict, layout, gaze_range, settings, events: list, results: list, started: float):
    """Write the run to ``smartcal/<time>.json`` in the log folder and return
    its path, or None when nothing was traced. ``traces`` maps each eye to
    its frames as (monotonic time, raw x, raw y, lid, brow). Times are seconds from the
    start of the run.

    Format 2: ``layout`` (normalised dot positions), ``gaze_range`` (yaw, top,
    bottom, centre in degrees, or null), ``limits`` (the output gaze limits in
    degrees), ``capture_window_s``, ``events`` as [time, kind, dot] with kind
    "ready" (dot: whether the gaze rested), then per dot "show" (not for a
    centre dot already up), "held" (its ring converged), "capture" and
    "captured" (the frames that captured it) or "unrested" (none were), and a final "end", ``eyes`` as {eye: [[time, raw x, raw y, lid, brow], ...]} with every
    frame of the run, and ``results`` (SmartCalEyeResult per fitted eye)."""
    from utils.logging_utils import log_directory

    # Frames after the last dot (the summary in the headset) say nothing.
    ended = next((at for at, kind, _ in events if kind == "end"), math.inf)
    traces = {_eye_key(eye): [f for f in frames if f[0] <= ended] for eye, frames in traces.items() if frames}
    traces = {eye: frames for eye, frames in traces.items() if frames}
    if not traces:
        return None
    recording = {
        "format": RECORDING_FORMAT,
        "layout": [list(dot) for dot in layout],
        "gaze_range": list(gaze_range) if gaze_range is not None else None,
        "limits": {
            "yaw": float(getattr(settings, "gui_gaze_yaw_max_deg", 40.0)),
            "up": float(getattr(settings, "gui_gaze_pitch_up_deg", 15.0)),
            "down": float(getattr(settings, "gui_gaze_pitch_down_deg", 40.0)),
        },
        "capture_window_s": NEXT_SMARTCAL_CAPTURE_WINDOW_S,
        "events": [[round(at - started, 4), kind, dot] for at, kind, dot in events],
        "eyes": {
            eye: [[round(at - started, 4), *(round(float(v), 5) for v in values)] for at, *values in frames]
            for eye, frames in traces.items()
        },
        "results": [{**asdict(result), "eye": _eye_key(result.eye)} for result in results],
    }
    folder = log_directory() / "smartcal"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / time.strftime("%Y%m%d-%H%M%S.json")
    path.write_text(json.dumps(recording, separators=(",", ":")), encoding="utf-8")
    for old in sorted(folder.glob("*.json"))[:-RECORDINGS_KEPT]:
        old.unlink(missing_ok=True)
    return path


def samples_from_recording(recording: dict, window_s: float | None = None) -> dict:
    """{eye: {dot: [(raw x, raw y, lid, brow), ...]}}: the samples the fit
    took from a recorded run. With ``window_s``, the frames from when each dot
    was held for that long instead.

    Format 1 recordings captured a fixed window after each dot was held."""
    if recording.get("format", 1) >= 2 and window_s is None:
        windows = []
        starts = {}
        for at, kind, dot in recording["events"]:
            if kind == "capture":
                starts[dot] = at
            elif kind == "captured" and dot in starts:
                windows.append((dot, starts[dot], at))
        return {
            eye: {dot: [tuple(values) for t, *values in frames if start <= t <= end] for dot, start, end in windows}
            for eye, frames in recording["eyes"].items()
        }
    window_s = recording["capture_window_s"] if window_s is None else window_s
    # A dot is sampled until its window closes, the next dot is held or the
    # pass ends, whichever comes first.
    marks = [(at, kind, dot) for at, kind, dot in recording["events"] if kind in ("held", "end")]
    windows = [
        (dot, at, min(at + window_s, marks[i + 1][0] if i + 1 < len(marks) else math.inf))
        for i, (at, kind, dot) in enumerate(marks)
        if kind == "held"
    ]
    samples = {}
    for eye, frames in recording["eyes"].items():
        per_dot = samples.setdefault(eye, {})
        for dot, start, end in windows:
            per_dot[dot] = [tuple(values) for t, *values in frames if start <= t <= end]
    return samples


def _save_recording_safely(*args) -> None:
    try:
        path = save_recording(*args)
        if path is not None:
            logger.info("NEXT smart cal: run recorded to %s", path)
    except Exception:
        logger.exception("NEXT smart cal: could not record the run")


def _publish_report(results, finished: bool) -> None:
    """Log what the run did."""
    try:
        from smartcal_report import log_report

        logger.info("NEXT smart cal report:\n%s", log_report(results, finished))
    except Exception:
        logger.exception("NEXT smart cal: could not build the calibration report")
