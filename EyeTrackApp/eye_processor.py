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
RANSAC 3D By: Summer#2406 (Main Algorithm Engineer), Pupil Labs (pye3d), Sean.Denka (Optimization)
BLOB By: Prohurtz#0001 (Main App Developer)
Algorithm App Implimentations By: Prohurtz#0001, qdot (Inital App Creator)

Additional Contributors: [Assassin], Summer404NotFound, lorow, ZanzyTHEbar

Copyright (c) 2022 EyeTrackVR <3                                
------------------------------------------------------------------------------------------------------
'''                                                                         

from operator import truth
from dataclasses import dataclass
import sys
import asyncio

sys.path.append(".")
from config import EyeTrackCameraConfig
from config import EyeTrackSettingsConfig
from pye3d.camera import CameraModel
from pye3d.detector_3d import Detector3D, DetectorMode
import queue
import threading
import numpy as np
import cv2
from enum import Enum
from one_euro_filter import OneEuroFilter
if sys.platform.startswith("win"):
    from winsound import PlaySound, SND_FILENAME, SND_ASYNC

import _thread
import functools
import math
import os
import timeit
import time
from collections import namedtuple
from functools import lru_cache
import xxhash

class InformationOrigin(Enum):
    RANSAC = 1
    BLOB = 2
    FAILURE = 3
    HSF = 4


@dataclass
class EyeInformation:
    info_type: InformationOrigin
    x: float
    y: float
    pupil_dialation: int
    blink: bool


lowb = np.array(0)


def run_once(f):
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return f(*args, **kwargs)

    wrapper.has_run = False
    return wrapper


async def delayed_setting_change(setting, value):
    await asyncio.sleep(5)
    setting = value
    if sys.platform.startswith("win"):
        PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)

def cal_osc(self, cx, cy):
    if self.eye_id == "EyeId.RIGHT":
        flipx = self.settings.gui_flip_x_axis_right
    else:
        flipx = self.settings.gui_flip_x_axis_left
    if self.calibration_frame_counter == 0:
        self.calibration_frame_counter = None
        self.xoff = cx
        self.yoff = cy
        if sys.platform.startswith("win"):
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
        self.calibration_frame_counter -= 1
    if self.settings.gui_recenter_eyes == True:
        self.xoff = cx
        self.yoff = cy
        if self.ts == 0:
            self.settings.gui_recenter_eyes = False
            if sys.platform.startswith("win"):
                PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)
        else:
            self.ts = self.ts - 1
    else:
        self.ts = 10

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

    out_x = 0
    out_y = 0
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

    if flipx:  #TODO Check for working function
        if xr >= 0:
            out_x = -abs(max(0.0, min(1.0, xr)))
        if xl > 0:
            out_x = max(0.0, min(1.0, xl))
    else:
        if xr >= 0:
            out_x = max(0.0, min(1.0, xr))
        if xl > 0:
            out_x = -abs(max(0.0, min(1.0, xl)))

    try:
        noisy_point = np.array([float(out_x), float(out_y)])  # fliter our values with a One Euro Filter
        point_hat = self.one_euro_filter(noisy_point)
        out_x = point_hat[0]
        out_y = point_hat[1]
    except:
        pass
    return out_x, out_y


def HSFV():
    self.response_list = []



#HSF \/

# cache param
lru_maxsize_vvs = 16
lru_maxsize_vs = 64
# CV param
default_radius = 20
auto_radius_range = (default_radius - 10, default_radius + 10)  # (10,30)
blink_init_frames = 60 * 3  # 60fps*3sec,Number of blink statistical frames
# step==(x,y)
default_step = (5, 5)  # bigger the steps,lower the processing time! ofc acc also takes an impact
response_list = []

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
    
    # min_response, max_val, min_loc, max_loc = cv2.minMaxLoc(self.response_list)
    min_response, _, min_loc, _ = cv2.minMaxLoc(response_list)
    
    center = ((xy_steps_list[0][min_loc[0]] - padding), (xy_steps_list[1][min_loc[1]] - padding))
    
    frame_conv_stride[:, :] = response_list
    # or
    # frame_conv_stride[:, :] = self.response_list.astype(np.uint8)
    
    return frame_conv, min_response, center







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
def fit_rotated_ellipse_ransac(data: np.ndarray, rng: np.random.Generator, iter=100, sample_num=10, offset=80  # 80.0, 10, 80
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
        [data, data ** 2, (data[:, 0] * data[:, 1])[:, np.newaxis], np.ones((len_data, 1), dtype=ret_dtype),
         (-1 * data[:, 0] ** 2)[:, np.newaxis]], axis=1,
        dtype=ret_dtype)
    
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
        [datamod_rng_p[:, 2], datamod_rng_p[:, 3], np.ones(len(datamod_rng_p)), datamod_rng_p[:, 1], datamod_rng_p[:, 0]], dtype=ret_dtype)
    
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
    tc2 = theta_cos ** 2
    ts2 = theta_sin ** 2
    b_tcs = b * theta_cos * theta_sin
    
    # Do the calculation only once
    cxy = b ** 2 - 4 * a * c
    cx = (2 * c * d - b * e) / cxy
    cy = (2 * a * e - b * d) / cxy
    
    # I just want to clear things up around here.
    cu = a * cx ** 2 + b * cx * cy + c * cy ** 2 - f
    cu_r = np.array([(a * tc2 + b_tcs + c * ts2), (a * ts2 - b_tcs + c * tc2)])
    wh = np.sqrt(cu / cu_r)
    
    w, h = wh[0], wh[1]
    
    error_sum = np.sum(data)
    # print("fitting error = %.3f" % (error_sum))
    
    return (cx, cy, w, h, theta)


class EyeProcessor:
    def __init__(
        self,
        config: "EyeTrackCameraConfig",
        settings: "EyeTrackSettingsConfig",
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        capture_queue_incoming: "queue.Queue",
        image_queue_outgoing: "queue.Queue",
        eye_id,
    ):
        self.config = config
        self.settings = settings

        # Cross-thread communication management
        self.capture_queue_incoming = capture_queue_incoming
        self.image_queue_outgoing = image_queue_outgoing
        self.cancellation_event = cancellation_event
        self.capture_event = capture_event
        self.eye_id = eye_id

        # Cross algo state
        self.lkg_projected_sphere = None
        self.xc = None
        self.yc = None

        # Image state
        self.previous_image = None
        self.current_image = None
        self.current_image_gray = None
        self.current_frame_number = None
        self.current_fps = None
        self.threshold_image = None

        # Calibration Values
        self.xoff = 1
        self.yoff = 1
        # Keep large in order to recenter correctly
        self.calibration_frame_counter = None
        self.eyeoffx = 1

        self.xmax = -69420
        self.xmin = 69420
        self.ymax = -69420
        self.ymin = 69420
        self.cct = 300
        self.cccs = False
        self.ts = 10
        self.previous_rotation = self.config.rotation_angle
        self.calibration_frame_counter
        self.camera_model = None
        self.detector_3d = None

        self.camera_model = None
        self.detector_3d = None


        self.response_list = []  #TODO we need to unify this?
         #HSF
        
        
        self.cv_mode = ["first_frame", "radius_adjust", "init", "normal"]
        self.now_mode = self.cv_mode[0]
        self.cvparam = CvParameters(default_radius, default_step)




        self.default_radius = 15
        self.skip_blink_detect = False

        self.default_step = (5, 5)  # bigger the steps,lower the processing time! ofc acc also takes an impact
        # self.default_step==(x,y)
        self.radius_cand_list = []
        self.blink_init_frames = 60 * 3
        prev_max_size = 60 * 3  # 60fps*3sec
        # response_min=0
        self.response_max = None
        self.default_radius = 20
        self.auto_radius_range = (self.default_radius - 10, self.default_radius + 10) 

        #blink
        self.max_ints = []
        self.max_int = 0
        self.min_int = 4000000000000
        self.frames = 0 
        self.blinkvalue = False
        

        

        try:
            min_cutoff = float(self.settings.gui_min_cutoff)  # 0.0004
            beta = float(self.settings.gui_speed_coefficient)  # 0.9
        except:
            print('[WARN] OneEuroFilter values must be a legal number.')
            min_cutoff = 0.0004
            beta = 0.9
        noisy_point = np.array([1, 1])
        self.one_euro_filter = OneEuroFilter(
            noisy_point,
            min_cutoff=min_cutoff,
            beta=beta
        )

    def output_images_and_update(self, threshold_image, output_information: EyeInformation):
        image_stack = np.concatenate(
            (
                cv2.cvtColor(self.current_image_gray, cv2.COLOR_GRAY2BGR),
                cv2.cvtColor(threshold_image, cv2.COLOR_GRAY2BGR),
            ),
            axis=1,
        )
        self.image_queue_outgoing.put((image_stack, output_information))
        self.previous_image = self.current_image
        self.previous_rotation = self.config.rotation_angle

    def capture_crop_rotate_image(self):
        # Get our current frame
        
        try:
            # Get frame from capture source, crop to ROI
            self.current_image = self.current_image[
                int(self.config.roi_window_y): int(
                    self.config.roi_window_y + self.config.roi_window_h
                ),
                int(self.config.roi_window_x): int(
                    self.config.roi_window_x + self.config.roi_window_w
                ),
            ]
    
        except:
            # Failure to process frame, reuse previous frame.
            self.current_image = self.previous_image
            print("[ERROR] Frame capture issue detected.")

        try:
            # Apply rotation to cropped area. For any rotation area outside of the bounds of the image,
            # fill with white.
            try:
                rows, cols, _ = self.current_image.shape
            except:
                rows, cols, _ = self.previous_image.shape
            img_center = (cols / 2, rows / 2)
            rotation_matrix = cv2.getRotationMatrix2D(
                img_center, self.config.rotation_angle, 1
            )
            self.current_image = cv2.warpAffine(
                self.current_image,
                rotation_matrix,
                (cols, rows),
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            )
            return True
        except:
            pass

    def BLOB(self):
        
        # define circle
        if self.config.gui_circular_crop:
            if self.cct == 0:
                try:
                    ht, wd = self.current_image_gray.shape[:2]

                    radius = int(float(self.lkg_projected_sphere["axes"][0]))

                    # draw filled circle in white on black background as mask
                    mask = np.zeros((ht, wd), dtype=np.uint8)
                    mask = cv2.circle(mask, (self.xc, self.yc), radius, 255, -1)
                    # create white colored background
                    color = np.full_like(self.current_image_gray, (255))
                    # apply mask to image
                    masked_img = cv2.bitwise_and(self.current_image_gray, self.current_image_gray, mask=mask)
                    # apply inverse mask to colored image
                    masked_color = cv2.bitwise_and(color, color, mask=255 - mask)
                    # combine the two masked images
                    self.current_image_gray = cv2.add(masked_img, masked_color)
                except:
                    pass
            else:
                self.cct = self.cct - 1
        _, larger_threshold = cv2.threshold(self.current_image_gray, int(self.config.threshold + 12), 255, cv2.THRESH_BINARY)
    

        #try:
            # Try rebuilding our contours
        contours, _ = cv2.findContours(
            larger_threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)
        
        # If we have no contours, we have nothing to blob track. Fail here.
        if len(contours) == 0:
            raise RuntimeError("No contours found for image")
       # except:
           # self.output_images_and_update(larger_threshold, EyeInformation(InformationOrigin.FAILURE, 0, 0, 0, False))
          #  return

        rows, cols = larger_threshold.shape
        
        for cnt in contours:
            (x, y, w, h) = cv2.boundingRect(cnt)

            # if our blob width/height are within suitable (yet arbitrary) boundaries, call that good.
            #
            # TODO This should be scaled based on camera resolution.

            if not self.settings.gui_blob_minsize <= h <= self.settings.gui_blob_maxsize or not self.settings.gui_blob_minsize <= w <= self.settings.gui_blob_maxsize:
                continue
    
            cx = x + int(w / 2)

            cy = y + int(h / 2)

            cv2.line(
                self.current_image_gray,
                (x + int(w / 2), 0),
                (x + int(w / 2), rows),
                (255, 0, 0),
                1,
            )  # visualizes eyetracking on thresh
            cv2.line(
                self.current_image_gray,
                (0, y + int(h / 2)),
                (cols, y + int(h / 2)),
                (255, 0, 0),
                1,
            )
            cv2.drawContours(self.current_image_gray, [cnt], -1, (255, 0, 0), 3)
            cv2.rectangle(
                self.current_image_gray, (x, y), (x + w, y + h), (255, 0, 0), 2
            )

            out_x, out_y = cal_osc(self, cx, cy) #filter and calibrate values





            self.output_images_and_update(larger_threshold, EyeInformation(InformationOrigin.BLOB, out_x, out_y, 0, self.blinkvalue))
            f = False
            return f
            
       # self.output_images_and_update(
       #     larger_threshold, EyeInformation(InformationOrigin.BLOB, 0, 0, 0, True)
       # )
       # print("[INFO] BLINK Detected.")
        f = True
        return f
    

    def HSF(self):

        frame = self.current_image_gray     
        if self.now_mode == self.cv_mode[1]:

            
            prev_res_len = len(self.response_list)
            # adjustment of radius
            if prev_res_len == 1:
                # len==1==self.response_list==[self.default_radius]
                self.cvparam.radius = self.auto_radius_range[0]
            elif prev_res_len == 2:
                # len==2==self.response_list==[self.default_radius, self.auto_radius_range[0]]
                self.cvparam.radius = self.auto_radius_range[1]
            elif prev_res_len == 3:
                # len==3==self.response_list==[self.default_radius,self.auto_radius_range[0],self.auto_radius_range[1]]
                sort_res = sorted(self.response_list, key=lambda x: x[1])[0]
                # Extract the radius with the lowest response value
                if sort_res[0] == self.default_radius:
                    # If the default value is best, change self.now_mode to init after setting radius to the default value.
                    self.cvparam.radius = self.default_radius
                    self.now_mode = self.cv_mode[2] if not self.skip_blink_detect else self.cv_mode[3]
                    self.response_list = []
                elif sort_res[0] == self.auto_radius_range[0]:
                    self.radius_cand_list = [i for i in range(self.auto_radius_range[0], self.default_radius, self.default_step[0])][1:]
                    # self.default_step is defined separately for xy, but radius is shared by xy, so it may be buggy
                    # It should be no problem to set it to anything other than self.default_step
                    self.cvparam.radius = self.radius_cand_list.pop()
                else:
                    self.radius_cand_list = [i for i in range(self.default_radius, self.auto_radius_range[1], self.default_step[0])][1:]
                    # self.default_step is defined separately for xy, but radius is shared by xy, so it may be buggy
                    # It should be no problem to set it to anything other than self.default_step
                    self.cvparam.radius = self.radius_cand_list.pop()
            else:
                # Try the contents of the self.radius_cand_list in order until the self.radius_cand_list runs out
                # Better make it a binary search.
                if len(self.radius_cand_list) == 0:
                    sort_res = sorted(self.response_list, key=lambda x: x[1])[0]
                    self.cvparam.radius = sort_res[0]
                    self.now_mode = self.cv_mode[2] if not self.skip_blink_detect else self.cv_mode[3]
                    self.response_list = []
                else:
                    self.cvparam.radius = self.radius_cand_list.pop()
        
        radius, pad, step, hsf = self.cvparam.get_rpsh()
        
        # For measuring processing time of image processing
        cv_start_time = timeit.default_timer()
        
        gray_frame = frame
        
        # Calculate the integral image of the frame
        int_start_time = timeit.default_timer()
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
        upper_x = center_x + 20 #TODO make this a setting
        lower_x = center_x - 20
        upper_y = center_y + 20
        lower_y = center_y - 20
        
        # Crop the image using the calculated bounds
        cropped_image = gray_frame[lower_y:upper_y, lower_x:upper_x]
        
        if self.now_mode == self.cv_mode[0] or self.now_mode == self.cv_mode[1]:
            # If mode is first_frame or radius_adjust, record current radius and response
            self.response_list.append((radius, response))
        elif self.now_mode == self.cv_mode[2]:
            # Statistics for blink detection
            if len(self.response_list) < self.blink_init_frames:
                # Record the average value of cropped_image
                self.response_list.append(cv2.mean(cropped_image)[0])
            else:
                # Calculate self.response_max by computing interquartile range, IQR
                # Change self.cv_mode to normal
                self.response_list = np.array(self.response_list)
                # 25%,75%
                # This value may need to be adjusted depending on the environment.
                quartile_1, quartile_3 = np.percentile(self.response_list, [25, 75])
                iqr = quartile_3 - quartile_1
                # response_min = quartile_1 - (iqr * 1.5)
                self.response_max = quartile_3 + (iqr * 1.5)
                self.now_mode = self.cv_mode[3]
        else:
            if 0 in cropped_image.shape:
                # If shape contains 0, it is not detected well.
                print("Something's wrong.")
            else:
                # If the average value of cropped_image is greater than self.response_max
                # (i.e., if the cropimage is whitish
                if self.response_max is not None and cv2.mean(cropped_image)[0] > self.response_max:
                    # blink
                    
                    cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), -1)
        # If you want to update self.response_max. it may be more cost-effective to rewrite self.response_list in the following way
        # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue
        


        hsfandransac = False
        if not hsfandransac:
            out_x, out_y = cal_osc(self, center_x, center_y)
            
            cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), -1)
        # print(center_x, center_y)

            try:
                if self.settings.gui_BLINK: #tbh this is redundant, the algo already has blink detection built in
                    self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, self.blinkvalue))
                else:
                    self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False))
                f = False
            except:
                pass
                
            if self.now_mode != self.cv_mode[0] and self.now_mode != self.cv_mode[1]:
                if cropped_image.size < 400:
                    pass
        
            if self.now_mode == self.cv_mode[0]:
                self.now_mode = self.cv_mode[1]

            return f
                #self.output_images_and_update(thresh, EyeInformation(InformationOrigin.FAILURE, 0, 0, 0, False))
            # return

            #self.output_images_and_update(larger_threshold,EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False),)
        # return
            #self.output_images_and_update(larger_threshold, EyeInformation(InformationOrigin.HSF, 0, 0, 0, True))

        else: #run ransac on the HSF crop\
            try:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                thresh_add = 10
                rng = np.random.default_rng()
                
                f = False

                newImage2 = cropped_image.copy()
                # Crop first to reduce the amount of data to process.

            # img = self.current_image_gray[0:len(self.current_image_gray) - 10, :]

                # To reduce the processing data, first convert to 1-channel and then blur.
                # The processing results were the same when I swapped the order of blurring and 1-channelization.
            # image_gray = self.current_image_gray
                image_gray = cv2.GaussianBlur(cropped_image, (5, 5), 0)
                
                # this will need to be adjusted everytime hardware is changed (brightness of IR, Camera postion, etc)m
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(image_gray)
                
                maxloc0_hf, maxloc1_hf = int(0.5 * max_loc[0]), int(0.5 * max_loc[1])
                
                # crop 15% sqare around min_loc
            # image_gray = image_gray[max_loc[1] - maxloc1_hf:max_loc[1] + maxloc1_hf,
                #            max_loc[0] - maxloc0_hf:max_loc[0] + maxloc0_hf]
                
                threshold_value = min_val + thresh_add
                th_ret, thresh = cv2.threshold(image_gray, threshold_value, 255, cv2.THRESH_BINARY)
                try:
                    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
                    closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
                    image = 255 - closing
                except:
                    # I want to eliminate try here because try tends to be slow in execution.
                    image = 255 - image_gray
                contours, hierarchy = cv2.findContours(image, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
                hull = []
                # This way is faster than contours[i]
                # But maybe this one is faster. hull = [cv2.convexHull(cnt, False) for cnt in contours]
                for cnt in contours:
                    hull.append(cv2.convexHull(cnt, False))
                if not hull:
                    # If empty, go to next loop
                    pass
                try:
                    self.current_image_gray = cropped_image
                    cv2.drawContours(self.current_image_gray, contours, -1, (255, 0, 0), 1)
                    cnt = sorted(hull, key=cv2.contourArea)
                    maxcnt = cnt[-1]
                    ellipse = cv2.fitEllipse(maxcnt)
                    ransac_data = fit_rotated_ellipse_ransac(maxcnt.reshape(-1, 2))
                    if ransac_data is None:
                        # ransac_data is None==maxcnt.shape[0]<sample_num
                        # go to next loop
                        pass
                    cx, cy, w, h, theta = ransac_data
                    

                    ocx = center_x - cx
                    ocy = center_y - cy
                    print(ocx, ocy)
                    out_x, out_y = cal_osc(self, ocx, ocy)
                    cx, cy, w, h = int(cx), int(cy), int(w), int(h)
                    cv2.circle(self.current_image_gray, (cx, cy), 2, (0, 0, 255), -1)
                    # cx1, cy1, w1, h1, theta1 = fit_rotated_ellipse(maxcnt.reshape(-1, 2))
                    cv2.ellipse(self.current_image_gray, (cx, cy), (w, h), theta * 180.0 / np.pi, 0.0, 360.0, (50, 250, 200), 1, ) 
                    self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False)) 
                except:
                    pass
                #self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSF, 0, 0, 0, False))
            except:
                try:
                    if self.settings.gui_BLINK: #tbh this is redundant, the algo already has blink detection built in
                        self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, self.blinkvalue))
                    else:
                        self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False))
                    f = False
                except:
                    pass













    def RANSAC3D(self): 
        f = False
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        thresh_add = 10
        rng = np.random.default_rng()
        
        f = False
        self.capture_crop_rotate_image()
        
        # Convert the image to grayscale, and set up thresholding. Thresholds here are basically a
        # low-pass filter that will set any pixel < the threshold value to 0. Thresholding is user
        # configurable in this utility as we're dealing with variable lighting amounts/placement, as
        # well as camera positioning and lensing. Therefore everyone's cutoff may be different.
        #
        # The goal of thresholding settings is to make sure we can ONLY see the pupil. This is why we
        # crop the image earlier; it gives us less possible dark area to get confused about in the
        # next step.

        if self.config.gui_circular_crop == True:
            if self.cct == 0:
                try:
                    ht, wd = self.current_image_gray.shape[:2]
                    radius = int(float(self.lkg_projected_sphere["axes"][0]))
                    self.xc = int(float(self.lkg_projected_sphere["center"][0]))
                    self.yc = int(float(self.lkg_projected_sphere["center"][1]))
                    # draw filled circle in white on black background as mask
                    mask = np.zeros((ht, wd), dtype=np.uint8)
                    mask = cv2.circle(mask, (self.xc, self.yc), radius, 255, -1)
                    # create white colored background
                    color = np.full_like(self.current_image_gray, (255))
                    # apply mask to image
                    masked_img = cv2.bitwise_and(self.current_image_gray, self.current_image_gray, mask=mask)
                    # apply inverse mask to colored image
                    masked_color = cv2.bitwise_and(color, color, mask=255 - mask)
                    # combine the two masked images
                    self.current_image_gray = cv2.add(masked_img, masked_color)
                except:
                    pass
            else:
                self.cct = self.cct - 1
        else:
            self.cct = 300

       
        # Crop first to reduce the amount of data to process.
        newFrame2 = self.current_image_gray.copy()
        frame = self.current_image_gray
        # For measuring processing time of image processing
        # Crop first to reduce the amount of data to process.
        frame = frame[0:len(frame) - 5, :]
        # To reduce the processing data, first convert to 1-channel and then blur.
        # The processing results were the same when I swapped the order of blurring and 1-channelization.
        frame_gray = cv2.GaussianBlur(frame, (5, 5), 0)
    
       
        # this will need to be adjusted everytime hardware is changed (brightness of IR, Camera postion, etc)m
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(frame_gray)
        
        maxloc0_hf, maxloc1_hf = int(0.5 * max_loc[0]), int(0.5 * max_loc[1])
        
        # crop 15% sqare around min_loc
       # frame_gray = frame_gray[max_loc[1] - maxloc1_hf:max_loc[1] + maxloc1_hf,
         #               max_loc[0] - maxloc0_hf:max_loc[0] + maxloc0_hf]
        
        threshold_value = min_val + thresh_add
        _, thresh = cv2.threshold(frame_gray, threshold_value, 255, cv2.THRESH_BINARY)
        try:
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
            th_frame = 255 - closing
        except:
            # I want to eliminate try here because try tends to be slow in execution.
            th_frame = 255 - frame_gray

        
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
            out_x, out_y = cal_osc(self, cx, cy)
            # print(cx, cy)
            cx, cy, w, h = int(cx), int(cy), int(w), int(h)
            # once a pupil is found, crop 100x100 around it
            x1 = cx - 50
            x2 = cx + 50
            y1 = cy - 50
            y2 = cy + 50
            cropped_image = newFrame2[y1:y2, x1:x2]
            
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
            result_2d_final["ellipse"] = result_2d
            result_2d_final["diameter"] = w
            result_2d_final["location"] = (cx, cy)
            result_2d_final["confidence"] = 0.99
            result_2d_final["timestamp"] = self.current_frame_number / self.current_fps
            # Black magic happens here, but after this we have our reprojected pupil/eye, and all we had
            # to do was sell our soul to satan and/or C++.
            
            result_3d = self.detector_3d.update_and_detect(
                result_2d_final, self.current_image_gray
            )
            
            # Now we have our pupil
            ellipse_3d = result_3d["ellipse"]
            # And our eyeball that the pupil is on the surface of
            self.lkg_projected_sphere = result_3d["projected_sphere"]

            # Record our pupil center
            exm = ellipse_3d["center"][0]
            eym = ellipse_3d["center"][1]

            d = result_3d["diameter_3d"]

        except:
            f = True
        # Draw our image and stack it for visual output
        try:
            cv2.drawContours(self.current_image_gray, contours, -1, (255, 0, 0), 1)
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
                self.current_image_gray,
                tuple(int(v) for v in self.lkg_projected_sphere["center"]),
                tuple(int(v) for v in self.lkg_projected_sphere["axes"]),
                self.lkg_projected_sphere["angle"],
                0,
                360,  # start/end angle for drawing
                (0, 255, 0),  # color (BGR): red
            )

            # draw line from center of eyeball to center of pupil
           # cv2.line(
             #   self.current_image_gray,
            #    tuple(int(v) for v in self.lkg_projected_sphere["center"]),
             #   tuple(int(v) for v in ellipse_3d["center"]),
              #  (0, 255, 0),  # color (BGR): red
           # )
        
        except:
            pass
        
        try:
            if self.settings.gui_BLINK:
                self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, out_x, out_y, 0, self.blinkvalue))
            else:
                self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, out_x, out_y, 0, False))
            f = False
        except:
            if self.settings.gui_BLINK:
                self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, 0, 0, 0, self.blinkvalue))
            else:
                self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, 0, 0, 0, True))
            f = True
            pass
        # Shove a concatenated image out to the main GUI thread for rendering
        #self.output_images_and_update(thresh, EyeInformation(InformationOrigin.FAILURE, 0 ,0, 0, False))
        #self.output_images_and_update(thresh, output_info)
        #except:
       # self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, out_x, out_y, 0, self.blinkvalue))
        return f



    def BLINK(self): 

        intensity = np.sum(self.current_image_gray)
        self.frames = self.frames + 1

        if intensity > self.max_int:
            self.max_int = intensity 
            if self.frames > 200: 
                self.max_ints.append(self.max_int)
        if intensity < self.min_int:
            self.min_int = intensity

        if len(self.max_ints) > 1:
            if intensity > min(self.max_ints):
                print("Blink")
                self.blinkvalue = True
            else:
                self.blinkvalue = False
        print(self.blinkvalue)


    def run(self):

        cvparam = CvParameters(self.default_radius, self.default_step)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        thresh_add = 10
        rng = np.random.default_rng()

        f = True
        while True:
           # f = True
             # Check to make sure we haven't been requested to close
            if self.cancellation_event.is_set():
                print("\033[94m[INFO] Exiting Tracking thread\033[0m")
                return

            if self.config.roi_window_w <= 0 or self.config.roi_window_h <= 0:
                # At this point, we're waiting for the user to set up the ROI window in the GUI.
                # Sleep a bit while we wait.
                if self.cancellation_event.wait(0.1):
                    return
                continue


            
            # If our ROI configuration has changed, reset our model and detector
            if (self.camera_model is None
                or self.detector_3d is None
                or self.camera_model.resolution != (
                    self.config.roi_window_w,
                    self.config.roi_window_h,
                )
            ):
                self.camera_model = CameraModel(
                    focal_length=self.config.focal_length,
                    resolution=(self.config.roi_window_w, self.config.roi_window_h),
                )
                self.detector_3d = Detector3D(
                    camera=self.camera_model, long_term_mode=DetectorMode.blocking
                )

            try:
                if self.capture_queue_incoming.empty():
                    self.capture_event.set()
                # Wait a bit for images here. If we don't get one, just try again.
                (
                    self.current_image,
                    self.current_frame_number,
                    self.current_fps,
                ) = self.capture_queue_incoming.get(block=True, timeout=0.2)
            except queue.Empty:
                # print("No image available")
                continue
            
            if not self.capture_crop_rotate_image():
                continue

            self.current_image_gray = cv2.cvtColor(
            self.current_image, cv2.COLOR_BGR2GRAY
            )
           # print(self.settings.gui_RANSAC3D)
            
            """try: 
                if self.settings.gui_RANSAC3D == True: #for now ransac goes first
                    f == self.RANSAC3D()
                    
                if f and self.settings.gui_HSF == True: #if a fail has been reported and other algo is enabled, use it.
                    f == self.HSF()
                if f and self.settings.gui_BLOB == True:
                    f == self.BLOB()
                
            except:
                pass
                
             """   #print("[WARN] ALL ALGORITHIMS HAVE FAILED OR ARE DISABLED.")
            self.RANSAC3D()
            #self.BLINK()
           # self.HSF()
           # f == self.RANSAC3D()'''
           
        #FLOW MOCK

        #if PYE3D
        #RUN PYE
        #receive values, if fail reported, go to next method

        #IF HSF
        #RUN HSF
        #receive values, if fail reported, go to next method

        #IF BLOB
        #RUN BLOB (ew tbh)
        #receive values, if fail reported, end here in complete fail.





        
