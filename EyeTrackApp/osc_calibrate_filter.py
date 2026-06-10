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
    overlay_path = resource_path("Tools/EyeTrackVR-Overlay.exe")
    # Set working directory to the tools folder so overlay can find assets/Purple_Dot.png
    tools_dir = os.path.dirname(overlay_path)
    sock = None
    try:
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
    overlay_path = resource_path("Tools/EyeTrackVR-Overlay.exe")
    # Set working directory to the tools folder so overlay can find assets/Purple_Dot.png
    tools_dir = os.path.dirname(overlay_path)
    sock = None
    try:
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
    overlay_path = resource_path("Tools/EyeTrackVR-Overlay.exe")
    tools_dir = os.path.dirname(overlay_path)
    sock = None
    try:
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
            # Validate and load saved calibration data
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
                    # Valid calibration data - save it
                    self.config.calib_evecs = list(evecs.tolist() if hasattr(evecs, "tolist") else evecs)
                    self.config.calib_axes = list(axes.tolist() if hasattr(axes, "tolist") else axes)
                    if self.cal.center is not None:
                        self.config.calib_XOFF = float(self.cal.center[0])
                        self.config.calib_YOFF = float(self.cal.center[1])
                    else:
                        self.config.calib_XOFF = cx
                        self.config.calib_YOFF = cy
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
                # Polynomial path — degree-2 regression on raw keypoints
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
        # ~(0, 0) — a sudden jump from an extreme position to near-center.
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

        if (
            self.settings.gui_flip_y_axis
        ):  # check config on flipped values settings and apply accordingly
            out_y = -out_y  # flip
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
            noisy_point = np.array(
                [float(out_x), float(out_y)]
            )  # fliter our values with a One Euro Filter
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
