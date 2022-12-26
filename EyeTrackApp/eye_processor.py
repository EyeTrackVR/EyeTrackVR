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


from osc_calibrate_filter import *
from haar_surround_feature import *
from blob import *
from ransac import *
from hsrac import *
from blink import *

class InformationOrigin(Enum):
    RANSAC = 1
    BLOB = 2
    FAILURE = 3
    HSF = 4
    HSRAC = 5

bbb = 0
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

        self.failed = 0


        self.response_list = []  #This might not be correct. 
         #HSF
        
        self.cv_mode = ["first_frame", "radius_adjust", "init", "normal"]
        self.now_mode = self.cv_mode[0]
        self.cvparam = CvParameters(default_radius, default_step)
        self.skip_blink_detect = False

        self.default_step = (5, 5)  # bigger the steps,lower the processing time! ofc acc also takes an impact
        # self.default_step==(x,y)
        self.radius_cand_list = []
        self.blink_init_frames = 60 * 3
        prev_max_size = 60 * 3  # 60fps*3sec
        # response_min=0
        self.response_max = None

        self.auto_radius_range = (self.settings.gui_HSF_radius - 10, self.settings.gui_HSF_radius + 10) 

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

    

    def HSF(self):

        frame = self.current_image_gray     
        if self.now_mode == self.cv_mode[1]:

            
            prev_res_len = len(self.response_list)
            # adjustment of radius
            if prev_res_len == 1:
                # len==1==self.response_list==[self.settings.gui_HSF_radius]
                self.cvparam.radius = self.auto_radius_range[0]
            elif prev_res_len == 2:
                # len==2==self.response_list==[self.settings.gui_HSF_radius, self.auto_radius_range[0]]
                self.cvparam.radius = self.auto_radius_range[1]
            elif prev_res_len == 3:
                # len==3==self.response_list==[self.settings.gui_HSF_radius,self.auto_radius_range[0],self.auto_radius_range[1]]
                sort_res = sorted(self.response_list, key=lambda x: x[1])[0]
                # Extract the radius with the lowest response value
                if sort_res[0] == self.settings.gui_HSF_radius:
                    # If the default value is best, change self.now_mode to init after setting radius to the default value.
                    self.cvparam.radius = self.settings.gui_HSF_radius
                    self.now_mode = self.cv_mode[2] if not self.skip_blink_detect else self.cv_mode[3]
                    self.response_list = []
                elif sort_res[0] == self.auto_radius_range[0]:
                    self.radius_cand_list = [i for i in range(self.auto_radius_range[0], self.settings.gui_HSF_radius, self.default_step[0])][1:]
                    # self.default_step is defined separately for xy, but radius is shared by xy, so it may be buggy
                    # It should be no problem to set it to anything other than self.default_step
                    self.cvparam.radius = self.radius_cand_list.pop()
                else:
                    self.radius_cand_list = [i for i in range(self.settings.gui_HSF_radius, self.auto_radius_range[1], self.default_step[0])][1:]
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
        upper_x = center_x + 25 #TODO make this a setting
        lower_x = center_x - 25
        upper_y = center_y + 25
        lower_y = center_y - 25
        
        # Crop the image using the calculated bounds
        cropped_image = gray_frame[lower_y:upper_y, lower_x:upper_x] # y is 50px, x is 45? why?
        
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
                print("[WARN] HSF: Something's wrong.")
            else:
                # If the average value of cropped_image is greater than self.response_max
                # (i.e., if the cropimage is whitish
                if self.response_max is not None and cv2.mean(cropped_image)[0] > self.response_max:
                    # blink
                    
                    cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), -1)
        # If you want to update self.response_max. it may be more cost-effective to rewrite self.response_list in the following way
        # https://stackoverflow.com/questions/42771110/fastest-way-to-left-cycle-a-numpy-array-like-pop-push-for-a-queue
        
        


        out_x, out_y = cal_osc(self, center_x, center_y)
        
        cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), -1)
    # print(center_x, center_y)

        try:
            if self.settings.gui_BLINK: #tbh this is redundant, the algo already has blink detection built in
                self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, self.blinkvalue))
            else:
                self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False))
            self.failed = 0
            
        except:
            if self.settings.gui_BLINK: #tbh this is redundant, the algo already has blink detection built in
                self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, 0, 0, 0, self.blinkvalue))
            else:
                self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, 0, 0, 0, False))
            self.failed = self.failed + 1

            
        if self.now_mode != self.cv_mode[0] and self.now_mode != self.cv_mode[1]:
            if cropped_image.size < 400:
                pass
    
        if self.now_mode == self.cv_mode[0]:
            self.now_mode = self.cv_mode[1]

        return 
            #self.output_images_and_update(thresh, EyeInformation(InformationOrigin.FAILURE, 0, 0, 0, False))
        # return

        #self.output_images_and_update(larger_threshold,EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False),)
    # return
        #self.output_images_and_update(larger_threshold, EyeInformation(InformationOrigin.HSF, 0, 0, 0, True))




    def ALGOSELECT(self): 

        if self.failed == 0 and self.firstalgo != None: 
            print('first')
            self.firstalgo()
            
        else:
            self.failed = self.failed + 1

        if self.failed == 1 and self.secondalgo != None:
            print('2nd')
            self.secondalgo() #send the tracking algos previous fail number, in algo if we pass set to 0, if fail, + 1
            
        else:
            self.failed = self.failed + 1

        if self.failed == 2 and self.thirdalgo != None:
            print('3rd')
            self.thirdalgo()
            
        else:
            self.failed = self.failed + 1

        if self.failed == 3 and self.fourthalgo != None:
            print('4th')
            self.fourthalgo()
            
        else:
            self.failed = 0 # we have reached last possible algo and it is disabled, move to first algo
        print(self.failed)



    def run(self):

        self.firstalgo = None
        self.secondalgo = None
        self.thirdalgo = None
        self.fourthalgo = None
        #set algo priorities
        """"
        if self.settings.gui_HSF and self.settings.gui_HSFP == 1: #I feel like this is super innefficient though it only runs at startup and no solution is coming to me atm
            self.firstalgo = self.HSF
        elif self.settings.gui_HSF and self.settings.gui_HSFP == 2:
            self.secondalgo = self.HSF
        elif self.settings.gui_HSF and self.settings.gui_HSFP == 3:
            self.thirdalgo = self.HSF
        elif self.settings.gui_HSF and self.settings.gui_HSFP == 4:
            self.fourthalgo = self.HSF

        if self.settings.gui_RANSAC3D and self.settings.gui_RANSAC3DP == 1:
            self.firstalgo = self.RANSAC3D
        elif self.settings.gui_RANSAC3D and self.settings.gui_RANSAC3DP == 2:
            self.secondalgo = self.RANSAC3D
        elif self.settings.gui_RANSAC3D and self.settings.gui_RANSAC3DP == 3:
            self.thirdalgo = self.RANSAC3D
        elif self.settings.gui_RANSAC3D and self.settings.gui_RANSAC3DP == 4:
            self.fourthalgo = self.RANSAC3D

        if self.settings.gui_HSRAC and self.settings.gui_HSRACP == 1:
            self.firstalgo = self.HSRAC
        elif self.settings.gui_HSRAC and self.settings.gui_HSRACP == 2:
            self.secondalgo = self.HSRAC
        elif self.settings.gui_HSRAC and self.settings.gui_HSRACP == 3:
            self.thirdalgo = self.HSRAC
        elif self.settings.gui_HSRAC and self.settings.gui_HSRACP == 4:
            self.fourthalgo = self.HSRAC

        if self.settings.gui_BLOB and self.settings.gui_BLOBP == 1:
            self.firstalgo = self.BLOB
        elif self.settings.gui_BLOB and self.settings.gui_BLOBP == 2:
            self.secondalgo = self.BLOB
        elif self.settings.gui_BLOB and self.settings.gui_BLOBP == 3:
            self.thirdalgo = self.BLOB
        elif self.settings.gui_BLOB and self.settings.gui_BLOBP == 4:
            self.fourthalgo = self.BLOB
        
        """
       # if self.settings.gui_BLOBP
     #   if self.settings.gui_HSFP
      #  if self.settings.gui_RANSAC3DP

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
            self.current_image_gray_clean = self.current_image_gray.copy() #copy this frame to have a clean image for blink algo
           # print(self.settings.gui_RANSAC3D)

            BLINK(self)

            cx, cy, thresh =  HSRAC(self)
            out_x, out_y = cal_osc(self, cx, cy)
            if cx == 0:
                self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, out_x, out_y, 0, True)) #update app
            else:
                self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, out_x, out_y, 0, self.blinkvalue))
            

           # cx, cy, thresh =  RANSAC3D(self)
           # out_x, out_y = cal_osc(self, cx, cy)
           # self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, out_x, out_y, 0, False)) #update app


          #  cx, cy, larger_threshold = BLOB(self)
          #  out_x, out_y = cal_osc(self, cx, cy)
           # self.output_images_and_update(larger_threshold, EyeInformation(InformationOrigin.BLOB, out_x, out_y, 0, False)) #update app

            #center_x, center_y, frame = HSF(self) #run algo
            #out_x, out_y = cal_osc(self, center_x, center_y) #filter and calibrate
            #self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False)) #update app
            
           # self.ALGOSELECT() #run our algos in priority order set in settings
            

        


        
