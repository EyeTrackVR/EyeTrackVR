import functools
import math
import sys
import timeit
from functools import lru_cache

import cv2
import numpy as np

# from line_profiler_pycharm import profile

video_path = "ezgif.com-gif-maker.avi"
imshow_enable = True
calc_print_enable = True
save_video = False
skip_autoradius = False
skip_blink_detect = False

# cache param
lru_maxsize_vvs = 16
lru_maxsize_vs = 64
# CV param
default_radius = 20
auto_radius_range = (default_radius - 10, default_radius + 10)  # (10,30)
auto_radius_step = 1
blink_init_frames = 60 * 3  # 60fps*3sec,Number of blink statistical frames
# step==(x,y)
default_step = (5, 5)  # bigger the steps,lower the processing time! ofc acc also takes an impact

"""
Attention.
If using cv2.filter2D in this code, be careful with the kernel
https://stackoverflow.com/questions/39457468/convolution-without-any-padding-opencv-python
"""


def TimeitWrapper(*args, **kwargs):
    """
    This decorator @TimeitWrapper() prints the function name and execution time in seconds.
    :param args:
    :param kwargs:
    :return:
    """
    
    def decorator(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            start = timeit.default_timer()
            results = function(*args, **kwargs)
            end = timeit.default_timer()
            print('{} execution time: {:.10f} s'.format(function.__name__, end - start))
            return results
        
        return wrapper
    
    return decorator


class TimeitResult(object):
    """
    from https://github.com/ipython/ipython/blob/339c0d510a1f3cb2158dd8c6e7f4ac89aa4c89d8/IPython/core/magics/execution.py#L55

    Object returned by the timeit magic with info about the run.
    Contains the following attributes :
    loops: (int) number of loops done per measurement
    repeat: (int) number of times the measurement has been repeated
    best: (float) best execution time / number
    all_runs: (list of float) execution time of each run (in s)
    """
    
    def __init__(self, loops, repeat, best, worst, all_runs, precision):
        self.loops = loops
        self.repeat = repeat
        self.best = best
        self.worst = worst
        self.all_runs = all_runs
        self._precision = precision
        self.timings = [dt / self.loops for dt in all_runs]
    
    @property
    def average(self):
        return math.fsum(self.timings) / len(self.timings)
    
    @property
    def stdev(self):
        mean = self.average
        return (math.fsum([(x - mean) ** 2 for x in self.timings]) / len(self.timings)) ** 0.5
    
    def __str__(self):
        pm = '+-'
        if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding:
            try:
                u'\xb1'.encode(sys.stdout.encoding)
                pm = u'\xb1'
            except:
                pass
        return "min:{best} max:{worst} mean:{mean} {pm} {std} per loop (mean {pm} std. dev. of {runs} run{run_plural}, {loops:,} loop{loop_plural} each)".format(
            pm=pm,
            runs=self.repeat,
            loops=self.loops,
            loop_plural="" if self.loops == 1 else "s",
            run_plural="" if self.repeat == 1 else "s",
            mean=format_time(self.average, self._precision),
            std=format_time(self.stdev, self._precision),
            best=format_time(self.best, self._precision),
            worst=format_time(self.worst, self._precision),
        )
    
    def _repr_pretty_(self, p, cycle):
        unic = self.__str__()
        p.text(u'<TimeitResult : ' + unic + u'>')


class FPSResult(object):
    """
    base https://github.com/ipython/ipython/blob/339c0d510a1f3cb2158dd8c6e7f4ac89aa4c89d8/IPython/core/magics/execution.py#L55
    """
    
    def __init__(self, loops, repeat, best, worst, all_runs, precision):
        self.loops = loops
        self.repeat = repeat
        self.best = 1 / best
        self.worst = 1 / worst
        self.all_runs = all_runs
        self._precision = precision
        self.fps = [1 / dt for dt in all_runs]
        self.unit = "fps"
    
    @property
    def average(self):
        return math.fsum(self.fps) / len(self.fps)
    
    @property
    def stdev(self):
        mean = self.average
        return (math.fsum([(x - mean) ** 2 for x in self.fps]) / len(self.fps)) ** 0.5
    
    def __str__(self):
        pm = '+-'
        if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding:
            try:
                u'\xb1'.encode(sys.stdout.encoding)
                pm = u'\xb1'
            except:
                pass
        return "min:{best} max:{worst} mean:{mean} {pm} {std} per loop (mean {pm} std. dev. of {runs} run{run_plural}, {loops:,} loop{loop_plural} each)".format(
            pm=pm,
            runs=self.repeat,
            loops=self.loops,
            loop_plural="" if self.loops == 1 else "s",
            run_plural="" if self.repeat == 1 else "s",
            mean="%.*g%s" % (self._precision, self.average, self.unit),
            std="%.*g%s" % (self._precision, self.stdev, self.unit),
            best="%.*g%s" % (self._precision, self.best, self.unit),
            worst="%.*g%s" % (self._precision, self.worst, self.unit),
        )
    
    def _repr_pretty_(self, p, cycle):
        unic = self.__str__()
        p.text(u'<FPSResult : ' + unic + u'>')


def format_time(timespan, precision=3):
    """
    https://github.com/ipython/ipython/blob/339c0d510a1f3cb2158dd8c6e7f4ac89aa4c89d8/IPython/core/magics/execution.py#L1473
    Formats the timespan in a human readable form
    """
    
    if timespan >= 60.0:
        # we have more than a minute, format that in a human readable form
        # Idea from http://snipplr.com/view/5713/
        parts = [("d", 60 * 60 * 24), ("h", 60 * 60), ("min", 60), ("s", 1)]
        time = []
        leftover = timespan
        for suffix, length in parts:
            value = int(leftover / length)
            if value > 0:
                leftover = leftover % length
                time.append(u'%s%s' % (str(value), suffix))
            if leftover < 1:
                break
        return " ".join(time)
    
    # Unfortunately the unicode 'micro' symbol can cause problems in
    # certain terminals.
    # See bug: https://bugs.launchpad.net/ipython/+bug/348466
    # Try to prevent crashes by being more secure than it needs to
    # E.g. eclipse is able to print a µ, but has no sys.stdout.encoding set.
    units = [u"s", u"ms", u'us', "ns"]  # the save value
    if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding:
        try:
            u'\xb5'.encode(sys.stdout.encoding)
            units = [u"s", u"ms", u'\xb5s', "ns"]
        except:
            pass
    scaling = [1, 1e3, 1e6, 1e9]
    
    if timespan > 0.0:
        order = min(-int(math.floor(math.log10(timespan)) // 3), 3)
    else:
        order = 3
    return u"%.*g %s" % (precision, timespan * scaling[order], units[order])


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
        # print(r_outer)
        r_inner2 = r_inner * r_inner
        count_inner = r_inner2
        count_outer = r_outer * r_outer - r_inner2
        
        if val is None:
            val_inner = 1.0 / r_inner2
            val_outer = -val_inner * count_inner / count_outer
        
        else:
            val_inner = val[0]
            val_outer = val[1]
        
        self.val_in = np.array(val_inner, dtype=np.float64)
        self.val_out = np.array(val_outer, dtype=np.float64)
        self.r_in = r_inner
        self.r_out = r_outer
    
    def get_kernel(self):
        # Defined here, but not yet used?
        # Create a kernel filled with the value of self.val_out
        kernel = np.ones(shape=(2 * self.r_out - 1, 2 * self.r_out - 1), dtype=np.float64) * self.val_out
        
        # Set the values of the inner area of the kernel using array slicing
        start = (self.r_out - self.r_in)
        end = (self.r_out + self.r_in - 1)
        kernel[start:end, start:end] = self.val_in
        
        return kernel


def to_gray(frame):
    # Faster by quitting checking if the input image is already grayscale
    # Perhaps it would be faster with less overhead to call cv2.cvtColor directly instead of using this function
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


@lru_cache(maxsize=lru_maxsize_vs)
def frameint_get_xy_step(imageshape, xysteps, pad, start_offset=None, end_offset=None):
    """
    :param imageshape: (height(row),width(col)). row==y,cal==x
    :param xysteps: (x,y)
    :param pad: int
    :param start_offset: (x,y) or None
    :param end_offset: (x,y) or None
    :return: xy_np:tuple(x,y)
    """
    row, col = imageshape
    row -= 1
    col -= 1
    x_step, y_step = xysteps
    
    # This is not beautiful.
    start_pad_x = start_pad_y = end_pad_x = end_pad_y = pad
    
    if start_offset is not None:
        start_pad_x += start_offset[0]
        start_pad_y += start_offset[1]
    if end_offset is not None:
        end_pad_x += end_offset[0]
        end_pad_y += end_offset[1]
    y_np = np.arange(start_pad_y, row - end_pad_y, y_step)
    x_np = np.arange(start_pad_x, col - end_pad_x, x_step)
    
    xy_np = (x_np, y_np)
    
    return xy_np


@lru_cache(maxsize=lru_maxsize_vvs)
def get_hsf_empty_array(len_syx, frameint_x, frame_int_dtype, fcshape):
    # Function to reduce array allocation by providing an empty array first and recycling it with lru
    inner_sum = np.empty(len_syx, dtype=frame_int_dtype)
    outer_sum = np.empty(len_syx, dtype=frame_int_dtype)
    p_temp = np.empty((len_syx[0], frameint_x), dtype=frame_int_dtype)
    p00 = np.empty(len_syx, dtype=frame_int_dtype)
    p11 = np.empty(len_syx, dtype=frame_int_dtype)
    p01 = np.empty(len_syx, dtype=frame_int_dtype)
    p10 = np.empty(len_syx, dtype=frame_int_dtype)
    response_list = np.empty(len_syx, dtype=np.float64)
    frame_conv = np.zeros(shape=fcshape[0], dtype=np.uint8)
    frame_conv_stride = frame_conv[::fcshape[1], ::fcshape[2]]
    return (inner_sum, outer_sum), p_temp, (p00, p11, p01, p10), response_list, (frame_conv, frame_conv_stride)


# @profile
def conv_int(frame_int, kernel, xy_step, padding, xy_steps_list):
    """
    :param frame_int:
    :param kernel: hsf
    :param step: (x,y)
    :param padding: int
    :return:
    """
    row, col = frame_int.shape
    row -= 1
    col -= 1
    x_step, y_step = xy_step
    # padding2 = 2 * padding
    f_shape = row - 2 * padding, col - 2 * padding
    r_in = kernel.r_in
    
    len_sx, len_sy = len(xy_steps_list[0]), len(xy_steps_list[1])
    inout_sum, p_temp, p_list, response_list, frameconvlist = get_hsf_empty_array((len_sy, len_sx), col + 1,
                                                                                  frame_int.dtype, (f_shape, y_step, x_step))
    inner_sum, outer_sum = inout_sum
    p00, p11, p01, p10 = p_list
    frame_conv, frame_conv_stride = frameconvlist
    
    y_rin_m = xy_steps_list[1] - r_in
    x_rin_m = xy_steps_list[0] - r_in
    y_rin_p = xy_steps_list[1] + r_in
    x_rin_p = xy_steps_list[0] + r_in
    # xx==(y,x),m==MINUS,p==PLUS, ex: mm==(y-,x-)
    inarr_mm = frame_int[y_rin_m[0]:y_rin_m[-1] + 1:y_step, x_rin_m[0]:x_rin_m[-1] + 1:x_step]
    inarr_mp = frame_int[y_rin_m[0]:y_rin_m[-1] + 1:y_step, x_rin_p[0]:x_rin_p[-1] + 1:x_step]
    inarr_pm = frame_int[y_rin_p[0]:y_rin_p[-1] + 1:y_step, x_rin_m[0]:x_rin_m[-1] + 1:x_step]
    inarr_pp = frame_int[y_rin_p[0]:y_rin_p[-1] + 1:y_step, x_rin_p[0]:x_rin_p[-1] + 1:x_step]
    
    # == inarr_mm + inarr_pp - inarr_mp - inarr_pm
    inner_sum[:, :] = inarr_mm
    inner_sum += inarr_pp
    inner_sum -= inarr_mp
    inner_sum -= inarr_pm
    
    # Bottleneck here, I want to make it smarter. Someone do it.
    # (y,x)
    # p00=max(y_ro_m,0),max(x_ro_m,0)
    # p11=min(y_ro_p,ylim),min(x_ro_p,xlim)
    # p01=max(y_ro_m,0),min(x_ro_p,xlim)
    # p10=min(y_ro_p,ylim),max(x_ro_m,0)
    y_ro_m = xy_steps_list[1] - kernel.r_out
    x_ro_m = xy_steps_list[0] - kernel.r_out
    y_ro_p = xy_steps_list[1] + kernel.r_out
    x_ro_p = xy_steps_list[0] + kernel.r_out
    # p00 calc
    np.take(frame_int, y_ro_m, axis=0, mode="clip", out=p_temp)
    np.take(p_temp, x_ro_m, axis=1, mode="clip", out=p00)
    # p01 calc
    np.take(p_temp, x_ro_p, axis=1, mode="clip", out=p01)
    # p11 calc
    np.take(frame_int, y_ro_p, axis=0, mode="clip", out=p_temp)
    np.take(p_temp, x_ro_p, axis=1, mode="clip", out=p11)
    # p10 calc
    np.take(p_temp, x_ro_m, axis=1, mode="clip", out=p10)
    # the point is this
    # p00=np.take(np.take(frame_int, y_ro_m, axis=0, mode="clip"), x_ro_m, axis=1, mode="clip")
    # p11=np.take(np.take(frame_int, y_ro_p, axis=0, mode="clip"), x_ro_p, axis=1, mode="clip")
    # p01=np.take(np.take(frame_int, y_ro_m, axis=0, mode="clip"), x_ro_p, axis=1, mode="clip")
    # p10=np.take(np.take(frame_int, y_ro_p, axis=0, mode="clip"), x_ro_m, axis=1, mode="clip")
    
    outer_sum[:, :] = p00 + p11 - p01 - p10 - inner_sum
    
    np.multiply(kernel.val_in, inner_sum, dtype=np.float64, out=response_list)
    response_list += kernel.val_out * outer_sum
    
    # min_response, max_val, min_loc, max_loc = cv2.minMaxLoc(response_list)
    min_response, _, min_loc, _ = cv2.minMaxLoc(response_list)
    
    center = ((xy_steps_list[0][min_loc[0]] - padding), (xy_steps_list[1][min_loc[1]] - padding))
    
    frame_conv_stride[:, :] = response_list
    # or
    # frame_conv_stride[:, :] = response_list.astype(np.uint8)
    
    return frame_conv, min_response, center


class Auto_Radius_Calc(object):
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
            self.radius_cand_list = [i for i in range(self.left_item[0], self.right_item[0] + auto_radius_step, auto_radius_step)]
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


class Blink_Detector(object):
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


class CenterCorrection(object):
    def __init__(self):
        # Tunable parameters
        kernel_size = 7  # 3 or 5 or 7
        self.hist_thr = float(4)  # 4%
        self.center_q1_radius = 20
        
        self.setup_comp = False
        self.quartile_1 = None
        self.radius = None
        self.frame_shape = None
        self.frame_mask = None
        self.frame_bin = None
        self.frame_final = None
        self.morph_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        self.morph_kernel2 = np.ones((3, 3))
        self.hist_index = np.arange(256)
        self.hist = np.empty((256, 1))
        self.hist_norm = np.empty((256, 1))
    
    def init_array(self, gray_shape, quartile_1, radius):
        self.frame_shape = gray_shape
        self.frame_mask = np.empty(gray_shape, dtype=np.uint8)
        self.frame_bin = np.empty(gray_shape, dtype=np.uint8)
        self.frame_final = np.empty(gray_shape, dtype=np.uint8)
        self.quartile_1 = quartile_1
        self.radius = radius
        self.setup_comp = True
    
    # def reset_array(self):
    #     self.frame_mask.fill(0)
    
    def correction(self, gray_frame, orig_x, orig_y):
        center_x, center_y = orig_x, orig_y
        self.frame_mask.fill(0)
        
        cv2.circle(self.frame_mask, center=(center_x, center_y), radius=int(self.radius * 2), color=255, thickness=-1)
        
        # bottleneck
        cv2.calcHist([gray_frame], [0], None, [256], [0, 256], hist=self.hist)
        
        cv2.normalize(self.hist, self.hist_norm, alpha=100.0, norm_type=cv2.NORM_L1)
        hist_per = self.hist_norm.cumsum()
        hist_index_list = self.hist_index[hist_per >= self.hist_thr]
        frame_thr = hist_index_list[0] if len(hist_index_list) else np.percentile(cv2.bitwise_or(255 - self.frame_mask, gray_frame), 4)
        
        # bottleneck
        self.frame_bin = cv2.threshold(gray_frame, frame_thr, 1, cv2.THRESH_BINARY_INV)[1]
        cropped_x, cropped_y, cropped_w, cropped_h = cv2.boundingRect(self.frame_bin)
        
        self.frame_final = cv2.bitwise_and(self.frame_bin, self.frame_mask)
        
        # bottleneck
        self.frame_final = cv2.morphologyEx(self.frame_final, cv2.MORPH_CLOSE, self.morph_kernel)
        self.frame_final = cv2.morphologyEx(self.frame_final, cv2.MORPH_OPEN, self.morph_kernel)
        
        if (cropped_h, cropped_w) == self.frame_shape:
            # Not detected.
            base_x, base_y = center_x, center_y
        else:
            base_x = cropped_x + cropped_w // 2
            base_y = cropped_y + cropped_h // 2
            if self.frame_final[base_y, base_x] != 1:
                if self.frame_final[center_y, center_x] != 1:
                    self.frame_final = cv2.morphologyEx(self.frame_final, cv2.MORPH_DILATE, self.morph_kernel2, iterations=3)
                else:
                    base_x, base_y = center_x, center_y
        
        contours, _ = cv2.findContours(self.frame_final, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contours_box = [cv2.boundingRect(cnt) for cnt in contours]
        contours_dist = np.array(
            [abs(base_x - (cnt_x + cnt_w / 2)) + abs(base_y - (cnt_y + cnt_h / 2)) for cnt_x, cnt_y, cnt_w, cnt_h in contours_box])
        
        if len(contours_box):
            cropped_x2, cropped_y2, cropped_w2, cropped_h2 = contours_box[contours_dist.argmin()]
            x = cropped_x2 + cropped_w2 // 2
            y = cropped_y2 + cropped_h2 // 2
        else:
            x = center_x
            y = center_y
        
        # if imshow_enable:
        #     cv2.circle(frame, (orig_x, orig_y), 10, (255, 0, 0), -1)
        #     cv2.circle(frame, (x, y), 7, (0, 0, 255), -1)
        
        #
        # out_x = center_x if abs(x - center_x) > radius else x
        # out_y = center_y if abs(y - center_y) > radius else y
        out_x, out_y = orig_x, orig_y
        if gray_frame[int(max(y - 5, 0)):int(min(y + 5, self.frame_shape[0])),
           int(max(x - 5, 0)):int(min(x + 5, self.frame_shape[1]))].min() < self.quartile_1:
            out_x = x
            out_y = y
        
        # if imshow_enable:
        #     cv2.circle(frame, (out_x, out_y), 5, (0, 255, 0), -1)
        #
        #     cv2.imshow("frame_bin", self.frame_bin * 255)
        #     cv2.imshow("frame_final", self.frame_final * 255)
        return out_x, out_y


class HSRAC_cls(object):
    def __init__(self):
        # I'd like to take into account things like print, end_time - start_time processing time, etc., but it's too much trouble.
        
        # For measuring total processing time
        
        self.main_start_time = timeit.default_timer()
        
        self.rng = np.random.default_rng()
        self.cvparam = CvParameters(default_radius, default_step)
        
        self.cv_modeo = ["first_frame", "radius_adjust", "blink_adjust", "normal"]
        self.now_modeo = self.cv_modeo[0]
        
        self.auto_radius_calc = Auto_Radius_Calc()
        self.blink_detector = Blink_Detector()
        self.center_q1 = Blink_Detector()
        self.center_correct = CenterCorrection()
        
        self.cap = None
        
        self.timedict = {"to_gray": [], "int_img": [], "conv_int": [], "crop": [], "total_cv": []}
    
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
            self.current_image_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return True
        return False
    
    def single_run(self):
        # Temporary implementation to run
        
        ## default_radius = 14
        
        frame = self.current_image_gray
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
        
        gray_frame = frame
        self.timedict["to_gray"].append(timeit.default_timer() - cv_start_time)
        
        # Calculate the integral image of the frame
        int_start_time = timeit.default_timer()
        # BORDER_CONSTANT is faster than BORDER_REPLICATE There seems to be almost no negative impact when BORDER_CONSTANT is used.
        frame_pad = cv2.copyMakeBorder(gray_frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT)
        frame_int = cv2.integral(frame_pad)
        self.timedict["int_img"].append(timeit.default_timer() - int_start_time)
        
        # Convolve the feature with the integral image
        conv_int_start_time = timeit.default_timer()
        xy_step = frameint_get_xy_step(frame_int.shape, step, pad, start_offset=None, end_offset=None)
        frame_conv, response, center_xy = conv_int(frame_int, hsf, step, pad, xy_step)
        self.timedict["conv_int"].append(timeit.default_timer() - conv_int_start_time)
        
        crop_start_time = timeit.default_timer()
        # Define the center point and radius
        center_x, center_y = center_xy
        upper_x = center_x + radius
        lower_x = center_x - radius
        upper_y = center_y + radius
        lower_y = center_y - radius
        
        # Crop the image using the calculated bounds
        cropped_image = gray_frame[lower_y:upper_y, lower_x:upper_x]
        
        if self.now_modeo == self.cv_modeo[0] or self.now_modeo == self.cv_modeo[1]:
            # If mode is first_frame or radius_adjust, record current radius and response
            self.auto_radius_calc.add_response(radius, response)
        elif self.now_modeo == self.cv_modeo[2]:
            # Statistics for blink detection
            if self.blink_detector.response_len() < blink_init_frames:
                self.blink_detector.add_response(cv2.mean(cropped_image)[0])
                
                upper_x = center_x + self.center_correct.center_q1_radius
                lower_x = center_x - self.center_correct.center_q1_radius
                upper_y = center_y + self.center_correct.center_q1_radius
                lower_y = center_y - self.center_correct.center_q1_radius
                self.center_q1.add_response(cv2.mean(gray_frame[lower_y:upper_y, lower_x:upper_x])[0])
            
            else:
                
                self.blink_detector.calc_thresh()
                self.center_q1.calc_thresh()
                self.now_modeo = self.cv_modeo[3]
        else:
            if 0 in cropped_image.shape:
                # If shape contains 0, it is not detected well.
                print("Something's wrong.")
            else:
                orig_x, orig_y = center_x, center_y
                if self.blink_detector.enable_detect_flg:
                    # If the average value of cropped_image is greater than response_max
                    # (i.e., if the cropimage is whitish
                    if self.blink_detector.detect(cv2.mean(cropped_image)[0]):
                        # blink
                        pass
                    else:
                        pass
                 #       if not self.center_correct.setup_comp:
                  #          self.center_correct.init_array(gray_frame.shape, self.center_q1.quartile_1, radius)
                        
                #        center_x, center_y = self.center_correct.correction(gray_frame, center_x, center_y)
              #          # Define the center point and radius
              #          center_xy = (center_x, center_y)
             #           upper_x = center_x + radius
             #           lower_x = center_x - radius
              #          upper_y = center_y + radius
              #          lower_y = center_y - radius
              #          # Crop the image using the calculated bounds
               #         cropped_image = gray_frame[lower_y:upper_y, lower_x:upper_x]
                if imshow_enable or save_video:
                    cv2.circle(frame, (orig_x, orig_y), 10, (0, 0, 255), -1)
                    cv2.circle(frame, (center_x, center_y), 3, (255, 0, 0), -1)
        # If you want to update response_max. it may be more cost-effective to rewrite response_list in the following way
        # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue
        
        cv_end_time = timeit.default_timer()
        self.timedict["crop"].append(cv_end_time - crop_start_time)
        self.timedict["total_cv"].append(cv_end_time - cv_start_time)
        
        if calc_print_enable:
            # the lower the response the better the likelyhood of there being a pupil. you can adujst the radius and steps accordingly
            print('Kernel response:', response)
            print('Pixel position:', center_xy)
        
        if imshow_enable:
            if self.now_modeo != self.cv_modeo[0] and self.now_modeo != self.cv_modeo[1]:
                if 0 in cropped_image.shape:
                    # If shape contains 0, it is not detected well.
                    pass
                else:
                    cv2.imshow("crop", cropped_image)
                    cv2.imshow("frame", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                pass
        
        if self.now_modeo == self.cv_modeo[0]:
            # Moving from first_frame to the next mode
            if skip_autoradius and skip_blink_detect:
                self.now_modeo = self.cv_modeo[3]
            elif skip_autoradius:
                self.now_modeo = self.cv_modeo[2]
            else:
                self.now_modeo = self.cv_modeo[1]
        
        return center_x, center_y, frame

class External_Run:

    hsrac = HSRAC_cls()

    def HSRACE(self):
        External_Run.hsrac.current_image_gray = self.current_image_gray
        center_x, center_y, frame = External_Run.hsrac.single_run()
        return center_x, center_y, frame

if __name__ == '__main__':
    hsrac = HSRAC_cls()
    hsrac.open_video(video_path)
    while hsrac.read_frame():
        _ = hsrac.single_run()

'''
timedict = {"to_gray": [], "int_img": [], "conv_int": [], "crop": [], "total_cv": []}
# I'd like to take into account things like print, end_time - start_time processing time, etc., but it's too much trouble.
# For measuring total processing time
main_start_time = timeit.default_timer()
rng = np.random.default_rng()
cvparam = CvParameters(default_radius, default_step)
cv_mode = ["first_frame", "radius_adjust", "init", "normal"]
now_mode = cv_mode[0]
radius_cand_list = []
# response_min=0
response_max = None
response_list = []
prev_hsfx = 0
prev_hsfy = 0
prev_ranx = 0
prev_rany = 0
def HSRAC(self):
    global now_mode
    global response_list
    global radius_cand_list
    global response_max
    global skip_autoradius
    global default_radius
    global prev_rany
    global prev_ranx
    global prev_hsfy
    global prev_hsfx
    skip_autoradius = self.settings.gui_skip_autoradius
    default_radius  = self.settings.gui_HSF_radius
    thresh_add = self.settings.gui_thresh_add
    frame = self.current_image_gray
    if now_mode == cv_mode[1]:
        prev_res_len = len(response_list)
        # adjustment of radius
        if prev_res_len == 1:
            # len==1==response_list==[default_radius]
            cvparam.radius = auto_radius_range[0]
        elif prev_res_len == 2:
            # len==2==response_list==[default_radius, auto_radius_range[0]]
            cvparam.radius = auto_radius_range[1]
        elif prev_res_len == 3:
            # len==3==response_list==[default_radius,auto_radius_range[0],auto_radius_range[1]]
            sort_res = sorted(response_list, key=lambda x: x[1])[0]
            # Extract the radius with the lowest response value
            if sort_res[0] == default_radius:
                # If the default value is best, change now_mode to init after setting radius to the default value.
                cvparam.radius = default_radius
                now_mode = cv_mode[2] if not skip_blink_detect else cv_mode[3]
                response_list = []
            elif sort_res[0] == auto_radius_range[0]:
                radius_cand_list = [i for i in range(auto_radius_range[0], default_radius, default_step[0])][1:]
                # default_step is defined separately for xy, but radius is shared by xy, so it may be buggy
                # It should be no problem to set it to anything other than default_step
                cvparam.radius = radius_cand_list.pop()
            else:
                radius_cand_list = [i for i in range(default_radius, auto_radius_range[1], default_step[0])][1:]
                # default_step is defined separately for xy, but radius is shared by xy, so it may be buggy
                # It should be no problem to set it to anything other than default_step
                cvparam.radius = radius_cand_list.pop()
        else:
            # Try the contents of the radius_cand_list in order until the radius_cand_list runs out
            # Better make it a binary search.
            if len(radius_cand_list) == 0:
                sort_res = sorted(response_list, key=lambda x: x[1])[0]
                cvparam.radius = sort_res[0]
                now_mode = cv_mode[2] if not skip_blink_detect else cv_mode[3]
                response_list = []
            else:
                cvparam.radius = radius_cand_list.pop()

    radius, pad, step, hsf = cvparam.get_rpsh()

    # For measuring processing time of image processing
    cv_start_time = timeit.default_timer()

    gray_frame = frame
    timedict["to_gray"].append(timeit.default_timer() - cv_start_time)

    # Calculate the integral image of the frame
    int_start_time = timeit.default_timer()
    # BORDER_CONSTANT is faster than BORDER_REPLICATE There seems to be almost no negative impact when BORDER_CONSTANT is used.
    frame_pad = cv2.copyMakeBorder(gray_frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT)
    frame_int = cv2.integral(frame_pad)
    timedict["int_img"].append(timeit.default_timer() - int_start_time)

    # Convolve the feature with the integral image
    conv_int_start_time = timeit.default_timer()
    xy_step = frameint_get_xy_step(frame_int.shape, step, pad, start_offset=None, end_offset=None)
    frame_conv, response, center_xy = conv_int(frame_int, hsf, step, pad, xy_step)
    timedict["conv_int"].append(timeit.default_timer() - conv_int_start_time)
    # Define the center point and radius
    center_x, center_y = center_xy
    upper_x = center_x + 20
    lower_x = center_x - 20
    upper_y = center_y + 20
    lower_y = center_y - 20

    # Crop the image using the calculated bounds
    cropped_image = gray_frame[lower_y:upper_y, lower_x:upper_x]
    frame = cropped_image
    if now_mode == cv_mode[0] or now_mode == cv_mode[1]:
        # If mode is first_frame or radius_adjust, record current radius and response
        response_list.append((radius, response))
    elif now_mode == cv_mode[2]:
        # Statistics for blink detection
        if len(response_list) < blink_init_frames:
            # Record the average value of cropped_image
            response_list.append(cv2.mean(cropped_image)[0])
        else:
            # Calculate response_max by computing interquartile range, IQR
            # Change cv_mode to normal
            response_list = np.array(response_list)
            # 25%,75%
            # This value may need to be adjusted depending on the environment.
            quartile_1, quartile_3 = np.percentile(response_list, [25, 75])
            iqr = quartile_3 - quartile_1
            # response_min = quartile_1 - (iqr * 1.5)
            response_max = quartile_3 + (iqr * 1.5)
            now_mode = cv_mode[3]
    else:
        if 0 in cropped_image.shape:
            # If shape contains 0, it is not detected well.
            print("Something's wrong.")
        else:
            # If the average value of cropped_image is greater than response_max
            # (i.e., if the cropimage is whitish
            if response_max is not None and cv2.mean(cropped_image)[0] > response_max:
                # blink
                self.blinkvalue = True
                print("HSF BLINK")
    # If you want to update response_max. it may be more cost-effective to rewrite response_list in the following way
    # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue


    # the lower the response the better the likelyhood of there being a pupil. you can adujst the radius and steps accordingly
    print('Kernel response:', response)
    print('Pixel position:', center_xy)
    if now_mode == cv_mode[0]:
        # Moving from first_frame to the next mode
        if skip_autoradius and skip_blink_detect:
            now_mode = cv_mode[3]
            response_list = []
        elif skip_autoradius:
            now_mode = cv_mode[2]
            response_list = []
        else:
            now_mode = cv_mode[1]
    #run ransac on the HSF crop\
    frame = cropped_image

   # try:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    # Convert the image to grayscale, and set up thresholding. Thresholds here are basically a
    # low-pass filter that will set any pixel < the threshold value to 0. Thresholding is user
    # configurable in this utility as we're dealing with variable lighting amounts/placement, as
    # well as camera positioning and lensing. Therefore everyone's cutoff may be different.
    #
    # The goal of thresholding settings is to make sure we can ONLY see the pupil. This is why we
    # crop the image earlier; it gives us less possible dark area to get confused about in the
    # next step.

    # For measuring processing time of image processing
    # Crop first to reduce the amount of data to process.
    #frame = frame[0:len(frame) - 5, :]

    # To reduce the processing data, first convert to 1-channel and then blur.
    # The processing results were the same when I swapped the order of blurring and 1-channelization.
    try:
        frame = cv2.GaussianBlur(frame, (5, 5), 0)
    except:
        pass
    # this will need to be adjusted everytime hardware is changed (brightness of IR, Camera postion, etc)m
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(frame)

    maxloc0_hf, maxloc1_hf = int(0.5 * max_loc[0]), int(0.5 * max_loc[1])

    # crop 15% sqare around min_loc
# frame = frame[max_loc[1] - maxloc1_hf:max_loc[1] + maxloc1_hf,
    #               max_loc[0] - maxloc0_hf:max_loc[0] + maxloc0_hf]

    threshold_value = min_val + thresh_add
    _, thresh = cv2.threshold(frame, threshold_value, 255, cv2.THRESH_BINARY)
    try:
        opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
        th_frame = 255 - closing
    except:
        # I want to eliminate try here because try tends to be slow in execution.
        th_frame = 255 - frame

    contours, _ = cv2.findContours(th_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    hull = []
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
            print("NODATYA")
            pass

        crop_start_time = timeit.default_timer()
        cx, cy, w, h, theta = ransac_data
        csx = frame.shape[0]
        csy = frame.shape[1]
        cx = center_x - (csx - cx) # we find the difference between the crop size and ransac point, and subtract from the center point from HSF
        cy = center_y - (csy - cy)
        out_x, out_y = cx, cy
        prev_hsfx = center_x
        prev_hsfy = center_y
        prev_ranx = cx
        prev_rany = cy
        cx, cy, w, h = int(cx), int(cy), int(w), int(h)
        cv2.drawContours(frame, contours, -1, (255, 0, 0), 1)
        cv2.circle(frame, (cx, cy), 2, (0, 0, 255), -1)
        # cx1, cy1, w1, h1, theta1 = fit_rotated_ellipse(maxcnt.reshape(-1, 2))
        cv2.ellipse(frame, (cx, cy), (w, h), theta * 180.0 / np.pi, 0.0, 360.0, (50, 250, 200), 1, )
        cv2.circle(frame, min_loc, 2, (0, 0, 255),-1)  # the point of the darkest area in the image
        self.current_image_gray = frame
        #img = newImage2[y1:y2, x1:x2]
        #except:
           # print('R F')
          #  pass



        try:
          #  print(radius)
            return out_x, out_y, thresh

        except:
            xoff = prev_hsfx - prev_ranx
            yoff = prev_hsfy - prev_rany
            return (xoff), (yoff), thresh
    except:
        self.current_image_gray = frame #cv2.resize(frame, (150, 150), interpolation = cv2.INTER_AREA)
        xoff = prev_hsfx - 28
        yoff = prev_hsfy - 28
        print(prev_hsfx, prev_ranx)
        return (xoff), (yoff), thresh
    try:
        self.failed = 0
        cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), -1)
        return center_x, center_y, frame

    except:
        self.failed = self.failed + 1
        return 0, 0, frame
'''

'''
def HSRAC(self):
    global default_radius
    global auto_radius_range
    global response_list
    global radius_cand_list
    global response_max
    global now_mode
    global cv_mode
    default_radius = int(self.settings.gui_HSF_radius)
    auto_radius_range = (default_radius - 10, default_radius + 10)  # (10,30)

    print(default_radius, cv_mode, now_mode, radius_cand_list, response_max )
    if self.calibration_frame_counter == 0: # if reset triggered, reset all values
        now_mode = cv_mode[0]
        radius_cand_list = []
        # response_min=0
        response_max = None
        response_list = []
        print("RESET HSRAC")
    frame = self.current_image_gray
    if now_mode == cv_mode[1]:

        prev_res_len = len(response_list)
        # adjustment of radius
        if prev_res_len == 1:
            # len==1==response_list==[default_radius]
            self.cvparam.radius = self.auto_radius_range[0]
        elif prev_res_len == 2:
            # len==2==response_list==[default_radius, self.auto_radius_range[0]]
            self.cvparam.radius = self.auto_radius_range[1]
        elif prev_res_len == 3:
            # len==3==response_list==[default_radius,self.auto_radius_range[0],self.auto_radius_range[1]]
            sort_res = sorted(response_list, key=lambda x: x[1])[0]
            # Extract the radius with the lowest response value
            if sort_res[0] == default_radius:
                # If the default value is best, change now_mode to init after setting radius to the default value.
                self.cvparam.radius = default_radius
                now_mode = cv_mode[2] if not self.skip_blink_detect else cv_mode[3]
                response_list = []
            elif sort_res[0] == self.auto_radius_range[0]:
                radius_cand_list = [i for i in range(self.auto_radius_range[0], default_radius, self.default_step[0])][1:]
                # self.default_step is defined separately for xy, but radius is shared by xy, so it may be buggy
                # It should be no problem to set it to anything other than self.default_step
                self.cvparam.radius = radius_cand_list.pop()
            else:
                radius_cand_list = [i for i in range(default_radius, self.auto_radius_range[1], self.default_step[0])][1:]
                # self.default_step is defined separately for xy, but radius is shared by xy, so it may be buggy
                # It should be no problem to set it to anything other than self.default_step
                self.cvparam.radius = radius_cand_list.pop()
        else:
            # Try the contents of the radius_cand_list in order until the radius_cand_list runs out
            # Better make it a binary search.
            if len(radius_cand_list) == 0:
                sort_res = sorted(response_list, key=lambda x: x[1])[0]
                self.cvparam.radius = sort_res[0]
                now_mode = cv_mode[2] if not self.skip_blink_detect else cv_mode[3]
                response_list = []
            else:
                self.cvparam.radius = radius_cand_list.pop()

    radius, pad, step, hsf = self.cvparam.get_rpsh()

    gray_frame = frame
    try:
        # BORDER_CONSTANT is faster than BORDER_REPLICATE There seems to be almost no negative impact when BORDER_CONSTANT is used.
        frame_pad = cv2.copyMakeBorder(gray_frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT)
        frame_int = cv2.integral(frame_pad)

        # Convolve the feature with the integral image
        conv_int_start_time = timeit.default_timer()
        xy_step = frameint_get_xy_step(frame_int.shape, step, pad, start_offset=None, end_offset=None)
        frame_conv, response, center_xy = conv_int(frame_int, hsf, step, pad, xy_step)

        crop_start_time = timeit.default_timer()
        # Define the center point and radius
        center_x, center_y = center_xy
        upper_x = center_x + 25 #TODO make this a setting
        lower_x = center_x - 25
        upper_y = center_y + 25
        lower_y = center_y - 25

        # Crop the image using the calculated bounds
        cropped_image = gray_frame[lower_y:upper_y, lower_x:upper_x] # y is 50px, x is 45? why?

        if now_mode == cv_mode[0] or now_mode == cv_mode[1]:
            # If mode is first_frame or radius_adjust, record current radius and response
            response_list.append((radius, response))
        elif now_mode == cv_mode[2]:
            # Statistics for blink detection
            if len(response_list) < self.blink_init_frames:
                # Record the average value of cropped_image
                response_list.append(cv2.mean(cropped_image)[0])
            else:
                # Calculate response_max by computing interquartile range, IQR
                # Change cv_mode to normal
                response_list = np.array(response_list)
                # 25%,75%
                # This value may need to be adjusted depending on the environment.
                quartile_1, quartile_3 = np.percentile(response_list, [25, 75])
                iqr = quartile_3 - quartile_1
                # response_min = quartile_1 - (iqr * 1.5)
                response_max = quartile_3 + (iqr * 1.5)
                now_mode = cv_mode[3]
        else:
            if 0 in cropped_image.shape:
                # If shape contains 0, it is not detected well.
                print("Something's wrong.")
            else:
                # If the average value of cropped_image is greater than response_max
                # (i.e., if the cropimage is whitish
                if response_max is not None and cv2.mean(cropped_image)[0] > response_max:
                    # blink

                    cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), -1)
        # If you want to update response_max. it may be more cost-effective to rewrite response_list in the following way
        # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue

    except:
        return 0, 0, frame
#run ransac on the HSF crop\
    try:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        thresh_add = 10
        rng = np.random.default_rng()

        f = False

        # Convert the image to grayscale, and set up thresholding. Thresholds here are basically a
        # low-pass filter that will set any pixel < the threshold value to 0. Thresholding is user
        # configurable in this utility as we're dealing with variable lighting amounts/placement, as
        # well as camera positioning and lensing. Therefore everyone's cutoff may be different.
        #
        # The goal of thresholding settings is to make sure we can ONLY see the pupil. This is why we
        # crop the image earlier; it gives us less possible dark area to get confused about in the
        # next step.
        frame = cropped_image
        # For measuring processing time of image processing
        # Crop first to reduce the amount of data to process.
        #frame = frame[0:len(frame) - 5, :]

        # To reduce the processing data, first convert to 1-channel and then blur.
        # The processing results were the same when I swapped the order of blurring and 1-channelization.
        frame = cv2.GaussianBlur(frame, (5, 5), 0)


        # this will need to be adjusted everytime hardware is changed (brightness of IR, Camera postion, etc)m
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(frame)

        maxloc0_hf, maxloc1_hf = int(0.5 * max_loc[0]), int(0.5 * max_loc[1])

        # crop 15% sqare around min_loc
    # frame = frame[max_loc[1] - maxloc1_hf:max_loc[1] + maxloc1_hf,
        #               max_loc[0] - maxloc0_hf:max_loc[0] + maxloc0_hf]

        threshold_value = min_val + thresh_add
        _, thresh = cv2.threshold(frame, threshold_value, 255, cv2.THRESH_BINARY)
        try:
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
            th_frame = 255 - closing
        except:
            # I want to eliminate try here because try tends to be slow in execution.
            th_frame = 255 - frame

        detect_start_time = timeit.default_timer()
        contours, _ = cv2.findContours(th_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
        hull = []
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

            crop_start_time = timeit.default_timer()
            cx, cy, w, h, theta = ransac_data
            csx = frame.shape[0]
            csy = frame.shape[1]
            cx = center_x - (csx - cx) # we find the difference between the crop size and ransac point, and subtract from the center point from HSF
            cy = center_y - (csy - cy)
            out_x, out_y = cx, cy
            cx, cy, w, h = int(cx), int(cy), int(w), int(h)

            cv2.drawContours(self.current_image_gray, contours, -1, (255, 0, 0), 1)
            cv2.circle(self.current_image_gray, (cx, cy), 2, (0, 0, 255), -1)
            # cx1, cy1, w1, h1, theta1 = fit_rotated_ellipse(maxcnt.reshape(-1, 2))
            cv2.ellipse(self.current_image_gray, (cx, cy), (w, h), theta * 180.0 / np.pi, 0.0, 360.0, (50, 250, 200), 1, )

        #img = newImage2[y1:y2, x1:x2]
        except:
            pass

        self.current_image_gray = frame
        cv2.circle(self.current_image_gray, min_loc, 2, (0, 0, 255),
                -1)  # the point of the darkest area in the image
        try:
          #  print(radius)
            return out_x, out_y, thresh

        except:
            return 0, 0, thresh
    except:
         return center_x, center_y, self.current_image_gray
'''
