import timeit

import cv2
import numpy as np

from haar_surround_feature import (
    AutoRadiusCalc,
    BlinkDetector,
    CvParameters, conv_int,
    frameint_get_xy_step,
)
from utils.img_utils import safe_crop
from utils.misc_utils import clamp


# from line_profiler_pycharm import profile

#RANSAC

thresh_add = 10

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
        self.rng = np.random.default_rng()
        
        # self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        # or
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))

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
        ## default_radius = 14
        
        # ori_frame = self.current_image.copy()# debug code
        # cropbox=[] # debug code
        
        blink_bd = False
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
        cropped_image = safe_crop(gray_frame, lower_x, lower_y, upper_x, upper_y)
        
        # cropbox=[clamp(val, 0, gray_frame.shape[i]) for i,val in zip([1,0,1,0],[lower_x,lower_y,upper_x,upper_y])] # debug code
        
        if self.now_modeo == self.cv_modeo[0] or self.now_modeo == self.cv_modeo[1]:
            # If mode is first_frame or radius_adjust, record current radius and response
            self.auto_radius_calc.add_response(radius, response)
        elif self.now_modeo == self.cv_modeo[2]:
            # Statistics for blink detection
            if self.blink_detector.response_len() < blink_init_frames:
                self.blink_detector.add_response(cv2.mean(cropped_image)[0])

                upper_x = center_x + max(20,radius)
                lower_x = center_x - max(20,radius)
                upper_y = center_y + max(20,radius)
                lower_y = center_y - max(20,radius)
                self.center_q1.add_response(
                    cv2.mean(safe_crop(gray_frame, lower_x, lower_y, upper_x, upper_y,keepsize=False))[
                        0
                    ]
                )

            else:
                
                self.blink_detector.calc_thresh()
                self.center_q1.calc_thresh()
                self.now_modeo = self.cv_modeo[3]
        else:
            if 0 in cropped_image.shape: # This line may not be needed. The image will be cropped using safecrop.
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
                        blink_bd=True
            # if imshow_enable or save_video:
            #    cv2.circle(frame, (orig_x, orig_y), 6, (0, 0, 255), -1)
            # cv2.circle(ori_frame, (center_x, center_y), 7, (255, 0, 0), -1)
        # If you want to update response_max. it may be more cost-effective to rewrite response_list in the following way
        # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue
        
        cv_end_time = timeit.default_timer()
        self.timedict["crop"].append(cv_end_time - crop_start_time)
        self.timedict["total_cv"].append(cv_end_time - cv_start_time)
        
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
        cv_start_time = timeit.default_timer()
        # Crop first to reduce the amount of data to process.
        #  frame = cropped_image[0:len(cropped_image) - 10, :]
        # To reduce the processing data, first convert to 1-channel and then blur.
        # The processing results were the same when I swapped the order of blurring and 1-channelization.
        frame_gray = cv2.GaussianBlur(frame, (5, 5), 0)
        hsf_center_x, hsf_center_y = center_x.copy(), center_y.copy()
        # ransac_xy_offset = (hsf_center_x-20, hsf_center_y-20)
        upper_x = hsf_center_x + max(20, radius)
        lower_x = hsf_center_x - max(20, radius)
        upper_y = hsf_center_y + max(20, radius)
        lower_y = hsf_center_y - max(20, radius)
        ransac_xy_offset = (lower_x, lower_y)
        
        # Crop the image using the calculated bounds

        frame_gray_crop = safe_crop(frame_gray, lower_x, lower_y, upper_x, upper_y)
        frame = frame_gray_crop
        # this will need to be adjusted everytime hardware is changed (brightness of IR, Camera postion, etc)m
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(frame_gray_crop)

        threshold_value = min_val + thresh_add
        _, thresh = cv2.threshold(frame_gray_crop, threshold_value, 255, cv2.THRESH_BINARY)
        # print(thresh.shape, frame_gray.shape)
        try:
            
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self.kernel)
            closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, self.kernel)
            th_frame = 255 - closing
        except:
            # I want to eliminate try here because try tends to be slow in execution.
            th_frame = 255 - frame_gray_crop

        contours, _ = cv2.findContours(th_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
        # or
        # contours, _=cv2.findContours(th_frame, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        
        if not blink_bd and self.blink_detector.enable_detect_flg:
            threshold_value = self.center_q1.quartile_1
            if threshold_value<min_val + thresh_add:
                # In most of these cases, the pupil is at the edge of the eye.
                thresh = cv2.threshold(frame_gray_crop, (min_val + thresh_add*4+threshold_value)/2, 255, cv2.THRESH_BINARY)[1]

            else:
                threshold_value = self.center_q1.quartile_1
                _, thresh = cv2.threshold(frame_gray_crop, threshold_value, 255, cv2.THRESH_BINARY)
            try:
                opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self.kernel)
                closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, self.kernel)
                th_frame = 255 - closing
            except:
                # I want to eliminate try here because try tends to be slow in execution.
                th_frame = 255 - frame_gray_crop

            contours2, _ = cv2.findContours(th_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
            contours = (*contours, *contours2)
        
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
            ransac_data = fit_rotated_ellipse_ransac(maxcnt.reshape(-1, 2), self.rng)
            if ransac_data is None:
                # ransac_data is None==maxcnt.shape[0]<sample_num
                # go to next loop
                pass

            
            crop_start_time = timeit.default_timer()
            cx, cy, w, h, theta = ransac_data
            #  print(cx, cy)
            if w >= 2.1 * h: #new blink detection algo lmao this works pretty good actually
                print("RAN BLINK")
                #return center_x, center_y, frame, frame, True

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

            cv_end_time = timeit.default_timer()
            # if imshow_enable or save_video:
            #
            #     cv2.circle(ori_frame, (orig_x, orig_y), 3, (0, 255, 0), -1)
            #     cv2.drawContours(ori_frame, contours, -1, (255, 0, 0), 1)
            #     cv2.circle(ori_frame, (cx, cy), 2, (0, 0, 255), -1)
            #     # cx1, cy1, w1, h1, theta1 = fit_rotated_ellipse(maxcnt.reshape(-1, 2))
            #     cv2.ellipse(
            #         ori_frame,
            #         (cx, cy),
            #         (int(w), int(h)),
            #         theta * 180.0 / np.pi,
            #         0.0,
            #         360.0,
            #         (50, 250, 200),
            #         1,
            #     )
            #     cv2.imshow("crop", cropped_image)
            #     # cv2.imshow("frame", frame)
            #     cv2.imshow("ori_frame",ori_frame)
            #     if cv2.waitKey(1) & 0xFF == ord("q"):
            #         pass

        except Exception as e:
            # print(e)
            pass

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

        try:
            return int(cx), int(cy), thresh, frame, gray_frame
        except:
            return int(center_x), int(center_y), thresh, frame, gray_frame




class External_Run_HSRACS(object):
    def __init__(self, skip_autoradius_flg=False, radius=20):
        # temporary code
        global skip_autoradius,default_radius
        skip_autoradius = skip_autoradius_flg
        if skip_autoradius:
            default_radius = radius
        
        self.algo = HSRAC_cls()

    def run(self, current_image_gray):
        self.algo.current_image_gray = current_image_gray
        #debug code
        # center_x, center_y,cropbox,ori_frame, thresh, frame, gray_frame = self.algo.single_run()
        # return center_x, center_y,cropbox,ori_frame, thresh, frame, gray_frame
        center_x, center_y, thresh, frame, gray_frame = self.algo.single_run()
        return center_x, center_y, thresh, frame, gray_frame



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
    