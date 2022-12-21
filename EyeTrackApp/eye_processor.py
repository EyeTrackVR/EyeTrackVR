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
RANSAC 3D By: Summer#2406 (Main Algorithm Engineer), Pupil Labs (pye3d)
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
    print("BEFORE", out_x, out_y, float(cx), float(cy), self.xoff, self.yoff)
    #try:
    noisy_point = np.array([float(out_x), float(out_y)])  # fliter our values with a One Euro Filter
    point_hat = self.one_euro_filter(noisy_point)
    out_x = point_hat[0]
    out_y = point_hat[1]
  #  print("AFTER", out_x, out_y, float(cx), float(cy), self.xoff, self.yoff)
    #except:
     #   pass
    return out_x, out_y






#HSF \/
# cache param
lru_maxsize_vvs = 16
lru_maxsize_vs = 64
lru_maxsize_s = 512
lru_maxsize_m = 1024
lru_maxsize_l = 2048  # For functions with a large number of calls and a small amount of output data
lru_maxsize_vl = 4096  # 8192 #For functions with a very large number of calls and a small amount of output data
response_list = []


@lru_cache(maxsize=lru_maxsize_vs)
def _step2byte(iterable, itemsize):
    """
    https://github.com/chainer/chainer/blob/a8e15cbe55a90854a3918b8b5a976abbbff9ec94/chainer/functions/array/as_strided.py#L125
    :param iterable:
    :param itemsize:
    :return:
    """
    return tuple([i * itemsize for i in iterable])


@lru_cache(maxsize=lru_maxsize_vs)
def _min_index(shape, strides, storage_offset):
    """
    https://github.com/chainer/chainer/blob/a8e15cbe55a90854a3918b8b5a976abbbff9ec94/chainer/functions/array/as_strided.py#L125
    Returns the leftest index in the array (in the unit-steps)
    Args:
        shape (tuple of int): The shape of output.
        strides (tuple of int):
            The strides of output, given in the unit of steps.
        storage_offset (int):
            The offset between the head of allocated memory and the pointer of
            first element, given in the unit of steps.
    Returns:
        int: The leftest pointer in the array
    """
    sh_st_neg = [sh_st for sh_st in zip(shape, strides) if sh_st[1] < 0]
    if not sh_st_neg:
        return storage_offset
    else:
        return storage_offset + functools.reduce(
            lambda base, sh_st: base + (sh_st[0] - 1) * sh_st[1], sh_st_neg, 0)


@lru_cache(maxsize=lru_maxsize_vs)
def _max_index(shape, strides, storage_offset):
    """
    https://github.com/chainer/chainer/blob/a8e15cbe55a90854a3918b8b5a976abbbff9ec94/chainer/functions/array/as_strided.py#L125
    Returns the rightest index in the array
    Args:
        shape (tuple of int): The shape of output.
        strides (tuple of int): The strides of output, given in unit-steps.
        storage_offset (int):
            The offset between the head of allocated memory and the pointer of
            first element, given in the unit of steps.
    Returns:
        int: The rightest pointer in the array
    """
    sh_st_pos = [sh_st for sh_st in zip(shape, strides) if sh_st[1] > 0]
    if not sh_st_pos:
        return storage_offset
    else:
        return storage_offset + functools.reduce(
            lambda base, sh_st: base + (sh_st[0] - 1) * sh_st[1], sh_st_pos, 0)

def _get_base_array(array):
    """
    https://github.com/chainer/chainer/blob/a8e15cbe55a90854a3918b8b5a976abbbff9ec94/chainer/functions/array/as_strided.py#L125
    Get the founder of :class:`numpy.ndarray`.
    Args:
        array (:class:`numpy.ndarray`):
            The view of the base array.
    Returns:
        :class:`numpy.ndarray`:
            The base array.
    """
    base_array_candidate = array
    while base_array_candidate.base is not None:
        base_array_candidate = base_array_candidate.base
    return base_array_candidate


def _stride_array(array, shape, strides, storage_offset):
    """
    https://github.com/chainer/chainer/blob/a8e15cbe55a90854a3918b8b5a976abbbff9ec94/chainer/functions/array/as_strided.py#L125
    Wrapper of :func:`numpy.lib.stride_tricks.as_strided`.
    .. note:
        ``strides`` and ``storage_offset`` is given in the unit of steps
        instead the unit of bytes. This specification differs from that of
        :func:`numpy.lib.stride_tricks.as_strided`.
    Args:
        array (:class:`numpy.ndarray` of :class:`cupy.ndarray`):
            The base array for the returned view.
        shape (tuple of int):
            The shape of the returned view.
        strides (tuple of int):
            The strides of the returned view, given in the unit of steps.
        storage_offset (int):
            The offset from the leftest pointer of allocated memory to
            the first element of returned view, given in the unit of steps.
    Returns:
        :class:`numpy.ndarray` or :class:`cupy.ndarray`:
            The new view for the base array.
    """
    
    min_index = _min_index(shape, strides, storage_offset)
    max_index = _max_index(shape, strides, storage_offset)
    
    strides = _step2byte(strides, array.itemsize)
    storage_offset, = _step2byte((storage_offset,), array.itemsize)
    
    if min_index < 0:
        raise ValueError('Out of buffer: too small index was specified')
    
    base_array = _get_base_array(array)
    if (max_index + 1) * base_array.itemsize > base_array.nbytes:
        raise ValueError('Out of buffer: too large index was specified')
    
    return np.ndarray(shape, base_array.dtype, base_array.data,
                    storage_offset, strides)


# From functools
_CacheInfo2 = namedtuple("CacheInfo", ["hits", "misses", "maxsize", "currsize"])

class _HashedSeq2(list):
    """ This class guarantees that hash() will be called no more than once
        per element.  This is important because the lru_cache() will hash
        the key multiple times on a cache miss.

    """
    
    __slots__ = 'hashvalue'
    
    def __init__(self, tup, hash=hash):
        self[:] = tup
        self.hashvalue = hash(tup)
    
    def __hash__(self):
        return self.hashvalue


def _make_key2(args, kwds, typed,
            kwd_mark=(object(),),
            fasttypes={int, str},
            tuple=tuple, type=type, len=len):
    """Make a cache key from optionally typed positional and keyword arguments

    The key is constructed in a way that is flat as possible rather than
    as a nested structure that would take more memory.

    If there is only a single argument and its data type is known to cache
    its hash value, then that argument is returned without a wrapper.  This
    saves space and improves lookup speed.

    """
    # All of code below relies on kwds preserving the order input by the user.
    # Formerly, we sorted() the kwds before looping.  The new way is *much*
    # faster; however, it means that f(x=1, y=2) will now be treated as a
    # distinct call from f(y=2, x=1) which will be cached separately.
    key = args
    if kwds:
        key += kwd_mark
        for item in kwds.items():
            key += item
    key = tuple(xxhash.xxh3_128_intdigest(k) if isinstance(k, np.ndarray) else k for k in key)
    if typed:
        key += tuple(type(v) for v in args)
        if kwds:
            key += tuple(type(v) for v in kwds.values())
    elif len(key) == 1 and type(key[0]) in fasttypes:
        return key[0]
    return _HashedSeq2(key)



def np_lru_cache(maxsize=128, typed=False):
    """Least-recently-used cache decorator.

    If *maxsize* is set to None, the LRU features are disabled and the cache
    can grow without bound.

    If *typed* is True, arguments of different types will be cached separately.
    For example, f(3.0) and f(3) will be treated as distinct calls with
    distinct results.

    Arguments to the cached function must be hashable.

    View the cache statistics named tuple (hits, misses, maxsize, currsize)
    with f.cache_info().  Clear the cache and statistics with f.cache_clear().
    Access the underlying function with f.__wrapped__.

    See:  https://en.wikipedia.org/wiki/Cache_replacement_policies#Least_recently_used_(LRU)

    """
    
    # Users should only access the lru_cache through its public API:
    #       cache_info, cache_clear, and f.__wrapped__
    # The internals of the lru_cache are encapsulated for thread safety and
    # to allow the implementation to change (including a possible C version).
    
    if isinstance(maxsize, int):
        # Negative maxsize is treated as 0
        if maxsize < 0:
            maxsize = 0
    elif callable(maxsize) and isinstance(typed, bool):
        # The user_function was passed in directly via the maxsize argument
        user_function, maxsize = maxsize, 128
        wrapper = _np_lru_cache_wrapper(user_function, maxsize, typed, _CacheInfo2)
        wrapper.cache_parameters = lambda: {'maxsize': maxsize, 'typed': typed}
        return functools.update_wrapper(wrapper, user_function)
    elif maxsize is not None:
        raise TypeError(
            'Expected first argument to be an integer, a callable, or None')
    
    def decorating_function(user_function):
        wrapper = _np_lru_cache_wrapper(user_function, maxsize, typed, _CacheInfo2)
        wrapper.cache_parameters = lambda: {'maxsize': maxsize, 'typed': typed}
        return functools.update_wrapper(wrapper, user_function)
    
    return decorating_function



def _np_lru_cache_wrapper(user_function, maxsize, typed, _CacheInfo):
    # Constants shared by all lru cache instances:
    sentinel = object()  # unique object used to signal cache misses
    make_key = _make_key2  # build a key from the function arguments
    PREV, NEXT, KEY, RESULT = 0, 1, 2, 3  # names for the link fields
    
    cache = {}
    hits = misses = 0
    full = False
    cache_get = cache.get  # bound method to lookup a key or return None
    cache_len = cache.__len__  # get cache size without calling len()
    lock = _thread.RLock()  # because linkedlist updates aren't threadsafe
    root = []  # root of the circular doubly linked list
    root[:] = [root, root, None, None]  # initialize by pointing to self
    
    if maxsize == 0:
        
        def wrapper(*args, **kwds):
            # No caching -- just a statistics update
            nonlocal misses
            misses += 1
            result = user_function(*args, **kwds)
            return result
    
    elif maxsize is None:
        
        def wrapper(*args, **kwds):
            # Simple caching without ordering or size limit
            nonlocal hits, misses
            key = make_key(args, kwds, typed)
            result = cache_get(key, sentinel)
            if result is not sentinel:
                hits += 1
                return result
            misses += 1
            result = user_function(*args, **kwds)
            cache[key] = result
            return result
    
    else:
        
        def wrapper(*args, **kwds):
            # Size limited caching that tracks accesses by recency
            nonlocal root, hits, misses, full
            key = make_key(args, kwds, typed)
            with lock:
                link = cache_get(key)
                if link is not None:
                    # Move the link to the front of the circular queue
                    link_prev, link_next, _key, result = link
                    link_prev[NEXT] = link_next
                    link_next[PREV] = link_prev
                    last = root[PREV]
                    last[NEXT] = root[PREV] = link
                    link[PREV] = last
                    link[NEXT] = root
                    hits += 1
                    return result
                misses += 1
            result = user_function(*args, **kwds)
            with lock:
                if key in cache:
                    # Getting here means that this same key was added to the
                    # cache while the lock was released.  Since the link
                    # update is already done, we need only return the
                    # computed result and update the count of misses.
                    pass
                elif full:
                    # Use the old root to store the new key and result.
                    oldroot = root
                    oldroot[KEY] = key
                    oldroot[RESULT] = result
                    # Empty the oldest link and make it the new root.
                    # Keep a reference to the old key and old result to
                    # prevent their ref counts from going to zero during the
                    # update. That will prevent potentially arbitrary object
                    # clean-up code (i.e. __del__) from running while we're
                    # still adjusting the links.
                    root = oldroot[NEXT]
                    oldkey = root[KEY]
                    oldresult = root[RESULT]
                    root[KEY] = root[RESULT] = None
                    # Now update the cache dictionary.
                    del cache[oldkey]
                    # Save the potentially reentrant cache[key] assignment
                    # for last, after the root and links have been put in
                    # a consistent state.
                    cache[key] = oldroot
                else:
                    # Put result in a new link at the front of the queue.
                    last = root[PREV]
                    link = [last, root, key, result]
                    last[NEXT] = root[PREV] = cache[key] = link
                    # Use the cache_len bound method instead of the len() function
                    # which could potentially be wrapped in an lru_cache itself.
                    full = (cache_len() >= maxsize)
            return result
    
    def cache_info():
        """Report cache statistics"""
        with lock:
            return _CacheInfo(hits, misses, maxsize, cache_len())
    
    def cache_clear():
        """Clear the cache and cache statistics"""
        nonlocal hits, misses, full
        with lock:
            cache.clear()
            root[:] = [root, root, None, None]
            hits = misses = 0
            full = False
    
    wrapper.cache_info = cache_info
    wrapper.cache_clear = cache_clear
    return wrapper


class CvParameters:
    # It may be a little slower because a dict named "self" is read for each function call.
    def __init__(self, radius, step):
        # self.prev_radius=radius
        self._radius = radius
        self.pad = 2 * radius
        # self.prev_step=step
        self._step = step
        self._hsf = HaarSurroundFeature(radius)
        # self._imagesize = None
    
    # @lru_cache(maxsize=lru_maxsize_vs)
    def get_rpsh(self):
        return self.radius, self.pad, self.step, self.hsf
    
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
    frame_len = len(frame.shape)
    if frame_len == 2:
        return frame
    if frame_len == 3:
        frame_s2 = frame.shape[2]
        if frame_s2 == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif frame_s2 == 4:
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    raise ValueError('Unsupported number of channels')


@lru_cache(maxsize=lru_maxsize_vs)
def frameint_get_xy_step(imageshape, xysteps, pad, start_offset=None, end_offset=None):
    """

    :param imageshape: (height(row),width(col),channel) or (height(row),width(col)). row==y,cal==x
    :param xysteps: (x,y)
    :param pad: int
    :param start_offset: (x,y) or None
    :param end_offset: (x,y) or None
    :return: xy_np:tuple(x,y), xy_min:tuple(x,y), xy_rin_pm:tuple(x+rin,y+rin,x-rin,y-rin), xy_rout_pm:tuple(x+rout,y+rout,x-rout,y-rout)
    """
    if len(imageshape) == 2:
        row, col = imageshape
    else:
        row, col = imageshape[0], imageshape[1]
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
def get_emp_p_array(len_sxy, frameint_x, frame_int_dtype, fcshape):
    len_sx, len_sy = len_sxy
    inner_sum = np.empty((len_sy, len_sx), dtype=frame_int_dtype)
    outer_sum = np.empty((len_sy, len_sx), dtype=frame_int_dtype)
    p_temp = np.empty((len_sy, frameint_x), dtype=frame_int_dtype)
    p00 = np.empty((len_sy, len_sx), dtype=frame_int_dtype)
    p11 = np.empty((len_sy, len_sx), dtype=frame_int_dtype)
    p01 = np.empty((len_sy, len_sx), dtype=frame_int_dtype)
    p10 = np.empty((len_sy, len_sx), dtype=frame_int_dtype)
    response_list = np.empty((len_sy, len_sx), dtype=np.float64)
    frame_conv = np.zeros(shape=fcshape[0], dtype=np.uint8)
    frame_conv_stride = _stride_array(frame_conv, shape=(len_sy, len_sx), strides=(fcshape[1], fcshape[2]),
                                    storage_offset=0)
    return (inner_sum, outer_sum), p_temp, (
        p00, p11, p01, p10), response_list, (frame_conv, frame_conv_stride)


# @profile
def conv_int(frame_int, kernel, step, padding, xy_step):
    """

    :param frame_int:
    :param kernel: hsf
    :param step: (x,y)
    :param padding: int
    :return:
    """
    # Init
    row_b, col_b = frame_int.shape
    row, col = row_b, col_b
    row -= 1
    col -= 1
    x_step, y_step = step
    padding2 = 2 * padding
    f_shape = row - padding2, col - padding2
    r_in = kernel.r_in
    r_in3 = r_in * 3
    
    len_sx, len_sy = len(xy_step[0]), len(xy_step[1])
    col_rin = col_b * kernel.r_in
    col_padrin = col_b * (padding + r_in)
    col_ystep = col_b * y_step
    
    inout_sum, p_temp, p_list, response_list, frameconvlist = get_emp_p_array((len_sx, len_sy), col_b,
                                                                            frame_int.dtype, (f_shape, f_shape[1] * y_step, x_step))
    inner_sum, outer_sum = inout_sum
    p00, p11, p01, p10 = p_list
    frame_conv, frame_conv_stride = frameconvlist
    
    inarr_mm = _stride_array(frame_int, shape=(len_sy, len_sx), strides=(col_ystep, x_step), storage_offset=col_rin + r_in)
    inarr_mp = _stride_array(frame_int, shape=(len_sy, len_sx), strides=(col_ystep, x_step), storage_offset=col_rin + r_in3)
    inarr_pm = _stride_array(frame_int, shape=(len_sy, len_sx), strides=(col_ystep, x_step), storage_offset=(col_padrin + r_in))
    inarr_pp = _stride_array(frame_int, shape=(len_sy, len_sx), strides=(col_ystep, x_step), storage_offset=(col_padrin + r_in3))
    
    # inner_sum[:, :] = inarr_mm + inarr_pp - inarr_mp - inarr_pm
    inner_sum[:, :] = inarr_mm
    inner_sum += inarr_pp
    inner_sum -= inarr_mp
    inner_sum -= inarr_pm
    
    y_ro_m = xy_step[1] - kernel.r_out
    x_ro_m = xy_step[0] - kernel.r_out
    y_ro_p = xy_step[1] + kernel.r_out
    x_ro_p = xy_step[0] + kernel.r_out
    
    # y,x
    # p00=max(y_ro_m,0),max(x_ro_m,0)
    # p11=min(y_ro_p,ylim),min(x_ro_p,xlim)
    # p01=max(y_ro_m,0),min(x_ro_p,xlim)
    # p10=min(y_ro_p,ylim),max(x_ro_m,0)
    
    # Bottleneck here, I want to make it smarter. Someone do it.
    # p00 calc
    np.take(frame_int, y_ro_m, axis=0, mode="clip", out=p_temp)
    np.take(p_temp, x_ro_m, axis=1, mode="clip", out=p00)
    
    # p01 calc
    np.take(p_temp, x_ro_p, axis=1, mode="clip", out=p01)
    
    # p11 calc
    np.take(frame_int, y_ro_p, axis=0, mode="clip", out=p_temp)
    np.take(p_temp, x_ro_p, axis=1, mode="clip", out=p11)
    
    # p10 calk
    np.take(p_temp, x_ro_m, axis=1, mode="clip", out=p10)
    
    # p00=np.take(np.take(frame_int, y_ro_m, axis=0, mode="clip"), x_ro_m, axis=1, mode="clip")
    # p11=np.take(np.take(frame_int, y_ro_p, axis=0, mode="clip"), x_ro_p, axis=1, mode="clip")
    # p01=np.take(np.take(frame_int, y_ro_m, axis=0, mode="clip"), x_ro_p, axis=1, mode="clip")
    # p10=np.take(np.take(frame_int, y_ro_p, axis=0, mode="clip"), x_ro_m, axis=1, mode="clip")
    
    outer_sum[:, :] = p00 + p11 - p01 - p10 - inner_sum
    
    np.multiply(kernel.val_in, inner_sum, dtype=np.float64, out=response_list)
    response_list += kernel.val_out * outer_sum
    
    # min_response, max_val, min_loc, max_loc = cv2.minMaxLoc(response_list)
    min_response, _, min_loc, _ = cv2.minMaxLoc(response_list)
    
    center = ((xy_step[0][min_loc[0]] - padding), (xy_step[1][min_loc[1]] - padding))
    
    frame_conv_stride[:, :] = response_list
    # or
    # frame_conv_stride[:, :] = response_list.astype(np.uint8)
    
    return frame_conv, min_response, center





def fit_rotated_ellipse_ransac(
    data, iter=5, sample_num=10, offset=80  # 80.0, 10, 80
):  # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower
    count_max = 0
    effective_sample = None

    # TODO This iteration is extremely slow.
    #
    # Either we need to keep the iteration number low, or we need to keep a worker pool specifically
    # for handling this calculation. It's parallelizable, so just throwing something like joblib at
    # it would be fine.
    for i in range(iter):
        sample = np.random.choice(len(data), sample_num, replace=False)

        xs = data[sample][:, 0].reshape(-1, 1)
        ys = data[sample][:, 1].reshape(-1, 1)

        J = np.mat(
            np.hstack((xs * ys, ys**2, xs, ys, np.ones_like(xs, dtype=np.float)))
        )
        Y = np.mat(-1 * xs**2)
        P = (J.T * J).I * J.T * Y

        # fitter a*x**2 + b*x*y + c*y**2 + d*x + e*y + f = 0
        a = 1.0
        b = P[0, 0]
        c = P[1, 0]
        d = P[2, 0]
        e = P[3, 0]
        f = P[4, 0]
        ellipse_model = (
            lambda x, y: a * x**2 + b * x * y + c * y**2 + d * x + e * y + f
        )

        # thresh
        ran_sample = np.array(
            [[x, y] for (x, y) in data if np.abs(ellipse_model(x, y)) < offset]
        )

        if len(ran_sample) > count_max:
            count_max = len(ran_sample)
            effective_sample = ran_sample

    return fit_rotated_ellipse(effective_sample)


def fit_rotated_ellipse(data):
    xs = data[:, 0].reshape(-1, 1)
    ys = data[:, 1].reshape(-1, 1)

    J = np.mat(np.hstack((xs * ys, ys**2, xs, ys, np.ones_like(xs, dtype=np.float))))
    Y = np.mat(-1 * xs**2)
    P = (J.T * J).I * J.T * Y

    a = 1.0
    b = P[0, 0]
    c = P[1, 0]
    d = P[2, 0]
    e = P[3, 0]
    f = P[4, 0]
    theta = 0.5 * np.arctan(b / (a - c))

    cx = (2 * c * d - b * e) / (b**2 - 4 * a * c)
    cy = (2 * a * e - b * d) / (b**2 - 4 * a * c)

    cu = a * cx**2 + b * cx * cy + c * cy**2 - f
    w = np.sqrt(
        cu
        / (
            a * np.cos(theta)**2
            + b * np.cos(theta) * np.sin(theta)
            + c * np.sin(theta)**2
        )
    )
    h = np.sqrt(
        cu
        / (
            a * np.sin(theta)**2
            - b * np.cos(theta) * np.sin(theta)
            + c * np.cos(theta)**2
        )
    )

    ellipse_model = lambda x, y: a * x**2 + b * x * y + c * y**2 + d * x + e * y + f

    error_sum = np.sum([ellipse_model(x, y) for x, y in data])

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
        self.response_list = []
         #HSF
        
        
        self.cv_mode = ["first_frame", "radius_adjust", "init", "normal"]
        self.now_mode = self.cv_mode[0]
        self.default_radius = 20
        self.default_step = (5, 5)  # bigger the steps,lower the processing time! ofc acc also takes an impact
        # default_step==(x,y)
        self.radius_cand_list = []
        self.prev_max_size = 60 * 3  # 60fps*3sec
        # response_min=0
        self.response_max = 0
        

        

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
            self.output_images_and_update(larger_threshold, EyeInformation(InformationOrigin.BLOB, out_x, out_y, 0, False))

            self.output_images_and_update(
                larger_threshold,
                EyeInformation(InformationOrigin.BLOB, out_x, out_y, 0, False),
            )
            return
        self.output_images_and_update(
            larger_threshold, EyeInformation(InformationOrigin.BLOB, 0, 0, 0, True)
        )
        print("[INFO] BLINK Detected.")

    

    def HSF(self):
        
        if self.now_mode == self.cv_mode[1]:
            prev_res_len = len(self.response_list)
            # adjustment of radius
            if prev_res_len == 1:
                self.cvparam.radius = self.radius_range[0]
            elif prev_res_len == 2:
                self.cvparam.radius = self.radius_range[1]
            elif prev_res_len == 3:
                # response_list==[default_radius,self.radius_range[0],self.radius_range[1]]
                sort_res = sorted(self.response_list, key=lambda x: x[1])[0]
                if sort_res[0] == self.default_radius:
                    self.cvparam.radius = self.default_radius
                    self.now_mode = self.cv_mode[2]
                    response_list = []
                elif sort_res[0] == self.radius_range[0]:
                    self.radius_cand_list = [i for i in range(self.radius_range[0], self.default_radius, self.default_step[0])][1:]
                    self.cvparam.radius = self.radius_cand_list.pop()
                else:
                    self.radius_cand_list = [i for i in range(self.default_radius, self.radius_range[1], self.default_step[0])][1:]
                    self.cvparam.radius = self.radius_cand_list.pop()
            else:
                # Better make it a binary search.
                if len(self.radius_cand_list) == 0:
                    sort_res = sorted(self.response_list, key=lambda x: x[1])[0]
                    self.cvparam.radius = sort_res[0]
                    self.now_mode = self.cv_mode[2]
                    self.response_list = []
                else:
                    self.cvparam.radius = self.radius_cand_list.pop()

        radius, pad, step, hsf = self.cvparam.get_rpsh()
        
        gray_frame = to_gray(self.current_image_gray) #pretty sure we do no need this step, should already be receiving gray frame
        frame = self.current_image_gray
        # Calculate the integral image of the frame

        frame_pad = cv2.copyMakeBorder(gray_frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT)  #cv2.BORDER_REPLICATE
        frame_int = cv2.integral(frame_pad)
        
        # Convolve the feature with the integral image
        xy_step = frameint_get_xy_step(frame_int.shape, step, pad, start_offset=None, end_offset=None)
        frame_conv, response, center_xy = conv_int(frame_int, hsf, step, pad, xy_step)

        # Define the center point and radius
        # center_y, center_x = center
        center_x, center_y = center_xy
        upper_x = center_x + radius
        lower_x = center_x - radius
        upper_y = center_y + radius
        lower_y = center_y - radius
        
        # Crop the image using the calculated bounds
        # cropped_image = gray_frame[lower_x:upper_x, lower_y:upper_y]
        cropped_image = gray_frame[lower_y:upper_y, lower_x:upper_x]
        
        if self.now_mode == self.cv_mode[0] or self.now_mode == self.cv_mode[1]:
            self.response_list.append((radius, response))  # , center_x, center_y))
        elif self.now_mode == self.cv_mode[2]:
            if len(self.response_list) < self.prev_max_size:
                self.response_list.append(cropped_image.mean())
            else:
                self.response_list = np.array(self.response_list)
                # 25%,75%
                # This value may need to be adjusted depending on the environment.
                quartile_1, quartile_3 = np.percentile(self.response_list, [25, 75])
                iqr = quartile_3 - quartile_1
                # response_min = quartile_1 - (iqr * 1.5)
                self.response_max = quartile_3 + (iqr * 1.5)
                self.now_mode = self.cv_mode[3]
        else:
            if cropped_image.size < 400:
                print("Something's wrong.")
            else:
                if cropped_image.mean() > self.response_max:  # or cropped_image.mean() < response_min:
                    # blink
                    print("BLINK")
                    cv2.circle(frame, (center_x, center_y), 20, (0, 0, 255), -1)
                    self.output_images_and_update(frame,EyeInformation(InformationOrigin.HSF, 0, 0, 0, True))
        # If you want to update self.response_max. it may be more cost-effective to rewrite response_list in the following way
        # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue
        
       
        out_x, out_y = cal_osc(self, center_x, center_y)
        
        cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), -1)
       # print(center_x, center_y)
        self.output_images_and_update(frame,EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False))
            
        if self.now_mode != self.cv_mode[0] and self.now_mode != self.cv_mode[1]:
            if cropped_image.size < 400:
                pass
    
        if self.now_mode == self.cv_mode[0]:
            self.now_mode = self.cv_mode[1]

            #self.output_images_and_update(thresh, EyeInformation(InformationOrigin.FAILURE, 0, 0, 0, False))
           # return

        #self.output_images_and_update(larger_threshold,EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False),)
       # return
        #self.output_images_and_update(larger_threshold, EyeInformation(InformationOrigin.HSF, 0, 0, 0, True))

    def RANSAC3D(self): 
        
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

        _, thresh = cv2.threshold(
            self.current_image_gray,
            int(self.config.threshold),
            255,
            cv2.THRESH_BINARY,
        )
        
        # Set up morphological transforms, for smoothing and clearing the image we get out of the
        # thresholding operation. After this, we'd really like to just have a black blob in the middle
        # of a bunch of white area.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
        image = 255 - closing

        # Now that the image is relatively clean, run contour finding in order to get us our pupil
        # boundaries in the 2D context. Ideally, we just get one border.
        contours, _ = cv2.findContours(image, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

        # Find the convex shape based on each contour, and sort the list of them from smallest to
        # largest area.
        convex_hulls = []
        for i in range(len(contours)):
            convex_hulls.append(cv2.convexHull(contours[i], False))

        # If we have no convex maidens, we have no pupil, and can't progress from here. Dump back to
        # using blob tracking.
        if len(convex_hulls) == 0:
            pass
        
        # Find our largest hull, which we expect will probably be the ellipse that represents the 2d
        # area for the pupil, which we can use as the search area for the eye in general.
        largest_hull = sorted(convex_hulls, key=cv2.contourArea)[-1]
        
        # However eyes are annoyingly three dimensional, so we need to take this ellipse and turn it
        # into a curve patch on the surface of a sphere (the eye itself). If it's not a sphere, see your
        # ophthalmologist about possible issues with astigmatism.
        try:
            cx, cy, w, h, theta = fit_rotated_ellipse_ransac(
                largest_hull.reshape(-1, 2)
            )

        
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
            
            out_x, out_y = cal_osc(self, cx, cy) #filter and calibrate values

        except:
            f = True
        # Draw our image and stack it for visual output
        try:
            cv2.drawContours(self.current_image_gray, contours, -1, (255, 0, 0), 1)
            cv2.circle(self.current_image_gray, (int(cx), int(cy)), 2, (0, 0, 255), -1)
        except:
            pass

        try:
            cv2.ellipse(
                self.current_image_gray,
                tuple(int(v) for v in ellipse_3d["center"]),
                tuple(int(v) for v in ellipse_3d["axes"]),
                ellipse_3d["angle"],
                0,
                360,  # start/end angle for drawing
                (0, 255, 0),  # color (BGR): red
            )
        except Exception:
            # Sometimes we get bogus axes and trying to draw this throws. Ideally we should check for
            # validity beforehand, but for now just pass. It usually fixes itself on the next frame.
            pass

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
            cv2.line(
                self.current_image_gray,
                tuple(int(v) for v in self.lkg_projected_sphere["center"]),
                tuple(int(v) for v in ellipse_3d["center"]),
                (0, 255, 0),  # color (BGR): red
            )
        except:
            pass

        self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, out_x, out_y, 0, False))
        # Shove a concatenated image out to the main GUI thread for rendering
        #self.output_images_and_update(thresh, EyeInformation(InformationOrigin.FAILURE, 0 ,0, 0, False))
        #self.output_images_and_update(thresh, output_info)
        #except:
        return f


    def run(self):
        f = None

        self.radius_range = (self.default_radius - 10, self.default_radius + 10)  # (10,30)
        self.cvparam = CvParameters(self.default_radius, self.default_step)

        while True:
            f = True
             # Check to make sure we haven't been requested to close
            if self.cancellation_event.is_set():
                print("Exiting Tracking thread")
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
            try: #This is flawed currently, i will come up with a better system soon
                if self.settings.gui_RANSAC3D == True: #for now ransac goes first
                    f == self.RANSAC3D()
                if  self.settings.gui_HSF == True: #if a fail has been reported and other algo is enabled, use it.
                    f == self.HSF()
                if  self.settings.gui_BLOB == True:
                    f == self.BLOB()
            except:
                pass
                print("[WARN] ALL ALGORITHIMS HAVE FAILED OR ARE DISABLED.")

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





        
