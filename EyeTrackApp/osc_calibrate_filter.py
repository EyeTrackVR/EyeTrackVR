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
    tools = Path("Tools")
    # try:
    if var.overlay_active != True:
        
        overlay_path = resource_path("tools/ETVR_SteamVR_Calibration_Overlay.exe")
        os.startfile(overlay_path, arguments="center")
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
            overlay_path = resource_path("tools/EyeTrackVR-Overlay.exe")
            os.startfile(overlay_path)
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

        # print(self.eye_id)

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
        if self.calibration_3d_frame_counter == -621:  # or self.settings.gui_3d_calibration:

            self.calibration_3d_frame_counter = self.calibration_3d_frame_counter - 1
            overlay_calibrate_3d(self)
            self.config.calibration_points_3d = []

        #  print(self.eye_id, cx, cy)
        # self.settings.gui_3d_calibration = False

        if self.settings.grab_3d_point:
            # Check if both calibrations are done
            if var.left_calib and var.right_calib:
                self.settings.grab_3d_point = False
                var.left_calib = False
                var.right_calib = False
                print("end", len(self.config.calibration_points_3d), self.config.calibration_points_3d)

            else:
                # Check if it's the left eye and left calibration is not done yet
                if self.eye_id == EyeId.LEFT and not var.left_calib:
                    var.left_calib = True
                    self.config.calibration_points_3d.append((cx, cy, 1))
                # Check if it's the right eye and right calibration is not done yet
                elif self.eye_id == EyeId.RIGHT and not var.right_calib:
                    var.right_calib = True
                    self.config.calibration_points_3d.append((cx, cy, 0))

        if self.eye_id == EyeId.LEFT and len(self.config.calibration_points_3d) == 9 and var.left_calib == False:
            var.left_calib = True
            receive_calibration_data(self.config.calibration_points_3d, self.eye_id)
            print("SENT LEFT EYE POINTS")
            var.completed_3d_calib += 1

        if self.eye_id == EyeId.RIGHT and len(self.config.calibration_points_3d) == 9 and var.right_calib == False:
            var.right_calib = True
            receive_calibration_data(self.config.calibration_points_3d, self.eye_id)
            print("SENT RIGHT EYE POINTS")
            var.completed_3d_calib += 1
        # print(len(self.config.calibration_points), self.eye_id)

        if var.completed_3d_calib >= 2:
            converge_3d()
        # pass

        if self.calibration_frame_counter == 0:
            self.calibration_frame_counter = None
            self.config.calib_XOFF = cx
            self.config.calib_YOFF = cy
            self.baseconfig.save()
            PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)
        if self.calibration_frame_counter == self.settings.calibration_samples:
            self.config.calib_XMAX = -69420
            self.config.calib_XMIN = 69420
            self.config.calib_YMAX = -69420
            self.config.calib_YMIN = 69420
            self.blink_clear = True
            self.calibration_frame_counter -= 1
        elif self.calibration_frame_counter != None:
            self.blink_clear = False
            self.settings.gui_recenter_eyes = False
            if cx > self.config.calib_XMAX:
                self.config.calib_XMAX = cx
            if cx < self.config.calib_XMIN:
                self.config.calib_XMIN = cx
            if cy > self.config.calib_YMAX:
                self.config.calib_YMAX = cy
            if cy < self.config.calib_YMIN:
                self.config.calib_YMIN = cy

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

        if self.config.calib_XMAX != None and self.config.calib_XOFF != None:

            calib_diff_x_MAX = self.config.calib_XMAX - self.config.calib_XOFF
            if calib_diff_x_MAX == 0:
                calib_diff_x_MAX = 1

            calib_diff_x_MIN = self.config.calib_XMIN - self.config.calib_XOFF
            if calib_diff_x_MIN == 0:
                calib_diff_x_MIN = 1

            calib_diff_y_MAX = self.config.calib_YMAX - self.config.calib_YOFF
            if calib_diff_y_MAX == 0:
                calib_diff_y_MAX = 1

            calib_diff_y_MIN = self.config.calib_YMIN - self.config.calib_YOFF
            if calib_diff_y_MIN == 0:
                calib_diff_y_MIN = 1

            xl = float((cx - self.config.calib_XOFF) / calib_diff_x_MAX)
            xr = float((cx - self.config.calib_XOFF) / calib_diff_x_MIN)
            yu = float((cy - self.config.calib_YOFF) / calib_diff_y_MIN)
            yd = float((cy - self.config.calib_YOFF) / calib_diff_y_MAX)

            if self.settings.gui_flip_y_axis:  # check config on flipped values settings and apply accordingly
                if yd >= 0:
                    out_y = max(0.0, min(1.0, yd))
                if yu > 0:
                    out_y = -abs(max(0.0, min(1.0, yu)))
            else:
                if yd >= 0:
                    out_y = -abs(max(0.0, min(1.0, yd)))
                if yu > 0:
                    out_y = max(0.0, min(1.0, yu))

            if flipx:
                if xr >= 0:
                    out_x = -abs(max(0.0, min(1.0, xr)))
                if xl > 0:
                    out_x = max(0.0, min(1.0, xl))
            else:
                if xr >= 0:
                    out_x = max(0.0, min(1.0, xr))
                if xl > 0:
                    out_x = -abs(max(0.0, min(1.0, xl)))

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
        else:
            if self.printcal:
                print("\033[91m[ERROR] Please Calibrate Eye(s).\033[0m")
                self.printcal = False
        return 0, 0, 0
