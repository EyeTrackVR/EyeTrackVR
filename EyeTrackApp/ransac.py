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

RANSAC 3D By: Summer#2406 (Main Algorithm Engineer), Pupil Labs (pye3d), PallasNeko (Optimization)
Algorithm App Implementations By: Prohurtz, qdot (Initial App Creator)

Copyright (c) 2025 EyeTrackVR <3
LICENSE: Summer Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""
import cv2
import numpy as np
from eye import EyeId
from utils.img_utils import safe_crop
from utils.misc_utils import clamp
import os
import psutil
import sys

process = psutil.Process(os.getpid())  # set process priority to low
try:  # medium chance this does absolutely nothing but eh
    sys.getwindowsversion()
except AttributeError:
    process.nice(0)  # UNIX: 0 low 10 high
    process.nice()
else:
    process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)  # Windows
    process.nice()


def ellipse_model(data, y, f):
    """
    There is no need to make this process a function, since making the process a function will slow it down a little by calling it.
    The results may be slightly different from the lambda version due to calculation errors derived from float types, but the calculation results are virtually the same.
    a = 1.0,b = P[0],c = P[1],d = P[2],e = P[3],f = P[4]
    :param data:
    :param y: np.c_[d, e, a, c, b]
    :param f: f == P[4, 0]
    :return: this_return == np.array([ellipse_model(x, y) for (x, y) in data ])
    """
    return data.dot(y) + f


# @profile
def fit_rotated_ellipse_ransac(
    data: np.ndarray,
    rng: np.random.Generator,
    iter=45,
    sample_num=10,
    offset=80,  # 80.0, 10, 80
):  # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower
    effective_sample = None

    # The array contents do not change during the loop, so only one call is needed.
    # They say len is faster than shape.
    # Reference url: https://stackoverflow.com/questions/35547853/what-is-faster-python3s-len-or-numpys-shape
    len_data = len(data)

    if len_data < sample_num:
        return None

    # Type of calculation result
    ret_dtype = np.float64

    # Sorts a random number array of size (iter,len_data). After sorting, returns the index of sample_num random numbers before sorting.
    # If the array size is less than about 100, this is faster than rng.choice.
    rng_sample = rng.random((iter, len_data)).argsort()[:, :sample_num]
    # or
    # I don't see any advantage to doing this.
    # rng_sample = np.asarray(rng.random((iter, len_data)).argsort()[:, :sample_num], dtype=np.int32)

    # I don't think it looks beautiful.
    # x,y,x**2,y**2,x*y,1,-1*x**2
    datamod = np.concatenate(
        [
            data,
            data**2,
            (data[:, 0] * data[:, 1])[:, np.newaxis],
            np.ones((len_data, 1), dtype=ret_dtype),
            (-1 * data[:, 0] ** 2)[:, np.newaxis],
        ],
        axis=1,
        dtype=ret_dtype,
    )

    datamod_slim = np.array(datamod[:, :5], dtype=ret_dtype)

    datamod_rng = datamod[rng_sample]
    datamod_rng6 = datamod_rng[:, :, 6]
    datamod_rng_swap = datamod_rng[:, :, [4, 3, 0, 1, 5]]
    datamod_rng_swap_trans = datamod_rng_swap.transpose((0, 2, 1))

    # These two lines are one of the bottlenecks
    datamod_rng_5x5 = np.matmul(datamod_rng_swap_trans, datamod_rng_swap)
    datamod_rng_p5smp = np.matmul(np.linalg.inv(datamod_rng_5x5), datamod_rng_swap_trans)

    datamod_rng_p = np.matmul(datamod_rng_p5smp, datamod_rng6[:, :, np.newaxis]).reshape((-1, 5))

    # I don't think it looks beautiful.
    ellipse_y_arr = np.asarray(
        [
            datamod_rng_p[:, 2],
            datamod_rng_p[:, 3],
            np.ones(len(datamod_rng_p)),
            datamod_rng_p[:, 1],
            datamod_rng_p[:, 0],
        ],
        dtype=ret_dtype,
    )

    ellipse_data_arr = ellipse_model(datamod_slim, ellipse_y_arr, np.asarray(datamod_rng_p[:, 4])).transpose((1, 0))
    ellipse_data_abs = np.abs(ellipse_data_arr)
    ellipse_data_index = np.argmax(np.sum(ellipse_data_abs < offset, axis=1), axis=0)
    effective_data_arr = ellipse_data_arr[ellipse_data_index]
    effective_sample_p_arr = datamod_rng_p[ellipse_data_index]

    return fit_rotated_ellipse(effective_data_arr, effective_sample_p_arr)


# @profile
def fit_rotated_ellipse(data, P):
    a = 1.0
    b = P[0]
    c = P[1]
    d = P[2]
    e = P[3]
    f = P[4]
    # The cost of trigonometric functions is high.
    theta = 0.5 * np.arctan(b / (a - c), dtype=np.float64)
    theta_sin = np.sin(theta, dtype=np.float64)
    theta_cos = np.cos(theta, dtype=np.float64)
    tc2 = theta_cos**2
    ts2 = theta_sin**2
    b_tcs = b * theta_cos * theta_sin

    # Do the calculation only once
    cxy = b**2 - 4 * a * c
    cx = (2 * c * d - b * e) / cxy
    cy = (2 * a * e - b * d) / cxy

    # I just want to clear things up around here.
    cu = a * cx**2 + b * cx * cy + c * cy**2 - f
    cu_r = np.array([(a * tc2 + b_tcs + c * ts2), (a * ts2 - b_tcs + c * tc2)])
    if cu > 1:  # negatives can get thrown which cause errors, just ignore them
        wh = np.sqrt(cu / cu_r)
    else:
        pass

    w, h = wh[0], wh[1]

    error_sum = np.sum(data)
   # print("fitting error = %.3f" % (error_sum))

    return (cx, cy, w, h, theta)


def get_center_noclamp(center_xy, radius):
    center_x, center_y = center_xy
    upper_x = center_x + radius
    lower_x = center_x - radius
    upper_y = center_y + radius
    lower_y = center_y - radius

    ransac_upper_x = center_x + max(20, radius)
    ransac_lower_x = center_x - max(20, radius)
    ransac_upper_y = center_y + max(20, radius)
    ransac_lower_y = center_y - max(20, radius)
    ransac_xy_offset = (ransac_lower_x, ransac_lower_y)
    return (
        center_x,
        center_y,
        upper_x,
        lower_x,
        upper_y,
        lower_y,
        ransac_lower_x,
        ransac_lower_y,
        ransac_upper_x,
        ransac_upper_y,
        ransac_xy_offset,
    )


cct = 300


def RANSAC3D(self, hsrac_en):
    f = False
    ranf = False
    blink = 0.8
    angle = 0

    if hsrac_en:
        (
            center_x,
            center_y,
            upper_x,
            lower_x,
            upper_y,
            lower_y,
            ransac_lower_x,
            ransac_lower_y,
            ransac_upper_x,
            ransac_upper_y,
            ransac_xy_offset,
        ) = get_center_noclamp((self.rawx, self.rawy), self.radius)

        frame = safe_crop(
            self.current_image_gray_clean,
            int(ransac_lower_x),
            int(ransac_lower_y),
            int(ransac_upper_x),
            int(ransac_upper_y),
            1,
        )

    else:
        frame = self.current_image_gray_clean
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    rng = np.random.default_rng()
    newFrame2 = self.current_image_gray.copy()
    # Convert the image to grayscale, and set up thresholding. Thresholds here are basically a
    # low-pass filter that will set any pixel < the threshold value to 0. Thresholding is user
    # configurable in this utility as we're dealing with variable lighting amounts/placement, as
    # well as camera positioning and lensing. Therefore, everyone's cutoff may be different.
    #
    # The goal of thresholding settings is to make sure we can ONLY see the pupil. This is why we
    # crop the image earlier; it gives us less possible dark area to get confused about in the
    # next step.

    # Crop first to reduce the amount of data to process.

    # frame = self.current_image_gray
    # For measuring processing time of image processing
    # Crop first to reduce the amount of data to process.
    # frame = frame[0:len(frame) - 5, :]
    # To reduce the processing data, blur.
    if frame is None:
        print("[WARN] Frame is empty")
        self.failed = self.failed + 1  # we have failed, move onto next algo
        return 0, 0, 0, frame, blink, 0, 0
    else:
        frame_gray = cv2.GaussianBlur(frame, (9, 9), 10)

    # this will need to be adjusted everytime hardware is changed (brightness of IR, Camera postion, etc)m
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(frame_gray)

    maxloc0_hf, maxloc1_hf = int(0.5 * max_loc[0]), int(0.5 * max_loc[1])

    # crop 15% sqare around min_loc
    # frame_gray = frame_gray[max_loc[1] - maxloc1_hf:max_loc[1] + maxloc1_hf,
    #               max_loc[0] - maxloc0_hf:max_loc[0] + maxloc0_hf]
    if self.settings.gui_legacy_ransac:
        if self.eye_id in [EyeId.LEFT]:
            threshold_value = self.settings.gui_legacy_ransac_thresh_left
        else:
            threshold_value = self.settings.gui_legacy_ransac_thresh_right
    else:
        threshold_value = min_val + self.settings.gui_thresh_add

    _, thresh = cv2.threshold(frame_gray, threshold_value, 255, cv2.THRESH_BINARY)
    try:
        opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
        th_frame = 255 - closing
    except:
        # I want to eliminate try here because try tends to be slow in execution.
        th_frame = 255 - frame_gray

    contours, _ = cv2.findContours(th_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    hull = []
    # print(contours)
    # This way is faster than contours[i]
    # But maybe this one is faster. hull = [cv2.convexHull(cnt, False) for cnt in contours]
    for cnt in contours:
        hull.append(cv2.convexHull(cnt, False))
    if not hull:
        # If empty, go to next loop
        pass
    try:

        cnt = sorted(hull, key=cv2.contourArea)
        maxcnt = cnt[-1]
        # ellipse = cv2.fitEllipse(maxcnt)
        ransac_data = fit_rotated_ellipse_ransac(maxcnt.reshape(-1, 2), rng)
        if ransac_data is None:
            # ransac_data is None==maxcnt.shape[0]<sample_num
            # go to next loop
            pass

        cx, cy, w, h, theta = ransac_data
        # print(cx, cy)
        # cxi, cyi, wi, hi = int(cx), int(cy), int(w), int(h)

        # cv2.drawContours(self.current_image_gray, contours, -1, (255, 0, 0), 1)
    # cv2.circle(self.current_image_gray, (cx, cy), 2, (0, 0, 255), -1)
    # cx1, cy1, w1, h1, theta1 = fit_rotated_ellipse(maxcnt.reshape(-1, 2))
    # cv2.ellipse(self.current_image_gray, (cx, cy), (w, h), theta * 180.0 / np.pi, 0.0, 360.0, (50, 250, 200), 1, )

    # img = newImage2[y1:y2, x1:x2]
    except:
        ranf = True
        pass

    self.current_image_gray = frame
    cv2.circle(self.current_image_gray, min_loc, 2, (0, 0, 255), -1)  # the point of the darkest area in the image

    # However eyes are annoyingly three dimensional, so we need to take this ellipse and turn it
    # into a curve patch on the surface of a sphere (the eye itself). If it's not a sphere, see your
    # ophthalmologist about possible issues with astigmatism.
    try:

        # Get axis and angle of the ellipse, using pupil labs 2d algos. The next bit of code ranges
        # from somewhat to completely magic, as most of it happens in native libraries (hence passing
        # via dicts).
        result_2d = {}
        result_2d_final = {}
        result_2d["center"] = (cx, cy)
        result_2d["axes"] = (w, h)
        result_2d["angle"] = theta * 180.0 / np.pi
        angle = result_2d["angle"]
        result_2d_final["ellipse"] = result_2d
        result_2d_final["diameter"] = w
        result_2d_final["location"] = (cx, cy)
        result_2d_final["confidence"] = 0.99
        result_2d_final["timestamp"] = self.current_frame_number / self.current_fps
        # Black magic happens here, but after this we have our reprojected pupil/eye, and all we had
        # to do was sell our soul to satan and/or C++.

        result_3d = self.detector_3d.update_and_detect(result_2d_final, self.current_image_gray)

        # Now we have our pupil
        ellipse_3d = result_3d["ellipse"]
        # And our eyeball that the pupil is on the surface of
        self.lkg_projected_sphere = result_3d["projected_sphere"]

        # Record our pupil center
        exm = ellipse_3d["center"][0]
        eym = ellipse_3d["center"][1]
        #  print(result_2d["angle"])
        d = result_3d["diameter_3d"]
        self.cc_radius = int(float(self.lkg_projected_sphere["axes"][0]))
        self.xc = int(float(self.lkg_projected_sphere["center"][0]))
        self.yc = int(float(self.lkg_projected_sphere["center"][1]))

    except:
        f = True

    csy = newFrame2.shape[0]
    csx = newFrame2.shape[1]
    if hsrac_en:

        if ranf:
            cx = self.rawx
            cy = self.rawy
        else:
            #  print(int(cx), int(clamp(cx + ransac_lower_x, 0, csx)), ransac_lower_x, csx, "y", int(cy), int(clamp(cy + ransac_lower_y, 0, csy)), ransac_lower_y, csy)
            cx = int(clamp(cx + ransac_lower_x, 0, csx))  # dunno why this is being weird
            cy = int(clamp(cy + ransac_lower_y, 0, csy))

    # print(contours)
    for cnt in contours:
        (x, y, w, h) = cv2.boundingRect(cnt)
        perscalarw = w / csx
        perscalarh = h / csy
        #  print(abs(perscalarw-perscalarh))
        # if abs(perscalarw-perscalarh) >= 0.2: # TODO setting
        #    blink = 0.0

        if self.settings.gui_RANSACBLINK:

            if self.ran_blink_check_for_file:
                if self.eye_id in [EyeId.LEFT]:
                    file_path = "RANSAC_blink_LEFT.cfg"
                if self.eye_id in [EyeId.RIGHT]:
                    file_path = "RANSAC_blink_RIGHT.cfg"
                else:
                    file_path = "RANSAC_blink_RIGHT.cfg"

                if os.path.exists(file_path):
                    with open(file_path, "r") as file:
                        self.blink_list = [float(line.strip()) for line in file]
                else:
                    print(
                        f"\033[93m[INFO] RANSAC Blink Config '{file_path}' not found. Waiting for calibration.\033[0m"
                    )
                self.ran_blink_check_for_file = False

            if len(self.blink_list) == 10000:  # self calibrate ransac blink IN TESTING
                if self.eye_id in [EyeId.LEFT]:
                    with open("RANSAC_BLINK_LEFT.cfg", "w") as file:
                        for item in self.blink_list:
                            file.write(str(item) + "\n")

                if self.eye_id in [EyeId.RIGHT]:
                    with open("RANSAC_BLINK_RIGHT.cfg", "w") as file:
                        for item in self.blink_list:
                            file.write(str(item) + "\n")

                # print("SAVE")

                # self.blink_list.pop(0)
                self.blink_list.append(abs(perscalarw - perscalarh))

            elif len(self.blink_list) < 10000:
                self.blink_list.append(abs(perscalarw - perscalarh))

            if abs(perscalarw - perscalarh) >= np.percentile(self.blink_list, 92):
                blink = 0.0

    try:
        cv2.drawContours(self.current_image_gray, contours, -1, (255, 0, 0), 1)  # TODO: fix visualizations with HSRAC
        cv2.circle(self.current_image_gray, (int(cx), int(cy)), 2, (0, 0, 255), -1)
    except:
        pass

    # try:  #for some reason the pye3d visualizations are wack, im going to just not visualize it for now..
    #   cv2.ellipse(
    #       self.current_image_gray,
    #     tuple(int(v) for v in ellipse_3d["center"]),
    #      tuple(int(v) for v in ellipse_3d["axes"]),
    #     ellipse_3d["angle"],
    #      0,
    #      360,  # start/end angle for drawing
    #      (0, 255, 0),  # color (BGR): red
    #  )
    # except Exception:
    # Sometimes we get bogus axes and trying to draw this throws. Ideally we should check for
    # validity beforehand, but for now just pass. It usually fixes itself on the next frame.
    #    pass

    try:
        # print(self.lkg_projected_sphere["angle"], self.lkg_projected_sphere["axes"], self.lkg_projected_sphere["center"])
        cv2.ellipse(
            newFrame2,
            tuple(int(v) for v in self.lkg_projected_sphere["center"]),
            tuple(int(v) for v in self.lkg_projected_sphere["axes"]),
            self.lkg_projected_sphere["angle"],
            0,
            360,  # start/end angle for drawing
            (0, 255, 0),  # color (BGR): red
        )

        # draw line from center of eyeball to center of pupil
        cv2.line(
            self.current_image_gray,
            tuple(int(v) for v in self.lkg_projected_sphere["center"]),
            tuple(int(v) for v in ellipse_3d["center"]),
            (0, 255, 0),  # color (BGR): red
        )

    except:
        pass

    self.current_image_gray = newFrame2
    y, x = self.current_image_gray.shape
    thresh = cv2.resize(thresh, (x, y))
    try:
        self.failed = 0  # we have succeded, continue with this
        return cx, cy, angle, thresh, blink, w, h
    except:
        self.failed = self.failed + 1  # we have failed, move onto next algo
        return 0, 0, 0, thresh, blink, 0, 0
