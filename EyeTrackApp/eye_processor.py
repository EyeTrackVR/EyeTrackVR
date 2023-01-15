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

import importlib
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

        self.skip_blink_detect = False

        #blink
        self.max_ints = []
        self.max_int = 0
        self.min_int = 4000000000000
        self.frames = 0 
        self.blinkvalue = False
        
        self.prev_x = None
        self.prev_y = None

        

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
        try:
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
        except: # If this fails it likely means that the images are not the same size for some reason.
            print('[ERROR] Size of frames to display are of unequal sizes.')

            pass
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

    def BLINKM(self):
        self.blinkvalue = BLINK(self)
  

    def HSRACM(self):
        cx, cy, thresh, gray_frame, self.blinkvalue = External_Run.HSRACS(self)
        self.current_image_gray = gray_frame
      #  thresh = gray_frame
        if self.prev_x == None:
            self.prev_x = cx
            self.prev_y = cy
        #print(self.prev_x, self.prev_y, cx, cy)
       # if (cx - self.prev_x) <= 45 and (cy - self.prev_y) <= 45 :
          #  self.prev_x = cx
          #  self.prev_y = cy
        print(self.blinkvalue)
        out_x, out_y = cal_osc(self, cx, cy)
        if cx == 0:
            self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, out_x, out_y, 0, self.blinkvalue)) #update app
        else:

            self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, out_x, out_y, 0, self.blinkvalue))
      #  else:
      #      print("EYE MOVED TOO FAST")
       #     self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, 0, 0, 0, False))
    def HSFM(self):
        cx, cy, frame = External_Run_HSF.HSFS(self)
        out_x, out_y = cal_osc(self, cx, cy)
        if cx == 0:
            self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, True)) #update app
        else:
            self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, self.blinkvalue))
        

    def RANSAC3DM(self):
        cx, cy, thresh = RANSAC3D(self)
        out_x, out_y = cal_osc(self, cx, cy)
        if cx == 0:
            self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, out_x, out_y, 0, True)) #update app
        else:
            self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, out_x, out_y, 0, self.blinkvalue))
        
    def BLOBM(self):
        cx, cy, thresh = BLOB(self)
        out_x, out_y = cal_osc(self, cx, cy)
        if cx == 0:
            self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, out_x, out_y, 0, True)) #update app
        else:
            self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, out_x, out_y, 0, self.blinkvalue))
        




    def ALGOSELECT(self): 

        if self.failed == 0 and self.firstalgo != None: 
            self.firstalgo()
        else:
            self.failed = self.failed + 1

        if self.failed == 1 and self.secondalgo != None:  #send the tracking algos previous fail number, in algo if we pass set to 0, if fail, + 1
            self.secondalgo()
        else:
            self.failed = self.failed + 1

        if self.failed == 2 and self.thirdalgo != None:
            self.thirdalgo()
        else:
            self.failed = self.failed + 1

        if self.failed == 3 and self.fourthalgo != None:
            self.fourthalgo()
        else:
            self.failed = 0 # we have reached last possible algo and it is disabled, move to first algo




    def run(self):

        self.firstalgo = None
        self.secondalgo = None
        self.thirdalgo = None
        self.fourthalgo = None
        #set algo priorities

        if self.settings.gui_HSF and self.settings.gui_HSFP == 1: #I feel like this is super innefficient though it only runs at startup and no solution is coming to me atm
            self.firstalgo = self.HSFM
        elif self.settings.gui_HSF and self.settings.gui_HSFP == 2:
            self.secondalgo = self.HSFM
        elif self.settings.gui_HSF and self.settings.gui_HSFP == 3:
            self.thirdalgo = self.HSFM
        elif self.settings.gui_HSF and self.settings.gui_HSFP == 4:
            self.fourthalgo = self.HSFM

        if self.settings.gui_RANSAC3D and self.settings.gui_RANSAC3DP == 1:
            self.firstalgo = self.RANSAC3DM
        elif self.settings.gui_RANSAC3D and self.settings.gui_RANSAC3DP == 2:
            self.secondalgo = self.RANSAC3DM
        elif self.settings.gui_RANSAC3D and self.settings.gui_RANSAC3DP == 3:
            self.thirdalgo = self.RANSAC3DM
        elif self.settings.gui_RANSAC3D and self.settings.gui_RANSAC3DP == 4:
            self.fourthalgo = self.RANSAC3DM

        if self.settings.gui_HSRAC == True and self.settings.gui_HSRACP == 1:
            self.firstalgo = self.HSRACM
        elif self.settings.gui_HSRAC and self.settings.gui_HSRACP == 2:
            self.secondalgo = self.HSRACM
        elif self.settings.gui_HSRAC and self.settings.gui_HSRACP == 3:
            self.thirdalgo = self.HSRACM
        elif self.settings.gui_HSRAC and self.settings.gui_HSRACP == 4:
            self.fourthalgo = self.HSRACM

        if self.settings.gui_BLOB and self.settings.gui_BLOBP == 1:
            self.firstalgo = self.BLOBM
        elif self.settings.gui_BLOB and self.settings.gui_BLOBP == 2:
            self.secondalgo = self.BLOBM
        elif self.settings.gui_BLOB and self.settings.gui_BLOBP == 3:
            self.thirdalgo = self.BLOBM
        elif self.settings.gui_BLOB and self.settings.gui_BLOBP == 4:
            self.fourthalgo = self.BLOBM

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

           # BLINK(self)

           # cx, cy, thresh =  HSRAC(self)
           # out_x, out_y = cal_osc(self, cx, cy)
           # if cx == 0:
          #      self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, out_x, out_y, 0, True)) #update app
           # else:
          #      self.output_images_and_update(thresh, EyeInformation(InformationOrigin.HSRAC, out_x, out_y, 0, self.blinkvalue))
            

           # cx, cy, thresh =  RANSAC3D(self)
           # out_x, out_y = cal_osc(self, cx, cy)
           # self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, out_x, out_y, 0, False)) #update app


          #  cx, cy, larger_threshold = BLOB(self)
          #  out_x, out_y = cal_osc(self, cx, cy)
           # self.output_images_and_update(larger_threshold, EyeInformation(InformationOrigin.BLOB, out_x, out_y, 0, False)) #update app

            #center_x, center_y, frame = HSF(self) #run algo
            #out_x, out_y = cal_osc(self, center_x, center_y) #filter and calibrate
            #self.output_images_and_update(frame, EyeInformation(InformationOrigin.HSF, out_x, out_y, 0, False)) #update app
            
            self.ALGOSELECT() #run our algos in priority order set in settings
            self.BLINKM()

        


        
