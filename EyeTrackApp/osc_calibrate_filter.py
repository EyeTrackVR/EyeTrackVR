"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import logging
import numpy as np
import time
from enum import IntEnum
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC, resource_path
from utils.eye_falloff import velocity_falloff
from utils.logging_utils import TrackingLogger
import socket
import struct
import sys
import threading
import os
import subprocess
import math
from utils.calibration_3d import receive_calibration_data, converge_3d
from utils.calibration_elipse import *
from utils.misc_utils import resource_path
from utils.robust_calibration import RobustCalibrationSession, CalibrationPhase
from utils.bs_detector import BSDetector
from pathlib import Path

logger = logging.getLogger(__name__)


def _overlay_executable() -> str:
    """Resolve the in-VR calibration overlay binary for this platform.

    Windows builds ship ``Tools/EyeTrackVR-Overlay.exe``. On Linux/macOS we
    look for a native binary of the same name (no extension) so a future port
    dropped into Tools/ lights up automatically. Raises FileNotFoundError when
    unavailable; callers' existing except/finally blocks log it and reset
    calibration state, so on-screen calibration remains usable.
    """
    name = "EyeTrackVR-Overlay.exe" if sys.platform == "win32" else "EyeTrackVR-Overlay"
    path = resource_path(f"Tools/{name}")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"in-VR overlay binary not found at {path}; overlay calibration "
            "currently ships with Windows builds only"
        )
    return path

tool = Path("Tools")


class TimeoutError(RuntimeError):
    pass


class AsyncCall(object):
    def __init__(self, fnc, callback=None):
        self.callable = fnc
        self.callback = callback

    def __call__(self, *args, **kwargs):
        self.thread = threading.Thread(
            target=self.run, name=self.callable.__name__, args=args, kwargs=kwargs
        )
        self.thread.start()
        return self

    def wait(self, timeout=None):
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise TimeoutError()
        else:
            return self.result

    def run(self, *args, **kwargs):
        self.result = self.callable(*args, **kwargs)
        if self.callback:
            self.callback(self.result)


class AsyncMethod(object):
    def __init__(self, fnc, callback=None):
        self.callable = fnc
        self.callback = callback

    def __call__(self, *args, **kwargs):
        return AsyncCall(self.callable, self.callback)(*args, **kwargs)


def Async(fnc=None, callback=None):
    if fnc is None:

        def add_async_callback(fnc):
            return AsyncMethod(fnc, callback)

        return add_async_callback
    else:
        return AsyncMethod(fnc, callback)


class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3


class var:
    # Per-eye velocity state. Both eye threads call cal_osc concurrently, so
    # everything that's read across eyes (velocity, last-seen position) must
    # be stored per side; otherwise eye B's "delta from previous frame"
    # computation silently uses eye A's last position as the baseline.
    # Keyed by EyeId.LEFT / EyeId.RIGHT.
    past_xy: dict = {}
    last_t: dict = {}
    velocity_rolling: dict = {}
    kp_past: dict = {}
    kp_rolling: dict = {}
    r_eye_x = 0.0
    l_eye_x = 0.0
    left_y = 0.0
    right_y = 0.0
    l_eye_velocity = 0.0
    r_eye_velocity = 0.0
    l_keypoint_noise = 0.0
    r_keypoint_noise = 0.0
    l_eye_openness = 1.0
    r_eye_openness = 1.0
    overlay_active = False
    falloff_latch = False
    single_eye = True
    left_enb = 0
    right_enb = 0
    eye_wait = 10
    left_calib = False
    right_calib = False
    completed_3d_calib = 0


_VEL_WINDOW = 15
_KP_WINDOW = 15
# Cap dt at 1s to keep a long pause (tab switch, breakpoint, etc.) from
# producing a single divide-by-tiny-dt that pollutes the rolling average.
_MAX_DT = 1.0


def _update_eye_velocity(eye_id, out_x, out_y, now):
    """Compute a smoothed per-eye velocity and write it into ``var.{l,r}_eye_velocity``
    so the downstream falloff heuristic has real numbers to compare. Returns
    the instantaneous magnitude (used by the noise map)."""
    prev = var.past_xy.get(eye_id)
    last_t = var.last_t.get(eye_id, now)
    var.past_xy[eye_id] = (out_x, out_y)
    var.last_t[eye_id] = now
    if prev is None:
        return 0.0
    dt = now - last_t
    if dt <= 0 or dt > _MAX_DT:
        return 0.0
    dx = out_x - prev[0]
    dy = out_y - prev[1]
    # Magnitude in normalized-gaze units per second. Scale-free; the falloff
    # comparison is relative between the two eyes so absolute units don't matter.
    inst = math.sqrt(dx * dx + dy * dy) / dt

    bucket = var.velocity_rolling.setdefault(eye_id, [])
    bucket.append(inst)
    if len(bucket) > _VEL_WINDOW:
        del bucket[0]
    smoothed = sum(bucket) / len(bucket)

    if eye_id == EyeId.LEFT:
        var.l_eye_velocity = smoothed
    elif eye_id == EyeId.RIGHT:
        var.r_eye_velocity = smoothed
    return inst


def _update_keypoint_noise(eye_id, cx, cy, roi_diag):
    """Track raw pupil-keypoint jitter as a self-computed confidence signal.

    Frame-to-frame displacement of (cx, cy) normalised by the ROI diagonal
    gives a scale-free noise estimate: smooth tracking → low value, jittery
    detection → high value.  Higher jitter means the tracker is less confident
    even if the calibrated output hasn't moved much.
    """
    prev = var.kp_past.get(eye_id)
    var.kp_past[eye_id] = (cx, cy)
    if prev is None or roi_diag < 1.0:
        return
    dx = cx - prev[0]
    dy = cy - prev[1]
    inst = math.sqrt(dx * dx + dy * dy) / roi_diag
    bucket = var.kp_rolling.setdefault(eye_id, [])
    bucket.append(inst)
    if len(bucket) > _KP_WINDOW:
        del bucket[0]
    smoothed = sum(bucket) / len(bucket)
    if eye_id == EyeId.LEFT:
        var.l_keypoint_noise = smoothed
    elif eye_id == EyeId.RIGHT:
        var.r_keypoint_noise = smoothed


@Async
def center_overlay_calibrate(self):
    if var.overlay_active:
        return
    sock = None
    try:
        overlay_path = _overlay_executable()
        # Set working directory to the tools folder so overlay can find assets/Purple_Dot.png
        tools_dir = os.path.dirname(overlay_path)
        # Bind before launching the overlay so no UDP packets are dropped due to
        # the socket not being ready when the overlay sends its first signal.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 2112))
        subprocess.Popen(
            [overlay_path, "center"],
            cwd=tools_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        var.overlay_active = True
        data, _ = sock.recvfrom(4096)
        struct.unpack("!l", data)[0]  # value currently unused; kept for protocol parity
    except (OSError, FileNotFoundError, struct.error) as e:
        logger.warning(
            "Center-overlay calibration failed (%s). Make sure SteamVR is running.",
            e,
        )
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self.settings.gui_recenter_eyes = False
        self.calibration_start_time = None
        var.overlay_active = False


@Async
def overlay_calibrate_3d(self):
    if var.overlay_active:
        return
    sock = None
    try:
        overlay_path = _overlay_executable()
        # Set working directory to the tools folder so overlay can find assets/Purple_Dot.png
        tools_dir = os.path.dirname(overlay_path)
        # Bind before launching the overlay so no UDP packets are dropped due to
        # the socket not being ready when the overlay sends its first signal.
        # Bind once and reuse across messages; rebinding the same port every
        # iteration would race the OS releasing it on close.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 2112))
        subprocess.Popen(
            [overlay_path],
            cwd=tools_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        var.overlay_active = True
        while var.overlay_active:
            data, _ = sock.recvfrom(4096)
            message = struct.unpack("!l", data)[0]
            self.settings.gui_recenter_eyes = False
            self.settings.grab_3d_point = True
            logger.debug("3D overlay calibration message: %s", message)
            if message == 9:
                var.overlay_active = False
    except (OSError, FileNotFoundError, struct.error) as e:
        logger.warning(
            "3D calibration overlay error (%s). Make sure SteamVR is running.",
            e,
        )
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self.settings.gui_recenter_eyes = False
        var.overlay_active = False


# ── DFR output helpers ────────────────────────────────────────────────────────
# Unclamped gaze vector for Dynamic Foveated Rendering (OpenXR toolkit etc.)
# Packet format: 1 uint8 (eye_id) + 2 float32 (x, y) = 9 bytes per datagram.

_dfr_socket: socket.socket | None = None
_dfr_socket_lock = threading.Lock()


def _get_dfr_socket() -> socket.socket:
    global _dfr_socket
    with _dfr_socket_lock:
        if _dfr_socket is None:
            _dfr_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return _dfr_socket


def _dispatch_dfr(settings, eye_id: int, x: float, y: float) -> None:
    try:
        addr = getattr(settings, "gui_dfr_address", "127.0.0.1")
        port = int(getattr(settings, "gui_dfr_port", 9002))
        payload = struct.pack("!Bff", eye_id & 0xFF, float(x), float(y))
        _get_dfr_socket().sendto(payload, (addr, port))
    except Exception:
        pass


# ── Robust calibration persistence helper ─────────────────────────────────────

def _save_robust_calib(eye_processor) -> None:
    """Serialize RobustCalibrationSession → config → disk."""
    try:
        robust_cal: RobustCalibrationSession = eye_processor.robust_cal
        eye_processor.config.robust_calib_data = robust_cal.to_dict()
        eye_processor.baseconfig.save()
    except Exception as e:
        logger.warning("Failed to save robust calibration: %s", e)


def _mark_next_classic_calibration_active(eye_processor) -> None:
    """Record whether the latest ellipse fit belongs to NEXT or a pixel tracker."""
    eye_processor.config.next_classic_calibration_active = bool(
        getattr(eye_processor, "_next_active", False)
    )


# ── Overlay ellipse calibration (port 2112) ───────────────────────────────────
#
# The overlay animates the dot in a shrinking spiral and sends two signals:
#   int32(0) → start continuous per-frame sampling
#   int32(9) → stop sampling, fit and save the ellipse
#
# cal_osc accumulates raw cx/cy into CalibrationEllipse every frame while
# _ellipse_collect_active is set.  The std-deviation fit benefits from many
# uniformly distributed samples, so continuous collection is better than
# per-point IQR grabs.


@Async
def overlay_ellipse_calibrate(eye_processors: list, settings, baseconfig) -> None:
    """
    Launch the overlay in ellipse-calibration (spiral) mode and drive classic
    CalibrationEllipse per eye via continuous frame sampling.
    """
    if var.overlay_active:
        return
    sock = None
    try:
        overlay_path = _overlay_executable()
        tools_dir = os.path.dirname(overlay_path)
        # Bind before launching the overlay so no UDP packets are dropped while
        # the socket is not yet ready. The overlay may send signal 0 almost
        # immediately after startup; if Python hasn't bound by then, that packet
        # is silently discarded and the calibration never starts collecting.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(120.0)
        sock.bind(("127.0.0.1", 2112))
        subprocess.Popen(
            [overlay_path, "ellipse"],
            cwd=tools_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        var.overlay_active = True

        # Reset calibration samples so this run starts fresh
        for ep in eye_processors:
            ep.cal.xs = []
            ep.cal.ys = []
            ep.cal.fitted = False

        while var.overlay_active:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                logger.warning("Overlay ellipse calibration timed out")
                # Save a partial fit if samples were collected before the timeout.
                # This handles the case where signal 0 was received and the spiral
                # ran but signal 9 never arrived before the deadline.
                _saved_partial = False
                for ep in eye_processors:
                    ep._ellipse_collect_active = False
                    if len(ep.cal.xs) >= 2:
                        evecs, axes = ep.cal.fit_ellipse()
                        if not (isinstance(evecs, int) and isinstance(axes, int)
                                and evecs == 0 and axes == 0):
                            ep.config.calib_evecs = list(
                                evecs.tolist() if hasattr(evecs, "tolist") else evecs)
                            ep.config.calib_axes = list(
                                axes.tolist() if hasattr(axes, "tolist") else axes)
                            if ep.cal.center is not None:
                                ep.config.calib_XOFF = float(ep.cal.center[0])
                                ep.config.calib_YOFF = float(ep.cal.center[1])
                            _mark_next_classic_calibration_active(ep)
                            ep.baseconfig.save()
                            logger.info(
                                "Ellipse cal: partial fit saved from %d samples (timeout)",
                                len(ep.cal.xs),
                            )
                            _saved_partial = True
                if _saved_partial:
                    settings.calib_mode = "classic"
                    PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)
                break
            if not data or len(data) < 4:
                continue

            signal = struct.unpack("!l", data)[0]

            if signal == 0:
                # Start continuous per-frame sampling
                logger.debug("Overlay ellipse calibration: sampling started")
                for ep in eye_processors:
                    ep._ellipse_collect_active = True

            elif signal == 9:
                # Stop sampling, fit, and save
                for ep in eye_processors:
                    ep._ellipse_collect_active = False
                    evecs, axes = ep.cal.fit_ellipse()
                    if not (isinstance(evecs, int) and isinstance(axes, int)
                            and evecs == 0 and axes == 0):
                        ep.config.calib_evecs = list(evecs.tolist()
                                                     if hasattr(evecs, "tolist") else evecs)
                        ep.config.calib_axes = list(axes.tolist()
                                                    if hasattr(axes, "tolist") else axes)
                        if ep.cal.center is not None:
                            ep.config.calib_XOFF = float(ep.cal.center[0])
                            ep.config.calib_YOFF = float(ep.cal.center[1])
                        _mark_next_classic_calibration_active(ep)
                        ep.baseconfig.save()
                        logger.info(
                            "Ellipse cal: fitted from %d samples", len(ep.cal.xs)
                        )
                settings.calib_mode = "classic"
                PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)
                var.overlay_active = False
                break

    except (OSError, FileNotFoundError, struct.error) as e:
        logger.warning("Ellipse overlay calibration error: %s", e)
    finally:
        # Always clear collect flag so cal_osc doesn't keep sampling
        for ep in eye_processors:
            ep._ellipse_collect_active = False
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        var.overlay_active = False


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
# dot at overlay-normalized n at physical angle atan(n * tan(cap)) — linear in
# TANGENT out to these oculomotor caps. Keep in sync if the overlay's finetune
# caps change. (Assumes the caps bind, true on wide-FOV HMDs; if the overlay's
# coverage clamp binds instead the true dot angle is a touch smaller, which only
# makes the derived targets slightly conservative — never larger than the old
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
    (0.0, 0.8), (0.760845, 0.247214), (0.470228, -0.647214),
    (-0.470228, -0.647214), (-0.760845, 0.247214),
    (0.246870, 0.339787), (0.399444, -0.129787), (0.0, -0.42),
    (-0.399444, -0.129787), (-0.246870, 0.339787), (0.0, 0.0),
)
NEXT_SMARTCAL_DONE_SIGNAL = 100


def next_smartcal_targets(settings):
    """Calibration fit target (output-normalized gaze) for each overlay dot.

    The overlay draws a dot at overlay-normalized (nx, ny), which physically sits
    at atan(n * tan(overlay_cap)) — an oculomotor-limited eccentricity INSIDE the
    display FOV. Fitting the outer ring straight to its overlay radius (~0.90)
    makes that inset dot ≈full output, so calibrated gaze clips at the oculomotor
    cap: the eye can travel further toward the FOV edge but the output is already
    pinned ("can't reach the edge").

    Instead, express each dot as its fraction of the OUTPUT full-scale FOV
    (config gui_gaze_*_max_deg — the angle ±1 maps to). Both the overlay
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
_SMARTCAL_MAX_GAIN = 1.75
_SMARTCAL_MIN_GAIN = 0.08
_SMARTCAL_MAX_BIAS = 0.30
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
# so no fold-back / monotonicity walk is needed — that was only for the old
# cubic.) The limit leaves headroom for a real per-user gain without allowing
# half gaze to clip at the output edge.
_SMARTCAL_SANITY_EARLY_R = 0.50
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
        pooled = [
            s for pts in (getattr(ep, "_next_smartcal_samples", {}) or {}).values()
            for s in pts if len(s) >= 4
        ]
        if len(pooled) < _SMARTCAL_MIN_NEUTRAL_SAMPLES:
            logger.warning(
                "NEXT smart cal (eye %s): only %d lid/brow samples (<%d); "
                "keeping previous lid/brow calibration.",
                eye, len(pooled), _SMARTCAL_MIN_NEUTRAL_SAMPLES,
            )
            continue
        arr = np.asarray(pooled, dtype=np.float64)
        lid = float(np.median(arr[:, 2]))
        brow = float(np.median(arr[:, 3]))
        logger.info(
            "NEXT smart cal (eye %s): neutral lid %.3f -> %.2f, brow %.3f -> %.2f "
            "(%d samples)",
            eye, lid, NEXT_SMARTCAL_LID_TARGET, brow, NEXT_SMARTCAL_BROW_TARGET,
            len(pooled),
        )
        if not _SMARTCAL_LID_NEUTRAL_MIN <= lid <= _SMARTCAL_LID_NEUTRAL_MAX:
            logger.warning(
                "NEXT smart cal (eye %s): neutral eyelid %.3f is outside "
                "[%.2f, %.2f] - were the eyes open and relaxed? Keeping the "
                "previous lid calibration.",
                eye, lid, _SMARTCAL_LID_NEUTRAL_MIN, _SMARTCAL_LID_NEUTRAL_MAX,
            )
        else:
            ep.config.next_smartcal_lid_neutral = lid
            ep._next_smartcal_lid_neutral = lid
            saved_any = True
        if not _SMARTCAL_BROW_NEUTRAL_MIN <= brow <= _SMARTCAL_BROW_NEUTRAL_MAX:
            logger.warning(
                "NEXT smart cal (eye %s): neutral eyebrow %.3f is outside "
                "[%.2f, %.2f]. Keeping the previous brow calibration.",
                eye, brow, _SMARTCAL_BROW_NEUTRAL_MIN, _SMARTCAL_BROW_NEUTRAL_MAX,
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
            w, b, warp,
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
    logger.info(
        "NEXT smart cal: transforms cleared (raw model gaze, lid and brow restored)."
    )


def _fit_next_smartcal(eye_processors: list, baseconfig, settings) -> bool:
    """Least-squares fit a per-eye affine gaze transform from collected samples.

    Each output axis is fit independently as a 3-unknown affine on the per-dot
    raw medians (optionally arctanh-warped first; off by default — see the module
    header for why this model uses a plain affine):
        x_cal = w11*gx + w12*gy + b1
        y_cal = w21*gx + w22*gy + b2   (gx, gy = raw, or arctanh(raw) if warping)

    Targets come from next_smartcal_targets(settings): each dot is fit to its
    fraction of the output full-scale FOV, not its overlay radius, so the outer
    ring keeps headroom to the edge (see that function).

    Returns True if at least one eye produced a usable transform (and was saved)."""
    targets = next_smartcal_targets(settings)
    saved_any = False
    for ep in eye_processors:
        eye = getattr(ep, "eye_id", "?")
        samples = getattr(ep, "_next_smartcal_samples", {}) or {}
        raws, tgts, fit_weights = [], [], []
        for dot in range(len(NEXT_SMARTCAL_DOTS)):
            pts = samples.get(dot, [])
            if len(pts) < _SMARTCAL_MIN_SAMPLES_PER_DOT:
                logger.debug(
                    "NEXT smart cal (eye %s): dot %d has %d samples (<%d): dropped.",
                    eye, dot, len(pts), _SMARTCAL_MIN_SAMPLES_PER_DOT,
                )
                continue
            arr = np.asarray(pts, dtype=np.float64)
            # Median over the hold window rejects blinks / transient outliers.
            raws.append([float(np.median(arr[:, 0])), float(np.median(arr[:, 1]))])
            tgts.append(targets[dot])
            fit_weights.append(
                _SMARTCAL_CENTER_WEIGHT if dot == len(NEXT_SMARTCAL_DOTS) - 1 else 1.0
            )

        if len(raws) < _SMARTCAL_MIN_DOTS:
            logger.warning(
                "NEXT smart cal (eye %s): only %d/%d dots captured (<%d); skipping fit.",
                eye, len(raws), len(NEXT_SMARTCAL_DOTS), _SMARTCAL_MIN_DOTS,
            )
            continue

        R = np.asarray(raws, dtype=np.float64)          # N x 2 raw gaze
        T = np.asarray(tgts, dtype=np.float64)          # N x 2 target gaze

        # Diagnostic dump (INFO so it shows without debug config): the captured
        # raw median for each held dot against its target. Lets a rejected fit be
        # read straight from the log — if the raw pairs don't separate the rings
        # (inner ≈ outer) the model output is plateauing; if a sign is inverted
        # vs the target the capture is flipped; wide scatter = noisy follow.
        logger.info(
            "NEXT smart cal (eye %s) captures [raw]->[target]  (samples/dot=%s):\n%s",
            eye,
            {d: len(samples.get(d, [])) for d in range(len(NEXT_SMARTCAL_DOTS))},
            "\n".join(
                f"  ({R[i, 0]:+.3f}, {R[i, 1]:+.3f}) -> ({T[i, 0]:+.3f}, {T[i, 1]:+.3f})"
                for i in range(len(R))
            ),
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
                eye, float(spread[0]), float(spread[1]),
            )
            continue

        warp = _SMARTCAL_WARP
        if warp == "atanh":
            # De-saturate into a space where a saturating model is ~linear in
            # true gaze. (Off by default — this model under-drives, see header.)
            Rc = np.clip(R, -_SMARTCAL_WARP_CLAMP, _SMARTCAL_WARP_CLAMP)
            G = np.arctanh(Rc)
        else:
            G = R                                       # plain raw-space affine
        gx = G[:, 0]
        gy = G[:, 1]
        ones = np.ones(len(G))
        A = np.column_stack([gx, gy, ones])             # N x 3  [gx, gy, 1]
        # Weighted least squares. Multiplying rows by sqrt(weight) makes the
        # centre anchor count more without duplicating or over-sampling frames.
        sw = np.sqrt(np.asarray(fit_weights, dtype=np.float64))
        Aw = A * sw[:, None]
        Tx = T[:, 0] * sw
        Ty = T[:, 1] * sw
        try:
            sol_x, *_ = np.linalg.lstsq(Aw, Tx, rcond=None)   # [w11, w12, b1]
            sol_y, *_ = np.linalg.lstsq(Aw, Ty, rcond=None)   # [w21, w22, b2]
        except np.linalg.LinAlgError as e:
            logger.warning("NEXT smart cal (eye %s): solve failed: %s", eye, e)
            continue

        w = [float(sol_x[0]), float(sol_x[1]),
             float(sol_y[0]), float(sol_y[1])]           # [w11, w12, w21, w22]
        b = [float(sol_x[2]), float(sol_y[2])]           # [b1, b2]

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
                eye, residual, _SMARTCAL_MAX_RESIDUAL,
                [round(v, 4) for v in w], [round(v, 4) for v in b],
            )
            continue
        if not next_smartcal_transform_is_sane(w, b, warp):
            logger.warning(
                "NEXT smart cal (eye %s): rejected degenerate transform W=%s B=%s "
                "(gain/bias/monotonicity out of bounds). Keeping previous "
                "calibration.",
                eye, [round(v, 4) for v in w], [round(v, 4) for v in b],
            )
            continue

        ep.config.next_smartcal_w = w
        ep.config.next_smartcal_b = b
        ep.config.next_smartcal_warp = warp
        ep._next_smartcal_w = w
        ep._next_smartcal_b = b
        ep._next_smartcal_warp = warp
        saved_any = True
        logger.info(
            "NEXT smart cal (eye %s): fit from %d dots (warp=%s): W=%s B=%s "
            "(residual %.3f)",
            eye, len(raws), warp,
            [round(v, 4) for v in w], [round(v, 4) for v in b], residual,
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
    sock = None
    try:
        overlay_path = _overlay_executable()
        tools_dir = os.path.dirname(overlay_path)
        # Bind before launching so the overlay's first signal isn't dropped.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(120.0)
        sock.bind(("127.0.0.1", 2112))
        subprocess.Popen(
            [overlay_path, "finetune"],
            cwd=tools_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        var.overlay_active = True

        # Fresh sample state for this run.
        for ep in eye_processors:
            ep._next_smartcal_active_dot = None
            ep._next_smartcal_samples = {}

        while var.overlay_active:
            try:
                data, _ = sock.recvfrom(16)
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
                    PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)
                var.overlay_active = False
                break
    except (OSError, FileNotFoundError, struct.error) as e:
        logger.warning(
            "NEXT smart calibration overlay error (%s). Make sure SteamVR is running.",
            e,
        )
    finally:
        for ep in eye_processors:
            ep._next_smartcal_active_dot = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        var.overlay_active = False


class cal:
    def cal_osc(self, cx, cy, angle):
        # Check if calibration data exists and is valid (list/array, not scalar like 0)
        has_valid_calib = (
            self.config.calib_evecs is not None
            and self.config.calib_axes is not None
            and self.config.calib_XOFF is not None
            and
            # Ensure evecs and axes are lists/arrays, not scalars (e.g., not the integer 0)
            isinstance(self.config.calib_evecs, (list, tuple))
            and isinstance(self.config.calib_axes, (list, tuple))
        )

        if has_valid_calib:
            if not self.cal.init_from_save(
                self.config.calib_evecs, self.config.calib_axes
            ):
                # If init_from_save fails, treat as uncalibrated
                if self.should_print_calibration_warning:
                    logger.error(
                        "Eye %s: failed to load calibration data. Please recalibrate.",
                        getattr(self, "eye_id", "?"),
                    )
                    self.should_print_calibration_warning = False

        else:
            if self.should_print_calibration_warning:
                logger.error(
                    "Eye %s: please calibrate eye(s).",
                    getattr(self, "eye_id", "?"),
                )
                self.should_print_calibration_warning = False

        if cx is None or cy is None:
            return (
                getattr(self, "_stable_out_x", 0.0),
                getattr(self, "_stable_out_y", 0.0),
                getattr(self, "_stable_velocity", 0.0),
            )
        if cx == 0:
            cx = 1
        if cy == 0:
            cy = 1
        if self.eye_id == EyeId.RIGHT:
            flipx = self.settings.gui_flip_x_axis_right
        else:
            flipx = self.settings.gui_flip_x_axis_left

        if self.calibration_start_time is not None:
            if (
                time.time() - self.calibration_start_time
                >= self.settings.calibration_duration
            ):
                self.calibration_start_time = None

                # Only save ellipse calibration data if samples were actually collected
                evecs, axes = self.cal.fit_ellipse()
                # Check if fit was successful (returns (0, 0) on failure)
                if not (
                    isinstance(evecs, int)
                    and isinstance(axes, int)
                    and evecs == 0
                    and axes == 0
                ):
                    self.config.calib_evecs = list(evecs.tolist() if hasattr(evecs, "tolist") else evecs)
                    self.config.calib_axes = list(axes.tolist() if hasattr(axes, "tolist") else axes)
                    if self.cal.center is not None:
                        self.config.calib_XOFF = float(self.cal.center[0])
                        self.config.calib_YOFF = float(self.cal.center[1])
                    else:
                        self.config.calib_XOFF = cx
                        self.config.calib_YOFF = cy
                    _mark_next_classic_calibration_active(self)
                    self.baseconfig.save()
                    PlaySound(
                        resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC
                    )
                else:
                    # No samples collected - only save the offset (for Recenter Eyes)
                    # Don't overwrite existing ellipse calibration
                    self.config.calib_XOFF = cx
                    self.config.calib_YOFF = cy
                    logger.warning(
                        "Eye %s: calibration stopped without collecting samples. "
                        "Ellipse calibration preserved, offset updated.",
                        getattr(self, "eye_id", "?"),
                    )
                    self.baseconfig.save()  # Still save to persist the offset changes
                self.blink_clear = False
            else:
                self.cal.add_sample(cx, cy)
                # Restore fitted=True so normalize() returns old calibration during collection.
                if has_valid_calib:
                    self.cal.init_from_save(self.config.calib_evecs, self.config.calib_axes)
                self.blink_clear = False
                self.settings.gui_recenter_eyes = False

        if self.settings.gui_recenter_eyes == True:
            self.config.calib_XOFF = cx
            self.config.calib_YOFF = cy
            # Time-based gate (previously a 10-frame counter tuned for ~50 fps
            # = 0.2s). Frame-count gates skew with capture rate.
            now = time.perf_counter()
            if self._recenter_armed_at is None:
                self._recenter_armed_at = now
            if now - self._recenter_armed_at >= self._recenter_delay_s:
                center_overlay_calibrate(self)  # TODO: Only call on supported desktop platforms.
                self.settings.gui_recenter_eyes = False
                PlaySound(
                    resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC
                )
                self._recenter_armed_at = None
        else:
            self._recenter_armed_at = None

        # ── Overlay ellipse continuous sampling ───────────────────────────────────
        if (getattr(self, "_ellipse_collect_active", False)
                and cx is not None and cy is not None
                and self.calibration_start_time is None):
            self.cal.add_sample(float(cx), float(cy))
            if has_valid_calib:
                self.cal.init_from_save(self.config.calib_evecs, self.config.calib_axes)

        # ── Robust calibration frame feeding ─────────────────────────────────────
        _robust_cal: RobustCalibrationSession | None = getattr(self, "robust_cal", None)
        if _robust_cal is not None:
            _eye_frame = getattr(self, "current_image_gray_clean", None)
            if _eye_frame is None:
                _eye_frame = getattr(self, "current_image_gray", None)
            _phase = _robust_cal.phase

            if _phase == CalibrationPhase.EXPRESS:
                _target_done = _robust_cal.feed_express_frame(cx, cy)
                if _target_done and _robust_cal.phase == CalibrationPhase.DONE:
                    _save_robust_calib(self)
                    PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)

            elif _phase == CalibrationPhase.BLINK:
                _blink_done = _robust_cal.feed_blink_frame(_eye_frame)
                if _blink_done:
                    PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)

            elif _phase == CalibrationPhase.BLINK_END:
                _robust_cal.check_blink_end_timer()

            elif _phase == CalibrationPhase.PURSUIT:
                _pursuit_done = _robust_cal.feed_pursuit_frame(_eye_frame, float(cx), float(cy))
                if _pursuit_done and _robust_cal.phase == CalibrationPhase.DONE:
                    _save_robust_calib(self)
                    PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)

        # ── Normalization / routing ───────────────────────────────────────────
        out_x = 0.5
        out_y = 0.5
        dfr_x = 0.0
        dfr_y = 0.0

        _calib_mode = getattr(self.settings, "calib_mode", "classic")
        _use_robust = (
            _calib_mode in ("express", "robust")
            and _robust_cal is not None
            and (_robust_cal.express_calibrated or _robust_cal.poly_trained)
            and _robust_cal.phase == CalibrationPhase.DONE
        )

        _bs_valid = True
        if _use_robust:
            if _calib_mode == "robust" and _robust_cal.poly_trained:
                _eye_frame = getattr(self, "current_image_gray_clean", None)
                if _eye_frame is None:
                    _eye_frame = getattr(self, "current_image_gray", None)
                _bs_det: BSDetector | None = getattr(self, "bs_detector", None)
                if _bs_det is not None:
                    _bs_valid = _bs_det.check(_eye_frame, cx, cy)

            if _robust_cal.poly_trained and _bs_valid:
                # Polynomial path: degree-2 regression on raw keypoints
                _poly_result = _robust_cal.predict_poly(cx, cy, clamp=True)
                if _poly_result is not None:
                    out_x, out_y = _poly_result
                    _dfr_result = _robust_cal.predict_poly(cx, cy, clamp=False)
                    dfr_x, dfr_y = _dfr_result if _dfr_result is not None else _poly_result
                else:
                    out_x, out_y = _robust_cal.normalize_express(cx, cy, clamp=True)
                    dfr_x, dfr_y = _robust_cal.normalize_express(cx, cy, clamp=False)
            else:
                # Express min-max normalization (no poly, or BS detector rejected frame)
                out_x, out_y = _robust_cal.normalize_express(cx, cy, clamp=True)
                dfr_x, dfr_y = _robust_cal.normalize_express(cx, cy, clamp=False)
        else:
            # Classic ellipse path
            out_x, out_y = self.cal.normalize(
                (cx, cy), (self.config.calib_XOFF, self.config.calib_YOFF)
            )
            # DFR: unclamped classic normalize
            dfr_x, dfr_y = self.cal.normalize(
                (cx, cy), (self.config.calib_XOFF, self.config.calib_YOFF), clip=False
            )

        # Capture calibrated output before snap-hold / falloff adjustments for logging.
        _pre_snap_x, _pre_snap_y = out_x, out_y

        # ── Snap-to-center hold ───────────────────────────────────────────────────
        # When the pupil tracker loses the pupil at an extreme gaze angle it
        # often reports the image center.  After calibration this maps to
        # ~(0, 0), a sudden jump from an extreme position to near-center.
        # Detect this and hold the last valid calibrated position with a slow drift.
        if (
            getattr(self.settings, "gui_snap_hold_enabled", True)
            and _use_robust
            and _robust_cal is not None
            and _robust_cal.express_calibrated
            and _robust_cal.phase == CalibrationPhase.DONE
        ):
            if not hasattr(self, "_last_cal_x"):
                self._last_cal_x = out_x
                self._last_cal_y = out_y
                self._cal_hold_frames = 0

            _was_extreme = abs(self._last_cal_x) >= 0.50 or abs(self._last_cal_y) >= 0.50
            _now_center = abs(out_x) <= 0.30 and abs(out_y) <= 0.30
            _jump = math.sqrt(
                (out_x - self._last_cal_x) ** 2 + (out_y - self._last_cal_y) ** 2
            )
            _big_jump = _jump > 0.40

            # In full-robust mode (poly trained) require BS detector confirmation
            # to avoid false holds on genuine fast saccades.
            # In express-only mode use geometry alone (no BS detector available).
            _is_snap = _was_extreme and _now_center and _big_jump
            if _calib_mode == "robust" and _robust_cal.poly_trained:
                _is_snap = _is_snap and not _bs_valid

            if _is_snap:
                _kp_noise = (
                    var.l_keypoint_noise
                    if self.eye_id == EyeId.LEFT
                    else var.r_keypoint_noise
                )
                _hold_rate = max(8.0, 20.0 - min(12.0, _kp_noise * 80.0))
                _drift = min(1.0, self._cal_hold_frames / _hold_rate)
                out_x = self._last_cal_x + _drift * (out_x - self._last_cal_x)
                out_y = self._last_cal_y + _drift * (out_y - self._last_cal_y)
                dfr_x = out_x
                dfr_y = out_y
                self._cal_hold_frames = min(self._cal_hold_frames + 1, 30)
                self._snap_active = True
                self._last_drift = _drift

                # When drift has fully caught up, accept the new position as the
                # anchor.  Without this reset, a stale extreme in _last_cal_x
                # re-fires the snap condition any time the user looks near centre,
                # creating permanent "gravity wells" in certain gaze regions.
                if _drift >= 1.0:
                    self._last_cal_x = out_x
                    self._last_cal_y = out_y
                    self._cal_hold_frames = 0

                if self.eye_id == EyeId.LEFT:
                    var.l_eye_velocity = max(var.l_eye_velocity, var.r_eye_velocity * 2.0 + 0.5)
                elif self.eye_id == EyeId.RIGHT:
                    var.r_eye_velocity = max(var.r_eye_velocity, var.l_eye_velocity * 2.0 + 0.5)
                logger.debug(
                    "Snap hold (frame %d, drift=%.2f): holding (%.2f, %.2f)",
                    self._cal_hold_frames, _drift, out_x, out_y,
                )
            else:
                self._snap_active = False
                self._last_drift = 0.0
                # Valid frame: update last-valid only when not in a BS-flagged state
                if not (_calib_mode == "robust" and not _bs_valid):
                    self._last_cal_x = out_x
                    self._last_cal_y = out_y
                self._cal_hold_frames = max(0, self._cal_hold_frames - 2)

        if self.settings.gui_flip_y_axis:
            out_y = -out_y
            dfr_y = -dfr_y

        if flipx:
            out_x = -out_x
            dfr_x = -dfr_x

        # ── DFR output (unclamped, before 1€ filter) ──────────────────────────
        if getattr(self.settings, "gui_dfr_enabled", False):
            _dispatch_dfr(self.settings, int(self.eye_id), dfr_x, dfr_y)

        # Per-eye velocity must be tracked whenever any falloff/dominance mode
        # is on, since velocity_falloff() compares the two eyes' velocities to
        # pick the cleaner one. The noise map also feeds on the instantaneous
        # magnitude returned here.
        # Share eye openness so velocity_falloff can mirror the open eye when
        # the other eye is closed (wink / sustained blink).
        _eyeopen = getattr(self, "eyeopen", 1.0)
        if self.eye_id == EyeId.LEFT:
            var.l_eye_openness = float(_eyeopen)
        else:
            var.r_eye_openness = float(_eyeopen)

        inst_velocity = 0.0
        if (
            self.settings.gui_outer_side_falloff
            or self.settings.gui_left_eye_dominant
            or self.settings.gui_right_eye_dominant
        ):
            inst_velocity = _update_eye_velocity(
                self.eye_id, float(out_x), float(out_y), time.time()
            )
            _roi_diag = math.sqrt(
                self.config.roi_window_w ** 2 + self.config.roi_window_h ** 2
            )
            _update_keypoint_noise(self.eye_id, float(cx), float(cy), _roi_diag)

        out_x, out_y = velocity_falloff(
            self, var, out_x, out_y, inst_velocity=inst_velocity
        )

        try:
            _oef = self.one_euro_filter
            try:
                _mc = float(self.settings.gui_min_cutoff)
                _b = float(self.settings.gui_speed_coefficient)
                if _oef.min_cutoff[0] != _mc:
                    _oef.min_cutoff.fill(_mc)
                if _oef.beta[0] != _b:
                    _oef.beta.fill(_b)
            except (TypeError, ValueError, AttributeError, IndexError):
                pass
            noisy_point = np.array([float(out_x), float(out_y)])
            point_hat = self.one_euro_filter(noisy_point)
            out_x = point_hat[0]
            out_y = point_hat[1]

        except (TypeError, ValueError, AttributeError) as e:
            logger.debug("One-euro filter pass failed: %s", e)

        # Report this eye's own smoothed velocity (was previously a single
        # shared scalar across both eyes, which made the downstream falloff
        # comparison meaningless).
        my_velocity = (
            var.l_eye_velocity if self.eye_id == EyeId.LEFT else var.r_eye_velocity
        )
        self._stable_out_x = float(out_x)
        self._stable_out_y = float(out_y)
        self._stable_velocity = float(my_velocity)

        _tlog = TrackingLogger.get()
        if _tlog is not None:
            from utils.eye_falloff import _latched_eye as _fe_latch
            _tlog.record(
                t=time.time(),
                eye="L" if self.eye_id == EyeId.LEFT else "R",
                cx=float(cx),
                cy=float(cy),
                cal_x=_pre_snap_x,
                cal_y=_pre_snap_y,
                out_x=float(out_x),
                out_y=float(out_y),
                snap=getattr(self, "_snap_active", False),
                hold_f=getattr(self, "_cal_hold_frames", 0),
                drift=getattr(self, "_last_drift", 0.0),
                kp_noise=float(
                    var.l_keypoint_noise if self.eye_id == EyeId.LEFT else var.r_keypoint_noise
                ),
                velocity=float(my_velocity),
                latch="" if _fe_latch is None else str(int(_fe_latch)),
            )

        return out_x, out_y, my_velocity
