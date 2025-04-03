import sys
import math
import os
import timeit
from functools import lru_cache
from logging import Formatter, INFO, StreamHandler, FileHandler, getLogger
import cv2
import numpy as np
from numpy.linalg import _umath_linalg


if os.environ.get("PYCHARM_HOSTED", None) is None:
    sys.path.append("../")
    from utils.img_utils import safe_crop  # noqa
    from utils.misc_utils import clamp  # noqa
    from utils.time_utils import FPSResult, TimeitResult, format_time  # noqa
else:
    from utils.img_utils import safe_crop
    from utils.misc_utils import clamp
    from utils.time_utils import FPSResult, TimeitResult, format_time

    # from line_profiler_pycharm import profile


this_file_basename = os.path.basename(__file__)
this_file_name = this_file_basename.replace(".py", "")
alg_ver = "230318-1"  # Do not change it.

##############################
# These can be changed
old_mode = False
save_logfile = False  # This setting is disabled when imshow_enable or save_img or save_video is true
imshow_enable = False
save_img = False
save_video = False
loop_num = 1 if imshow_enable or save_img or save_video else 100
input_video_path = "Pro_demo2.mp4"
output_img_path = f"./{this_file_name}_{alg_ver}_new.png" if not old_mode else f"./{this_file_name}_{alg_ver}_old.png"
output_video_path = f"./{this_file_name}_{alg_ver}_new.mp4" if not old_mode else f"./{this_file_name}_{alg_ver}_old.mp4"
logfilename = f"./{this_file_name}_{alg_ver}_new.log" if not old_mode else f"./{this_file_name}_{alg_ver}_old.log"
print_enable = False  # I don't recommend changing to True.

# RANSAC
thresh_add = 10
skip_autoradius = False
skip_blink_detect = False
##############################


##############################
# Do not change these.

imsave_flg = imshow_enable or save_img or save_video

# cache param
lru_maxsize_vvs = 16
lru_maxsize_vs = 64
lru_maxsize_s = 128
# CV param
default_radius = 20
auto_radius_range = (default_radius - 10, default_radius + 10)  # (10,30)
auto_radius_step = 1
blink_init_frames = 60 * 3  # 60fps*3sec,Number of blink statistical frames
# step==(x,y)
default_step = (5, 5)  # bigger the steps,lower the processing time! ofc acc also takes an impact

logger = getLogger(__name__)
logger.setLevel(INFO)
formatter = Formatter("%(message)s")
handler = StreamHandler()
handler.setLevel(INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)
if save_logfile and not imsave_flg:
    handler = FileHandler(logfilename, encoding="utf8", mode="w")
    handler.setLevel(INFO)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
else:
    save_logfile = False

all_point_img = None
video_wr = cv2.VideoWriter(output_video_path, cv2.VideoWriter_fourcc(*"x264"), 60.0, (200, 150)) if save_video else None


##############################


class CvParameters:
    # It may be a little slower because a dict named "self" is read for each function call.
    def __init__(self, radius, step):
        # self.prev_radius=radius
        self._radius = radius
        self.pad = 2 * radius
        # self.prev_step=step
        self._step = step
        self._hsf = HaarSurroundFeature(radius)

    def get_rpsh(self):
        return self._radius, self.pad, self._step, self._hsf
        # Essentially, the following would be preferable, but it would take twice as long to call.
        # return self.radius, self.pad, self.step, self.hsf

    @property
    def radius(self):
        return self._radius

    @radius.setter
    def radius(self, now_radius):
        # self.prev_radius=self._radius
        self._radius = now_radius
        self.pad = 2 * now_radius
        self.hsf = now_radius

    @property
    def step(self):
        return self._step

    @step.setter
    def step(self, now_step):
        # self.prev_step=self.step
        self._step = now_step

    @property
    def hsf(self):
        return self._hsf

    @hsf.setter
    def hsf(self, now_radius):
        self._hsf = HaarSurroundFeature(now_radius)


class HaarSurroundFeature:
    def __init__(self, r_inner, r_outer=None, val=None):
        if r_outer is None:
            r_outer = r_inner * 3
        r_inner2 = r_inner * r_inner
        count_inner = r_inner2
        count_outer = r_outer * r_outer - r_inner2

        if val is None:
            val_inner = 1.0 / r_inner2
            val_outer = -val_inner * count_inner / count_outer

        else:
            val_inner = val[0]
            val_outer = val[1]

        self.val_in = float(val_inner)  # np.array(val_inner, dtype=np.float64)
        self.val_out = float(val_outer)  # np.array(val_outer, dtype=np.float64)
        self.r_in = r_inner
        self.r_out = r_outer

    def get_kernel(self):
        # Defined here, but not yet used?
        # Create a kernel filled with the value of self.val_out
        kernel = np.ones(shape=(2 * self.r_out - 1, 2 * self.r_out - 1), dtype=np.float64) * self.val_out

        # Set the values of the inner area of the kernel using array slicing
        start = self.r_out - self.r_in
        end = self.r_out + self.r_in - 1
        kernel[start:end, start:end] = self.val_in

        return kernel


def to_gray(frame):
    # Faster by quitting checking if the input image is already grayscale
    # Perhaps it would be faster with less overhead to call cv2.cvtColor directly instead of using this function
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


@lru_cache(maxsize=lru_maxsize_vvs)
def get_frameint_empty_array(frame_shape, pad, x_step, y_step, r_in, r_out):
    frame_int_dtype = np.intc

    frame_pad = np.empty((frame_shape[0] + (pad * 2), frame_shape[1] + (pad * 2)), dtype=np.uint8)

    row, col = frame_pad.shape

    frame_int = np.empty((row + 1, col + 1), dtype=frame_int_dtype)

    y_steps_arr = np.arange(pad, row - pad, y_step, dtype=np.int16)
    x_steps_arr = np.arange(pad, col - pad, x_step, dtype=np.int16)
    len_sx, len_sy = len(x_steps_arr), len(y_steps_arr)
    len_syx = (len_sy, len_sx)
    y_end = pad + (y_step * (len_sy - 1))
    x_end = pad + (x_step * (len_sx - 1))

    y_rin_m = slice(pad - r_in, y_end - r_in + 1, y_step)
    y_rin_p = slice(pad + r_in, y_end + r_in + 1, y_step)
    x_rin_m = slice(pad - r_in, x_end - r_in + 1, x_step)
    x_rin_p = slice(pad + r_in, x_end + r_in + 1, x_step)

    in_p00 = frame_int[y_rin_m, x_rin_m]
    in_p11 = frame_int[y_rin_p, x_rin_p]
    in_p01 = frame_int[y_rin_m, x_rin_p]
    in_p10 = frame_int[y_rin_p, x_rin_m]

    y_ro_m = np.maximum(y_steps_arr - r_out, 0)  # [:,np.newaxis]
    x_ro_m = np.maximum(x_steps_arr - r_out, 0)  # [np.newaxis,:]
    y_ro_p = np.minimum(row, y_steps_arr + r_out)  # [:,np.newaxis]
    x_ro_p = np.minimum(col, x_steps_arr + r_out)  # [np.newaxis,:]

    inner_sum = np.empty(len_syx, dtype=frame_int_dtype)
    outer_sum = np.empty(len_syx, dtype=frame_int_dtype)

    out_p_temp = np.empty((len_sy, col + 1), dtype=frame_int_dtype)
    out_p00 = np.empty(len_syx, dtype=frame_int_dtype)
    out_p11 = np.empty(len_syx, dtype=frame_int_dtype)
    out_p01 = np.empty(len_syx, dtype=frame_int_dtype)
    out_p10 = np.empty(len_syx, dtype=frame_int_dtype)
    response_list = np.empty(len_syx, dtype=np.float64)  # or np.int32
    frame_conv = np.zeros(shape=(row - 2 * pad, col - 2 * pad), dtype=np.uint8)  # or np.float64
    frame_conv_stride = frame_conv[::y_step, ::x_step]

    return (
        frame_pad,
        frame_int,
        inner_sum,
        in_p00,
        in_p11,
        in_p01,
        in_p10,
        y_ro_m,
        x_ro_m,
        y_ro_p,
        x_ro_p,
        outer_sum,
        out_p_temp,
        out_p00,
        out_p11,
        out_p01,
        out_p10,
        response_list,
        frame_conv,
        frame_conv_stride,
    )


def conv_int(
    frame_int,
    kernel,
    inner_sum,
    in_p00,
    in_p11,
    in_p01,
    in_p10,
    y_ro_m,
    x_ro_m,
    y_ro_p,
    x_ro_p,
    outer_sum,
    out_p_temp,
    out_p00,
    out_p11,
    out_p01,
    out_p10,
    response_list,
    frame_conv_stride,
):
    # inner_sum[:, :] = in_p00 + in_p11 - in_p01 - in_p10
    cv2.add(in_p00, in_p11, dst=inner_sum)
    cv2.subtract(inner_sum, in_p01, dst=inner_sum)
    cv2.subtract(inner_sum, in_p10, dst=inner_sum)

    # p00 calc
    frame_int.take(y_ro_m, axis=0, mode="clip", out=out_p_temp)
    out_p_temp.take(x_ro_m, axis=1, mode="clip", out=out_p00)
    # p01 calc
    out_p_temp.take(x_ro_p, axis=1, mode="clip", out=out_p01)
    # p11 calc
    frame_int.take(y_ro_p, axis=0, mode="clip", out=out_p_temp)
    out_p_temp.take(x_ro_p, axis=1, mode="clip", out=out_p11)
    # p10 calc
    out_p_temp.take(x_ro_m, axis=1, mode="clip", out=out_p10)

    # outer_sum[:, :] = out_p00 + out_p11 - out_p01 - out_p10 - inner_sum
    cv2.add(out_p00, out_p11, dst=outer_sum)
    cv2.subtract(outer_sum, out_p01, dst=outer_sum)
    cv2.subtract(outer_sum, out_p10, dst=outer_sum)
    cv2.subtract(outer_sum, inner_sum, dst=outer_sum)
    # cv2.transform(np.asarray([p00, p11, -p01, -p10, -inner_sum]).transpose((1, 2, 0)), np.ones((1, 5)),
    #               dst=outer_sum)  # https://answers.opencv.org/question/3120/how-to-sum-a-3-channel-matrix-to-a-one-channel-matrix/

    # np.multiply(kernel.val_in, inner_sum, dtype=np.float64, out=response_list)
    # response_list += kernel.val_out * outer_sum
    cv2.addWeighted(
        inner_sum,
        kernel.val_in,
        outer_sum,  # or p00 + p11 - p01 - p10 - inner_sum
        kernel.val_out,
        0.0,
        dtype=cv2.CV_64F,  # or cv2.CV_32S
        dst=response_list,
    )

    min_response, _, min_loc, _ = cv2.minMaxLoc(response_list)

    frame_conv_stride[:, :] = response_list
    # or
    # frame_conv_stride[:, :] = response_list.astype(np.uint8)

    return min_response, min_loc


@lru_cache(maxsize=lru_maxsize_s)
def get_hsf_center(padding, x_step, y_step, min_loc):  # min_x,min_y):
    return padding + (x_step * min_loc[0]) - padding, padding + (y_step * min_loc[1]) - padding


class AutoRadiusCalc(object):
    def __init__(self):
        self.response_list = []
        self.radius_cand_list = []
        self.adj_comp_flag = False

        self.radius_middle_index = None

        self.left_item = None
        self.right_item = None
        self.left_index = None
        self.right_index = None

    def get_radius(self):
        prev_res_len = len(self.response_list)
        # adjustment of radius
        if prev_res_len == 1:
            # len==1==response_list==[default_radius]
            self.adj_comp_flag = False
            return auto_radius_range[0]
        elif prev_res_len == 2:
            # len==2==response_list==[default_radius, auto_radius_range[0]]
            self.adj_comp_flag = False
            return auto_radius_range[1]
        elif prev_res_len == 3:
            # len==3==response_list==[default_radius,auto_radius_range[0],auto_radius_range[1]]
            if self.response_list[1][1] < self.response_list[2][1]:
                self.left_item = self.response_list[1]
                self.right_item = self.response_list[0]
            else:
                self.left_item = self.response_list[0]
                self.right_item = self.response_list[2]
            self.radius_cand_list = [
                i for i in range(self.left_item[0], self.right_item[0] + auto_radius_step, auto_radius_step)
            ]
            self.left_index = 0
            self.right_index = len(self.radius_cand_list) - 1
            self.radius_middle_index = (self.left_index + self.right_index) // 2
            self.adj_comp_flag = False
            return self.radius_cand_list[self.radius_middle_index]
        else:
            if self.left_index <= self.right_index and self.left_index != self.radius_middle_index:
                if (self.left_item[1] + self.response_list[-1][1]) < (self.right_item[1] + self.response_list[-1][1]):
                    self.right_item = self.response_list[-1]
                    self.right_index = self.radius_middle_index - 1
                    self.radius_middle_index = (self.left_index + self.right_index) // 2
                    self.adj_comp_flag = False
                    return self.radius_cand_list[self.radius_middle_index]
                if (self.left_item[1] + self.response_list[-1][1]) > (self.right_item[1] + self.response_list[-1][1]):
                    self.left_item = self.response_list[-1]
                    self.left_index = self.radius_middle_index + 1
                    self.radius_middle_index = (self.left_index + self.right_index) // 2
                    self.adj_comp_flag = False
                    return self.radius_cand_list[self.radius_middle_index]
            self.adj_comp_flag = True
            return self.radius_cand_list[self.radius_middle_index]

    def get_radius_base(self):
        """
        Use it when the new version doesn't work well.
        :return:
        """

        prev_res_len = len(self.response_list)
        # adjustment of radius
        if prev_res_len == 1:
            # len==1==response_list==[default_radius]
            self.adj_comp_flag = False
            return auto_radius_range[0]
        elif prev_res_len == 2:
            # len==2==response_list==[default_radius, auto_radius_range[0]]
            self.adj_comp_flag = False
            return auto_radius_range[1]
        elif prev_res_len == 3:
            # len==3==response_list==[default_radius,auto_radius_range[0],auto_radius_range[1]]
            sort_res = sorted(self.response_list, key=lambda x: x[1])[0]
            # Extract the radius with the lowest response value
            if sort_res[0] == default_radius:
                # If the default value is best, change now_mode to init after setting radius to the default value.
                self.adj_comp_flag = True
                return default_radius
            elif sort_res[0] == auto_radius_range[0]:
                self.radius_cand_list = [i for i in range(auto_radius_range[0], default_radius, auto_radius_step)][1:]
                self.adj_comp_flag = False
                return self.radius_cand_list.pop()
            else:
                self.radius_cand_list = [i for i in range(default_radius, auto_radius_range[1], auto_radius_step)][1:]
                self.adj_comp_flag = False
                return self.radius_cand_list.pop()
        else:
            # Try the contents of the radius_cand_list in order until the radius_cand_list runs out
            # Better make it a binary search.
            if len(self.radius_cand_list) == 0:
                sort_res = sorted(self.response_list, key=lambda x: x[1])[0]
                self.adj_comp_flag = True
                return sort_res[0]
            else:
                self.adj_comp_flag = False
                return self.radius_cand_list.pop()

    def add_response(self, radius, response):
        self.response_list.append((radius, response))
        return None


class BlinkDetector(object):
    def __init__(self):
        self.response_list = []
        self.response_max = None
        self.enable_detect_flg = False
        self.quartile_1 = None

    def calc_thresh(self):
        # Calculate response_max by computing interquartile range, IQR
        # self.response_listo = np.array(self.response_listo)
        # 25%,75%
        # This value may need to be adjusted depending on the environment.
        # quartile_1, quartile_3 = np.percentile(self.response_listo, [25, 75])
        # iqr = quartile_3 - quartile_1
        # self.response_maxo = quartile_3 + (iqr * 1.5)

        # quartile_1, quartile_3 = np.percentile(self.response_list, [25, 75])
        # or
        quartile_1, quartile_3 = np.percentile(np.array(self.response_list), [25, 75])
        self.quartile_1 = quartile_1
        iqr = quartile_3 - quartile_1
        # response_min = quartile_1 - (iqr * 1.5)

        self.response_max = float(quartile_3 + (iqr * 1.5))
        # or
        # self.response_max = quartile_3 + (iqr * 1.5)

        self.enable_detect_flg = True
        return None

    def detect(self, now_response):
        return now_response > self.response_max

    def add_response(self, response):
        self.response_list.append(response)
        return None

    def response_len(self):
        return len(self.response_list)


@lru_cache(maxsize=lru_maxsize_s)
def get_ransac_empty_array_old(iter_num, sample_num, len_data):
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
    return (
        dm_rng,
        dm_rng_swap,
        dm_rng_swap_trans,
        dm_rng_5x5,
        dm_rng_p5smp,
        dm_rng_p,
        dm_rng_p_npaxis,
        ellipse_y_arr,
        swap_index,
        dm_brod,
        dm_rng_six,
        dm_rng_p_24,
        dm_rng_p_10,
        el_y_arr_2,
        el_y_arr_3,
        datamod,
        datamod_b,
        dm_data,
        dm_p2,
        dm_mul,
        dm_neg,
        rdm_index_init_arr,
        rdm_index,
        rdm_index_smpnum,
        ellipse_data_arr,
        th_abs,
        inv_ext,
    )


# @profile
def fit_rotated_ellipse_ransac_old(data: np.ndarray, sfc: np.random.Generator, iter_num=100, sample_num=10, offset=80):
    # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower

    # The array contents do not change during the loop, so only one call is needed.
    # They say len is faster than shape.
    # Reference url: https://stackoverflow.com/questions/35547853/what-is-faster-python3s-len-or-numpys-shape
    len_data = len(data)

    if len_data < sample_num:
        return None

    (
        dm_rng,
        dm_rng_swap,
        dm_rng_swap_trans,
        dm_rng_5x5,
        dm_rng_p5smp,
        dm_rng_p,
        dm_rng_p_npaxis,
        ellipse_y_arr,
        swap_index,
        dm_brod,
        dm_rng_six,
        dm_rng_p_24,
        dm_rng_p_10,
        el_y_arr_2,
        el_y_arr_3,
        datamod,
        datamod_b,
        dm_data,
        dm_p2,
        dm_mul,
        dm_neg,
        rdm_index_init_arr,
        rdm_index,
        rdm_index_smpnum,
        ellipse_data_arr,
        th_abs,
        inv_ext,
    ) = get_ransac_empty_array_old(iter_num, sample_num, len_data)

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
    _umath_linalg.inv(dm_rng_5x5, signature="d->d", extobj=inv_ext, out=dm_rng_5x5)
    np.matmul(dm_rng_5x5, dm_rng_swap_trans, out=dm_rng_p5smp)

    np.matmul(dm_rng_p5smp, dm_rng_six, out=dm_rng_p_npaxis)

    el_y_arr_2[:, :] = dm_rng_p_24
    el_y_arr_3[:, :] = dm_rng_p_10

    cv2.gemm(ellipse_y_arr, datamod_b, 1.0, dm_brod, 1.0, dst=ellipse_data_arr, flags=cv2.GEMM_2_T)

    np.abs(ellipse_data_arr, out=th_abs)
    cv2.threshold(th_abs, offset, 1.0, cv2.THRESH_BINARY_INV, dst=th_abs)
    ellipse_data_index = cv2.minMaxLoc(cv2.reduce(th_abs, 1, cv2.REDUCE_SUM))[3][1]

    # error_num = ellipse_data_arr[ellipse_data_index].sum()
    error_num = cv2.sumElems(ellipse_data_arr[ellipse_data_index])[0]
    effective_sample_p_arr = dm_rng_p[ellipse_data_index].tolist()

    return fit_rotated_ellipse_old(error_num, effective_sample_p_arr)


# @profile
def fit_rotated_ellipse_old(data, P):
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
    # cu = a * cx * cx + b * cx * cy + c * cy * cy - P[4]
    cu = c * cy * cy + cx * (a * cx + b * cy) - P[4]
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
    return (
        dm_rng,
        dm_rng_swap,
        dm_rng_swap_trans,
        dm_rng_5x5,
        dm_rng_p5smp,
        dm_rng_p,
        dm_rng_p_npaxis,
        ellipse_y_arr,
        swap_index,
        dm_brod,
        dm_rng_six,
        dm_rng_p_24,
        dm_rng_p_10,
        el_y_arr_2,
        el_y_arr_3,
        datamod,
        datamod_b,
        dm_data,
        dm_p2,
        dm_mul,
        dm_neg,
        rdm_index_init_arr,
        rdm_index,
        rdm_index_smpnum,
        ellipse_data_arr,
        th_abs,
        inv_ext,
    )


# @profile
def fit_rotated_ellipse_ransac_new(data: np.ndarray, sfc: np.random.Generator, iter_num=100, sample_num=10, offset=80):
    # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower

    # The array contents do not change during the loop, so only one call is needed.
    # They say len is faster than shape.
    # Reference url: https://stackoverflow.com/questions/35547853/what-is-faster-python3s-len-or-numpys-shape
    len_data = len(data)

    if len_data < sample_num:
        return None

    (
        dm_rng,
        dm_rng_swap,
        dm_rng_swap_trans,
        dm_rng_5x5,
        dm_rng_p5smp,
        dm_rng_p,
        dm_rng_p_npaxis,
        ellipse_y_arr,
        swap_index,
        dm_brod,
        dm_rng_six,
        dm_rng_p_24,
        dm_rng_p_10,
        el_y_arr_2,
        el_y_arr_3,
        datamod,
        datamod_b,
        dm_data,
        dm_p2,
        dm_mul,
        dm_neg,
        rdm_index_init_arr,
        rdm_index,
        rdm_index_smpnum,
        ellipse_data_arr,
        th_abs,
        inv_ext,
    ) = get_ransac_empty_array_new(iter_num, sample_num, len_data)

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
    _umath_linalg.inv(dm_rng_5x5, signature="d->d", extobj=inv_ext, out=dm_rng_5x5)
    np.matmul(dm_rng_5x5, dm_rng_swap_trans, out=dm_rng_p5smp)

    np.matmul(dm_rng_p5smp, dm_rng_six, out=dm_rng_p_npaxis)

    el_y_arr_2[:, :] = dm_rng_p_24
    el_y_arr_3[:, :] = dm_rng_p_10

    cv2.gemm(ellipse_y_arr, datamod_b, 1.0, dm_brod, 1.0, dst=ellipse_data_arr, flags=cv2.GEMM_2_T)

    np.abs(ellipse_data_arr, out=th_abs)
    cv2.threshold(th_abs, offset, 1.0, cv2.THRESH_BINARY_INV, dst=th_abs)
    ellipse_data_index = cv2.minMaxLoc(cv2.reduce(th_abs, 1, cv2.REDUCE_SUM))[3][1]

    # error_num = ellipse_data_arr[ellipse_data_index].sum()
    error_num = cv2.sumElems(ellipse_data_arr[ellipse_data_index])[0]
    effective_sample_p_arr = dm_rng_p[ellipse_data_index].tolist()

    return fit_rotated_ellipse_new(error_num, effective_sample_p_arr)


# @profile
def fit_rotated_ellipse_new(data, P):
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


class HSRAC_cls(object):
    def __init__(self):
        # I'd like to take into account things like print, end_time - start_time processing time, etc., but it's too much trouble.

        # For measuring total processing time

        self.main_start_time = timeit.default_timer()

        # self.rng = np.random.default_rng()
        # if old_mode:
        #     self.cvparam = CvParameters_old(default_radius, default_step)
        # else:
        #     # os.environ["OPENBLAS_NUM_THREADS"]="1" # https://github.com/numpy/numpy/issues/22928
        #     self.cvparam = CvParameters_new(default_radius, default_step)
        self.cvparam = CvParameters(default_radius, default_step)

        self.cv_modeo = ["first_frame", "radius_adjust", "blink_adjust", "normal"]
        self.now_modeo = self.cv_modeo[0]

        self.auto_radius_calc = AutoRadiusCalc()
        self.blink_detector = BlinkDetector()
        self.center_q1 = BlinkDetector()

        self.cap = None

        self.timedict = {"to_gray": [], "int_img": [], "hsf": [], "crop": [], "ransac": [], "total_cv": []}

        # ransac
        # self.rng = np.random.default_rng()
        self.sfc = np.random.default_rng(np.random.SFC64())

        # self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        # or
        # https://stackoverflow.com/questions/31025368/erode-is-too-slow-opencv
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        if old_mode:
            self.gauss_k = cv2.getGaussianKernel(5, 2)
        else:
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
            if imsave_flg:
                self.current_image = frame  # debug code
            self.current_image_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return True
        return False

    # @profile
    def single_run(self):
        # Temporary implementation to run
        if imsave_flg:
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
        cv_start_time = timeit.default_timer()
        frame = self.current_image_gray
        gray_frame = frame
        self.timedict["to_gray"].append(timeit.default_timer() - cv_start_time)

        # Calculate the integral image of the frame
        int_start_time = timeit.default_timer()
        (
            frame_pad,
            frame_int,
            inner_sum,
            in_p00,
            in_p11,
            in_p01,
            in_p10,
            y_ro_m,
            x_ro_m,
            y_ro_p,
            x_ro_p,
            outer_sum,
            out_p_temp,
            out_p00,
            out_p11,
            out_p01,
            out_p10,
            response_list,
            frame_conv,
            frame_conv_stride,
        ) = get_frameint_empty_array(gray_frame.shape, pad, step[0], step[1], hsf.r_in, hsf.r_out)
        cv2.copyMakeBorder(gray_frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT, dst=frame_pad)
        cv2.integral(frame_pad, sum=frame_int, sdepth=cv2.CV_32S)

        self.timedict["int_img"].append(timeit.default_timer() - int_start_time)

        # Convolve the feature with the integral image
        conv_int_start_time = timeit.default_timer()
        # if old_mode:
        #     response, hsf_min_loc = conv_int_old(frame_int, hsf, inner_sum, in_p00, in_p11, in_p01, in_p10, y_ro_m, x_ro_m, y_ro_p, x_ro_p,
        #                                          outer_sum, out_p_temp, out_p00, out_p11, out_p01, out_p10, response_list,
        #                                          frame_conv_stride)
        # else:
        #     response, hsf_min_loc = conv_int_new(frame_int, hsf, inner_sum, in_p00, in_p11, in_p01, in_p10, y_ro_m, x_ro_m, y_ro_p, x_ro_p,
        #                                          outer_sum, out_p_temp, out_p00, out_p11, out_p01, out_p10, response_list,
        #                                          frame_conv_stride)
        response, hsf_min_loc = conv_int(
            frame_int,
            hsf,
            inner_sum,
            in_p00,
            in_p11,
            in_p01,
            in_p10,
            y_ro_m,
            x_ro_m,
            y_ro_p,
            x_ro_p,
            outer_sum,
            out_p_temp,
            out_p00,
            out_p11,
            out_p01,
            out_p10,
            response_list,
            frame_conv_stride,
        )
        center_xy = get_hsf_center(pad, step[0], step[1], hsf_min_loc)
        # visualization of HSF
        # cv2.normalize(cv2.filter2D(cv2.filter2D(frame_pad, cv2.CV_64F, hsf.get_kernel()[hsf.get_kernel().shape[0]//2,:].reshape(1,-1), borderType=cv2.BORDER_CONSTANT), cv2.CV_64F, hsf.get_kernel()[:,hsf.get_kernel().shape[1]//2].reshape(-1,1), borderType=cv2.BORDER_CONSTANT),None,0,255,cv2.NORM_MINMAX,dtype=cv2.CV_8U))

        self.timedict["hsf"].append(timeit.default_timer() - conv_int_start_time)

        crop_start_time = timeit.default_timer()
        # Define the center point and radius

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
        ) = get_center_noclamp(center_xy, radius)

        if self.now_modeo == self.cv_modeo[0] or self.now_modeo == self.cv_modeo[1]:
            # If mode is first_frame or radius_adjust, record current radius and response
            self.auto_radius_calc.add_response(radius, response)
        elif self.now_modeo == self.cv_modeo[2]:
            # Statistics for blink detection
            if self.blink_detector.response_len() < blink_init_frames:
                self.blink_detector.add_response(
                    cv2.mean(safe_crop(gray_frame, lower_x, lower_y, upper_x, upper_y, 1))[0]
                )
                self.center_q1.add_response(
                    cv2.mean(
                        safe_crop(
                            gray_frame,
                            center_x - max(20, radius),
                            center_y - max(20, radius),
                            center_x + max(20, radius),
                            center_y + max(20, radius),
                            keepsize=False,
                        )
                    )[0]
                )

            else:

                self.blink_detector.calc_thresh()
                self.center_q1.calc_thresh()
                self.now_modeo = self.cv_modeo[3]
        else:
            if self.blink_detector.enable_detect_flg and self.blink_detector.detect(
                cv2.mean(safe_crop(gray_frame, lower_x, lower_y, upper_x, upper_y, 1))[0]
            ):
                # If the average value of cropped_image is greater than response_max
                # (i.e., if the cropimage is whitish blink
                blink_bd = True

        # if imshow_enable or save_video:
        #    cv2.circle(frame, (orig_x, orig_y), 6, (0, 0, 255), -1)
        # cv2.circle(ori_frame, (center_x, center_y), 7, (255, 0, 0), -1)

        # If you want to update response_max. it may be more cost-effective to rewrite response_list in the following way
        # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue

        # cv_end_time = timeit.default_timer()
        self.timedict["crop"].append(timeit.default_timer() - crop_start_time)
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
        if old_mode:
            frame_gray = cv2.sepFilter2D(frame, -1, self.gauss_k, self.gauss_k)
        else:
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

        if old_mode:
            cv2.threshold(frame_gray_crop, min_val + thresh_add, 255, cv2.THRESH_BINARY_INV, dst=th_frame)
            # print(thresh.shape, frame_gray.shape)

            # cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)
            # cv2.morphologyEx(fic_frame, cv2.MORPH_CLOSE, self.kernel, dst=fic_frame)
            # cv2.bitwise_not(fic_frame, fic_frame)
            # https://stackoverflow.com/questions/23062572/why-multiple-openings-closing-with-a-same-kernel-does-not-have-effect
            # try (cv2.absdiff(cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel),cv2.morphologyEx( cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel), cv2.MORPH_CLOSE, self.kernel))>1).sum()
            cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)  # or cv2.MORPH_CLOSE
        else:
            if not blink_bd and self.blink_detector.enable_detect_flg:
                cv2.threshold(
                    frame_gray_crop,
                    (min_val + thresh_add + self.center_q1.quartile_1) / 2,
                    255,
                    cv2.THRESH_BINARY_INV,
                    dst=th_frame,
                )
                cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)
                # cv2.morphologyEx(fic_frame, cv2.MORPH_CLOSE, self.kernel, dst=fic_frame)
                # cv2.erode(fic_frame,self.kernel,dst=fic_frame)
                # cv2.bitwise_not(fic_frame, fic_frame)
            # cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)  # or cv2.MORPH_CLOSE
            else:
                cv2.threshold(frame_gray_crop, min_val + thresh_add, 255, cv2.THRESH_BINARY, dst=th_frame)
                # print(thresh.shape, frame_gray.shape)
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
            return int(center_x), int(center_y), th_frame, frame, gray_frame
        cnt_ind = None
        max_area = -1
        for i, cnt in enumerate(contours):
            now_area = cv2.contourArea(cnt)
            if max_area < now_area:
                max_area = now_area
                cnt_ind = i
        hull = cv2.convexHull(contours[cnt_ind], False)
        if old_mode:
            ransac_data = fit_rotated_ellipse_ransac_old(hull.reshape(-1, 2).astype(np.float64), self.sfc)
        else:
            ransac_data = fit_rotated_ellipse_ransac_new(hull.reshape(-1, 2).astype(np.float64), self.sfc)
        if ransac_data is None:
            # ransac_data is None==maxcnt.shape[0]<sample_num
            # go to next loop
            # pass
            return int(center_x), int(center_y), th_frame, frame, gray_frame

        # crop_start_time = timeit.default_timer()
        cx, cy, w, h, theta = ransac_data
        #  print(cx, cy)
        #     if w >= 2.1 * h:  # new blink detection algo lmao this works pretty good actually
        #         pass
        # return center_x, center_y, frame, frame, True

        # cx = center_x - (csx - cx) # we find the difference between the crop size and ransac point, and subtract from the center point from HSF
        # cy = center_y - (csy - cy)

        # csy = frame.shape[0]
        # csx = frame.shape[1]
        csy = gray_frame.shape[0]
        csx = gray_frame.shape[1]

        # cx = clamp((cx - 20) + center_x, 0, csx)
        # cy = clamp((cy - 20) + center_y, 0, csy)
        cx = int(clamp(cx + ransac_xy_offset[0], 0, csx))
        cy = int(clamp(cy + ransac_xy_offset[1], 0, csy))

        # cv_end_time = timeit.default_timer()
        if imsave_flg:

            cv2.circle(ori_frame, (int(center_x), int(center_y)), 3, (128, 0, 0), -1)
            cv2.drawContours(ori_frame, contours, -1, (255, 0, 0), 1)
            cv2.circle(ori_frame, (int(cx), int(cy)), 2, (255, 0, 0), -1)
            # cx1, cy1, w1, h1, theta1 = fit_rotated_ellipse(maxcnt.reshape(-1, 2))
            # cv2.ellipse(
            #     ori_frame,
            #     (cx, cy),
            #     (int(w), int(h)),
            #     theta * 180.0 / np.pi,
            #     0.0,
            #     360.0,
            #     (50, 250, 200),
            #     1,
            # )
            # cv2.imshow("crop", cropped_image)
            # cv2.imshow("frame", frame)
            if imshow_enable:
                cv2.imshow("ori_frame", ori_frame)
                cv2.imshow("fic", fic_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    pass

        cv_end_time = timeit.default_timer()
        self.timedict["ransac"].append(cv_end_time - ransac_start_time)
        self.timedict["total_cv"].append(cv_end_time - cv_start_time)

        try:
            return int(cx), int(cy), th_frame, frame, gray_frame
        except:
            return int(center_x), int(center_y), th_frame, frame, gray_frame


if __name__ == "__main__":
    # print(np.show_config())
    logger.info(this_file_basename)
    if save_logfile:
        logger.info("log path: {}".format(logfilename))
    logger.info("alg ver: {}".format(alg_ver))
    logger.info("alg mode: {}".format("old" if old_mode else "new"))
    logger.info("loops: {}".format(loop_num))
    if not os.path.exists(input_video_path) or not os.path.isfile(input_video_path):
        raise FileNotFoundError(input_video_path)
    logger.info("video name: {}".format(os.path.basename(input_video_path)))
    cap = cv2.VideoCapture(input_video_path)
    logger.info(
        "video info: size:{}x{} fps:{} frames:{} total:{:.3f} sec".format(
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            cap.get(cv2.CAP_PROP_FPS),
            int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS),
        )
    )
    if save_img:
        all_point_img = np.zeros(
            (int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), 3), dtype=np.uint8
        )
    cap.release()

    if not print_enable:

        def print(*args, **kwargs):
            pass

    hsrac = HSRAC_cls()
    # For measuring total processing time
    main_start_time = timeit.default_timer()

    for i in range(loop_num):
        hsrac.open_video(input_video_path)

        while hsrac.read_frame():
            if imsave_flg:
                base_gray = hsrac.current_image_gray.copy()
                base_img = hsrac.current_image.copy()

                hsf_x, hsf_y, hsf_cropbox, *_ = hsrac.single_run()

                # # hsrac_x, hsrac_y, hsrac_cropbox, *_ = er_hsracs.run(base_gray)
                # if 0:#random.random()<0.1:
                #     hsrac_x, hsrac_y, hsrac_cropbox, *_ = er_hsracs.run(cv2.resize(base_gray,None,fx=0.75,fy=0.75).copy())
                #     hsrac_x=int(hsrac_x*1.25)
                #     hsrac_y=int(hsrac_y*1.25)
                #     hsrac_cropbox=[int(val*1.25) for val in hsrac_cropbox]
                # else:
                #     hsrac_x, hsrac_y, hsrac_cropbox,ori_frame, *_ = er_hsracs.run(base_gray)
                # cv2.rectangle(base_img, hsf_cropbox[:2], hsf_cropbox[2:], (0, 0, 255), 3)
                # cv2.rectangle(base_img, hsrac_cropbox[:2], hsrac_cropbox[2:], (255, 0, 0), 1)
                cv2.circle(base_img, (hsf_x, hsf_y), 3, (0, 0, 255), -1)
                if save_img:
                    cv2.circle(all_point_img, (hsf_x, hsf_y), 2, (0, 0, 255), -1)
                # try:
                #     cv2.circle(base_img, (hsrac_x, hsrac_y), 3, (255, 0, 0), -1)
                # except:
                #     print()
                if imshow_enable:
                    cv2.imshow("frame", base_gray)
                    cv2.imshow("hsf_hsrac", base_img)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        pass
              #  if save_video:
                #    video_wr.write(cv2.resize(base_img, (200, 150)))
            else:
                _ = hsrac.single_run()

        if save_video:
            video_wr.release()
            logger.info("video output: {}".format(output_video_path))
        hsrac.cap.release()
        cv2.destroyAllWindows()
    main_end_time = timeit.default_timer()
    main_total_time = main_end_time - main_start_time
    if save_img:
     #   cv2.imwrite(output_img_path, all_point_img)
        logger.info("image output: {}".format(output_img_path))
        if imshow_enable:
            cv2.imshow("allpoint", all_point_img)
            if cv2.waitKey(10000):  # wait 10sec
                cv2.destroyAllWindows()
    if not print_enable:
        # del print
        # or
        print = __builtins__.print
    logger.info("")
    for k, v in hsrac.timedict.items():
        # number=1, precision=5
        len_v = len(v)
        best = min(v)  # / number
        worst = max(v)  # / number
        logger.info(k + ":")
        logger.info(TimeitResult(loop_num, len_v, best, worst, v, 5))
        logger.info(FPSResult(loop_num, len_v, worst, best, v, 5))
        # print("")
    logger.info("")
    logger.info(f"{this_file_basename}: ALL Finish {format_time(main_total_time)}")

