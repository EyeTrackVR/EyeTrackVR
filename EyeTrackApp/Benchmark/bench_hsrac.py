import os
import timeit
from functools import lru_cache

from logging import getLogger, Formatter, StreamHandler, FileHandler, INFO

old_mode=True#False

this_file_name = os.path.basename(__file__)
logger = getLogger(__name__)
logger.setLevel(INFO)
formatter = Formatter('%(message)s')
handler = StreamHandler()
handler.setLevel(INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)

# handler = FileHandler(f'./{this_file_name.replace(".py","")}2.log' if not old_mode else f'./{this_file_name.replace(".py","")}.log',encoding="utf8",mode="w")
# handler.setLevel(INFO)
# handler.setFormatter(formatter)
# logger.addHandler(handler)


import cv2
import numpy as np
from numpy.linalg import _umath_linalg
from EyeTrackApp.utils.time_utils import FPSResult, TimeitResult, format_time
from EyeTrackApp.haar_surround_feature import (
    AutoRadiusCalc,
    BlinkDetector,
    # CvParameters,
    # conv_int,
    # frameint_get_xy_step,
)
from EyeTrackApp.utils.img_utils import safe_crop
from EyeTrackApp.utils.misc_utils import clamp
import math
from line_profiler_pycharm import profile

# RANSAC

thresh_add = 10

# imshow_enable = True
# calc_print_enable = True
print_enable = False
save_video = False
skip_autoradius = False
skip_blink_detect = False

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


# from scipy.linalg import cho_factor, cho_solve
import scipy


# from scipy.linalg import solve

# def inv_sc(a):
#     orig_shape = a.shape
#     dim1 = int(math.sqrt(a.shape[0]))
#     # u, s, vt = scipy.linalg.svd(a.reshape((a.shape[0],a.shape[1] * a.shape[2])), full_matrices=False,compute_uv=True,overwrite_a=False, check_finite=False)
#     u, s, vt = scipy.linalg.svd(a.reshape(((a.shape[1] * dim1) + (a.shape[0] % 2), a.shape[2] * dim1)), full_matrices=False,
#                                 compute_uv=True, overwrite_a=False,
#                                 check_finite=False)
#     # rcond = np.array(1e-15)
#     # # discard small singular values
#     # cutoff = rcond[..., np.newaxis] * np.amax(s, axis=-1, keepdims=True)
#     # large = s > cutoff
#     # s = np.divide(1, s, where=large, out=s)
#     # s[~large] = 0
#
#     res = np.matmul(vt.T, s[..., np.newaxis] * u.T)
#     return res.reshape(orig_shape)


# @profile
def fit_rotated_ellipse_ransac_bad(data: np.ndarray, rng: np.random.Generator, iter=100, sample_num=10, offset=80  # 80.0, 10, 80
                                   ):  # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower
    # effective_sample = None
    
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
    # rng_sample = rng.random((iter, len_data)).argsort()[:, :sample_num]
    # or
    # I don't see any advantage to doing this.
    # rng_sample = np.asarray(rng.random((iter, len_data)).argsort()[:, :sample_num], dtype=np.int32)
    
    # I don't think it looks beautiful.
    # x,y,x**2,y**2,x*y,1,-1*x**2
    data_squared = np.square(data)
    datamod = np.empty((len(data), 7), dtype=ret_dtype)  # np.empty((len(data), 7), dtype=ret_dtype)
    datamod[:, :2] = data
    datamod[:, 2:4] = data_squared
    datamod[:, 4] = data[:, 0] * data[:, 1]
    datamod[:, 5] = 1
    datamod[:, 6] = -data_squared[:, 0]
    
    # datamod = np.concatenate(
    #     [data, data_squared, (data[:, 0] * data[:, 1])[:, np.newaxis], np.ones((len_data, 1), dtype=ret_dtype),
    #      (-data_squared[:,0])[:, np.newaxis]], axis=1,
    #     dtype=ret_dtype)
    
    # datamod_slim = datamod[:, :5]#np.array(datamod[:, :5], dtype=ret_dtype)
    #
    # datamod_rng = datamod[rng_sample]
    datamod_rng = rng.choice(datamod, (iter, sample_num), replace=True, shuffle=False)
    # datamod_rng6 = datamod_rng[:, :, 6]
    # datamod_rng_swap = datamod_rng[:, :, [4, 3, 0, 1, 5]]
    # datamod_rng_swap_trans = datamod_rng_swap.transpose((0, 2, 1))
    #
    # # These two lines are one of the bottlenecks
    # datamod_rng_5x5 = np.matmul(datamod_rng_swap_trans, datamod_rng_swap)
    # datamod_rng_p5smp = np.matmul(np.linalg.inv(datamod_rng_5x5), datamod_rng_swap_trans)
    #
    # datamod_rng_p = np.matmul(datamod_rng_p5smp, datamod_rng6[:, :, np.newaxis]).reshape((-1, 5))
    #
    # # I don't think it looks beautiful.
    # ellipse_y_arr = np.asarray(
    #     [datamod_rng_p[:, 2], datamod_rng_p[:, 3], np.ones(len(datamod_rng_p)), datamod_rng_p[:, 1], datamod_rng_p[:, 0]], dtype=ret_dtype)
    #
    # ellipse_data_arr = ellipse_model(datamod_slim, ellipse_y_arr, np.asarray(datamod_rng_p[:, 4])).transpose((1, 0))
    # ellipse_data_abs = np.abs(ellipse_data_arr)
    # ellipse_data_index = np.argmax(np.sum(ellipse_data_abs < offset, axis=1), axis=0)
    # effective_data_arr = ellipse_data_arr[ellipse_data_index]
    # effective_sample_p_arr = datamod_rng_p[ellipse_data_index]
    # datamod_rng[:, [3, 4]] = datamod_rng[:, [4, 3]]  # Swap columns 3 and 4
    
    # datamod_rng_swap = datamod_rng[..., [2, 3, 4, 1, 0, 5]]
    datamod_rng_swap = datamod_rng[:, :, [4, 3, 0, 1, 5]]
    
    # datamod_rng_5x5 = np.matmul(datamod_rng[:, :, None, :].transpose(0,1,3,2), datamod_rng[:, :, None, :]).squeeze()#np.matmul(datamod_rng[:, :, None, :].transpose(0,1,3,2), datamod_rng[:, :, :, None]).squeeze()
    # datamod_rng_5x5_inv = np.linalg.inv(datamod_rng_5x5)
    datamod_rng_swap_trans = datamod_rng_swap.transpose(0, 2, 1)
    # datamod_rng_5x5 = datamod_rng_swap_trans@datamod_rng_swap#np.matmul(datamod_rng_swap_trans, datamod_rng_swap)
    # datamod_rng_p5smp = np.matmul(np.linalg.inv(datamod_rng_5x5), datamod_rng_swap_trans)
    datamod_rng6 = datamod_rng[:, :, 6]
    # These two lines are one of the bottlenecks
    datamod_rng_5x5 = np.matmul(datamod_rng_swap_trans, datamod_rng_swap)
    datamod_rng_p5smp = np.matmul(np.linalg.inv(datamod_rng_5x5), datamod_rng_swap_trans)
    
    datamod_rng_p = np.matmul(datamod_rng_p5smp, datamod_rng6[:, :, np.newaxis]).reshape((-1, 5))
    
    # inv_sc(datamod_rng_5x5)
    # datamod_rng_p5smp = np.linalg.inv(datamod_rng_5x5) @ datamod_rng_swap_trans
    # chol = np.linalg.cholesky(datamod_rng_5x5)
    # datamod_rng_p5smp = np.linalg.solve(chol.T, np.linalg.solve(chol, datamod_rng_swap_trans))
    # Compute the Cholesky factorization of datamod_rng_5x5
    
    # datamod_rng_p5smp = solve(datamod_rng_5x5, datamod_rng_swap_trans)
    # Q, R = np.linalg.qr(datamod_rng_5x5)
    # datamod_rng_p5smp = np.matmul(Q.T, np.matmul(Q, datamod_rng_swap_trans))
    # datamod_rng_p5smp=np.linalg.solve(datamod_rng_5x5,datamod_rng_swap_trans)
    # datamod_rng_p = np.matmul(datamod_rng_5x5_inv, datamod_rng[:, :, 5])[:, :5]
    
    # datamod_rng_p=np.matmul(datamod_rng_p5smp, datamod_rng[..., 6,np.newaxis]).reshape(-1, 5)
    # datamod_rng_p=np.matmul(datamod_rng_p5smp, datamod_rng[..., 6, np.newaxis])[:, :5].reshape((-1, 5))
    ellipse_y_arr = np.asarray(
        [datamod_rng_p[:, 2], datamod_rng_p[:, 3], np.ones(len(datamod_rng_p), dtype=ret_dtype), datamod_rng_p[:, 1], datamod_rng_p[:, 0]],
        dtype=ret_dtype)
    ellipse_data_arr = np.dot(datamod[:, :5], ellipse_y_arr) + datamod_rng_p[:,
                                                               4]  # np.dot(datamod[:, :5], ellipse_y_arr) + datamod_rng_p[:, 4, None]
    ellipse_data_abs = np.abs(ellipse_data_arr)
    # ellipse_data_index = np.argmax(np.sum(ellipse_data_abs < offset, axis=1), axis=0)
    ellipse_data_index = np.argmax(
        cv2.reduce(cv2.threshold(ellipse_data_abs, offset, 1, cv2.THRESH_BINARY_INV)[1], 1, cv2.REDUCE_SUM).reshape(-1), axis=0)
    effective_data_arr = ellipse_data_arr[ellipse_data_index]
    effective_sample_p_arr = datamod_rng_p[ellipse_data_index]
    return fit_rotated_ellipse2(effective_data_arr, effective_sample_p_arr)


# @profile
def fit_rotated_ellipse2(data, P):
    a = 1.0
    b, c, d, e, f = P[:5]
    # The cost of trigonometric functions is high.
    # theta = 0.5 * np.arctan(b / (a - c), dtype=np.float64)
    # theta = 0.5 * np.arctan2(b, a - c, dtype=np.float64)
    theta = 0.5 * math.atan(b / (a - c))
    # theta_sin = np.sin(theta, dtype=np.float64)
    # theta_cos = np.cos(theta, dtype=np.float64)
    theta_sin = math.sin(theta)
    theta_cos = math.cos(theta)
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


def fit_rotated_ellipse3(data, P):
    # a, b, c, d, e, f = P
    a = 1.0
    b, c, d, e, f = P  # [:5]
    theta = 0.5 * math.atan2(b, a - c)
    ct, st = math.cos(theta), math.sin(theta)
    a2 = a * ct ** 2 + b * ct * st + c * st ** 2
    b2 = a * st ** 2 - b * ct * st + c * ct ** 2
    cu = a * d ** 2 + b * d * e + c * e ** 2 - f * a2 * b2
    # wh = np.sqrt(abs(cu / (a2+b2)))
    wh = [math.sqrt(abs(cu / a2)), math.sqrt(abs(cu / b2))]
    w, h = wh[0], wh[1]
    cx = (b * e - 2 * c * d) / (4 * a2 * b2 - c ** 2)
    cy = (b * d - 2 * a * e) / (4 * a2 * b2 - c ** 2)
    error_sum = np.sum(data)
    return cx, cy, w, h, theta


def fit_rotated_ellipse_ransac_base(data: np.ndarray, rng: np.random.Generator, iter=100, sample_num=10,
                                    offset=80):  # before changing these values, please read up on the ransac algorithm
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
    
    return fit_rotated_ellipse_base(effective_data_arr, effective_sample_p_arr)


# @profile
def fit_rotated_ellipse_base(data, P):
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


@lru_cache(maxsize=lru_maxsize_vs)
def get_ransac_empty_array_lendata(len_data,iter_num, sample_num):
    # Function to reduce array allocation by providing an empty array first and recycling it with lru
    use_dtype=np.float64
    datamod = np.empty((len_data, 7), dtype=use_dtype)  # np.empty((len(data), 7), dtype=ret_dtype)
    datamod[:, 5] = 1
    datamod_b=datamod[:, :5]#.T
    random_index_init_arr = np.empty((iter_num, len_data), dtype=np.uint16)
    random_index_init_arr[:, :] = np.arange(len_data, dtype=np.uint16)
    random_index = np.empty((iter_num, len_data), dtype=np.uint16)
    random_index_samplenum=random_index[:, :sample_num]
    ellipse_data_arr=np.empty((iter_num,len_data),dtype=use_dtype)
    th_abs=np.empty((iter_num,len_data),dtype=use_dtype)
    
    dm_data_view=datamod[:, :2]# = data
    dm_p2_view=datamod[:, 2:4]# = data * data
    dm_mul_view=datamod[:, 4]# = data[:, 0] * data[:, 1]
    dm_neg_view=datamod[:, 6]# = -datamod[:, 2]
    
    # return datamod,random_index_init_arr,random_index,ellipse_data_arr,th_abs
    return datamod,datamod_b,dm_data_view,dm_p2_view,dm_mul_view,dm_neg_view, random_index_init_arr, random_index,random_index_samplenum, ellipse_data_arr, th_abs

@lru_cache(maxsize=lru_maxsize_s)
def get_ransac_empty_array_iternum_samplenum(iter_num, sample_num,len_data):
    # Function to reduce array allocation by providing an empty array first and recycling it with lru
    use_dtype=np.float64
    datamod_rng=np.empty((iter_num,sample_num,7),dtype=use_dtype)
    datamod_rng_swap = np.empty((iter_num, sample_num, 5), dtype=use_dtype)
    datamod_rng_swap_trans=datamod_rng_swap.transpose((0,2,1))
    # datamod_rng_swap_trans = np.empty((iter_num, 5,sample_num), dtype=use_dtype)
    datamod_rng_5x5= np.empty((iter_num, 5,5), dtype=use_dtype)
    datamod_rng_p5smp = np.empty((iter_num, 5,sample_num), dtype=use_dtype)
    datamod_rng_p=np.empty((iter_num,5),dtype=use_dtype)
    datamod_rng_p_npaxis=datamod_rng_p[:,:,np.newaxis]
    ellipse_y_arr=np.empty((iter_num,5),dtype=use_dtype)
    ellipse_y_arr[:, 2] = 1
    swap_index=np.array([4, 3, 0, 1, 5])
    dm_brod=np.broadcast_to(datamod_rng_p[:, 4, np.newaxis], (iter_num, len_data))
    dm_rng_six=datamod_rng[:, :, 6, np.newaxis]
    dm_rng_p_24_view= datamod_rng_p[:, 2:4]
    dm_rng_p_10_view= datamod_rng_p[:, 1::-1]
    el_y_arr_2_view=ellipse_y_arr[:, :2]
    el_y_arr_3_view=ellipse_y_arr[:, 3:]
    return datamod_rng,datamod_rng_swap,datamod_rng_swap_trans,datamod_rng_5x5,datamod_rng_p5smp,datamod_rng_p,datamod_rng_p_npaxis,ellipse_y_arr,swap_index,dm_brod,dm_rng_six,dm_rng_p_24_view,dm_rng_p_10_view,el_y_arr_2_view,el_y_arr_3_view

# @profile
def fit_rotated_ellipse_ransac(data: np.ndarray, sfc: np.random.Generator, iter_num=100, sample_num=10, offset=80  # 80.0, 10, 80
                               ):  # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower
    
    # The array contents do not change during the loop, so only one call is needed.
    # They say len is faster than shape.
    # Reference url: https://stackoverflow.com/questions/35547853/what-is-faster-python3s-len-or-numpys-shape
    len_data = len(data)
    
    if len_data < sample_num:
        return None
    
    # Type of calculation result
    # ret_dtype = np.float64
    # todo:create view
    datamod_rng, datamod_rng_swap, datamod_rng_swap_trans, datamod_rng_5x5, datamod_rng_p5smp, datamod_rng_p,datamod_rng_p_npaxis, ellipse_y_arr,swap_index,dm_brod,dm_rng_six,dm_rng_p_24_view,dm_rng_p_10_view,el_y_arr_2_view,el_y_arr_3_view=get_ransac_empty_array_iternum_samplenum(iter_num,sample_num,len_data)

    datamod,datamod_b,dm_data_view,dm_p2_view,dm_mul_view,dm_neg_view,random_index_init_arr,random_index,random_index_samplenum,ellipse_data_arr,th_abs=get_ransac_empty_array_lendata(len_data,iter_num,sample_num)
    
    # Sorts a random number array of size (iter,len_data). After sorting, returns the index of sample_num random numbers before sorting.
    # If the array size is less than about 100, this is faster than rng.choice.
    # rng_sample = rng.random((iter_num, len_data),dtype=np.float32).argsort()[:, :sample_num]#out=
    # or
    # I don't see any advantage to doing this.
    # rng_sample = np.asarray(rng.random((iter, len_data)).argsort()[:, :sample_num], dtype=np.int32)
    
    # I don't think it looks beautiful.
    # x,y,x**2,y**2,x*y,1,-1*x**2
    # datamod = np.concatenate(
    #     [data, data ** 2, (data[:, 0] * data[:, 1])[:, np.newaxis], np.ones((len_data, 1), dtype=ret_dtype),
    #      (-1 * data[:, 0] ** 2)[:, np.newaxis]], axis=1,
    #     dtype=ret_dtype)
    
    # I don't think it looks beautiful.
    # x,y,x**2,y**2,x*y,1,-1*x**2
    # data_squared = np.square(data)
    # datamod = np.empty((len(data), 7), dtype=ret_dtype)  # np.empty((len(data), 7), dtype=ret_dtype)
    # datamod[:, :2] = data#[:]
    # # datamod[:, 2:4] = np.square(data) # or data**2
    # # np.square(data,out=datamod[:, 2:4])#casting,dtype
    # datamod[:, 2:4] = data * data
    # datamod[:, 4] = data[:, 0] * data[:, 1]
    # # datamod[:, 4]=data.prod(axis=1,dtype=np.float64)
    # # datamod[:, 5] = 1
    # datamod[:, 6] = -datamod[:, 2]  # -1 * data[:, 0] ** 2#
    
    dm_data_view[:, :] = data#[:]
    dm_p2_view[:,:] = data * data
    dm_mul_view[:] = data[:, 0] * data[:, 1]
    dm_neg_view[:] = -dm_p2_view[:,0] # -1 * data[:, 0] ** 2#
    
    
    
    # datamod_slim = np.array(datamod[:, :5], dtype=ret_dtype)
    #
    # datamod_rng = datamod[rng_sample]
    # datamod_rng = rng.choice(datamod, (iter, sample_num), replace=True, shuffle=False)
    # datamod_rng =  datamod[rng.choice(len_data, (iter,len_data),shuffle=False)[:,:sample_num]]
    
    # random_index = np.empty((iter_num, len_data), dtype=np.uint16)
    # random_index[:, :] = np.arange(len_data, dtype=np.uint16)
    # random_index_bro = np.broadcast_to(np.arange(len_data, dtype=np.uint16), (iter_num, len_data))
    # or
    # random_index = np.zeros(100,dtype=np.uint16).reshape((-1,1))+ np.arange(len_data, dtype=np.uint16).reshape((1, len_data))
    # sfc.permuted(random_index, axis=1, out=random_index)
    sfc.permuted(random_index_init_arr, axis=1, out=random_index)
    # random_index = sfc.permuted(np.broadcast_to(np.arange(len_data, dtype=np.uint16), (iter_num, len_data)),axis=1)
    
    # datamod_rng = datamod[random_index[:,:sample_num]]#take
    # np.take replaces a[ind,:] and is 3-4 times faster, https://gist.github.com/rossant/4645217
    # datamod_rng = np.take(datamod,random_index[:,:sample_num],axis=0)
    # datamod_rng = datamod.take(random_index[:, :sample_num], axis=0, mode="clip")# iter_num,sample_num,7
    # datamod.take(random_index[:, :sample_num], axis=0, mode="clip",out=datamod_rng)  # iter_num,sample_num,7
    datamod.take(random_index_samplenum, axis=0, mode="clip", out=datamod_rng)

    # datamod_rng = datamod[rng_sample]#out=
    
    # datamod_rng_swap = datamod_rng[:, :, [4, 3, 0, 1, 5]]  # out= # iter_num,sample_num,5
    # datamod_rng_swap[:,:,:] = datamod_rng[:, :, [4, 3, 0, 1, 5]]  # out= # iter_num,sample_num,
    
    datamod_rng.take(swap_index, axis=2,mode="clip",out=datamod_rng_swap)
    # or
    # datamod_rng_swap = np.take(datamod_rng,[4, 3, 0, 1, 5],axis=2)
    
    # datamod_rng_swap_trans = datamod_rng_swap.transpose((0, 2, 1))  # out=
    # datamod_rng_swap_trans[:,:,:] = datamod_rng_swap.transpose((0, 2, 1))#.copy()  # out=
    #
    # # These two lines are one of the bottlenecks
    # datamod_rng_5x5 = np.matmul(datamod_rng_swap_trans, datamod_rng_swap)
    # datamod_rng_p5smp = np.matmul(np.linalg.inv(datamod_rng_5x5), datamod_rng_swap_trans)
    # datamod_rng_p5smp = np.matmul(np.linalg.inv(np.matmul(datamod_rng_swap_trans, datamod_rng_swap)), datamod_rng_swap_trans)
    np.matmul(datamod_rng_swap_trans, datamod_rng_swap,out=datamod_rng_5x5)
    # I want to use cv2.mulTransposed, but for some reason the results are different and it can only use 1-channel arrays.
    # np.linalg.inv(datamod_rng_5x5)
    # datamod_rng_5x5[:,:,:]=np.linalg.inv(datamod_rng_5x5)
    _umath_linalg.inv(datamod_rng_5x5,out=datamod_rng_5x5)# check error
    np.matmul(datamod_rng_5x5, datamod_rng_swap_trans,out=datamod_rng_p5smp)
    # global ein_path
    # if ein_path is None:
    #     ein_path = np.einsum_path("ijk,ijl->ikl", datamod_rng_swap, datamod_rng_swap, optimize='optimal')[0]#'optimal','greedy'
    # datamod_rng_p5smp = np.matmul(np.linalg.inv(np.einsum("ijk,ijl->ikl", datamod_rng_swap, datamod_rng_swap,casting="no",optimize=ein_path)), datamod_rng_swap_trans)
    # # np.einsum('ijk,ilk->ijl', dataswap_trans, dataswap)
    #
    # datamod_rng_p = np.matmul(datamod_rng_p5smp, datamod_rng[:, :, 6, np.newaxis]).reshape((-1, 5))  # out= # iter_num,5
    # datamod_rng_p[:,:]=np.matmul(datamod_rng_p5smp, datamod_rng[:, :, 6, np.newaxis]).reshape((-1, 5)) # out= # iter_num,5
    np.matmul(datamod_rng_p5smp, dm_rng_six,out=datamod_rng_p_npaxis)
    
    
    
    #
    # # I don't think it looks beautiful.
    # ellipse_y_arr = np.asarray(
    #     [datamod_rng_p[:, 2], datamod_rng_p[:, 3], np.ones(iter_num,dtype=ret_dtype), datamod_rng_p[:, 1], datamod_rng_p[:, 0]], dtype=ret_dtype)
    
    # ellipse_y_arr = np.empty((iter_num, 5), dtype=ret_dtype)
    # ellipse_y_arr[0,:]=datamod_rng_p[:, 2]
    # ellipse_y_arr[1, :]=datamod_rng_p[:, 3]
    # ellipse_y_arr[:, :2] = datamod_rng_p[:, 2:4]
    # # ellipse_y_arr[:, 2] = 1
    # ellipse_y_arr[:, 3:] = datamod_rng_p[:, 1::-1]
    
    el_y_arr_2_view[:,:]= dm_rng_p_24_view#datamod_rng_p[:, 2:4]
    el_y_arr_3_view[:,:] = dm_rng_p_10_view#datamod_rng_p[:, 1::-1]
    
    # ellipse_y_arr[:,3:]=datamod_rng_p[:,1]
    # ellipse_y_arr[4,:]=datamod_rng_p[:,0]
    # ellipse_data_arr = np.asarray(ellipse_model(datamod[:, :5], ellipse_y_arr.T, np.asarray(datamod_rng_p[:, 4])).transpose((1, 0)))
    # ellipse_data_arr = datamod[:, :5].dot(ellipse_y_arr.T)+np.asarray(datamod_rng_p[:, 4])
    # ellipse_data_arr = np.matmul(ellipse_y_arr, datamod[:, :5].T) + np.asarray(datamod_rng_p[:, 4, np.newaxis])# iter_num,len_data
    # np.matmul(ellipse_y_arr, datamod_t,out=ellipse_data_arr)
    # ellipse_y_arr.dot(datamod[:, :5].T, out=ellipse_data_arr)
    # ellipse_data_arr+=datamod_rng_p[:, 4, np.newaxis]#np.asarray(datamod_rng_p[:, 4, np.newaxis])
    # cv2.gemm is slower and for some reason the src3 argument for addition is not available
    cv2.gemm(ellipse_y_arr,datamod_b,1.0,dm_brod,1.0,dst=ellipse_data_arr,flags=cv2.GEMM_2_T)
    # ellipse_data_arr[:,:]=scipy.linalg.blas.dgemm(alpha=1.0, a=ellipse_y_arr, b=datamod_b, beta=1.0, c=np.broadcast_to(datamod_rng_p[:, 4, np.newaxis], (iter_num, len_data)),trans_b=True, overwrite_c=False)

    # ellipse_data_arr=ellipse_y_arr.dot(datamod[:, :5].T) + np.asarray(datamod_rng_p[:, 4, np.newaxis])
    # ellipse_data_arr =ellipse_data_arr.transpose((1, 0))
    # ellipse_data_arr = np.einsum("ij,kj->ki",np.asarray(datamod[:, :5]),ellipse_y_arr)+np.asarray(datamod_rng_p[:, 4,np.newaxis])
    
    # Q, R = np.linalg.qr(datamod_rng_swap_trans)
    # # datarng_T = datamod_rng.transpose((0, 2, 1))
    # Qtb = Q @ datamod_rng[:, :, 6].reshape((iter_num,5,5))
    # p = np.linalg.solve(R, Qtb)
    # Q, R = np.linalg.qr(datamod_rng_swap)#, mode='raw')
    # Qtb = Q.transpose((0, 2, 1)) @ datamod_rng[:, :, 6, np.newaxis]
    # p = np.linalg.solve(R, Qtb.reshape((-1, 5)))
    # hoge=datamod_rng_swap.transpose((0, 2, 1))@datamod_rng_swap
    # inv_h=np.linalg.inv(hoge)
    # D, U = np.linalg.eigh(hoge)
    # Ap = (U * np.sqrt(D)).T
    
    # smp=np.linalg.solve(R, Q.transpose((0, 2, 1)))
    # smp= np.matmul(np.linalg.inv(R), Q.transpose((0, 2, 1)))
    # datamod_rng_p=np.matmul(smp, datamod_rng[:, :,6, np.newaxis]).reshape((-1, 5))
    # ellipse_y_arr = np.asarray([datamod_rng_p[:,2], datamod_rng_p[:,3], np.ones(iter_num), datamod_rng_p[:,1], datamod_rng_p[:,0]], dtype=ret_dtype)
    # ellipse_data_arr = datamod[:, :5].dot(ellipse_y_arr) + datamod_rng_p[:,4]
    # ellipse_data_arr = ellipse_data_arr.transpose((1, 0))
    
    # ellipse_data_abs = np.abs(ellipse_data_arr)
    # ellipse_data_abs = cv2.absdiff(ellipse_data_arr, 0)
    # ellipse_data_index = np.argmax(np.sum(ellipse_data_abs < offset, axis=1), axis=0)
    # ellipse_data_index = np.argmax(cv2.reduce(cv2.threshold(ellipse_data_abs, offset, 1, cv2.THRESH_BINARY_INV)[1], 1, cv2.REDUCE_SUM).reshape(-1), axis=0)
    # ellipse_data_index = cv2.reduceArgMax(cv2.reduce((ellipse_data_abs < offset)*1.0, 1, cv2.REDUCE_SUM),axis=0)[0,0]
    # ellipse_data_index = cv2.reduceArgMax(cv2.reduce(cv2.threshold(ellipse_data_abs, offset, 1, cv2.THRESH_BINARY_INV)[1], 1, cv2.REDUCE_SUM),axis=0)[0,0]
    # ellipse_data_index = np.einsum("ij->i", cv2.threshold(ellipse_data_abs, offset, 1, cv2.THRESH_BINARY_INV)[1]).argmax()
    # ellipse_data_index = \
    # cv2.minMaxLoc(cv2.reduce(cv2.threshold(np.abs(ellipse_data_arr), offset, 1, cv2.THRESH_BINARY_INV)[1], 1, cv2.REDUCE_SUM))[3][1]
    np.abs(ellipse_data_arr,out=th_abs)
    cv2.threshold(th_abs, offset, 1.0, cv2.THRESH_BINARY_INV,dst=th_abs)#[1]
    ellipse_data_index = \
    cv2.minMaxLoc(cv2.reduce(th_abs, 1, cv2.REDUCE_SUM))[3][1]
    # ellipse_data_index = np.linalg.norm(cv2.threshold(ellipse_data_abs, offset, 1, cv2.THRESH_BINARY_INV)[1],ord=0,axis=1).argmax()
    # if ellipse_data_index!=a:
    #     print()
    # effective_data_arr = ellipse_data_arr[ellipse_data_index]
    # error_num = ellipse_data_arr[ellipse_data_index].sum()
    error_num = cv2.sumElems(ellipse_data_arr[ellipse_data_index])[0]
    effective_sample_p_arr = datamod_rng_p[ellipse_data_index].tolist()
    
    # if fit_rotated_ellipse(effective_data_arr.sum(), effective_sample_p_arr)!= fit_rotated_ellipse_base(effective_data_arr, effective_sample_p_arr):
    #     print()
    return fit_rotated_ellipse(error_num, effective_sample_p_arr)


# @profile
def fit_rotated_ellipse(data, P):
    # a = 1.0
    # # b, c, d, e, f = P
    # b, c, d, e, f = P[0], P[1], P[2], P[3], P[4]
    # # b = P[0]
    # # c = P[1]
    # # d = P[2]
    # # e = P[3]
    # # f = P[4]
    # # The cost of trigonometric functions is high.
    # theta = 0.5 * math.atan2(b, a-c)# math.atan(b / (a - c))# #np.arctan(b / (a - c), dtype=np.float64)
    # # theta_sin = np.sin(theta, dtype=np.float64)
    # # theta_cos = np.cos(theta, dtype=np.float64)
    # theta_sin, theta_cos = math.sin(theta), math.cos(theta)
    # tc2 = theta_cos ** 2
    # ts2 = theta_sin ** 2
    # b_tcs = b * theta_cos * theta_sin
    #
    # # Do the calculation only once
    # cxy = b ** 2 - 4 * a * c
    # cx = (2 * c * d - b * e) / cxy
    # cy = (2 * a * e - b * d) / cxy
    #
    # # I just want to clear things up around here.
    # cu = a * cx ** 2 + b * cx * cy + c * cy ** 2 - f
    # # cu_r = np.array([(a * tc2 + b_tcs + c * ts2), (a * ts2 - b_tcs + c * tc2)])
    # # wh = np.sqrt(cu / cu_r)
    #
    # w = math.sqrt(cu/(a * tc2 + b_tcs + c * ts2))
    # h = math.sqrt(cu/(a * ts2 - b_tcs + c * tc2))
    
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
    # cu = a * cx * cx + b * cx * cy + c * cy * cy - P[4]#f
    cu = c * cy * cy + cx * (a * cx + b * cy) - P[4]
    # here: https://stackoverflow.com/questions/327002/which-is-faster-in-python-x-5-or-math-sqrtx
    # and : https://gist.github.com/zed/783011
    w = math.sqrt(cu / (a * tc2 + b_tcs + c * ts2))
    h = math.sqrt(cu / (a * ts2 - b_tcs + c * tc2))
    
    # error_sum = data.sum()#sum(data)#np.sum(data)
    # error_sum = data[0] + data[1] + data[2] + data[3] + data[4] + data[5] + data[6] + data[7] + data[8] + data[9] + data[10]
    error_sum = data  # sum(data)
    # print("fitting error = %.3f" % (error_sum))
    
    # cxy2 = P[0] * P[0] - 4 * a * P[1]
    # theta2 = 0.5 * math.atan(P[0] / (a - P[1]))
    # theta_sin2, theta_cos2 = math.sin(theta2), math.cos(theta2)
    # tc22 = theta_cos2 * theta_cos2
    # ts22 = theta_sin2 * theta_sin2
    # b_tcs2 = P[0] * theta_cos2 * theta_sin2
    # cx2 = (2 * P[1] * P[2] - P[0] * P[3]) / cxy2
    # cy2 = (2 * a * P[3] - P[0] * P[2]) / cxy2
    # cu2 = P[1] * cy2 * cy2 + cx2 * (a * cx2 + P[0] * cy2) - P[4]
    # w2 = math.sqrt(cu2 / (a * tc22 + b_tcs2 + P[1] * ts22))
    # h2 = math.sqrt(cu2 / (a * ts22 - b_tcs2 + P[1] * tc22))
    
    return cx, cy, w, h, theta


class CvParameters_base:
    # It may be a little slower because a dict named "self" is read for each function call.
    def __init__(self, radius, step):
        # self.prev_radius=radius
        self._radius = radius
        self.pad = 2 * radius
        # self.prev_step=step
        self._step = step
        self._hsf = HaarSurroundFeature_base(radius)
    
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
        self._hsf = HaarSurroundFeature_base(now_radius)


class HaarSurroundFeature_base:
    
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

@lru_cache(maxsize=lru_maxsize_vvs)
def get_hsf_empty_array_base(len_syx, frameint_x, frame_int_dtype, fcshape):
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


@lru_cache(maxsize=lru_maxsize_vs)
def frameint_get_xy_step_base(imageshape, xysteps, pad, start_offset=None, end_offset=None):
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


# @profile
def conv_int_base(frame_int, kernel, xy_step, padding, xy_steps_list):
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
    inout_sum, p_temp, p_list, response_list, frameconvlist = get_hsf_empty_array_base((len_sy, len_sx), col + 1,
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


class CvParameters_new:
    # It may be a little slower because a dict named "self" is read for each function call.
    def __init__(self, radius, step):
        # self.prev_radius=radius
        self._radius = radius
        self.pad = 2 * radius
        # self.prev_step=step
        self._step = step
        self._hsf = HaarSurroundFeature_new(radius)
    
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
        self._hsf = HaarSurroundFeature_new(now_radius)


class HaarSurroundFeature_new:
    
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
        
        self.val_in = float(val_inner)#np.array(val_inner, dtype=np.float64)
        self.val_out = float(val_outer)#np.array(val_outer, dtype=np.float64)
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

@lru_cache(maxsize=lru_maxsize_vvs)
def get_hsf_empty_array(len_sx,len_sy, frameint_x, frame_int_dtype, fcshape):
# def get_hsf_empty_array(len_syx, frameint_x, frame_int_dtype, fcshape):
    # Function to reduce array allocation by providing an empty array first and recycling it with lru
    len_syx=(len_sy,len_sx)
    inner_sum = np.empty(len_syx, dtype=frame_int_dtype)
    
    # in_p_temp = np.empty((len_syx[0], frameint_x), dtype=frame_int_dtype)
    # in_p00 = np.empty(len_syx, dtype=frame_int_dtype)
    # in_p11 = np.empty(len_syx, dtype=frame_int_dtype)
    # in_p01 = np.empty(len_syx, dtype=frame_int_dtype)
    # in_p10 = np.empty(len_syx, dtype=frame_int_dtype)
    
    # inner_sum_temp = np.empty((*len_syx,4), dtype=frame_int_dtype)
    outer_sum = np.empty(len_syx, dtype=frame_int_dtype)
    # outer_sum_temp = np.empty((*len_syx,5), dtype=frame_int_dtype)
    p_temp = np.empty((len_sy, frameint_x), dtype=frame_int_dtype)
    p00 = np.empty(len_syx, dtype=frame_int_dtype)
    p11 = np.empty(len_syx, dtype=frame_int_dtype)
    p01 = np.empty(len_syx, dtype=frame_int_dtype)
    p10 = np.empty(len_syx, dtype=frame_int_dtype)
    response_list = np.empty(len_syx, dtype=np.float64)# or np.int32
    frame_conv = np.zeros(shape=fcshape[0], dtype=np.uint8)# or np.float64
    frame_conv_stride = frame_conv[::fcshape[1], ::fcshape[2]]
    return inner_sum, outer_sum, p_temp, p00, p11, p01, p10, response_list, frame_conv, frame_conv_stride
    # return inner_sum,in_p_temp,in_p00,in_p11,in_p01,in_p10, outer_sum, p_temp, p00, p11, p01, p10, response_list, frame_conv, frame_conv_stride


@lru_cache(maxsize=lru_maxsize_vvs)
def get_hsf_inout_index(padding, x_step, y_step, col, row, r_in, r_out):#,val_in,val_out):
    # y_steps,x_steps=np.ogrid[padding:y_step * len_sy + padding:y_step, padding:x_step * len_sx + padding:x_step]
    y_steps_arr = np.arange(padding, row - padding, y_step,dtype=np.int16)
    x_steps_arr = np.arange(padding, col - padding, x_step,dtype=np.int16)
    len_sx, len_sy = len(x_steps_arr), len(y_steps_arr)
    
    # y_steps_arr = np.arange(padding, row - padding, y_step)
    # x_steps_arr = np.arange(padding, col - padding, x_step)
    # len_sx, len_sy = len(x_steps_arr), len(y_steps_arr)

    # inarr_m = frame_int[y_steps[0]-r_in:y_steps[-1]-r_in+1:y_step]
    # inarr_p =  frame_int[y_steps[0]+r_in:y_steps[-1]+r_in+1:y_step]
    # inarr_mm = inarr_m[:, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # inarr_mp = inarr_m[:, x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    # inarr_pm = inarr_p[:, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # inarr_pp = inarr_p[:,  x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    
    # inarr_ym = np.arange(y_steps_arr[0]-r_in,y_steps_arr[-1]-r_in+1,y_step).reshape(-1,1)#np.ogrid[padding-r_in:y_steps[-1]-r_in+1:y_step],frame_int[y_steps[0]-r_in:y_steps[-1]-r_in+1:y_step]
    # inarr_yp =  np.arange(y_steps_arr[0]+r_in,y_steps_arr[-1]+r_in+1,y_step).reshape(-1,1)#np.ogrid[padding+r_in:y_steps[-1]+r_in+1:y_step],frame_int[y_steps[0]+r_in:y_steps[-1]+r_in+1:y_step]
    # inarr_mm_index = (inarr_ym,np.arange(x_steps_arr[0]-r_in,x_steps_arr[-1]-r_in+1,x_step).reshape(1,-1))#inarr_m[:, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # inarr_mp_index = (inarr_ym,np.arange(x_steps_arr[0]+r_in,x_steps_arr[-1]+r_in+1,x_step).reshape(1,-1))#inarr_m[:, x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    # inarr_pm_index = (inarr_yp,inarr_mm_index[1].copy())#inarr_p[:, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # inarr_pp_index = (inarr_yp,inarr_mp_index[1].copy())#inarr_p[:,  x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    #
    # y_ro_m = y_steps_arr - r_out
    # x_ro_m = x_steps_arr - r_out
    # y_ro_p = y_steps_arr + r_out
    # x_ro_p = x_steps_arr + r_out
    #
    # return x_steps_arr,y_steps_arr,len_sx,len_sy,inarr_mm_index,inarr_mp_index,inarr_pm_index,inarr_pp_index,y_ro_m,x_ro_m,y_ro_p,x_ro_p
    
    # y_rin_m_f = y_steps_arr[0] - r_in
    # y_rin_m_e = y_steps_arr[-1] - r_in + 1
    # y_rin_p_f = y_steps_arr[0] + r_in
    # y_rin_p_e = y_steps_arr[-1] + r_in + 1
    #
    # x_rin_m_f = x_steps_arr[0] - r_in
    # x_rin_m_e = x_steps_arr[-1] - r_in + 1
    # x_rin_p_f = x_steps_arr[0] + r_in
    # x_rin_p_e = x_steps_arr[-1] + r_in + 1

    # y_rin_m_f = padding - r_in
    # y_rin_m_e = y_steps_arr[-1] - r_in + 1
    # y_rin_p_f = padding + r_in
    # y_rin_p_e = y_steps_arr[-1] + r_in + 1
    #
    # x_rin_m_f = padding - r_in
    # x_rin_m_e = x_steps_arr[-1] - r_in + 1
    # x_rin_p_f = padding + r_in
    # x_rin_p_e = x_steps_arr[-1] + r_in + 1
    
    y_end=padding+(y_step*(len_sy-1))
    x_end=padding+(x_step*(len_sx-1))
    y_rin_m_f = padding - r_in
    y_rin_m_e = y_end - r_in + 1
    y_rin_p_f = padding + r_in
    y_rin_p_e = y_end + r_in + 1

    x_rin_m_f = padding - r_in
    x_rin_m_e = x_end - r_in + 1
    x_rin_p_f = padding + r_in
    x_rin_p_e = x_end + r_in + 1
    
    y_rin_m=slice(y_rin_m_f,y_rin_m_e,y_step)
    y_rin_p=slice(y_rin_p_f,y_rin_p_e,y_step)
    x_rin_m=slice(x_rin_m_f,x_rin_m_e,x_step)
    x_rin_p=slice(x_rin_p_f,x_rin_p_e,x_step)
    
    # y_rin_m=np.arange(padding-r_in,y_end-r_in+1,y_step,dtype=np.int16)
    # y_rin_p=np.arange(padding+r_in,y_end+r_in+1,y_step,dtype=np.int16)
    # x_rin_m=np.arange(padding-r_in,x_end-r_in+1,x_step,dtype=np.int16)
    # x_rin_p=np.arange(padding+r_in,x_end+r_in+1,x_step,dtype=np.int16)
    
    # y_ro_m = y_steps_arr - r_out
    # x_ro_m = x_steps_arr - r_out
    # y_ro_p = y_steps_arr + r_out
    # x_ro_p = x_steps_arr + r_out
    
    # y_ro_m = slice(max(0,y_steps_arr[0]-r_out),max(0,y_steps_arr[-1]-r_out),y_step)#,y_steps_arr - r_out
    # x_ro_m = slice(max(0,x_steps_arr[0]-r_out),max(0,x_steps_arr[-1]-r_out),x_step)#x_steps_arr - r_out
    # y_ro_p = slice(min(row,y_steps_arr[0]+r_out),min(row,y_steps_arr[-1]+r_out),y_step)#y_steps_arr + r_out
    # x_ro_p = slice(min(col,x_steps_arr[0]+r_out),min(col,x_steps_arr[-1]+r_out),x_step)#x_steps_arr + r_out
    
    # y_ro_m = np.clip(y_steps_arr - r_out,0,y_steps_arr[-1])#[:,np.newaxis]
    # x_ro_m = np.clip(x_steps_arr - r_out,0,x_steps_arr[-1])#[np.newaxis,:]
    # y_ro_p = np.clip(y_steps_arr + r_out,0,row)#[:,np.newaxis]
    # x_ro_p = np.clip(x_steps_arr + r_out,0,col)#[np.newaxis,:]
    
    y_ro_m = np.maximum(y_steps_arr - r_out,0)#[:,np.newaxis]
    x_ro_m = np.maximum(x_steps_arr - r_out,0)#[np.newaxis,:]
    y_ro_p = np.minimum(row,y_steps_arr + r_out)#[:,np.newaxis]
    x_ro_p = np.minimum(col,x_steps_arr + r_out)#[np.newaxis,:]
    
    # return x_steps_arr, y_steps_arr, len_sx, len_sy, y_rin_m_f, y_rin_m_e, y_rin_p_f, y_rin_p_e, x_rin_m_f, x_rin_m_e, x_rin_p_f, x_rin_p_e, y_ro_m, x_ro_m, y_ro_p, x_ro_p
    # return len_sx, len_sy, y_rin_m, y_rin_p, x_rin_m, x_rin_p, y_ro_m, x_ro_m, y_ro_p, x_ro_p,val_in,val_out,(row - 2 * padding, col - 2 * padding)
    return len_sx, len_sy, y_rin_m, y_rin_p, x_rin_m, x_rin_p, y_ro_m, x_ro_m, y_ro_p, x_ro_p,(row - 2 * padding, col - 2 * padding)

@lru_cache(maxsize=lru_maxsize_s)
def get_hsf_center(padding, x_step, y_step, min_loc):#min_x,min_y):
    # y_steps,x_steps=np.ogrid[padding:y_step * len_sy + padding:y_step, padding:x_step * len_sx + padding:x_step]
    # y_steps_arr = np.arange(padding, row - padding, y_step)
    # x_steps_arr = np.arange(padding, col - padding, x_step)
    # return x_steps_arr[min_x] - padding, y_steps_arr[min_y] - padding
    # return np.array(padding+(x_step*min_loc[0])-padding),np.array(padding+(y_step*min_loc[1])-padding)
    return padding+(x_step*min_loc[0])-padding,padding+(y_step*min_loc[1])-padding

@lru_cache(maxsize=lru_maxsize_vvs)
def get_frameint_empty_array(frame_shape,pad,x_step, y_step, r_in, r_out):
    frame_int_dtype=np.intc
    
    frame_pad=np.empty((frame_shape[0]+(pad*2),frame_shape[1]+(pad*2)),dtype=np.uint8)
    
    row,col=frame_pad.shape
    
    frame_int=np.empty((row+1,col+1),dtype=frame_int_dtype)
    
    y_steps_arr = np.arange(pad, row - pad, y_step,dtype=np.int16)
    x_steps_arr = np.arange(pad, col - pad, x_step,dtype=np.int16)
    len_sx, len_sy = len(x_steps_arr), len(y_steps_arr)
    y_end = pad + (y_step * (len_sy - 1))
    x_end = pad + (x_step * (len_sx - 1))
    
    y_rin_m = slice( pad - r_in,  y_end - r_in + 1, y_step)
    y_rin_p = slice(pad + r_in, y_end + r_in + 1, y_step)
    x_rin_m = slice(pad - r_in, x_end - r_in + 1, x_step)
    x_rin_p = slice(pad + r_in, x_end + r_in + 1, x_step)

    in_p00_view=frame_int[y_rin_m,x_rin_m]
    in_p11_view=frame_int[y_rin_p,x_rin_p]
    in_p01_view=frame_int[y_rin_m,x_rin_p]
    in_p10_view=frame_int[y_rin_p,x_rin_m]
    
    y_ro_m = np.maximum(y_steps_arr - r_out,0)#[:,np.newaxis]
    x_ro_m = np.maximum(x_steps_arr - r_out,0)#[np.newaxis,:]
    y_ro_p = np.minimum(row,y_steps_arr + r_out)#[:,np.newaxis]
    x_ro_p = np.minimum(col,x_steps_arr + r_out)#[np.newaxis,:]
    
    return frame_pad,frame_int,in_p00_view,in_p11_view,in_p01_view,in_p10_view,y_ro_m, x_ro_m, y_ro_p, x_ro_p,(row - 2 * pad, col - 2 * pad),len_sx, len_sy

# todo: Check performance when changing integer type numpy array to low bits integer type
# todo: Consider using np.clip if the clamp function input meets some conditions
# @profile
def conv_int(frame_int, kernel, x_step,y_step, padding,in_p00_view, in_p11_view, in_p01_view, in_p10_view, y_ro_m, x_ro_m, y_ro_p, x_ro_p, f_shape, len_sx, len_sy):  # , x_steps,y_steps):#xy_steps_list):
    """
    :param frame_int:
    :param kernel: hsf
    :param step: (x,y)
    :param padding: int
    :return:
    """
    # row, col = frame_int.shape
    # row -= 1
    # col -= 1
    # x_step, y_step = xy_step
    # padding2 = 2 * padding
    # f_shape = row - 2 * padding, col - 2 * padding
    # r_in = kernel.r_in
    # len_sx, len_sy = len(x_steps), len(y_steps)
    # inout_sum, p_temp, p_list, response_list, frameconvlist = get_hsf_empty_array((len_sy, len_sx), col + 1,
    #                                                                               frame_int.dtype, (f_shape, y_step, x_step))
    # inner_sum, outer_sum = inout_sum
    # p00, p11, p01, p10 = p_list
    # frame_conv, frame_conv_stride = frameconvlist
    # len_sx, len_sy, y_rin_m, y_rin_p, x_rin_m, x_rin_p, y_ro_m, x_ro_m, y_ro_p, x_ro_p,val_in,val_out,f_shape = get_hsf_inout_index(
    #     padding, x_step, y_step, col, row, kernel.r_in, kernel.r_out,kernel.val_in,kernel.val_out)
    # len_sx, len_sy, y_rin_m, y_rin_p, x_rin_m, x_rin_p, y_ro_m, x_ro_m, y_ro_p, x_ro_p, f_shape = get_hsf_inout_index(
    #     padding, x_step, y_step, col, row, kernel.r_in, kernel.r_out)
    
    inner_sum, outer_sum,p_temp, p00, p11, p01, p10, response_list, frame_conv, frame_conv_stride = get_hsf_empty_array(len_sx,len_sy,#(len_sy, len_sx),
                                                                                                                         frame_int.shape[1],#col + 1,
                                                                                                                         frame_int.dtype, (
                                                                                                                         f_shape, y_step,
                                                                                                                         x_step))
    #
    # inner_sum, in_p_temp, in_p00, in_p11, in_p01, in_p10, outer_sum, p_temp, p00, p11, p01, p10, response_list, frame_conv, frame_conv_stride= get_hsf_empty_array((len_sy, len_sx),
    #                                                                                                                      col + 1,
    #                                                                                                                      frame_int.dtype, (
    #                                                                                                                      f_shape, y_step,
    #                                                                                                                      x_step))
    # inout_sum, p_temp, p_list, response_list, frameconvlist = hsf_empty_array
    # inner_sum, outer_sum = inout_sum
    # p00, p11, p01, p10 = p_list
    # frame_conv, frame_conv_stride = frameconvlist
    
    # x_steps_st_end=np.asarray([x_steps[0],x_steps[len_sx-1]+1])
    # # x_steps_st_end[1]+=1
    # y_steps_st_end=np.asarray([y_steps[0],y_steps[len_sy-1]+1])
    # y_steps_st_end[1] += 1
    
    # x_steps_st_end=np.asarray([x_steps[0],x_steps[len_sx-1]+1])
    # y_steps_st_end=np.asarray([y_steps[0],y_steps[len_sy-1]+1])
    # xy_steps_st_end=np.asarray([[x_steps[0],x_steps[-1]],[y_steps[0],y_steps[-1]]])
    # xy_steps_st_end[:,1]+=1
    
    # xy_rin_m = xy_steps_st_end-r_in
    # xy_rin_p = xy_steps_st_end + r_in
    
    # xx==(y,x),m==MINUS,p==PLUS, ex: mm==(y-,x-)
    # inarr_m = frame_int[y_steps[0]-r_in:y_steps[-1]-r_in+1:y_step]
    # inarr_p =  frame_int[y_steps[0]+r_in:y_steps[-1]+r_in+1:y_step]
    # inarr_mm = inarr_m[:, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # inarr_mp = inarr_m[:, x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    # inarr_pm = inarr_p[:, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # inarr_pp = inarr_p[:,  x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    
    # y_rin_m = y_steps_st_end - r_in
    # x_rin_m = x_steps_st_end - r_in
    # y_rin_p = y_steps_st_end + r_in
    # x_rin_p = x_steps_st_end + r_in
    # # xx==(y,x),m==MINUS,p==PLUS, ex: mm==(y-,x-)
    # inarr_mm = frame_int[y_rin_m[0]:y_rin_m[1]:y_step, x_rin_m[0]:x_rin_m[1]:x_step]
    # inarr_mp = frame_int[y_rin_m[0]:y_rin_m[1]:y_step, x_rin_p[0]:x_rin_p[1]:x_step]
    # inarr_pm = frame_int[y_rin_p[0]:y_rin_p[1]:y_step, x_rin_m[0]:x_rin_m[1]:x_step]
    # inarr_pp = frame_int[y_rin_p[0]:y_rin_p[1]:y_step, x_rin_p[0]:x_rin_p[1]:x_step]
    
    # == inarr_mm + inarr_pp - inarr_mp - inarr_pm
    # inner_sum[:, :] = inarr_mm
    # inner_sum += inarr_pp
    # inner_sum -= inarr_mp
    # inner_sum -= inarr_pm
    
    # cv2.subtract(cv2.subtract(cv2.add(inarr_mm,inarr_pp),inarr_mp),inarr_pm,dst=inner_sum[:,:])
    # inner_sum[:, :]=inarr_mm.__add__(inarr_pp).__sub__(inarr_mp).__sub__(inarr_pm)
    # inner_sum[:,:]=inarr_m[:, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # inner_sum += inarr_p[:,  x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    # inner_sum -= inarr_m[:, x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    # inner_sum -= inarr_p[:, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # y_m_f=y_steps[0] - r_in
    # y_m_e=y_steps[-1] - r_in + 1
    # y_p_f=y_steps[0] + r_in
    # y_p_e=y_steps[-1] + r_in + 1
    #
    # x_m_f=x_steps[0] - r_in
    # x_m_e=x_steps[-1] - r_in + 1
    # x_p_f=x_steps[0] + r_in
    # x_p_e=x_steps[-1] + r_in + 1
    
    # inner_sum[:,:]=frame_int[y_steps[0]-r_in:y_steps[-1]-r_in+1:y_step, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]
    # inner_sum += frame_int[y_steps[0]+r_in:y_steps[-1]+r_in+1:y_step,  x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    # inner_sum -= frame_int[y_steps[0]-r_in:y_steps[-1]-r_in+1:y_step, x_steps[0]+r_in:x_steps[-1]+r_in+1:x_step]
    # inner_sum -= frame_int[y_steps[0]+r_in:y_steps[-1]+r_in+1:y_step, x_steps[0]-r_in:x_steps[-1]-r_in+1:x_step]


    # inner_sum[:, :] = frame_int[y_rin_m_f:y_rin_m_e:y_step, x_rin_m_f:x_rin_m_e:x_step]
    # inner_sum += frame_int[y_rin_p_f:y_rin_p_e:y_step, x_rin_p_f:x_rin_p_e:x_step]
    # inner_sum -= frame_int[y_rin_m_f:y_rin_m_e:y_step, x_rin_p_f:x_rin_p_e:x_step]
    # inner_sum -= frame_int[y_rin_p_f:y_rin_p_e:y_step, x_rin_m_f:x_rin_m_e:x_step]

    # inner_sum_temp[:, :,0] = frame_int[y_rin_m, x_rin_m].copy()
    # inner_sum_temp[:, :,1] = frame_int[y_rin_p, x_rin_p].copy()
    # inner_sum_temp[:, :,2] = -frame_int[y_rin_m, x_rin_p].copy()
    # inner_sum_temp[:, :,3] = -frame_int[y_rin_p, x_rin_m].copy()
    # cv2.transform(inner_sum_temp, np.ones((1, 4)),
    #     dst=inner_sum)
    
    #
    # inner_sum[:, :] = frame_int[y_rin_m, x_rin_m]
    # inner_sum += frame_int[y_rin_p, x_rin_p]
    # inner_sum -= frame_int[y_rin_m, x_rin_p]
    # inner_sum -= frame_int[y_rin_p, x_rin_m]

    # inner_sum[:, :] = frame_int[y_rin_m, x_rin_m]+ frame_int[y_rin_p, x_rin_p]-frame_int[y_rin_m, x_rin_p]- frame_int[y_rin_p, x_rin_m]

    # inner_sum[:, :] = frame_int[y_rin_m, x_rin_m] + frame_int[y_rin_p, x_rin_p] - frame_int[y_rin_m, x_rin_p] - frame_int[y_rin_p, x_rin_m]

    inner_sum[:, :] = in_p00_view + in_p11_view - in_p01_view - in_p10_view
    
    # inarr_m = frame_int[inarr_ym]
    # inarr_p =  frame_int[inarr_yp]
    # inner_sum[:, :] = inarr_m[:,inarr_xm]#inarr_mm
    # inner_sum +=  inarr_p[:,inarr_xp]#inarr_pp
    # inner_sum -=  inarr_m[:,inarr_xp]#inarr_mp
    # inner_sum -=  inarr_p[:,inarr_xm]#inarr_pm
    
    # Bottleneck here, I want to make it smarter. Someone do it.
    # (y,x)
    # p00=max(y_ro_m,0),max(x_ro_m,0)
    # p11=min(y_ro_p,ylim),min(x_ro_p,xlim)
    # p01=max(y_ro_m,0),min(x_ro_p,xlim)
    # p10=min(y_ro_p,ylim),max(x_ro_m,0)
    # y_ro_m = y_steps - kernel.r_out
    # x_ro_m = x_steps - kernel.r_out
    # y_ro_p = y_steps + kernel.r_out
    # x_ro_p = x_steps + kernel.r_out
    # p00 calc
    # np.take(frame_int,  y_steps - kernel.r_out, axis=0, mode="clip", out=p_temp)
    
    # np.take(frame_int, y_ro_m, axis=0, mode="clip", out=p_temp)
    # np.take(p_temp, x_ro_m, axis=1, mode="clip", out=p00)
    # # p01 calc
    # np.take(p_temp, x_ro_p, axis=1, mode="clip", out=p01)
    # # p11 calc
    # np.take(frame_int, y_ro_p, axis=0, mode="clip", out=p_temp)
    # np.take(p_temp, x_ro_p, axis=1, mode="clip", out=p11)
    # # p10 calc
    # np.take(p_temp, x_ro_m, axis=1, mode="clip", out=p10)
    
    # np.take(frame_int, y_ro_m, axis=0, mode="clip", out=p_temp)
    # np.take(p_temp, x_ro_m, axis=1, mode="clip", out=p00)
    # # p01 calc
    # np.take(p_temp, x_ro_p, axis=1, mode="clip", out=p01)
    # # p11 calc
    # np.take(frame_int, y_ro_p, axis=0, mode="clip", out=p_temp)
    # np.take(p_temp, x_ro_p, axis=1, mode="clip", out=p11)
    # # p10 calc
    # np.take(p_temp, x_ro_m, axis=1, mode="clip", out=p10)
    
    frame_int.take( y_ro_m, axis=0, mode="clip", out=p_temp)
    p_temp.take(x_ro_m, axis=1, mode="clip", out=p00)
    # p01 calc
    p_temp.take( x_ro_p, axis=1, mode="clip", out=p01)
    # p11 calc
    frame_int.take( y_ro_p, axis=0, mode="clip", out=p_temp)
    p_temp.take( x_ro_p, axis=1, mode="clip", out=p11)
    # p10 calc
    p_temp.take( x_ro_m, axis=1, mode="clip", out=p10)
    
    # p_temp[:,:]=frame_int[y_ro_m.reshape(-1),:]#.copy()
    # p00[:,:]=np.asarray(p_temp[:,x_ro_m.reshape(-1)])#.copy()
    # # p01 calc
    # p01[:,:]=-p_temp[:,x_ro_p.reshape(-1)]#.copy()
    # # p11 calc
    # p_temp[:,:]=frame_int[y_ro_p.reshape(-1),:]
    # p11[:,:]=np.asarray(p_temp[:,x_ro_p.reshape(-1)])#.copy()
    # # p10 calc
    # p10[:,:]=-p_temp[:,x_ro_m.reshape(-1)]#.copy()

    # the point is this
    # p00=np.take(np.take(frame_int, y_ro_m, axis=0, mode="clip"), x_ro_m, axis=1, mode="clip")
    # p11=np.take(np.take(frame_int, y_ro_p, axis=0, mode="clip"), x_ro_p, axis=1, mode="clip")
    # p01=np.take(np.take(frame_int, y_ro_m, axis=0, mode="clip"), x_ro_p, axis=1, mode="clip")
    # p10=np.take(np.take(frame_int, y_ro_p, axis=0, mode="clip"), x_ro_m, axis=1, mode="clip")
    
    outer_sum[:, :] = p00 + p11 - p01 - p10 - inner_sum
    # cv2.transform(np.asarray([p00, p11, -p01, -p10, -inner_sum]).transpose((1, 2, 0)), np.ones((1, 5)),
    #               dst=outer_sum)  # https://answers.opencv.org/question/3120/how-to-sum-a-3-channel-matrix-to-a-one-channel-matrix/
    # cv2.transform(np.asarray([frame_int[y_ro_m,x_ro_m], frame_int[y_ro_m,x_ro_p], -frame_int[y_ro_p,x_ro_p], -frame_int[y_ro_p,x_ro_m], -inner_sum]).transpose((1, 2, 0)), np.ones((1, 5)),
    #               dst=outer_sum)  # https://answers.opencv.org/question/3120/how-to-sum-a-3-channel-matrix-to-a-one-channel-matrix/
    # cv2.transform(np.asarray([
    #     frame_int[y_ro_m,x_ro_m],
    #     frame_int[y_ro_p,x_ro_p],
    #     -frame_int[y_ro_m,x_ro_p],
    #     -frame_int[y_ro_p,x_ro_m],
    #     -inner_sum]).transpose((1, 2, 0)), np.ones((1, 5)),
    #               dst=outer_sum)  # https://answers.opencv.org/question/3120/how-to-sum-a-3-channel-matrix-to-a-one-channel-matrix/
    
    # outer_sum_temp[:,:,0]=p00#frame_int[y_ro_m, x_ro_m]
    # outer_sum_temp[:, :, 1] = p11#frame_int[y_ro_p, x_ro_p]
    # outer_sum_temp[:, :, 2] = p01#frame_int[y_ro_m, x_ro_p]
    # outer_sum_temp[:, :, 3] = p10#frame_int[y_ro_p, x_ro_m]
    
    # p_temp[:,:]=frame_int[y_ro_m.reshape(-1),:]#.copy()
    # outer_sum_temp[:,:,0]=np.asarray(p_temp[:,x_ro_m.reshape(-1)])#frame_int[y_ro_m, x_ro_m]
    # outer_sum_temp[:, :, 2] = -p_temp[:,x_ro_p.reshape(-1)]#frame_int[y_ro_m, x_ro_p]
    # p_temp[:,:]=frame_int[y_ro_p.reshape(-1),:]
    # outer_sum_temp[:, :, 1] = np.asarray(p_temp[:,x_ro_p.reshape(-1)])#frame_int[y_ro_p, x_ro_p]
    # outer_sum_temp[:, :, 3] = -p_temp[:,x_ro_m.reshape(-1)]#frame_int[y_ro_p, x_ro_m]
    # outer_sum_temp[:, :, 4] = -inner_sum
    # cv2.transform(outer_sum_temp, np.ones((1, 5)),
    #               dst=outer_sum)  # https://answers.opencv.org/question/3120/how-to-sum-a-3-channel-matrix-to-a-one-channel-matrix/
    
    
    # np.multiply(kernel.val_in, inner_sum, dtype=np.float64, out=response_list)
    # response_list += kernel.val_out * outer_sum
    cv2.addWeighted(inner_sum,
                    kernel.val_in,
                    outer_sum,# or p00 + p11 - p01 - p10 - inner_sum
                    kernel.val_out,
                    0.0,
                    dtype=cv2.CV_64F,#or cv2.CV_32S
                    dst=response_list)
    
    # min_response, max_val, min_loc, max_loc = cv2.minMaxLoc(response_list)
    min_response, _, min_loc, _ = cv2.minMaxLoc(response_list)
    
    # center = ((x_steps_arr[min_loc[0]] - padding), (y_steps_arr[min_loc[1]] - padding))
    # center = get_hsf_center(padding,x_step,y_step,min_loc)#[0],min_loc[1])
    
    frame_conv_stride[:, :] = response_list
    # or
    # frame_conv_stride[:, :] = response_list.astype(np.uint8)
    
    # return frame_conv, min_response, center
    return frame_conv, min_response, get_hsf_center(padding,x_step,y_step,min_loc)


@lru_cache(lru_maxsize_vvs)
def get_ransac_frame(frame_shape):
    return np.empty(frame_shape,dtype=np.uint8),np.empty(frame_shape,dtype=np.uint8)#np.float64)


@lru_cache(lru_maxsize_s)
def get_center_noclamp(center_xy,radius):
    center_x, center_y = center_xy
    upper_x = center_x + radius
    lower_x = center_x - radius
    upper_y = center_y + radius
    lower_y = center_y - radius
    return center_x,center_y,upper_x,lower_x,upper_y,lower_y


@lru_cache(lru_maxsize_s)
def get_hsf_center_uplow(center_x,center_y,radius):
    hsf_center_x, hsf_center_y = center_x, center_y
    # ransac_xy_offset = (hsf_center_x-20, hsf_center_y-20)
    upper_x = hsf_center_x + max(20, radius)
    lower_x = hsf_center_x - max(20, radius)
    upper_y = hsf_center_y + max(20, radius)
    lower_y = hsf_center_y - max(20, radius)
    ransac_xy_offset = (lower_x, lower_y)
    return upper_x,lower_x,upper_y,lower_y,ransac_xy_offset
    
class HSRAC_cls(object):
    def __init__(self):
        # I'd like to take into account things like print, end_time - start_time processing time, etc., but it's too much trouble.
        
        # For measuring total processing time
        
        self.main_start_time = timeit.default_timer()
        
        self.rng = np.random.default_rng()
        if old_mode:
            self.cvparam = CvParameters_base(default_radius, default_step)
        else:
            self.cvparam = CvParameters_new(default_radius, default_step)
        
        self.cv_modeo = ["first_frame", "radius_adjust", "blink_adjust", "normal"]
        self.now_modeo = self.cv_modeo[0]
        
        self.auto_radius_calc = AutoRadiusCalc()
        self.blink_detector = BlinkDetector()
        self.center_q1 = BlinkDetector()
        
        self.cap = None
        
        self.timedict = {"to_gray": [], "int_img": [], "conv_int": [], "crop": [], "ransac": [], "total_cv": []}
        
        # ransac
        self.rng = np.random.default_rng()
        self.sfc = np.random.default_rng(np.random.SFC64())
        
        # self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        # or
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        self.gauss_k = cv2.getGaussianKernel(5, 0)
    
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
            self.current_image = frame  # debug code
            self.current_image_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return True
        return False
    
    # @profile
    def single_run(self):
        # Temporary implementation to run
        ## default_radius = 14
        
        # ori_frame = self.current_image.copy()# debug code
        # cropbox=[] # debug code
        
        blink_bd = False
        # frame = self.current_image_gray
        
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
        if old_mode:
            # BORDER_CONSTANT is faster than BORDER_REPLICATE There seems to be almost no negative impact when BORDER_CONSTANT is used.
            frame_pad = cv2.copyMakeBorder(gray_frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT)
            frame_int = cv2.integral(frame_pad)
        else:
            frame_pad, frame_int, in_p00_view, in_p11_view, in_p01_view, in_p10_view, y_ro_m, x_ro_m, y_ro_p, x_ro_p, f_shape, len_sx, len_sy = get_frameint_empty_array(gray_frame.shape,pad,step[0],step[1],hsf.r_in,hsf.r_out)
            cv2.copyMakeBorder(gray_frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT,dst=frame_pad)
            cv2.integral(frame_pad,sum=frame_int,sdepth=cv2.CV_32S)
        self.timedict["int_img"].append(timeit.default_timer() - int_start_time)
        
        # Convolve the feature with the integral image
        conv_int_start_time = timeit.default_timer()
        if old_mode:
            xy_step = frameint_get_xy_step_base(frame_int.shape, step, pad, start_offset=None, end_offset=None)
            frame_conv, response, center_xy = conv_int_base(frame_int, hsf, step, pad, xy_step)
        else:
            # frame_conv, response, center_xy = conv_int(frame_int, hsf, step, pad)  # , x_step,y_step)
            frame_conv, response, center_xy = conv_int(frame_int, hsf, step[0],step[1], pad,in_p00_view, in_p11_view, in_p01_view, in_p10_view, y_ro_m, x_ro_m, y_ro_p, x_ro_p, f_shape, len_sx, len_sy)  # , x_step,y_step)
        # x_step,y_step = frameint_get_xy_step(frame_int.shape, step, pad, start_offset=None, end_offset=None)

        self.timedict["conv_int"].append(timeit.default_timer() - conv_int_start_time)
        
        crop_start_time = timeit.default_timer()
        # Define the center point and radius
        # center_x, center_y = center_xy
        # upper_x = center_x + radius
        # lower_x = center_x - radius
        # upper_y = center_y + radius
        # lower_y = center_y - radius
        center_x, center_y, upper_x, lower_x, upper_y, lower_y=get_center_noclamp(center_xy,radius)
        
        # Crop the image using the calculated bounds
        cropped_image = safe_crop(gray_frame, lower_x, lower_y, upper_x, upper_y)
        
        # cropbox=[clamp(val, 0, gray_frame.shape[i]) for i,val in zip([1,0,1,0],[lower_x,lower_y,upper_x,upper_y])] # debug code
        
        if self.now_modeo == self.cv_modeo[0] or self.now_modeo == self.cv_modeo[1]:
            # If mode is first_frame or radius_adjust, record current radius and response
            self.auto_radius_calc.add_response(radius, response)
        elif self.now_modeo == self.cv_modeo[2]:
            # Statistics for blink detection
            if self.blink_detector.response_len() < blink_init_frames:
                self.blink_detector.add_response(cv2.mean(cropped_image)[0])
                
                upper_x = center_x + max(20, radius)
                lower_x = center_x - max(20, radius)
                upper_y = center_y + max(20, radius)
                lower_y = center_y - max(20, radius)
                self.center_q1.add_response(
                    cv2.mean(safe_crop(gray_frame, lower_x, lower_y, upper_x, upper_y, keepsize=False))[
                        0
                    ]
                )
            
            else:
                
                self.blink_detector.calc_thresh()
                self.center_q1.calc_thresh()
                self.now_modeo = self.cv_modeo[3]
        else:
            if 0 in cropped_image.shape:  # This line may not be needed. The image will be cropped using safecrop.
                # If shape contains 0, it is not detected well.
                print("Something's wrong.")
            else:
                orig_x, orig_y = center_x, center_y
                if self.blink_detector.enable_detect_flg:
                    # If the average value of cropped_image is greater than response_max
                    # (i.e., if the cropimage is whitish
                    if self.blink_detector.detect(cv2.mean(cropped_image)[0]):
                        # blink
                        print("BLINK BD")
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
        # Crop first to reduce the amount of data to process.
        #  frame = cropped_image[0:len(cropped_image) - 10, :]
        # To reduce the processing data, first convert to 1-channel and then blur.
        # The processing results were the same when I swapped the order of blurring and 1-channelization.
        # frame_gray = cv2.GaussianBlur(frame, (5, 5), 0)
        # cv2.GaussianBlur is slow (use 10%)
        # use cv2.blur() or cv2.boxFilter()?
        # or
        # frame_gray =cv2.boxFilter(frame, -1,(5, 5))# https://github.com/bfraboni/FastGaussianBlur
        # cv2.boxFilter(frame_gray, -1,(5, 5),dst=frame_gray)
        # cv2.boxFilter(frame_gray, -1,(5, 5),dst=frame_gray)
        if old_mode:
            frame_gray = cv2.GaussianBlur(frame, (5, 5), 0)
        else:
            frame_gray = cv2.sepFilter2D(frame, -1, self.gauss_k, self.gauss_k)
        

        #todo:no numpy and int and use lru
        # hsf_center_x, hsf_center_y = center_x.copy(), center_y.copy()
        # # ransac_xy_offset = (hsf_center_x-20, hsf_center_y-20)
        # upper_x = hsf_center_x + max(20, radius)
        # lower_x = hsf_center_x - max(20, radius)
        # upper_y = hsf_center_y + max(20, radius)
        # lower_y = hsf_center_y - max(20, radius)
        # ransac_xy_offset = (lower_x, lower_y)
        upper_x, lower_x, upper_y, lower_y, ransac_xy_offset = get_hsf_center_uplow(center_x,center_y,radius)
        
        # Crop the image using the calculated bounds
        #todo:safecrop tune
        frame_gray_crop = safe_crop(frame_gray, lower_x, lower_y, upper_x, upper_y)
        th_frame,fic_frame=get_ransac_frame(frame_gray_crop.shape)
        frame = frame_gray_crop
        # this will need to be adjusted everytime hardware is changed (brightness of IR, Camera postion, etc)m
        # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(frame_gray_crop)
        min_val = cv2.minMaxLoc(frame_gray_crop)[0]
        # min_val=cv2.reduce(frame_gray_crop,1,cv2.REDUCE_MIN).min()
        # threshold_value = min_val + thresh_add
        if old_mode:
            _, thresh = cv2.threshold(frame_gray_crop, min_val + thresh_add, 255, cv2.THRESH_BINARY)
        else:
            cv2.threshold(frame_gray_crop, min_val + thresh_add, 255, cv2.THRESH_BINARY, dst=th_frame)
        # print(thresh.shape, frame_gray.shape)
        try:
            if old_mode:
                opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self.kernel)
                closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, self.kernel)
                th_frame = 255 - closing
            else:
                cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel,dst=fic_frame)
                cv2.morphologyEx(fic_frame, cv2.MORPH_CLOSE, self.kernel,dst=fic_frame)
                cv2.bitwise_not(fic_frame,fic_frame)
            # th_frame = 255 - closing
        except Exception as e:
            raise e
            # I want to eliminate try here because try tends to be slow in execution.
            fic_frame = 255 - frame_gray_crop
        if old_mode:
            contours, _ = cv2.findContours(th_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
        else:
            contours = cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
            # contours, _ = cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        # or
        # contours, _=cv2.findContours(th_frame, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        # cv2.findContours(th_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
        # cv2.findContours(th_frame, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        # cv2.findContours(th_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        
        if not blink_bd and self.blink_detector.enable_detect_flg:
            threshold_value = self.center_q1.quartile_1
            if threshold_value < min_val + thresh_add:
                # In most of these cases, the pupil is at the edge of the eye.
                if old_mode:
                    thresh = cv2.threshold(frame_gray_crop, (min_val + thresh_add * 4 + threshold_value) / 2, 255, cv2.THRESH_BINARY)[1]
                else:
                    cv2.threshold(frame_gray_crop, (min_val + thresh_add * 4 + threshold_value) / 2, 255, cv2.THRESH_BINARY,dst=th_frame)
            else:
                threshold_value = self.center_q1.quartile_1
                if old_mode:
                    _, thresh = cv2.threshold(frame_gray_crop, threshold_value, 255, cv2.THRESH_BINARY)
                else:
                    cv2.threshold(frame_gray_crop, threshold_value, 255, cv2.THRESH_BINARY,dst=th_frame)
            try:
                if old_mode:
                    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self.kernel)
                    closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, self.kernel)
                    th_frame = 255 - closing
                else:
                    cv2.morphologyEx(th_frame, cv2.MORPH_OPEN, self.kernel, dst=fic_frame)
                    cv2.morphologyEx(fic_frame, cv2.MORPH_CLOSE, self.kernel, dst=fic_frame)
                    cv2.bitwise_not(fic_frame, fic_frame)
            except Exception as e:
                raise e
                # I want to eliminate try here because try tends to be slow in execution.
                fic_frame = 255 - frame_gray_crop
            if old_mode:
                contours2, _ = cv2.findContours(th_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
                contours = (*contours, *contours2)
            else:
                # contours2, _ = cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)#cv2.CHAIN_APPROX_NONE)
                # contours2 = cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
                contours = (*contours, *cv2.findContours(fic_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0])
            # contours = (*contours, *contours2)
        
        # hull = []
        # # This way is faster than contours[i]
        # # But maybe this one is faster. hull = [cv2.convexHull(cnt, False) for cnt in contours]
        # for cnt in contours:
        #     # pass
        #     hull.append(cv2.convexHull(cnt, False))
        if not contours:
            #     If empty, go to next loop
            return int(center_x), int(center_y), th_frame, frame, gray_frame
        if old_mode:
            hull = [cv2.convexHull(cnt, False) for cnt in contours]
        else:
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
        if 1:
            if old_mode:
                cnt = sorted(hull, key=cv2.contourArea)
                maxcnt = cnt[-1]
            else:
                maxcnt = hull
            # ellipse = cv2.fitEllipse(maxcnt)
            if old_mode:
                ransac_data = fit_rotated_ellipse_ransac_base(maxcnt.reshape(-1, 2), self.rng)
            else:
                ransac_data = fit_rotated_ellipse_ransac(maxcnt.reshape(-1, 2).astype(np.float64), self.sfc)
            if ransac_data is None:
                # ransac_data is None==maxcnt.shape[0]<sample_num
                # go to next loop
                # pass
                return int(center_x), int(center_y), th_frame, frame, gray_frame
            
            # crop_start_time = timeit.default_timer()
            cx, cy, w, h, theta = ransac_data
            #  print(cx, cy)
            if w >= 2.1 * h:  # new blink detection algo lmao this works pretty good actually
                print("RAN BLINK")
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
            if 0:  # imshow_enable or save_video:
                
                cv2.circle(ori_frame, (int(center_x), int(center_y)), 3, (0, 255, 0), -1)
                cv2.drawContours(ori_frame, contours, -1, (255, 0, 0), 1)
                cv2.circle(ori_frame, (int(cx), int(cy)), 2, (0, 0, 255), -1)
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
                cv2.imshow("ori_frame", ori_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    pass
        
        # except Exception as e:
        #     print(e)
        # pass
        
        # debug code
        # try:
        #     if any([isinstance(val, float) for val in [cx, cy]]):
        #         print()
        #     return int(cx), int(cy),cropbox, ori_frame,thresh, frame, gray_frame
        # except:
        #     if any([isinstance(val, float) for val in [center_x, center_y]]):
        #         print()
        #     return center_x, center_y,cropbox, ori_frame,thresh, frame, gray_frame
        #  print(frame_gray.shape, thresh.shape)
        
        cv_end_time = timeit.default_timer()
        self.timedict["ransac"].append(cv_end_time - ransac_start_time)
        self.timedict["total_cv"].append(cv_end_time - cv_start_time)
        
        try:
            return int(cx), int(cy), th_frame, frame, gray_frame
        except:
            return int(center_x), int(center_y), th_frame, frame, gray_frame


if __name__ == "__main__":
    
    loop_num = 100
    
    logger.info(this_file_name)
    video_path = "Pro_demo2.mp4"
    cap = cv2.VideoCapture(video_path)
    logger.info("video: size:{}x{} fps:{} frames:{} total:{:.3f} sec".format(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                                                             int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                                                                             cap.get(cv2.CAP_PROP_FPS),
                                                                             int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                                                                             cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)))
    cap.release()
    filepath = 'test.mp4'
    codec = cv2.VideoWriter_fourcc(*"x264")
    # video = cv2.VideoWriter(filepath, codec, 60.0, (200,150))#(60, 60))  # (150, 200))
    if not print_enable:
        def print(*args, **kwargs):
            pass
    
    hsrac = HSRAC_cls()
    # For measuring total processing time
    main_start_time = timeit.default_timer()
    for i in range(loop_num):
        hsrac.open_video(video_path)
        
        while hsrac.read_frame():
            if 1:
                base_gray = hsrac.current_image_gray.copy()
                base_img = hsrac.current_image.copy()
                cv2.imshow("frame", base_gray)
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
                cv2.circle(base_img, (hsf_x, hsf_y), 6, (0, 0, 255), -1)
                # try:
                #     cv2.circle(base_img, (hsrac_x, hsrac_y), 3, (255, 0, 0), -1)
                # except:
                #     print()
                cv2.imshow("hsf_hsrac", base_img)
                video.write(cv2.resize(base_img, (200, 150)))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    pass
            else:
                _ = hsrac.single_run()
            
            # _ = hsrac.single_run()
        video.release()
        hsrac.cap.release()
        cv2.destroyAllWindows()
    main_end_time = timeit.default_timer()
    main_total_time = main_end_time - main_start_time
    if not print_enable:
        # del print
        # or
        print = __builtins__.print
    logger.info("")
    for k, v in hsrac.timedict.items():
        # number=1, precision=5
        len_v = len(v)
        if not len_v:
            print()
        best = min(v)  # / number
        worst = max(v)  # / number
        logger.info(k + ":")
        logger.info(TimeitResult(loop_num, len_v, best, worst, v, 5))
        logger.info(FPSResult(loop_num, len_v, worst, best, v, 5))
        # print("")
    logger.info("")
    logger.info(f"{this_file_name}: ALL Finish {format_time(main_total_time)}")
    
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
