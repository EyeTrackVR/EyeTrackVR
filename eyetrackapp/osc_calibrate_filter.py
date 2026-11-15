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
import math
from calibration_state import var
from overlay_calibration import _mark_next_classic_calibration_active, center_overlay_calibrate

logger = logging.getLogger(__name__)


class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3


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
            if not self.cal.init_from_save(self.config.calib_evecs, self.config.calib_axes):
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
            if time.time() - self.calibration_start_time >= self.settings.calibration_duration:
                self.calibration_start_time = None

                # Only save ellipse calibration data if samples were actually collected
                evecs, axes = self.cal.fit_ellipse()
                # Check if fit was successful (returns (0, 0) on failure)
                if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
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
                    PlaySound(resource_path("assets/audio/completed.wav"), SND_FILENAME | SND_ASYNC)
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

        if self.settings.gui_recenter_eyes:
            self.config.calib_XOFF = cx
            self.config.calib_YOFF = cy
            # Time-based gate (previously a 10-frame counter tuned for ~50 fps
            # = 0.2s). Frame-count gates skew with capture rate.
            now = time.perf_counter()
            if self._recenter_armed_at is None:
                self._recenter_armed_at = now
            if now - self._recenter_armed_at >= self._recenter_delay_s:
                # Recenter also works without the optional SteamVR target (for
                # example, LEAP on Linux where no overlay binary is shipped).
                if self.settings.gui_use_overlay_cal:
                    center_overlay_calibrate(self)
                self.settings.gui_recenter_eyes = False
                self.baseconfig.save()
                PlaySound(resource_path("assets/audio/completed.wav"), SND_FILENAME | SND_ASYNC)
                self._recenter_armed_at = None
        else:
            self._recenter_armed_at = None

        # ── Overlay ellipse continuous sampling ───────────────────────────────────
        if (
            getattr(self, "_ellipse_collect_active", False)
            and cx is not None
            and cy is not None
            and self.calibration_start_time is None
        ):
            self.cal.add_sample(float(cx), float(cy))
            if has_valid_calib:
                self.cal.init_from_save(self.config.calib_evecs, self.config.calib_axes)

        # ── Normalization ─────────────────────────────────────────────────────
        out_x, out_y = self.cal.normalize((cx, cy), (self.config.calib_XOFF, self.config.calib_YOFF))
        # Foveated-rendering gaze: calibrated and unclamped, before falloff and
        # the One-Euro filter (EyeInfo.dfr_x). VRChat keeps out_x.
        dfr_x, dfr_y = self.cal.normalize((cx, cy), (self.config.calib_XOFF, self.config.calib_YOFF), clip=False)

        # Capture calibrated output before falloff adjustments for logging.
        _cal_x, _cal_y = out_x, out_y

        if self.settings.gui_flip_y_axis:
            out_y = -out_y
            dfr_y = -dfr_y

        if flipx:
            out_x = -out_x
            dfr_x = -dfr_x

        if math.isfinite(dfr_x) and math.isfinite(dfr_y):
            self.dfr_x, self.dfr_y = float(dfr_x), float(dfr_y)

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
            inst_velocity = _update_eye_velocity(self.eye_id, float(out_x), float(out_y), time.time())
            _roi_diag = math.sqrt(self.config.roi_window_w**2 + self.config.roi_window_h**2)
            _update_keypoint_noise(self.eye_id, float(cx), float(cy), _roi_diag)

        out_x, out_y = velocity_falloff(self, var, out_x, out_y, inst_velocity=inst_velocity)

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
        my_velocity = var.l_eye_velocity if self.eye_id == EyeId.LEFT else var.r_eye_velocity
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
                cal_x=_cal_x,
                cal_y=_cal_y,
                out_x=float(out_x),
                out_y=float(out_y),
                # Snap-hold was removed; the columns stay so the CSV format is unchanged.
                snap=False,
                hold_f=0,
                drift=0.0,
                kp_noise=float(var.l_keypoint_noise if self.eye_id == EyeId.LEFT else var.r_keypoint_noise),
                velocity=float(my_velocity),
                latch="" if _fe_latch is None else str(int(_fe_latch)),
            )

        return out_x, out_y, my_velocity
