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

Intensity Based Openess By: Prohurtz, PallasNeko (Optimization)
Algorithm App Implementations By: Prohurtz

Copyright (c) 2023 EyeTrackVR <3
------------------------------------------------------------------------------------------------------
"""
import os
import time
from enum import IntEnum

import numpy as np

import cv2
from one_euro_filter import OneEuroFilter


class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3


# higher intensity means more closed/ more white/less pupil

# Hm I need an acronym for this, any ideas?
# IBO Intensity Based Openness

# HOW THIS WORKS: we get the intensity of pupil area from HSF crop, When the eyelid starts to close, the pupil starts
# being obstructed by skin which is generally lighter than the pupil. This causes the intensity to increase. We save
# all of the darkest intensities of each pupil position to calculate for pupil movement. ex. when you look up there
# is less pupil visible, which results in an uncalculated change in intensity even though the eyelid has not moved in
# a meaningful way. We compare the darkest intensity of that area, to the lightest (global) intensity to find the
# appropriate openness state via a float.


# Note. OpenCV on Windows will generate an error if the file path contains non-ASCII characters when using
# cv2.imread(), cv2.imwrite(), etc. https://stackoverflow.com/questions/43185605/how-do-i-read-an-image-from-a-path
# -with-unicode-characters https://github.com/opencv/opencv/issues/18305

def csv2data(frameshape, filepath):
    # For data checking
    frameshape = (frameshape[0], frameshape[1] + 1)
    out = np.zeros(frameshape, dtype=np.uint32)
    xy_list = []
    val_list = []
    with open(filepath, mode="r", encoding="utf-8") as in_f:
        # Skip header.
        _ = in_f.readline()
        for s in in_f:
            xyval = [int(val) for val in s.strip().split(',')]
            xy_list.append((xyval[0], xyval[1]))
            val_list.append(xyval[2])
    xy_list = np.array(xy_list)
    val_list = np.array(val_list)
    out[xy_list[:, 1], xy_list[:, 0]] = val_list[:]
    return out


def data2csv(data_u32, filepath):
    # For data checking
    nonzero_index = np.nonzero(data_u32)  # (row,col)
    data_list = data_u32[nonzero_index].tolist()
    datalines = ["{},{},{}\n".format(x, y, val) for y, x, val in zip(*nonzero_index, data_list)]
    with open(filepath, 'w', encoding="utf-8") as out_f:
        out_f.write("x,y,intensity\n")
        out_f.writelines(datalines)
    return


def u32_1ch_to_u16_3ch(img):
    out = np.zeros((*img.shape[:2], 3), dtype=np.uint16)
    # https://github.com/numpy/numpy/issues/2524
    # https://stackoverflow.com/questions/52782511/why-is-numpy-slower-than-python-for-left-bit-shifts
    out[:, :, 0] = img & np.uint32(65535)
    out[:, :, 1] = (img >> np.uint32(16)) & np.uint32(65535)

    return out


def u16_3ch_to_u32_1ch(img):
    # The image format with the most bits that can be displayed on Windows without additional software and that
    # opencv can handle is PNG's uint16
    out = img[:, :, 0].astype(np.float64)  # float64 = max 2^53
    cv2.add(out, img[:, :, 1].astype(np.float64) * np.float64(65536), dst=out)  # opencv did not have uint32 type
    return out.astype(np.uint32)  # cast


def newdata(frameshape):
    print("\033[94m[INFO] Initialise data for blinking.\033[0m")
    return np.zeros(frameshape, dtype=np.uint32)


class IntensityBasedOpeness:
    def __init__(self, eye_id):
        # todo: It is necessary to consider whether the filename can be changed in the configuration file, etc.
        if eye_id in [EyeId.LEFT]:
            self.imgfile = "IBO_LEFT.png"
        else:
            pass
        if eye_id in [EyeId.RIGHT]:
            self.imgfile = "IBO_RIGHT.png"
        else:
            pass
        # self.imgfile = "IBO_LEFT.png" if eyeside is EyeLR.LEFT else "IBO_RIGHT.png"
        # self.data[0, -1] = maxval, [1, -1] = rotation, [2, -1] = x, [3, -1] = y
        self.data = None
        self.lct = None
        self.maxval = 0
        # self.img_roi = self.now_roi == {"rotation": 0, "x": 0, "y": 0}
        self.img_roi = np.zeros(3, dtype=np.int32)
        self.now_roi = np.zeros(3, dtype=np.int32)
        self.prev_val = 0.5

        self.old = []
        self.color = []
        self.x = []
        self.fc = 0
        self.filterlist = []

        self.maxinten = 0

        self.tri_filter = []
        #  try:
        #      min_cutoff = float(self.settings.gui_min_cutoff)  # 0.0004
        #     beta = float(self.settings.gui_speed_coefficient)  # 0.9
        # except:
        print('\033[93m[WARN] OneEuroFilter values must be a legal number.\033[0m')
        min_cutoff = 0.0004
        beta = 0.9
        noisy_point = np.array([1, 1])
        self.one_euro_filter = OneEuroFilter(
            noisy_point,
            min_cutoff=min_cutoff,
            beta=beta
        )

    def check(self, frameshape):
        # 0 in data is used as the initial value.
        # When assigning a value, +1 is added to the value to be assigned.
        self.load(frameshape)
        # self.maxval = self.data[0, -1]
        if self.lct is None:
            self.lct = time.time()

    def load(self, frameshape):
        req_newdata = False
        # Not very clever, but increase the width by 1px to save the maximum value.
        frameshape = (frameshape[0], frameshape[1] + 1)
        if self.data is None:
            print(f"\033[92m[INFO] Loaded data for blinking: {self.imgfile}\033[0m")
            if os.path.isfile(self.imgfile):
                try:
                    img = cv2.imread(self.imgfile, flags=cv2.IMREAD_UNCHANGED)
                    # check code: cv2.absdiff(img,u32_1ch_to_u16_3ch(u16_3ch_to_u32_1ch(img)))
                    if img.shape[:2] != frameshape:
                        print("size does not match the input frame.")
                        req_newdata = True
                    else:
                        self.data = u16_3ch_to_u32_1ch(img)
                        self.img_roi[:] = self.data[1:4, -1]
                        if not np.array_equal(self.img_roi, self.now_roi):
                            # If the ROI recorded in the image file differs from the current ROI
                            req_newdata = True
                        else:
                            self.maxval = self.data[0, -1]
                except:
                    print("[ERROR] File read error: {}".format(self.imgfile))
                    req_newdata = True
            else:
                print("\033[94m[INFO] File does not exist.\033[0m")
                req_newdata = True
        else:
            if self.data.shape != frameshape or not np.array_equal(self.img_roi, self.now_roi):
                # If the ROI recorded in the image file differs from the current ROI todo: Using the previous and
                #  current frame sizes and centre positions from the original, etc., the data can be ported to some
                #  extent, but there may be many areas where code changes are required.
                print("[INFO] \033[94mFrame size changed.\033[0m")
                req_newdata = True
        if req_newdata:
            self.data = newdata(frameshape)
            self.maxval = 0
            self.img_roi = self.now_roi.copy()

    def save(self):
        self.data[0, -1] = self.maxval
        self.data[1:4, -1] = self.now_roi
        cv2.imwrite(self.imgfile, u32_1ch_to_u16_3ch(self.data))

    def change_roi(self, roiinfo: dict):
        self.now_roi[:] = [v for v in roiinfo.values()]

    def intense(self, x, y, frame):
        # x,y = 0~(frame.shape[1 or 0]-1), frame = 1-channel frame cropped by ROI
        self.check(frame.shape)
        int_x, int_y = int(x), int(y)
        if int_x < 0 or int_y < 0:
            return self.prev_val
        upper_x = min(int_x + 25, frame.shape[1] - 1)  # TODO make this a setting
        lower_x = max(int_x - 25, 0)
        upper_y = min(int_y + 25, frame.shape[0] - 1)
        lower_y = max(int_y - 25, 0)

        # frame_crop = frame[lower_y:upper_y, lower_x:upper_x]
        # frame = safe_crop(frame, lower_x, lower_y, upper_x, upper_y, False)
        # ret_, th = cv2.threshold(frame_crop, 80, 1.0, cv2.THRESH_BINARY_INV, dst=frame_crop)
        frame_crop = frame

        # ret, f = cv2.threshold(frame, 80, 255, cv2.THRESH_BINARY)
        #  ret, frame_crop = cv2.threshold(frame_crop, 80, 255, cv2.THRESH_BINARY)

        # The same can be done with cv2.integral, but since there is only one area of the rectangle for which we want
        # to know the total value, there is no advantage in terms of computational complexity.
        intensity = frame_crop.sum() + 1
        # cv2.imshow('e', frame)
        # if cv2.waitKey(10) == 27:
        #    exit()
        if len(self.filterlist) < 800:
            self.filterlist.append(intensity)
        else:
            self.filterlist.pop()
            self.filterlist.append(intensity)

        if intensity >= np.percentile(self.filterlist, 99):  # filter abnormally high values
            intensity = self.maxval

        # self.tri_filter.append(intensity)
        # if len(self.tri_filter) > 3:
        #   self.tri_filter.pop(0)
        #  intensity = sum(self.tri_filter) / 3
        # avg_color_per_row = np.average(frame_crop, axis=0)
        # avg_color = np.average(avg_color_per_row, axis=0)
        # ar, ag, ab = avg_color
        #  intensity = int(ar * 8) #higher = closed

        # cv2.imshow("IBO", frame_crop)
        # if cv2.waitKey(1) & 0xFF == ord("q"):
        #   pass

        # numpy:np.sum(),ndarray.sum()
        # opencv:cv2.sumElems()
        # I don't know which is faster.
        changed = False
        newval_flg = False
        oob = False

        if int_x >= frame.shape[1]:
            int_x = frame.shape[1] - 1
            oob = True

        if int_x < 0:
            int_x = True
            oob = True

        if int_y >= frame.shape[0]:
            int_y = frame.shape[0] - 1
            oob = True

        if int_y < 0:
            int_y = 1
            oob = True

        if not oob:
            data_val = self.data[int_y, int_x]
        else:
            data_val = 0

        # max pupil per cord
        if data_val == 0:
            # The value of the specified coordinates has not yet been recorded.
            self.data[int_y, int_x] = intensity
            changed = True
            newval_flg = True
        else:
            if intensity < data_val:  # if current intensity value is less (more pupil), save that
                self.data[int_y, int_x] = intensity  # set value
                changed = True
            else:
                intensitya = max(data_val + 0.001, 1)  # if current intensity value is not less use
                self.data[int_y, int_x] = intensitya  # set value
                changed = True

        # min pupil global
        if self.maxval == 0:  # that value is not yet saved
            self.maxval = intensity  # set value at 0 index
        else:
            if intensity > self.maxval:  # if current intensity value is more (less pupil), save that NOTE: we have the
                self.maxval = intensity - 5  # set value at 0 index
            else:
                intensityd = max((self.maxval - 5),
                                 1)  # continuously adjust closed intensity, will be set when user blink, used to allow eyes to close when lighting changes
                self.maxval = intensityd  # set value at 0 index
        if newval_flg:
            # Do the same thing as in the original version.
            eyeopen = self.prev_val  # 0.9
        else:
            maxp = self.data[int_y, int_x]
            minp = self.maxval

            eyeopen = ((intensity - maxp) / (
                        minp - maxp))  # for whatever reason when input and maxp are too close it outputs high
            #   eyeopen = ((eyeopen - 0.3) / (1.0 - 0.3))
            eyeopen = 1 - eyeopen

        if changed and ((time.time() - self.lct) > 5):  # save every 5 seconds if something changed to save disk usage
            self.save()
            self.lct = time.time()
        # @filter_eyeopen = (eyeopen + self.prev_val) / 2

        self.prev_val = eyeopen
        try:
            noisy_point = np.array([float(eyeopen), float(eyeopen)])  # filter our values with a One Euro Filter
            point_hat = self.one_euro_filter(noisy_point)
            eyeopenx = point_hat[0]
            eyeopeny = point_hat[1]
            eyeopen = (eyeopenx + eyeopeny) / 2
        except:
            pass

        # intensityold = img.sum() + 1
        #  avg_color_per_row = np.average(img, axis=0)
        # avg_color = np.average(avg_color_per_row, axis=0)
        # ar, ag, ab = avg_color
        # intensity = int(ar * 8)  # higher = closed
        # self.old.append(intensity)
        # self.color.append(intensity)
        # self.x.append(self.fc)

        # cv2.imshow("show_img.jpg", img)
        # self.fc = self.fc + 1
        return eyeopen
