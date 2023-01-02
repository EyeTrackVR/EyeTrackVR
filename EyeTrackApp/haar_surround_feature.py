'''
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

HSR By: Sean.Denka (Optimization Wizard, Contributor), Summer#2406 (Main Algorithm Engineer)  
Algorithm App Implimentations By: Prohurtz#0001, qdot (Inital App Creator)

Copyright (c) 2022 EyeTrackVR <3                                
------------------------------------------------------------------------------------------------------
'''     


import functools
import math
import os
import sys
import timeit
from functools import lru_cache

import cv2
import numpy as np

# from line_profiler_pycharm import profile

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


# @profile

    

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

def HSF(self):

    global now_mode
    global response_list
    global radius_cand_list
    global response_max
   # default_radius = 15
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
    
    crop_start_time = timeit.default_timer()
    # Define the center point and radius
    center_x, center_y = center_xy
    upper_x = center_x + radius
    lower_x = center_x - radius
    upper_y = center_y + radius
    lower_y = center_y - radius
    
    # Crop the image using the calculated bounds
    cropped_image = gray_frame[lower_y:upper_y, lower_x:upper_x]
    
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
                cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), -1)
                
    # If you want to update response_max. it may be more cost-effective to rewrite response_list in the following way
    # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue
    
    cv_end_time = timeit.default_timer()
    timedict["crop"].append(cv_end_time - crop_start_time)
    timedict["total_cv"].append(cv_end_time - cv_start_time)
    
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

    try:
        self.failed = 0
        return center_x, center_y, frame
        
    except:     
        self.failed = self.failed + 1
        return 0, 0, frame



