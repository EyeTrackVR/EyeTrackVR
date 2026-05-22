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
import socket
import struct
import threading
import os
import subprocess
import math
from utils.calibration_3d import receive_calibration_data, converge_3d
from utils.calibration_elipse import *
from utils.misc_utils import resource_path
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
    r_eye_x = 0.0
    l_eye_x = 0.0
    left_y = 0.0
    right_y = 0.0
    l_eye_velocity = 0.0
    r_eye_velocity = 0.0
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


@Async
def center_overlay_calibrate(self):
    if var.overlay_active:
        return
    overlay_path = resource_path("Tools/EyeTrackVR-Overlay.exe")
    # Set working directory to the tools folder so overlay can find assets/Purple_Dot.png
    tools_dir = os.path.dirname(overlay_path)
    sock = None
    try:
        subprocess.Popen(
            [overlay_path, "center"],
            cwd=tools_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        var.overlay_active = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("localhost", 2112))
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
        subprocess.Popen(
            [overlay_path],
            cwd=tools_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        var.overlay_active = True
        # Bind once and reuse across messages; rebinding the same port every
        # iteration would race the OS releasing it on close.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("localhost", 2112))
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

        if cx == None or cy == None:
            return 0, 0
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
                # Always save offset (XOFF/YOFF) for recenter functionality
                self.config.calib_XOFF = cx
                self.config.calib_YOFF = cy

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
                    self.config.calib_evecs, self.config.calib_axes = evecs, axes
                    self.baseconfig.save()
                    PlaySound(
                        resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC
                    )
                else:
                    # No samples collected - only save the offset (for Recenter Eyes)
                    # Don't overwrite existing ellipse calibration
                    logger.warning(
                        "Eye %s: calibration stopped without collecting samples. "
                        "Ellipse calibration preserved, offset updated.",
                        getattr(self, "eye_id", "?"),
                    )
                    self.baseconfig.save()  # Still save to persist the offset changes
                self.blink_clear = False
            else:
                self.cal.add_sample(cx, cy)
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

        out_x = 0.5
        out_y = 0.5

        out_x, out_y = self.cal.normalize(
            (cx, cy), (self.config.calib_XOFF, self.config.calib_YOFF)
        )

        if (
            self.settings.gui_flip_y_axis
        ):  # check config on flipped values settings and apply accordingly
            out_y = -out_y  # flip

        if flipx:
            out_x = -out_x

        # Per-eye velocity must be tracked whenever any falloff/dominance mode
        # is on, since velocity_falloff() compares the two eyes' velocities to
        # pick the cleaner one. The noise map also feeds on the instantaneous
        # magnitude returned here.
        inst_velocity = 0.0
        if (
            self.settings.gui_outer_side_falloff
            or self.settings.gui_left_eye_dominant
            or self.settings.gui_right_eye_dominant
        ):
            inst_velocity = _update_eye_velocity(
                self.eye_id, float(out_x), float(out_y), time.time()
            )

        out_x, out_y = velocity_falloff(
            self, var, out_x, out_y, inst_velocity=inst_velocity
        )

        try:
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
        return out_x, out_y, my_velocity
