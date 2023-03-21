import sys
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC
import numpy as np
from enum import IntEnum
from config import EyeTrackConfig
from config import EyeTrackSettingsConfig

class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3


class cal():
  #  main_config = EyeTrackConfig

   # def __init__(self, main_config: EyeTrackSettingsConfig):
  #      self.settings = main_config

    def cal_osc(self, cx, cy):
        svs = False
        if self.eye_id == EyeId.RIGHT:
            flipx = self.settings.gui_flip_x_axis_right
        else:
            flipx = self.settings.gui_flip_x_axis_left
        if self.calibration_frame_counter == 0:
            self.calibration_frame_counter = None
            self.xoff = cx
            self.yoff = cy
            self.config.calib_XMAX = self.xmax
            self.config.calib_YMAX = self.ymax
            self.config.calib_XMIN = self.xmin
            self.config.calib_YMIN = self.ymin
            svs = False
           # self.settings.save()
            PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)
        elif self.calibration_frame_counter != None:
            self.settings.gui_recenter_eyes = False
            if cx > self.xmax:
                self.xmax = cx
            if cx < self.xmin:
                self.xmin = cx
            if cy > self.ymax:
                self.ymax = cy
            if cy < self.ymin:
                self.ymin = cy

        #self.config.calib_XMIN not None and self.config.calib_YMAX
            self.calibration_frame_counter -= 1

        if not any(i == None for i in (self.config.calib_XMIN, self.config.calib_YMIN, self.config.calib_XMAX, self.config.calib_YMAX)) and not svs:
            self.xmax = self.config.calib_XMAX
            self.ymax = self.config.calib_YMAX 
            self.xmin = self.config.calib_XMIN
            self.ymin = self.config.calib_YMIN
            svs = True

        if self.settings.gui_recenter_eyes == True:
            self.xoff = cx
            self.yoff = cy
            if self.ts == 0:
                self.settings.gui_recenter_eyes = False
                PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)
            else:
                self.ts = self.ts - 1
        else:
            self.ts = 10

        try:
            out_x = 0.5
            out_y = 0.5
            xl = float(
                (cx - self.xoff) / (self.xmax - self.xoff)
            )
            xr = float(
                (cx - self.xoff) / (self.xmin - self.xoff)
            )
            yu = float(
                (cy - self.yoff) / (self.ymin - self.yoff)
            )
            yd = float(
                (cy - self.yoff) / (self.ymax - self.yoff)
            )

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
        except:
            print("\033[91m[ERROR] Eye Calibration Invalid!\033[0m")
            out_x = 0.5
            out_y = 0.5
        try:
            noisy_point = np.array([float(out_x), float(out_y)])  # fliter our values with a One Euro Filter
            point_hat = self.one_euro_filter(noisy_point)
            out_x = point_hat[0]
            out_y = point_hat[1]
        except:
            pass
        return out_x, out_y