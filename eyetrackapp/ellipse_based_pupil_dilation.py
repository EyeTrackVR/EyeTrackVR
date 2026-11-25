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

Ellipse Based Pupil Dilation By: Prohurtz, PallasNeko (Optimization)
Algorithm App Implementations By: Prohurtz

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import logging
from collections import deque

import numpy
import numpy as np
import threading
import time
import os
import cv2

from eye import EyeId
from one_euro_filter import OneEuroFilter
from utils.user_data import user_data_path

logger = logging.getLogger(__name__)

# np.percentile sorts the whole filter window (up to calibration seconds x fps
# samples). Below this window length it is computed every frame; above it, the
# outlier cut-off is refreshed every _PERCENTILE_REFRESH_FRAMES frames.
_PERCENTILE_EXACT_BELOW = 64
_PERCENTILE_REFRESH_FRAMES = 10

os.environ["OMP_NUM_THREADS"] = "1"

# Note.
# OpenCV on Windows will generate an error if the file path contains non-ASCII characters when using cv2.imread(), cv2.imwrite(), etc.
# https://stackoverflow.com/questions/43185605/how-do-i-read-an-image-from-a-path-with-unicode-characters
# https://github.com/opencv/opencv/issues/18305


def u32_1ch_to_u16_3ch(img):
    out = np.zeros((*img.shape[:2], 3), dtype=np.uint16)
    # https://github.com/numpy/numpy/issues/2524
    # https://stackoverflow.com/questions/52782511/why-is-numpy-slower-than-python-for-left-bit-shifts
    out[:, :, 0] = img & np.uint32(65535)
    out[:, :, 1] = (img >> np.uint32(16)) & np.uint32(65535)

    return out


def u16_3ch_to_u32_1ch(img):
    # The image format with the most bits that can be displayed on Windows without additional software and that opencv can handle is PNG's uint16
    out = img[:, :, 0].astype(np.float64)  # float64 = max 2^53
    cv2.add(out, img[:, :, 1].astype(np.float64) * np.float64(65536), dst=out)  # opencv did not have uint32 type
    return out.astype(np.uint32)  # cast


def newdata(frameshape):
    logger.info("Initialise data for dilation (shape=%s).", frameshape)
    return np.zeros(frameshape, dtype=np.uint32)


# EBPD
class EllipseBasedPupilDilation:
    def __init__(self, eye_id):
        # The calibration image lives in the user data folder. Older builds wrote
        # it to the working directory; that copy is still read while it is the
        # only one, so existing calibration survives the move.
        name = "EBPD_LEFT.png" if eye_id == EyeId.LEFT else "EBPD_RIGHT.png"
        self.imgfile = user_data_path(name)
        self._legacy_imgfile = name
        self._save_thread: threading.Thread | None = None
        # self.data[0, -1] = maxval, [1, -1] = rotation, [2, -1] = x, [3, -1] = y
        self.data = None
        self.lct = None
        self.maxval = 0
        # self.img_roi = self.now_roi == {"rotation": 0, "x": 0, "y": 0}
        self.img_roi = np.zeros(3, dtype=np.int32)
        self.now_roi = np.zeros(3, dtype=np.int32)
        self.prev_val = 0.5
        self.filterlist = deque()
        # Cached 99th percentile of filterlist and frames since it was computed.
        self._p99 = None
        self._p99_age = 0
        self.averageList = []
        self.eye_id = eye_id
        min_cutoff = 0.00001
        beta = 0.05
        noisy_point = np.array([1, 1])
        self.one_euro_filter = OneEuroFilter(noisy_point, min_cutoff=min_cutoff, beta=beta)

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
            logger.info("Loading data for pupil dilation: %s", self.imgfile)
            src = self.imgfile
            if not os.path.isfile(src) and os.path.isfile(self._legacy_imgfile):
                src = self._legacy_imgfile
            if os.path.isfile(src):
                try:
                    img = cv2.imread(src, flags=cv2.IMREAD_UNCHANGED)
                    # check code: cv2.absdiff(img,u32_1ch_to_u16_3ch(u16_3ch_to_u32_1ch(img)))
                    if img is None or img.shape[:2] != frameshape:
                        logger.warning(
                            "Dilation calibration size mismatch or unreadable image (%s).",
                            self.imgfile,
                        )
                        req_newdata = True
                    else:
                        self.data = u16_3ch_to_u32_1ch(img)
                        self.img_roi[:] = self.data[1:4, -1]
                        if not np.array_equal(self.img_roi, self.now_roi):
                            # If the ROI recorded in the image file differs from the current ROI
                            req_newdata = True
                        else:
                            self.maxval = self.data[0, -1]
                except (cv2.error, OSError, ValueError, AttributeError) as e:
                    logger.error(
                        "File read error for dilation calibration %s: %s",
                        self.imgfile,
                        e,
                    )
                    req_newdata = True
            else:
                logger.info("Dilation calibration file does not exist: %s", self.imgfile)
                req_newdata = True
        else:
            if self.data.shape != frameshape or not np.array_equal(self.img_roi, self.now_roi):
                # If the ROI recorded in the image file differs from the current ROI
                # TODO: Migrate compatible calibration data instead of resetting on ROI/frame size changes.
                logger.info("Dilation calibration frame size changed; resetting data.")
                req_newdata = True
        if req_newdata:
            self.data = newdata(frameshape)
            self.maxval = 0
            self.img_roi = self.now_roi.copy()

    def save(self):
        self.data[0, -1] = self.maxval
        self.data[1:4, -1] = self.now_roi
        # PNG encoding takes milliseconds: write a snapshot (the conversion makes
        # a new array) on a short-lived thread instead of the tracking thread.
        # If the previous write is still running, skip; the next save follows.
        if self._save_thread is not None and self._save_thread.is_alive():
            return
        snapshot = u32_1ch_to_u16_3ch(self.data)
        self._save_thread = threading.Thread(target=self._write_image, args=(self.imgfile, snapshot), name="EBPD save")
        self._save_thread.start()

    @staticmethod
    def _write_image(path, img):
        try:
            if not cv2.imwrite(path, img):
                logger.warning("Could not save dilation calibration to %s", path)
        except (cv2.error, OSError) as e:
            logger.warning("Could not save dilation calibration to %s: %s", path, e)

    def change_roi(self, roiinfo: dict):
        self.now_roi[:] = [v for v in roiinfo.values()]

    def clear_filter(self):
        self.data = None
        self.filterlist.clear()
        self._p99 = None
        self.averageList.clear()
        # A write still in flight would recreate the file after the removal.
        if self._save_thread is not None:
            self._save_thread.join()
        # Both copies: a leftover working-directory one would be loaded again.
        for path in (self.imgfile, self._legacy_imgfile):
            if os.path.exists(path):
                os.remove(path)

    def intense(self, w, h, x, y, frame, filterSamples, outputSamples):
        # x,y = 0~(frame.shape[1 or 0]-1), frame = 1-channel frame cropped by ROI
        self.check(frame.shape)
        int_x, int_y = int(x), int(y)
        if int_x < 0 or int_y < 0:
            return self.prev_val
        # TODO: Base this sample radius on the active tracking radius.

        # The same can be done with cv2.integral, but since there is only one area of the rectangle for which we want to know the total value, there is no advantage in terms of computational complexity.
        pupil_area = numpy.pi * (w / 2) * (h / 2)

        self.filterlist.append(pupil_area)
        while len(self.filterlist) > filterSamples:
            self.filterlist.popleft()

        try:
            self._p99_age += 1
            if (
                self._p99 is None
                or len(self.filterlist) < _PERCENTILE_EXACT_BELOW
                or self._p99_age >= _PERCENTILE_REFRESH_FRAMES
            ):
                self._p99 = np.percentile(self.filterlist, 99)
                self._p99_age = 0
            if pupil_area >= self._p99:  # filter abnormally high values
                pupil_area = self.maxval

        except (ValueError, IndexError) as e:
            logger.debug("Pupil area percentile filter skipped: %s", e)

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

        if not oob and self.data.any():
            data_val = self.data[int_y, int_x]
        else:
            data_val = 0

        # max pupil per cord
        if data_val == 0:
            # The value of the specified coordinates has not yet been recorded.
            self.data[int_y, int_x] = pupil_area
            changed = True
            newval_flg = True
        else:
            if pupil_area < data_val:  # if current intensity value is less (more pupil), save that
                self.data[int_y, int_x] = pupil_area  # set value
                changed = True
            else:
                pupil_areaa = max(
                    data_val + 5000, 1
                )  # if current intensity value is not less use  this is an agressive adjust, test
                self.data[int_y, int_x] = pupil_areaa  # set value
                changed = True

        # min pupil global
        if self.maxval == 0:  # that value is not yet saved
            self.maxval = pupil_area  # set value at 0 index
        else:
            if pupil_area > self.maxval:  # if current intensity value is more (less pupil), save that NOTE: we have the
                self.maxval = pupil_area - 5  # set value at 0 index
            else:
                pupil_aread = max(
                    (self.maxval - 5), 1
                )  # continuously adjust closed intensity, will be set when user blink, used to allow eyes to close when lighting changes
                self.maxval = pupil_aread  # set value at 0 index

        if newval_flg:
            # Do the same thing as in the original version.
            eyedilation = self.prev_val  # 0.9
        else:
            maxp = float(self.data[int_y, int_x])
            minp = float(self.maxval)

            try:
                if not np.isfinite(pupil_area) or not np.isfinite(maxp) or not np.isfinite(minp) or (minp - maxp) == 0:
                    eyedilation = 0.5
                else:
                    eyedilation = (pupil_area - maxp) / (minp - maxp)

            except (ZeroDivisionError, ValueError, TypeError) as e:
                logger.debug("Eyedilation ratio fallback to 0.5: %s", e)
                eyedilation = 0.5
            eyedilation = 1 - eyedilation

            if outputSamples > 0:
                if len(self.averageList) < outputSamples:
                    self.averageList.append(eyedilation)
                else:
                    self.averageList.pop(0)
                    self.averageList.append(eyedilation)
                    eyedilation = np.average(self.averageList)

            if eyedilation > 1:  # clamp values
                eyedilation = 1.0

            if eyedilation < 0:
                eyedilation = 0.0

        if changed and ((time.time() - self.lct) > 15):  # save every 5 seconds if something changed to save disk usage
            self.save()
            self.lct = time.time()

        self.prev_val = eyedilation
        try:
            noisy_point = np.array([float(eyedilation), float(eyedilation)])  # fliter our values with a One Euro Filter
            point_hat = self.one_euro_filter(noisy_point)
            eyedilationx = point_hat[0]
            eyedilationy = point_hat[1]
            eyedilation = (eyedilationx + eyedilationy) / 2

        except (TypeError, ValueError, AttributeError) as e:
            logger.debug("Eyedilation one-euro filter skipped: %s", e)

        return eyedilation
