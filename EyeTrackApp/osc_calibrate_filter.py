import numpy as np

from EyeTrackApp.consts import EyeId
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC


class cal():
    def cal_osc(self, cx, cy):
        if self.eye_id == EyeId.RIGHT:
            flipx = self.settings.gui_flip_x_axis_right
        else:
            flipx = self.settings.gui_flip_x_axis_left
        if self.calibration_frame_counter == 0:
            self.calibration_frame_counter = None
            self.config.calib_XOFF = cx
            self.config.calib_YOFF = cy
            PlaySound('Audio/completed.wav', SND_FILENAME | SND_ASYNC)
        if self.calibration_frame_counter == 300:
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
                self.settings.gui_recenter_eyes = False
                PlaySound('Audio/completed.wav', SND_FILENAME | SND_ASYNC)
            else:
                self.ts = self.ts - 1
        else:
            self.ts = 10

        try:
            out_x = 0.5
            out_y = 0.5
            xl = float(
                (cx - self.config.calib_XOFF) / (self.config.calib_XMAX - self.config.calib_XOFF)
            )
            xr = float(
                (cx - self.config.calib_XOFF) / (self.config.calib_XMIN - self.config.calib_XOFF)
            )
            yu = float(
                (cy - self.config.calib_YOFF) / (self.config.calib_YMIN - self.config.calib_YOFF)
            )
            yd = float(
                (cy - self.config.calib_YOFF) / (self.config.calib_YMAX - self.config.calib_YOFF)
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
          #  print("\033[91m[ERROR] Eye Calibration Invalid!\033[0m")
            self.config.calib_XOFF = 0
            self.config.calib_YOFF = 0
            self.config.calib_XMAX = 1
            self.config.calib_YMAX = 1
            self.config.calib_XMIN = 1
            self.config.calib_YMIN = 1
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