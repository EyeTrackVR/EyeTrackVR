import math
import timeit
from functools import lru_cache

import cv2
import numpy as np
from numpy.linalg import _umath_linalg

from haar_surround_feature import (
    AutoRadiusCalc,
    BlinkDetector,
    CvParameters, conv_int, get_frameint_empty_array, get_hsf_center,
)
from utils.img_utils import safe_crop
from utils.misc_utils import clamp

# from line_profiler_pycharm import profile

#RANSAC

thresh_add = 10

imshow_enable = True
calc_print_enable = False
save_video = False
skip_autoradius = False
skip_blink_detect = False

# cache param
lru_maxsize_vvs = 16
lru_maxsize_vs = 64
lru_maxsize_s=128
# CV param
default_radius = 20
auto_radius_range = (default_radius - 18, default_radius + 20)  # (10,30)
auto_radius_step = 1
blink_init_frames = 60 * 3  # 60fps*3sec,Number of blink statistical frames
# step==(x,y)
default_step = (5, 5)  # bigger the steps,lower the processing time! ofc acc also takes an impact


@lru_cache(maxsize=lru_maxsize_s)
def get_ransac_empty_array_new(iter_num, sample_num, len_data):
    # Function to reduce array allocation by providing an empty array first and recycling it with lru
    use_dtype = np.float64
    dm_rng = np.empty((iter_num, sample_num, 7), dtype=use_dtype)
    dm_rng_swap = np.empty((iter_num, sample_num, 5), dtype=use_dtype)
    dm_rng_swap_trans = dm_rng_swap.transpose((0, 2, 1))
    # dm_rng_swap_trans = np.empty((iter_num, 5,sample_num), dtype=use_dtype)
    dm_rng_5x5 = np.empty((iter_num, 5, 5), dtype=use_dtype)
    dm_rng_p5smp = np.empty((iter_num, 5, sample_num), dtype=use_dtype)
    dm_rng_p = np.empty((iter_num, 5), dtype=use_dtype)
    dm_rng_p_npaxis = dm_rng_p[:, :, np.newaxis]
    ellipse_y_arr = np.empty((iter_num, 5), dtype=use_dtype)
    ellipse_y_arr[:, 2] = 1
    swap_index = np.array([4, 3, 0, 1, 5], dtype=np.uint8)
    dm_brod = np.broadcast_to(dm_rng_p[:, 4, np.newaxis], (iter_num, len_data))
    dm_rng_six = dm_rng[:, :, 6, np.newaxis]
    dm_rng_p_24 = dm_rng_p[:, 2:4]
    dm_rng_p_10 = dm_rng_p[:, 1::-1]
    el_y_arr_2 = ellipse_y_arr[:, :2]
    el_y_arr_3 = ellipse_y_arr[:, 3:]
    datamod = np.empty((len_data, 7), dtype=use_dtype)  # np.empty((len(data), 7), dtype=ret_dtype)
    datamod[:, 5] = 1
    datamod_b = datamod[:, :5]  # .T
    rdm_index_init_arr = np.empty((iter_num, len_data), dtype=np.uint16)
    rdm_index_init_arr[:, :] = np.arange(len_data, dtype=np.uint16)
    rdm_index = np.empty((iter_num, len_data), dtype=np.uint16)
    rdm_index_smpnum = rdm_index[:, :sample_num]
    ellipse_data_arr = np.empty((iter_num, len_data), dtype=use_dtype)
    th_abs = np.empty((iter_num, len_data), dtype=use_dtype)
    dm_data = datamod[:, :2]  # = data
    dm_p2 = datamod[:, 2:4]  # = data * data
    dm_mul = datamod[:, 4]  # = data[:, 0] * data[:, 1]
    dm_neg = datamod[:, 6]  # = -datamod[:, 2]
    inv_ext = np.linalg.linalg.get_linalg_error_extobj(np.linalg.linalg._raise_linalgerror_singular)
    return dm_rng, dm_rng_swap, dm_rng_swap_trans, dm_rng_5x5, dm_rng_p5smp, dm_rng_p, dm_rng_p_npaxis, ellipse_y_arr, swap_index, dm_brod, dm_rng_six, dm_rng_p_24, dm_rng_p_10, el_y_arr_2, el_y_arr_3, datamod, datamod_b, dm_data, dm_p2, dm_mul, dm_neg, rdm_index_init_arr, rdm_index, rdm_index_smpnum, ellipse_data_arr, th_abs, inv_ext


# @profile
def fit_rotated_ellipse_ransac(data: np.ndarray, sfc: np.random.Generator, iter_num=100, sample_num=10, offset=80):
    # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower
    
    # The array contents do not change during the loop, so only one call is needed.
    # They say len is faster than shape.
    # Reference url: https://stackoverflow.com/questions/35547853/what-is-faster-python3s-len-or-numpys-shape
    len_data = len(data)
    
    if len_data < sample_num:
        return None
    
    dm_rng, dm_rng_swap, dm_rng_swap_trans, dm_rng_5x5, dm_rng_p5smp, dm_rng_p, dm_rng_p_npaxis, ellipse_y_arr, swap_index, dm_brod, dm_rng_six, dm_rng_p_24, dm_rng_p_10, el_y_arr_2, el_y_arr_3, datamod, datamod_b, dm_data, dm_p2, dm_mul, dm_neg, rdm_index_init_arr, rdm_index, rdm_index_smpnum, ellipse_data_arr, th_abs, inv_ext = get_ransac_empty_array_new(
        iter_num, sample_num, len_data)
    
    dm_data[:, :] = data  # [:]
    dm_p2[:, :] = data * data
    dm_mul[:] = data[:, 0] * data[:, 1]
    dm_neg[:] = -dm_p2[:, 0]  # -1 * data[:, 0] ** 2#
    
    sfc.permuted(rdm_index_init_arr, axis=1, out=rdm_index)
    
    # np.take replaces a[ind,:] and is 3-4 times faster, https://gist.github.com/rossant/4645217
    # a.take() is faster than np.take(a)
    datamod.take(rdm_index_smpnum, axis=0, mode="clip", out=dm_rng)
    
    dm_rng_swap[:, :, :] = dm_rng[:, :, swap_index]
    # or
    # dm_rng.take(swap_index, axis=2, mode="clip", out=dm_rng_swap)
    # or
    # dm_rng_swap = np.take(dm_rng,[4, 3, 0, 1, 5],axis=2)
    
    np.matmul(dm_rng_swap_trans, dm_rng_swap, out=dm_rng_5x5)
    # np.linalg.solve(np.matmul(dm_rng_swap_trans, dm_rng_swap), dm_rng_swap_trans) # solve is slow https://github.com/bogovicj/JaneliaMLCourse/issues/1
    #_umath_linalg.inv(dm_rng_5x5, signature='d->d',
                      extobj=inv_ext, out=dm_rng_5x5)
    dm_rng_5x5 = np.linalg.pinv(dm_rng_5x5)
    np.matmul(dm_rng_5x5, dm_rng_swap_trans, out=dm_rng_p5smp)
    
    np.matmul(dm_rng_p5smp, dm_rng_six, out=dm_rng_p_npaxis)
    
    el_y_arr_2[:, :] = dm_rng_p_24
    el_y_arr_3[:, :] = dm_rng_p_10
    
    cv2.gemm(ellipse_y_arr, datamod_b, 1.0, dm_brod, 1.0, dst=ellipse_data_arr, flags=cv2.GEMM_2_T)
    
    np.abs(ellipse_data_arr, out=th_abs)
    cv2.threshold(th_abs, offset, 1.0, cv2.THRESH_BINARY_INV, dst=th_abs)
    ellipse_data_index = \
        cv2.minMaxLoc(cv2.reduce(th_abs, 1, cv2.REDUCE_SUM))[3][1]
    
    # error_num = ellipse_data_arr[ellipse_data_index].sum()
    error_num = cv2.sumElems(ellipse_data_arr[ellipse_data_index])[0]
    effective_sample_p_arr = dm_rng_p[ellipse_data_index].tolist()
    
    return fit_rotated_ellipse(error_num, effective_sample_p_arr)


# @profile
def fit_rotated_ellipse(data, P):
    a = 1.0
    # b, c, d, e, f = P[0], P[1], P[2], P[3], P[4]
    b, c, d, e = P[0], P[1], P[2], P[3]
    theta = 0.5 * math.atan(b / (a - c))  # math.atan2(b, a - c)
    theta_sin, theta_cos = math.sin(theta), math.cos(theta)
    tc2 = theta_cos * theta_cos
    ts2 = theta_sin * theta_sin
    b_tcs = b * theta_cos * theta_sin
    cxy = b * b - 4 * a * c
    cx = (2 * c * d - b * e) / cxy
    cy = (2 * a * e - b * d) / cxy
    cu = a * cx * cx + b * cx * cy + c * cy * cy - P[4]
    # cu = c * cy * cy + cx * (a * cx + b * cy) - P[4]
    # here: https://stackoverflow.com/questions/327002/which-is-faster-in-python-x-5-or-math-sqrtx
    # and : https://gist.github.com/zed/783011
    try:
        # For some reason, a negative value may cause an error.
        w = math.sqrt(cu / (a * tc2 + b_tcs + c * ts2))
        h = math.sqrt(cu / (a * ts2 - b_tcs + c * tc2))
    except ValueError:
        return None
    error_sum = data  # sum(data)
    # print("fitting error = %.3f" % (error_sum))
    
    return cx, cy, w, h, theta


@lru_cache(lru_maxsize_vvs)
def get_ransac_frame(frame_shape):
    return np.empty(frame_shape, dtype=np.uint8), np.empty(frame_shape, dtype=np.uint8)  # np.float64)


@lru_cache(lru_maxsize_s)
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
    return center_x, center_y, upper_x, lower_x, upper_y, lower_y, ransac_lower_x, ransac_lower_y, ransac_upper_x, ransac_upper_y, ransac_xy_offset


class HSRAC_cls(object):
    def __init__(self):
        # I'd like to take into account things like print, end_time - start_time processing time, etc., but it's too much trouble.
        
        # For measuring total processing time
        
        self.main_start_time = timeit.default_timer()
        
        self.rng = np.random.default_rng()
        self.cvparam = CvParameters(default_radius, default_step)
        
        self.cv_modeo = ["first_frame", "radius_adjust", "blink_adjust", "normal"]
        self.now_modeo = self.cv_modeo[0]

        self.auto_radius_calc = AutoRadiusCalc()
        self.blink_detector = BlinkDetector()
        self.center_q1 = BlinkDetector()


        self.cap = None
        
        self.timedict = {"to_gray": [], "int_img": [], "conv_int": [], "crop": [], "total_cv": []}

        # ransac
        self.sfc = np.random.default_rng(np.random.SFC64())

        # self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        # or
        # https://stackoverflow.com/questions/31025368/erode-is-too-slow-opencv
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

        self.gauss_k = cv2.getGaussianKernel(5, 1)
        # cv2.getGaussianKernel(kernel size, sigma)
        # Increasing the kernel size improves accuracy but slows down performance.
        # Increasing sigma improves accuracy a little, but has less effect than kernel size.

    def open_video(self, video_path):
        # Temporary implementation to run
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError("Error opening video stream or file")
        self.cap = cap
        return True
    
    def read_frame(self):
        # Temporary implementation to run
        if not self.cap.isOpened():
            return False
        ret, frame = self.cap.read()
        if ret:
            # I have set it to grayscale (1ch) just in case, but if the frame is 1ch, this line can be commented out.
            # self.current_image=frame # debug code
            self.current_image_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return True
        return False
    
    def single_run(self):
        # Temporary implementation to run
      #  if imshow_enable:
        ori_frame = self.current_image_gray.copy()  # debug code
            
        blink_bd = False
        if self.now_modeo == self.cv_modeo[1]:
            # adjustment of radius
    
            # debug print
            # if calc_print_enable:
            #     temp_radius = self.auto_radius_calc.get_radius()
            #     print('Now radius:', temp_radius)
            #     self.cvparam.radius = temp_radius
    
            self.cvparam.radius = self.auto_radius_calc.get_radius()
            if self.auto_radius_calc.adj_comp_flag:
                self.now_modeo = self.cv_modeo[2] if not skip_blink_detect else self.cv_modeo[3]

        radius, pad, step, hsf = self.cvparam.get_rpsh()

        # For measuring processing time of image processing
        # cv_start_time = timeit.default_timer()
        frame = self.current_image_gray
        gray_frame = frame
        # self.timedict["to_gray"].append(timeit.default_timer() - cv_start_time)

        # Calculate the integral image of the frame
        # int_start_time = timeit.default_timer()
        frame_pad, frame_int, inner_sum, in_p00, in_p11, in_p01, in_p10, y_ro_m, x_ro_m, y_ro_p, x_ro_p, outer_sum, out_p_temp, out_p00, out_p11, out_p01, out_p10, response_list, frame_conv, frame_conv_stride = get_frameint_empty_array(
            gray_frame.shape, pad, step[0], step[1], hsf.r_in, hsf.r_out)
        cv2.copyMakeBorder(gray_frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT, dst=frame_pad)
        cv2.integral(frame_pad, sum=frame_int, sdepth=cv2.CV_32S)

        # self.timedict["int_img"].append(timeit.default_timer() - int_start_time)

        # Convolve the feature with the integral image
        # conv_int_start_time = timeit.default_timer()
        response, hsf_min_loc = conv_int(frame_int, hsf, inner_sum, in_p00, in_p11, in_p01, in_p10, y_ro_m, x_ro_m, y_ro_p, x_ro_p,
                                             outer_sum, out_p_temp, out_p00, out_p11, out_p01, out_p10, response_list,
                                             frame_conv_stride)
        center_xy = get_hsf_center(pad, step[0], step[1], hsf_min_loc)
        # visualization of HSF
        # cv2.normalize(cv2.filter2D(cv2.filter2D(frame_pad, cv2.CV_64F, hsf.get_kernel()[hsf.get_kernel().shape[0]//2,:].reshape(1,-1), borderType=cv2.BORDER_CONSTANT), cv2.CV_64F, hsf.get_kernel()[:,hsf.get_kernel().shape[1]//2].reshape(-1,1), borderType=cv2.BORDER_CONSTANT),None,0,255,cv2.NORM_MINMAX,dtype=cv2.CV_8U))


        # self.timedict["conv_int"].append(timeit.default_timer() - conv_int_start_time)

        # crop_start_time = timeit.default_timer()
        # Define the center point and radius

        center_x, center_y, upper_x, lower_x, upper_y, lower_y, ransac_lower_x, ransac_lower_y, ransac_upper_x, ransac_upper_y, ransac_xy_offset = get_center_noclamp(
                center_xy, radius)

        if self.now_modeo == self.cv_modeo[0] or self.now_modeo == self.cv_modeo[1]:
            # If mode is first_frame or radius_adjust, record current radius and response
            self.auto_radius_calc.add_response(radius, response)
        elif self.now_modeo == self.cv_modeo[2]:
            # Statistics for blink detection
            if self.blink_detector.response_len() < blink_init_frames:
                self.blink_detector.add_response(cv2.mean(safe_crop(gray_frame, lower_x, lower_y, upper_x, upper_y, 1))[0])
                self.center_q1.add_response(
                    cv2.mean(safe_crop(gray_frame, center_x - max(20, radius), center_y - max(20, radius), center_x + max(20, radius),
                                       center_y + max(20, radius), keepsize=False))[
                        0
                    ]
                )
    
            else:
        
                self.blink_detector.calc_thresh()
                self.center_q1.calc_thresh()
                self.now_modeo = self.cv_modeo[3]
        else:
            if self.blink_detector.enable_detect_flg and self.blink_detector.detect(
                    cv2.mean(safe_crop(gray_frame, lower_x, lower_y, upper_x, upper_y, 1))[0]):
                # If the average value of cropped_image is greater than response_max
                # (i.e., if the cropimage is whitish
                # blink
               # print("BLINK BD")
                blink_bd = True

        # if imshow_enable or save_video:
        #    cv2.circle(frame, (orig_x, orig_y), 6, (0, 0, 255), -1)
        # cv2.circle(ori_frame, (center_x, center_y), 7, (255, 0, 0), -1)

        # If you want to update response_max. it may be more cost-effective to rewrite response_list in the following way
        # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue

        # cv_end_time = timeit.default_timer()
        # self.timedict["crop"].append(timeit.default_timer() - crop_start_time)
        # self.timedict["total_cv"].append(cv_end_time - cv_start_time)

        # if calc_print_enable:
        #      the lower the response the better the likelyhood of there being a pupil. you can adujst the radius and steps accordingly
        #     print('Kernel response:', response)
        #     print('Pixel position:', center_xy)

        #
        # if imshow_enable:
        #     if self.now_modeo != self.cv_modeo[0] and self.now_modeo != self.cv_modeo[1]:
        #         if 0 in cropped_image.shape:
        #              If shape contains 0, it is not detected well.
        #              pass
        #          else:
        #              cv2.imshow("crop", cropped_image)
        #              cv2.imshow("frame", frame)
        #      if cv2.waitKey(1) & 0xFF == ord("q"):
        #          pass

        if self.now_modeo == self.cv_modeo[0]:
            # Moving from first_frame to the next mode
            if skip_autoradius and skip_blink_detect:
                self.now_modeo = self.cv_modeo[3]
            elif skip_autoradius:
                self.now_modeo = self.cv_modeo[2]
            else:
                self.now_modeo = self.cv_modeo[1]

        # For measuring processing time of image processing
        ransac_start_time = timeit.default_timer()

        # frame_gray = cv2.GaussianBlur(frame, (5, 5), 0)
        # cv2.GaussianBlur is slow (uses 10% of the time of all this script)
        # use cv2.blur()
        # or
        # frame_gray =cv2.boxFilter(frame, -1,(5, 5))# https://github.com/bfraboni/FastGaussianBlur
        # cv2.boxFilter(frame_gray, -1,(5, 5),dst=frame_gray)
        # cv2.boxFilter(frame_gray, -1,(5, 5),dst=frame_gray)
        # or
        frame_gray = cv2.sepFilter2D(frame, -1, self.gauss_k, self.gauss_k)


        # Crop the image using the calculated bounds
        # todo:safecrop tune
        frame_gray_crop = safe_crop(frame_gray, ransac_lower_x, ransac_lower_y, ransac_upper_x, ransac_upper_y, 1)
        th_frame, fic_frame = get_ransac_frame(frame_gray_crop.shape)
        frame = frame_gray_crop  # todo: It can cause bugs.

        # this will need to be adjusted everytime hardware is changed (brightness of IR, Camera postion, etc)m
        # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(frame_gray_crop)
        min_val = cv2.minMaxLoc(frame_gray_crop)[0]
        # threshold_value = min_val + thresh_add

        # if not blink_bd and self.blink_detector.enable_detect_flg:
        #     cv2.threshold(frame_gray_crop, ((min_val + self.center_q1.quartile_1) - thresh_add) / 2, 255, cv2.THRESH_BINARY_INV, dst=th_frame)
        #     cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)
        #     # cv2.morphologyEx(fic_frame, cv2.MORPH_CLOSE, self.kernel, dst=fic_frame)
        #     # cv2.erode(fic_frame,self.kernel,dst=fic_frame)
        #     # cv2.bitwise_not(fic_frame, fic_frame)
        # else:
        
        cv2.threshold(frame_gray_crop, min_val + thresh_add, 255, cv2.THRESH_BINARY, dst=th_frame)

        cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)  # or cv2.MORPH_CLOSE
        cv2.morphologyEx(fic_frame, cv2.MORPH_CLOSE, self.kernel, dst=fic_frame)
        cv2.bitwise_not(fic_frame, fic_frame)

        contours = cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
        # or
        # contours = cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0]
        # if not blink_bd and self.blink_detector.enable_detect_flg:
        #     threshold_value = self.center_q1.quartile_1
        #     if threshold_value < min_val + thresh_add:
        #         # In most of these cases, the pupil is at the edge of the eye.
        #         cv2.threshold(frame_gray_crop, (min_val + thresh_add * 4 + threshold_value) / 2, 255, cv2.THRESH_BINARY, dst=th_frame)
        #     else:
        #         threshold_value = self.center_q1.quartile_1
        #         cv2.threshold(frame_gray_crop, threshold_value, 255, cv2.THRESH_BINARY_INV, dst=th_frame)
        #         # cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)
        #         # cv2.morphologyEx(fic_frame, cv2.MORPH_CLOSE, self.kernel, dst=fic_frame)
        #         # cv2.bitwise_not(fic_frame, fic_frame)
        #         # https://stackoverflow.com/questions/23062572/why-multiple-openings-closing-with-a-same-kernel-does-not-have-effect
        #         # try (cv2.absdiff(cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel),cv2.morphologyEx( cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel), cv2.MORPH_CLOSE, self.kernel))>1).sum()
        #     cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)  # or cv2.MORPH_CLOSE
        #     contours = (*contours, *cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0])
        #     # or
        #     # contours = (*contours, *cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0])


        if not contours:
            #     If empty, go to next loop
            y, x = ori_frame.shape
            th_frame = cv2.resize(th_frame, (x, y))
            return int(center_x), int(center_y), th_frame, ori_frame, blink_bd
        cnt_ind = None
        max_area = -1
        for i, cnt in enumerate(contours):
            now_area = cv2.contourArea(cnt)
            if max_area < now_area:
                max_area = now_area
                cnt_ind = i
        hull = cv2.convexHull(contours[cnt_ind], False)
        # if not hull:
        #     If empty, go to next loop
        #     return int(center_x), int(center_y), th_frame, frame, gray_frame
        ransac_data = fit_rotated_ellipse_ransac(hull.reshape(-1, 2).astype(np.float64), self.sfc)
        if ransac_data is None:
            # ransac_data is None==maxcnt.shape[0]<sample_num
            # go to next loop
            # pass
            y, x = ori_frame.shape
            th_frame = cv2.resize(th_frame, (x, y))
            return int(center_x), int(center_y), th_frame, ori_frame, blink_bd

        # crop_start_time = timeit.default_timer()
        cx, cy, w, h, theta = ransac_data

      #  if w >= 2.1 * h:  # new blink detection algo lmao this works pretty good actually
            #print("RAN BLINK")

        csy = gray_frame.shape[0]
        csx = gray_frame.shape[1]

        # cx = clamp((cx - 20) + center_x, 0, csx)
        # cy = clamp((cy - 20) + center_y, 0, csy)
        cx = int(clamp(cx + ransac_xy_offset[0], 0, csx))
        cy = int(clamp(cy + ransac_xy_offset[1], 0, csy))

        # cv_end_time = timeit.default_timer()
        if imshow_enable:#imsave_flg:

            cv2.circle(ori_frame, (int(center_x), int(center_y)), 3, (128, 0, 0), -1)
            #cv2.drawContours(ori_frame, contours, -1, (255, 0, 0), 1)
            cv2.circle(ori_frame, (int(cx), int(cy)), 2, (255, 0, 0), -1)
            # cx1, cy1, w1, h1, theta1 = fit_rotated_ellipse(maxcnt.reshape(-1, 2))
            cv2.ellipse(
                 ori_frame,
                 (cx, cy),
                 (int(w), int(h)),
                 theta * 180.0 / np.pi,
                 0.0,
                 360.0,
                 (50, 250, 200),
                 1,
             )
            # cv2.imshow("crop", cropped_image)
         #    # cv2.imshow("frame", frame)
         #   if imshow_enable:
         #       cv2.imshow("ori_frame", ori_frame)
         #       if cv2.waitKey(1) & 0xFF == ord("q"):
         #           pass

        # cv_end_time = timeit.default_timer()
        # self.timedict["ransac"].append(cv_end_time - ransac_start_time)
        # self.timedict["total_cv"].append(cv_end_time - cv_start_time)

        try:
            y, x = ori_frame.shape
            th_frame = cv2.resize(th_frame, (x, y))
            return int(cx), int(cy), th_frame, ori_frame, blink_bd
        except:
            y, x = ori_frame.shape
            th_frame = cv2.resize(th_frame, (x, y))
            return int(center_x), int(center_y), th_frame, ori_frame, blink_bd




class External_Run_HSRACS(object):
    def __init__(self, skip_autoradius_flg=False, radius=20, threshold=10):
        # temporary code
        global skip_autoradius,default_radius, thresh_add
        skip_autoradius = skip_autoradius_flg
        if skip_autoradius:
            default_radius = radius
        thresh_add = threshold
        print(radius)
        self.algo = HSRAC_cls()

    def run(self, current_image_gray):
        self.algo.current_image_gray = current_image_gray
        #debug code
        # center_x, center_y,cropbox,ori_frame, thresh, frame, gray_frame = self.algo.single_run()
        # return center_x, center_y,cropbox,ori_frame, thresh, frame, gray_frame
        center_x, center_y, thresh, frame, bd_blink = self.algo.single_run()
        return center_x, center_y, thresh, frame, bd_blink



if __name__ == "__main__":
    hsrac = HSRAC_cls()
    hsrac.open_video(video_path)
    while hsrac.read_frame():
        _ = hsrac.single_run()
    
    # hsrac = HSRAC_cls()
    # hsrac.open_video(video_path)
    # hsf = HSF_cls()
    # while hsrac.read_frame():
    #     hsf.current_image_gray = hsrac.current_image_gray.copy()
    #     _ = hsrac.single_run()
    #
    #     _ = hsf.single_run()
    
    # w_video=True
    #
    # er_hsracs=External_Run_HSRACS()
    # er_hsracs.algo.open_video(video_path)
    # er_hsf=External_Run_HSF()
    #
    # if w_video:
    #     filepath = 'test.mp4'
    #     codec = cv2.VideoWriter_fourcc(*"x264")
    #     video = cv2.VideoWriter(filepath, codec, 60.0, (200,150))#(60, 60))  # (150, 200))
    # while er_hsracs.algo.read_frame():
    #     base_gray =  er_hsracs.algo.current_image_gray.copy()
    #     base_img=er_hsracs.algo.current_image.copy()
    #     cv2.imshow("frame",base_gray)
    #     hsf_x, hsf_y, hsf_cropbox,*_ = er_hsf.run(base_gray)
    #
    #     # hsrac_x, hsrac_y, hsrac_cropbox, *_ = er_hsracs.run(base_gray)
    #     if 0:#random.random()<0.1:
    #         hsrac_x, hsrac_y, hsrac_cropbox, *_ = er_hsracs.run(cv2.resize(base_gray,None,fx=0.75,fy=0.75).copy())
    #         hsrac_x=int(hsrac_x*1.25)
    #         hsrac_y=int(hsrac_y*1.25)
    #         hsrac_cropbox=[int(val*1.25) for val in hsrac_cropbox]
    #     else:
    #         hsrac_x, hsrac_y, hsrac_cropbox,ori_frame, *_ = er_hsracs.run(base_gray)
    #
    #
    #
    #     cv2.rectangle(base_img,hsf_cropbox[:2],hsf_cropbox[2:],(0, 0, 255),3)
    #     cv2.rectangle(base_img, hsrac_cropbox[:2], hsrac_cropbox[2:], (255, 0, 0), 1)
    #     cv2.circle(base_img, (hsf_x, hsf_y), 6, (0, 0, 255), -1)
    #     try:
    #         cv2.circle(base_img, (hsrac_x, hsrac_y), 3, (255, 0, 0), -1)
    #     except:
    #         print()
    #     cv2.imshow("hsf_hsrac",base_img)
    #     if cv2.waitKey(1) & 0xFF == ord("q"):
    #         pass
    #     if w_video:
    #         video.write(ori_frame)
    # if w_video:
    #     video.release()
    # # cv2.imwrite("b.png",er_hsracs.algo.result2)
    # er_hsracs.algo.cap.release()
    # cv2.destroyAllWindows()
    