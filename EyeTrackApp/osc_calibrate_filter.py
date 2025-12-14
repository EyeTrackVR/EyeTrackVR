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

Copyright (c) 2023 EyeTrackVR <3

LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

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

tool = Path("Tools")
class TimeoutError(RuntimeError):
    pass


class AsyncCall(object):
    def __init__(self, fnc, callback=None):
        self.Callable = fnc
        self.Callback = callback

    def __call__(self, *args, **kwargs):
        self.Thread = threading.Thread(target=self.run, name=self.Callable.__name__, args=args, kwargs=kwargs)
        self.Thread.start()
        return self

    def wait(self, timeout=None):
        self.Thread.join(timeout)
        if self.Thread.isAlive():
            raise TimeoutError()
        else:
            return self.Result

    def run(self, *args, **kwargs):
        self.Result = self.Callable(*args, **kwargs)
        if self.Callback:
            self.Callback(self.Result)


class AsyncMethod(object):
    def __init__(self, fnc, callback=None):
        self.Callable = fnc
        self.Callback = callback

    def __call__(self, *args, **kwargs):
        return AsyncCall(self.Callable, self.Callback)(*args, **kwargs)


def Async(fnc=None, callback=None):
    if fnc == None:

        def AddAsyncCallback(fnc):
            return AsyncMethod(fnc, callback)

        return AddAsyncCallback
    else:
        return AsyncMethod(fnc, callback)


class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3


class var:
    average_velocity = 0
    velocity_rolling_list = []
    past_x = 0
    past_y = 0
    start_time = time.time()
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


@Async
def center_overlay_calibrate(self):
    # try:
    if var.overlay_active != True:
        
        overlay_path = resource_path("Tools/EyeTrackVR-Overlay.exe")
        # Set working directory to the tools folder so overlay can find assets/Purple_Dot.png
        tools_dir = Path(overlay_path).parent
        subprocess.Popen([overlay_path, "center"], cwd=str(tools_dir))
        var.overlay_active = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = ("localhost", 2112)
        sock.bind(server_address)
        data, address = sock.recvfrom(4096)
        received_int = struct.unpack("!l", data)[0]
        message = received_int
        self.settings.gui_recenter_eyes = False
        self.calibration_frame_counter = 0
        var.overlay_active = False


#  except:
#  print("[WARN] Calibration overlay error. Make sure SteamVR is Running.")
#   self.settings.gui_recenter_eyes = False
#   var.overlay_active = False


@Async
def overlay_calibrate_3d(self):
    try:
        if var.overlay_active != True:
            overlay_path = resource_path("Tools/EyeTrackVR-Overlay.exe")
            # Set working directory to the tools folder so overlay can find assets/Purple_Dot.png
            tools_dir = Path(overlay_path).parent
            subprocess.Popen([overlay_path], cwd=str(tools_dir))
            var.overlay_active = True
            while var.overlay_active:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                server_address = ("localhost", 2112)
                sock.bind(server_address)
                data, address = sock.recvfrom(4096)
                received_int = struct.unpack("!l", data)[0]
                message = received_int
                self.settings.gui_recenter_eyes = False
                self.settings.grab_3d_point = True

                print(message)
                if message == 9:
                    var.overlay_active = False

    except:
        print("[WARN] Calibration overlay error. Make sure SteamVR is Running.")
        self.settings.gui_recenter_eyes = False
        var.overlay_active = False


class cal:
    def cal_osc(self, cx, cy, angle):
        # Check if calibration data exists and is valid (list/array, not scalar like 0)
        has_valid_calib = (
            self.config.calib_evecs is not None and 
            self.config.calib_axes is not None and
            self.config.calib_XOFF is not None and
            # Ensure evecs and axes are lists/arrays, not scalars (e.g., not the integer 0)
            isinstance(self.config.calib_evecs, (list, tuple)) and
            isinstance(self.config.calib_axes, (list, tuple))
        )
        
        if has_valid_calib:
            # Validate and load saved calibration data
            if not self.cal.init_from_save(self.config.calib_evecs, self.config.calib_axes):
                # If init_from_save fails, treat as uncalibrated
                if self.printcal:
                    print("\033[91m[ERROR] Failed to load calibration data. Please recalibrate.\033[0m")
                    self.printcal = False

        else:
            if self.printcal:
                print("\033[91m[ERROR] Please Calibrate Eye(s).\033[0m")
                self.printcal = False

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


        if self.calibration_frame_counter == 0:
            self.calibration_frame_counter = None
            # Always save offset (XOFF/YOFF) for recenter functionality
            self.config.calib_XOFF = cx
            self.config.calib_YOFF = cy
            
            # Only save ellipse calibration data if samples were actually collected
            evecs, axes = self.cal.fit_ellipse()
            # Check if fit was successful (returns (0, 0) on failure)
            if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
                # Valid calibration data - save it
                self.config.calib_evecs, self.config.calib_axes = evecs, axes
                self.baseconfig.save()
                PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)
            else:
                # No samples collected - only save the offset (for Recenter Eyes)
                # Don't overwrite existing ellipse calibration
                print("\033[93m[WARN] Calibration stopped without collecting samples. Ellipse calibration preserved, offset updated.\033[0m")
                self.baseconfig.save()  # Still save to persist the offset changes

        if self.calibration_frame_counter == self.settings.calibration_samples:
            self.blink_clear = True
            self.calibration_frame_counter -= 1
        elif self.calibration_frame_counter != None:

            self.cal.add_sample(cx, cy)




            self.blink_clear = False
            self.settings.gui_recenter_eyes = False
            self.calibration_frame_counter -= 1

        if self.settings.gui_recenter_eyes == True:
            self.config.calib_XOFF = cx
            self.config.calib_YOFF = cy
            if self.ts == 0:
                center_overlay_calibrate(self)  # TODO, only call on windows machines?
                self.settings.gui_recenter_eyes = False
                PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)
            else:
                self.ts = self.ts - 1

        else:
            self.ts = 10

        out_x = 0.5
        out_y = 0.5



        out_x, out_y = self.cal.normalize((cx, cy), (self.config.calib_XOFF, self.config.calib_YOFF))

        if self.settings.gui_flip_y_axis:  # check config on flipped values settings and apply accordingly
            out_y = -out_y # flip

        if flipx:
            out_x = -out_x

        if self.settings.gui_outer_side_falloff:

            run_time = time.time()
            out_x_mult = out_x * 100
            out_y_mult = out_y * 100
            velocity = abs(
                np.sqrt(abs(np.square(out_x_mult - var.past_x) - np.square(out_y_mult - var.past_y)))
                / ((var.start_time - run_time) * 10)
            )
            if len(var.velocity_rolling_list) < 15:
                var.velocity_rolling_list.append(float(velocity))
            else:
                var.velocity_rolling_list.pop(0)
                var.velocity_rolling_list.append(float(velocity))
            var.average_velocity = sum(var.velocity_rolling_list) / len(var.velocity_rolling_list)
            var.past_x = out_x_mult
            var.past_y = out_y_mult

        out_x, out_y = velocity_falloff(self, var, out_x, out_y)

        try:
            noisy_point = np.array([float(out_x), float(out_y)])  # fliter our values with a One Euro Filter
            point_hat = self.one_euro_filter(noisy_point)
            out_x = point_hat[0]
            out_y = point_hat[1]

        except:
            pass

        return out_x, out_y, var.average_velocity


