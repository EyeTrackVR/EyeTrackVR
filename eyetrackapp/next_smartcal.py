"""NEXT Smart Calibration: the overlay dot sequence, fitting the per-eye gaze
transform from it, and applying that transform.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import logging
import math
import re
import socket
import struct
import time

import numpy as np

from calibration_state import var
from next_eye_gaze import GAZE_MODE_FUSED, dominant_eye_from_settings, gaze_mode_from_settings
from utils.async_call import Async
from utils.misc_utils import PlaySound, SND_ASYNC, SND_FILENAME, resource_path
from utils.overlay_launch import OverlaySession

logger = logging.getLogger(__name__)


# ── NEXT Smart Calibration (overlay "finetune" mode, port 2112) ───────────────
#
# The overlay self-drives 11 dots and emits one big-endian int32 per dot at the
# moment it finishes shrinking and is held (capture-ready), then 100 when done:
#
#   0..4 outer pentagon, 5..9 rotated inner pentagon, 10 centre, 100 done
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
#   "angle" -> the fit above. W holds [w11, w12, w21, w22, y0, w22_up].
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
    if not (5.0 <= yaw <= 60.0 and bottom < centre < top and -60.0 <= bottom and top <= 60.0):
        return None
    return yaw, top, bottom, centre


# Five outer and five inner points. The inner pentagon is rotated halfway between
# outer rays, giving ten interleaved directions and better mid-field coverage.
# MUST match FINETUNE_POS order in the overlay's modes.cpp. Normalised
# overlay coordinates (+-1 = edge of the overlay's gaze range); the angle each
# dot sits at comes from next_smartcal_dot_tangents().
NEXT_SMARTCAL_DOTS = (
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
NEXT_SMARTCAL_DONE_SIGNAL = 100


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


def smartcal_tangents_to_gaze(tan_x: float, tan_y: float, settings):
    """Output gaze for a true gaze direction: its tangent as a fraction of the
    configured limit on that side (not clipped). The inverse of how the
    outputs read gaze, atan(gaze * tan(limit))."""

    def limit(name, default):
        return math.tan(math.radians(min(89.0, max(1.0, float(getattr(settings, name, default))))))

    pitch = ("gui_gaze_pitch_up_deg", 15.0) if tan_y >= 0.0 else ("gui_gaze_pitch_down_deg", 40.0)
    return tan_x / limit("gui_gaze_yaw_max_deg", 40.0), tan_y / limit(*pitch)


# The overlay holds each dot for 0.5 s (DC_HOLD_S in modes.cpp) after emitting
# its signal, then the NEXT dot appears/shrinks for ~0.65 s before ITS signal,
# during which the user is already following the new dot. Samples must
# therefore stop shortly before the hold ends, or ~55% of each dot's window is
# fixation on the WRONG dot and the fit degenerates (observed as gains of 10-200
# in the wild). Kept slightly under the hold so frame timing jitter can't leak
# transition frames in.
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


def next_smartcal_apply(w, b, warp, x_raw, y_raw):
    """Map a raw NEXT gaze (x_raw, y_raw) through a stored transform, into the
    space that fit lives in: gaze tangents for "angle", output-normalised gaze
    for the legacy fits. next_smartcal_gaze is the one that returns output."""
    if warp == SMARTCAL_SPACE_ANGLE:
        x, y = float(x_raw), float(y_raw)
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
    w11, w12, w21, w22, y0, w22_up = (float(v) for v in w)
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
            pieces = _angle_pieces(w, b)
        except (TypeError, ValueError, IndexError):
            return False
        return all(_affine_is_sane(pw, pb, None) for pw, pb in pieces)
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
    return [*(float(v) * r for v in cw), float(w[4]), up * r], [float(v) * r for v in cb], clamped


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
    medians = {}
    for dot in range(dot_count):
        pts = samples.get(dot, [])
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


def _solve_angle_fit(medians: dict, tangents, layout):
    """Weighted least-squares angle fit (see the module header) of the captured
    dots, as (w, b). None when the solve fails."""
    dots = sorted(medians)
    R = np.asarray([medians[d] for d in dots], dtype=np.float64)  # N x 2 raw gaze
    T = np.asarray([tangents[d] for d in dots], dtype=np.float64)  # N x 2 dot tangents
    gx, gy = R[:, 0], R[:, 1]
    A = np.column_stack([gx, gy, np.ones(len(R))])  # N x 3  [gx, gy, 1]
    # The separate upward gain needs the centre capture to hinge on and a
    # couple of dots on each side of it; otherwise one gain serves both.
    centres = [d for d in _centre_dots(layout) if d in medians]
    above = sum(layout[d][1] > 0.0 for d in dots)
    below = sum(layout[d][1] < 0.0 for d in dots)
    hinge = bool(centres) and above >= 2 and below >= 2
    y0 = float(np.mean([medians[d][1] for d in centres])) if hinge else 0.0
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
    return [float(sol_x[0]), float(sol_x[1]), float(sol_y[0]), w22, y0, w22_up], [float(sol_x[2]), float(sol_y[2])]


def _fit_next_smartcal(eye_processors: list, baseconfig, settings, gaze_range=None, layout=NEXT_SMARTCAL_DOTS) -> bool:
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

    Returns True if at least one eye produced a usable transform (and was saved)."""
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
        if len(dots) < _SMARTCAL_MIN_DOTS:
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
            continue

        solved = _solve_angle_fit(medians, tangents, layout)
        if solved is None:
            continue
        w, b = solved

        # Diagnostic dump (INFO so it shows without debug config): each held
        # dot's raw median, where the dot really is, and how far the fit lands
        # from it. Rings that do not separate in raw mean the model output is
        # plateauing; a sign inverted against the dot means the capture is
        # flipped; wide scatter means a noisy follow.
        errors = _fit_errors_deg(w, b, medians, tangents)
        truth = np.degrees(np.arctan(T))
        logger.info(
            "NEXT smart cal (eye %s) captures: dot raw -> dot angle (yaw, pitch deg), fit error (deg):\n%s",
            eye,
            "\n".join(
                f"  {d:2d} ({R[i, 0]:+.3f}, {R[i, 1]:+.3f}) -> ({truth[i, 0]:+5.1f}, {truth[i, 1]:+5.1f})"
                f"  err ({errors[i, 0]:+.1f}, {errors[i, 1]:+.1f})"
                for i, d in enumerate(dots)
            ),
        )

        # A usable fit must land close to its own fitting points AND look like
        # a gentle polish. Otherwise keep whatever the user had before.
        residual = float(np.mean(np.hypot(errors[:, 0], errors[:, 1])))
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
            continue

        for dst in eye_processors if shared_fit else (ep,):
            dst.config.next_smartcal_w = list(w)
            dst.config.next_smartcal_b = list(b)
            dst.config.next_smartcal_warp = SMARTCAL_SPACE_ANGLE
            dst._next_smartcal_w = list(w)
            dst._next_smartcal_b = list(b)
            dst._next_smartcal_warp = SMARTCAL_SPACE_ANGLE
        saved_any = True
        logger.info(
            "NEXT smart cal (eye %s%s): fit from %d dots: W=%s B=%s, mean error %.1f deg "
            "(worst %.1f), vertical gain up/down %.2f",
            eye,
            ", dominant: applied to both eyes" if shared_fit else "",
            len(dots),
            [round(v, 4) for v in w],
            [round(v, 4) for v in b],
            residual,
            float(np.max(np.hypot(errors[:, 0], errors[:, 1]))),
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


@Async
def next_smartcal_overlay(eye_processors: list, settings, baseconfig) -> None:
    """Drive the overlay "finetune" routine and fit the NEXT smart-cal transform.

    Self-driving overlay: no commands sent, no 255 handshake. It emits int32
    signals 0..10 (capture each dot) then 100 (done) on UDP 127.0.0.1:2112.
    """
    if var.overlay_active:
        return
    var.overlay_active = True
    try:
        with OverlaySession("finetune") as overlay:
            # Fresh sample state for this run.
            for ep in eye_processors:
                ep._next_smartcal_active_dot = None
                ep._next_smartcal_samples = {}

            while var.overlay_active:
                try:
                    data = overlay.recv(16)
                except socket.timeout:
                    logger.warning("NEXT smart calibration timed out before completion.")
                    break
                if not data or len(data) < 4:
                    continue

                signal = struct.unpack(">i", data[:4])[0]

                if 0 <= signal < len(NEXT_SMARTCAL_DOTS):
                    # Dot is held and capture-ready: start sampling it. The sampler
                    # (NEXTM) only accepts frames within NEXT_SMARTCAL_CAPTURE_WINDOW_S
                    # of this timestamp; the overlay's hold is 0.5 s, after which the
                    # user is already saccading to / following the next dot.
                    logger.debug("NEXT smart cal: capturing dot %d", signal)
                    _t0 = time.monotonic()
                    for ep in eye_processors:
                        ep._next_smartcal_dot_started = _t0
                        ep._next_smartcal_active_dot = signal
                elif signal == NEXT_SMARTCAL_DONE_SIGNAL:
                    # All dots done: stop sampling and fit.
                    for ep in eye_processors:
                        ep._next_smartcal_active_dot = None
                    gaze_range = parse_overlay_gaze_range(overlay.log_text())
                    if gaze_range is None:
                        logger.warning("NEXT smart cal: the overlay did not report its gaze range; assuming defaults.")
                    else:
                        logger.info(
                            "NEXT smart cal: overlay dots span +-%.1f deg yaw, %.1f..%.1f deg elevation.",
                            *gaze_range[:3],
                        )
                    if _fit_next_smartcal(eye_processors, baseconfig, settings, gaze_range):
                        PlaySound(resource_path("assets/audio/completed.wav"), SND_FILENAME | SND_ASYNC)
                    overlay.finish()
                    break
    except (OSError, struct.error) as e:
        logger.warning(
            "NEXT smart calibration overlay error (%s). Make sure SteamVR is running.",
            e,
        )
    finally:
        for ep in eye_processors:
            ep._next_smartcal_active_dot = None
        var.overlay_active = False
