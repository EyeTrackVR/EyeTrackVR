"""NEXT Smart Calibration: the overlay dot sequence, fitting the per-eye gaze
transform from it, and applying that transform.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import logging
import math
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
# Those positions are the regression *targets*: when the user fixates a dot, their
# true gaze equals the dot direction. We pair each dot's known position with
# the median raw NEXT gaze captured while it was held, then least-squares fit a
# per-eye transform that maps raw model output onto true gaze.
#
# The transform is a per-eye AFFINE fit (optionally in an arctanh-warped space;
# see ``warp`` below):
#     x_cal = w11*xr + w12*yr + b1
#     y_cal = w21*xr + w22*yr + b2
# W carries scale / roll / anisotropy, B the offset. Because the NEXT model
# UNDER-DRIVES its output range (measured: raw gaze only reaches ~±0.6 even at
# full gaze, and never saturates near ±1), the affine gain is > 1 (~1.5-2x) to
# stretch that onto the full ±1 output. That gain also multiplies raw jitter, so
# the model output MUST be de-spiked first (see _GAZE_MEDIAN_WINDOW in
# next_model.py) or a single noisy frame snaps the calibrated output to a corner.
#
# ``warp`` selects the fit space and is stored with the transform:
#   None    → plain raw-space affine. This is the DEFAULT, because this model
#             family under-drives (no saturation to undo); a warp would only add
#             gain where the model's range lives and amplify edge jitter.
#   "atanh" → fit in arctanh(raw) space (the inverse of a tanh output). Only
#             useful for a model that genuinely SATURATES (pins near ±1 for
#             moderate gaze); kept available for that case and to load such fits.

# arctanh blows up at ±1; clamp the raw magnitude just inside so a fully pinned
# sample maps to a large-but-finite warped value instead of inf.
_SMARTCAL_WARP_CLAMP = 0.999
# Default fit space. None = plain affine (right for this under-driving model);
# set to "atanh" only if a future model is shown to saturate.
_SMARTCAL_WARP = None


# Overlay finetune dot-placement caps (degrees), mirroring the overlay's fov.h
# defaults (max_deg / max_deg_up / max_deg_down). The finetune mode launches with
# no CLI args, so these fixed defaults are always in effect. The overlay places a
# dot at overlay-normalized n at physical angle atan(n * tan(cap)) which is linear in
# TANGENT out to these oculomotor caps. Keep in sync if the overlay's finetune
# caps change. (Assumes the caps bind, true on wide-FOV HMDs; if the overlay's
# coverage clamp binds instead the true dot angle is a touch smaller, which only
# makes the derived targets slightly conservative and never larger than the old
# radius-as-target behaviour, so headroom is never lost.)
_SMARTCAL_OVERLAY_CAP_YAW = 30.0
_SMARTCAL_OVERLAY_CAP_UP = 15.0
_SMARTCAL_OVERLAY_CAP_DOWN = 40.0


# Five outer and five inner points. The inner pentagon is rotated halfway between
# outer rays, giving ten interleaved directions and better mid-field coverage.
# MUST match FINETUNE_POS
# order in the overlay's modes.cpp. This is where each dot is DRAWN; the value
# it is FIT to (its calibration target) is derived separately by
# next_smartcal_targets() so the inset outer ring is not treated as full-scale.
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


def next_smartcal_targets(settings):
    """Calibration fit target (output-normalized gaze) for each overlay dot.

    The overlay draws a dot at overlay-normalized (nx, ny), which physically sits
    at atan(n * tan(overlay_cap)) which is an oculomotor-limited eccentricity INSIDE the
    display FOV. Fitting the outer ring straight to its overlay radius (~0.90)
    makes that inset dot ≈full output, so calibrated gaze clips at the oculomotor
    cap: the eye can travel further toward the FOV edge but the output is already
    pinned ("can't reach the edge").

    Instead, express each dot as its fraction of the OUTPUT full-scale FOV
    (config gui_gaze_*_max_deg which is the angle ±1 maps to). Both the overlay
    placement and the output angle are tangent-linear, so per axis:

        target = overlay_norm * tan(overlay_cap) / tan(output_edge)

    With the edge set wider than the cap (40 vs 30 yaw → ~×0.69) the targets
    shrink, leaving headroom ABOVE the outer ring. In-range angles are unchanged
    (a dot still renders at its true physical angle through the wider full-scale);
    the model's output then extrapolates through that headroom to ±1 as the eye
    continues to the edge. The y axis uses the up/down cap+edge by the sign of ny;
    the centre offset (overlay center_deg) is absorbed by the affine bias as
    before. Edges are floored at their cap (an edge inside the cap would re-pin
    the output) and kept below 90° so tan stays finite."""

    def _edge(name, cap):
        e = float(getattr(settings, name, cap))
        return min(89.0, max(cap, e))

    edge_yaw = _edge("gui_gaze_yaw_max_deg", _SMARTCAL_OVERLAY_CAP_YAW)
    edge_up = _edge("gui_gaze_pitch_up_deg", _SMARTCAL_OVERLAY_CAP_UP)
    edge_down = _edge("gui_gaze_pitch_down_deg", _SMARTCAL_OVERLAY_CAP_DOWN)
    kx = math.tan(math.radians(_SMARTCAL_OVERLAY_CAP_YAW)) / math.tan(math.radians(edge_yaw))
    k_up = math.tan(math.radians(_SMARTCAL_OVERLAY_CAP_UP)) / math.tan(math.radians(edge_up))
    k_down = math.tan(math.radians(_SMARTCAL_OVERLAY_CAP_DOWN)) / math.tan(math.radians(edge_down))
    targets = []
    for nx, ny in NEXT_SMARTCAL_DOTS:
        ky = k_up if ny >= 0.0 else k_down
        targets.append((nx * kx, ny * ky))
    return targets


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
# Sanity bounds for an accepted transform. The smart cal is a gentle per-user
# polish: singular values of W (direction-independent gains) must stay within
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
# A consistent fit (residual guard passed) that only overshoots those bounds
# moderately is CLAMPED onto them instead of thrown away: the weak tiny models
# under-read so much (held-out ETVR micro gaze_y gain ~0.31) that ~1/3 of users
# needed > 3.2x and ran fully uncalibrated. Simulated on held-out people,
# clamping kept the per-frame error and lifted vertical gain 0.31 -> 0.71
# (ETVR micro) / 0.62 -> 0.73 (BSB micro); the full model was unaffected.
# Beyond this factor over the bound the fit is still treated as degenerate
# (the bad captures seen in the wild were 10-200x).
_SMARTCAL_CLAMP_FACTOR = 2.0
# Mean L2 distance between the fitted mapping of the captured points and their
# targets. A transform that can't get within this of its OWN fitting points is
# fitting noise.
_SMARTCAL_MAX_RESIDUAL = 0.20
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
    """Map a raw NEXT gaze (x_raw, y_raw) through the (warp + affine) transform.

    ``warp`` is "atanh" for new fits or None for legacy raw-space affine
    transforms saved by older builds."""
    gx = _smartcal_warp_scalar(x_raw, warp)
    gy = _smartcal_warp_scalar(y_raw, warp)
    x_cal = w[0] * gx + w[1] * gy + b[0]
    y_cal = w[2] * gx + w[3] * gy + b[1]
    return x_cal, y_cal


def next_smartcal_transform_is_sane(w, b, warp=None) -> bool:
    """True if a smart-cal transform (W row-major [w11,w12,w21,w22], B [b1,b2],
    fit in the space selected by ``warp``) is plausibly a gentle per-user polish
    rather than a degenerate fit.

    Checked both when fitting (before save) and when loading from config, so
    garbage transforms persisted by older builds are ignored instead of
    pinning the gaze output to the clip bounds."""
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
    """Pull a moderately over-bound fit onto the sanity bounds.

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


def _fit_next_smartcal(eye_processors: list, baseconfig, settings) -> bool:
    """Least-squares fit a per-eye affine gaze transform from collected samples.

    Each output axis is fit independently as a 3-unknown affine on the per-dot
    raw medians with optional arctanh warping first. This is off by default. See the module
    header for why this model uses a plain affine):
        x_cal = w11*gx + w12*gy + b1
        y_cal = w21*gx + w22*gy + b2   (gx, gy = raw, or arctanh(raw) if warping)

    Targets come from next_smartcal_targets(settings): each dot is fit to its
    fraction of the output full-scale FOV, not its overlay radius, so the outer
    ring keeps headroom to the edge (see that function).

    In the per-eye gaze modes (gui_NEXT_gaze_mode, see next_eye_gaze) the gaze
    transform is fit ONCE, on the dominant eye, and applied to both eyes. Each
    eye's own fit would pull it onto the dots and erase exactly the deviation
    independent mode exists to show; the dominant eye is the one that actually
    fixates them. Both eyes share one monocular head, so one user-level
    correction fits both. (Lid/brow anchors stay per eye.)

    Returns True if at least one eye produced a usable transform (and was saved)."""
    targets = next_smartcal_targets(settings)
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
        samples = getattr(ep, "_next_smartcal_samples", {}) or {}
        raws, tgts, fit_weights = [], [], []
        for dot in range(len(NEXT_SMARTCAL_DOTS)):
            pts = samples.get(dot, [])
            if len(pts) < _SMARTCAL_MIN_SAMPLES_PER_DOT:
                logger.debug(
                    "NEXT smart cal (eye %s): dot %d has %d samples (<%d): dropped.",
                    eye,
                    dot,
                    len(pts),
                    _SMARTCAL_MIN_SAMPLES_PER_DOT,
                )
                continue
            arr = np.asarray(pts, dtype=np.float64)
            # Median over the hold window rejects blinks / transient outliers.
            raws.append([float(np.median(arr[:, 0])), float(np.median(arr[:, 1]))])
            tgts.append(targets[dot])
            fit_weights.append(_SMARTCAL_CENTER_WEIGHT if dot == len(NEXT_SMARTCAL_DOTS) - 1 else 1.0)

        if len(raws) < _SMARTCAL_MIN_DOTS:
            logger.warning(
                "NEXT smart cal (eye %s): only %d/%d dots captured (<%d); skipping fit.",
                eye,
                len(raws),
                len(NEXT_SMARTCAL_DOTS),
                _SMARTCAL_MIN_DOTS,
            )
            continue

        R = np.asarray(raws, dtype=np.float64)  # N x 2 raw gaze
        T = np.asarray(tgts, dtype=np.float64)  # N x 2 target gaze

        # Diagnostic dump (INFO so it shows without debug config): the captured
        # raw median for each held dot against its target. Lets a rejected fit be
        # read straight from the log when the raw pairs do not separate the rings
        # (inner ≈ outer) the model output is plateauing; if a sign is inverted
        # vs the target the capture is flipped; wide scatter = noisy follow.
        logger.info(
            "NEXT smart cal (eye %s) captures [raw]->[target]  (samples/dot=%s):\n%s",
            eye,
            {d: len(samples.get(d, [])) for d in range(len(NEXT_SMARTCAL_DOTS))},
            "\n".join(f"  ({R[i, 0]:+.3f}, {R[i, 1]:+.3f}) -> ({T[i, 0]:+.3f}, {T[i, 1]:+.3f})" for i in range(len(R))),
        )

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

        warp = _SMARTCAL_WARP
        if warp == "atanh":
            # De-saturate into a space where a saturating model is ~linear in
            # true gaze. This is off by default because this model under drives. See the header.
            Rc = np.clip(R, -_SMARTCAL_WARP_CLAMP, _SMARTCAL_WARP_CLAMP)
            G = np.arctanh(Rc)
        else:
            G = R  # plain raw-space affine
        gx = G[:, 0]
        gy = G[:, 1]
        ones = np.ones(len(G))
        A = np.column_stack([gx, gy, ones])  # N x 3  [gx, gy, 1]
        # Weighted least squares. Multiplying rows by sqrt(weight) makes the
        # centre anchor count more without duplicating or over-sampling frames.
        sw = np.sqrt(np.asarray(fit_weights, dtype=np.float64))
        Aw = A * sw[:, None]
        Tx = T[:, 0] * sw
        Ty = T[:, 1] * sw
        try:
            sol_x, *_ = np.linalg.lstsq(Aw, Tx, rcond=None)  # [w11, w12, b1]
            sol_y, *_ = np.linalg.lstsq(Aw, Ty, rcond=None)  # [w21, w22, b2]
        except np.linalg.LinAlgError as e:
            logger.warning("NEXT smart cal (eye %s): solve failed: %s", eye, e)
            continue

        w = [float(sol_x[0]), float(sol_x[1]), float(sol_y[0]), float(sol_y[1])]  # [w11, w12, w21, w22]
        b = [float(sol_x[2]), float(sol_y[2])]  # [b1, b2]

        # A usable fit must land close to its own fitting points AND look like
        # a gentle polish. Otherwise keep whatever the user had before.
        pred_x = A @ sol_x
        pred_y = A @ sol_y
        residual = float(np.mean(np.hypot(pred_x - T[:, 0], pred_y - T[:, 1])))
        if residual > _SMARTCAL_MAX_RESIDUAL:
            logger.warning(
                "NEXT smart cal (eye %s): fit residual %.3f exceeds %.2f "
                "(attempted W=%s B=%s): captures look inconsistent. Keeping "
                "previous calibration.",
                eye,
                residual,
                _SMARTCAL_MAX_RESIDUAL,
                [round(v, 4) for v in w],
                [round(v, 4) for v in b],
            )
            continue
        w_fit, b_fit = w, b
        w, b, clamped = clamp_next_smartcal_transform(w, b)
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
        if not next_smartcal_transform_is_sane(w, b, warp):
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
            dst.config.next_smartcal_warp = warp
            dst._next_smartcal_w = list(w)
            dst._next_smartcal_b = list(b)
            dst._next_smartcal_warp = warp
        saved_any = True
        logger.info(
            "NEXT smart cal (eye %s%s): fit from %d dots (warp=%s): W=%s B=%s (residual %.3f)",
            eye,
            ", dominant: applied to both eyes" if shared_fit else "",
            len(raws),
            warp,
            [round(v, 4) for v in w],
            [round(v, 4) for v in b],
            residual,
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
                    if _fit_next_smartcal(eye_processors, baseconfig, settings):
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
