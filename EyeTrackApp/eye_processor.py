"""
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

HSR By: PallasNeko (Optimization Wizard, Contributor), Summer#2406 (Main Algorithm Engineer)  
RANSAC 3D By: Summer#2406 (Main Algorithm Engineer), Pupil Labs (pye3d), PallasNeko (Optimization)
BLOB By: Prohurtz (Main App Developer)
Algorithm App Implementations By: Prohurtz, qdot (Initial App Creator), PallasNeko

Additional Contributors: [Assassin], Summer404NotFound, lorow, ZanzyTHEbar

Copyright (c) 2023 EyeTrackVR <3
------------------------------------------------------------------------------------------------------
"""

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
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC, resource_path
import importlib
from osc import EyeId
from osc_calibrate_filter import *
from daddy import External_Run_DADDY
from leap import External_Run_LEAP
from haar_surround_feature import External_Run_HSF
from blob import *
from ransac import *
from blink import *
from utils.img_utils import circle_crop
from eye import EyeInfo, EyeInfoOrigin
from intensity_based_openness import *


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
    PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)


class EyeProcessor:
    def __init__(
        self,
        config: "EyeTrackCameraConfig",
        settings: "EyeTrackSettingsConfig",
        baseconfig: "EyetrackConfig",
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        capture_queue_incoming: "queue.Queue",
        image_queue_outgoing: "queue.Queue",
        eye_id,
    ):
        self.main_config = EyeTrackSettingsConfig
        self.config = config
        self.settings = settings
        self.eye_id = eye_id
        # Cross-thread communication management
        self.capture_queue_incoming = capture_queue_incoming
        self.image_queue_outgoing = image_queue_outgoing
        self.cancellation_event = cancellation_event
        self.capture_event = capture_event
        self.eye_id = eye_id
        self.baseconfig = baseconfig
        self.filterlist = []

        # Cross algo state
        self.lkg_projected_sphere = None
        self.xc = 20
        self.yc = 20
        self.cc_radius = 40

        # Image state
        self.previous_image = None
        self.current_image = None
        self.current_image_gray = None
        self.current_frame_number = None
        self.current_fps = None
        self.threshold_image = None
        self.thresh = None
        # Calibration Values
        self.xoff = 1
        self.yoff = 1
        # Keep large in order to recenter correctly
        self.calibration_frame_counter = None
        self.eyeoffx = 1
        self.printcal = True

        self.xmax = -69420
        self.xmin = 69420
        self.ymax = -69420
        self.ymin = 69420
        self.blink_clear = False
        self.cct = 200
        self.cccs = False
        self.ts = 10
        self.previous_rotation = self.config.rotation_angle
        self.camera_model = None
        self.detector_3d = None
        self.er_hsf = None
        self.er_hsrac = None
        self.er_daddy = None
        self.er_leap = None
        self.ibo = IntensityBasedOpeness(self.eye_id)
        self.roi_include_set = {"rotation_angle", "roi_window_x", "roi_window_y"}
        self.failed = 0
        self.skip_blink_detect = False
        self.out_y = 0.0
        self.out_x = 0.0
        self.rawx = 0.0
        self.rawy = 0.0
        self.eyeopen = 0.9
        self.max_ints = []
        self.max_int = 0
        self.min_int = 4000000000000
        self.frames = 0
        self.blinkvalue = False
        self.hasrac_en = False
        self.radius = 10
        self.past_blink = 0.7
        self.prev_x = None
        self.prev_y = 0.1
        self.prev_x_list = []
        self.prev_y_list = []
        self.blink_list = []
        self.ran_blink_check_for_file = True
        self.bd_blink = False
        self.current_algo = EyeInfoOrigin.HSRAC

        try:
            min_cutoff = float(self.settings.gui_min_cutoff)  # 0.0004
            beta = float(self.settings.gui_speed_coefficient)  # 0.9
        except:
            print("\033[93m[WARN] OneEuroFilter values must be a legal number.\033[0m")
            min_cutoff = 0.0004
            beta = 0.9
        noisy_point = np.array([1, 1])
        self.one_euro_filter = OneEuroFilter(
            noisy_point, min_cutoff=min_cutoff, beta=beta
        )

    def output_images_and_update(self, threshold_image, output_information: EyeInfo):
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
        except:  # If this fails it likely means that the images are not the same size for some reason.
            print(
                "\033[91m[ERROR] Size of frames to display are of unequal sizes.\033[0m"
            )

            pass

    def capture_crop_rotate_image(self):
        # Get our current frame

        try:
            # Get frame from capture source, crop to ROI
            self.current_image = self.current_image[
                int(self.config.roi_window_y) : int(
                    self.config.roi_window_y + self.config.roi_window_h
                ),
                int(self.config.roi_window_x) : int(
                    self.config.roi_window_x + self.config.roi_window_w
                ),
            ]
            self.ibo.change_roi(self.config.dict(include=self.roi_include_set))

        except:
            # Failure to process frame, reuse previous frame.
            self.current_image = self.previous_image
            print("\033[91m[ERROR] Frame capture issue detected.\033[0m")

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
            avg_color_per_row = np.average(self.current_image, axis=0)
            avg_color = np.average(avg_color_per_row, axis=0)
            ar, ag, ab = avg_color
            self.current_image = cv2.warpAffine(
                self.current_image,
                rotation_matrix,
                (cols, rows),
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(ar + 10, ag + 10, ab + 10),  # (255, 255, 255),
            )
            self.current_image_white = cv2.warpAffine(
                self.current_image,
                rotation_matrix,
                (cols, rows),
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            )
            return True
        except:
            pass

    def UPDATE(self):

        if self.settings.gui_BLINK:
            self.eyeopen = BLINK(self)

        if self.settings.gui_IBO and self.eyeopen != 0.0: #TODO make ransac blink it's pwn self var to rid of this non-sense
            self.eyeopen = self.ibo.intense(
                self.rawx,
                self.rawy,
                self.current_image_white,
                self.settings.ibo_filter_samples,
                self.settings.ibo_average_output_samples,
            )
            if (
                self.eyeopen < self.settings.ibo_fully_close_eye_threshold
            ):  # threshold so the eye fully closes
                self.eyeopen = 0.0

            if self.bd_blink == True:
                pass


        if self.settings.gui_IBO and self.settings.gui_BLINK and self.eyeopen != 0.0:
            ibo = self.ibo.intense(
                self.rawx,
                self.rawy,
                self.current_image_white,
                self.settings.ibo_filter_samples,
                self.settings.ibo_average_output_samples,
            )

            blink = BLINK(self)
            if blink == 0.0:
                self.eyeopen = 0.0
            else:
                self.eyeopen = ibo


        if len(self.prev_y_list) >= 200: # "lock" eye when close/blink IN TESTING, kinda broke
            self.prev_y_list.pop(0)
            self.prev_y_list.append(self.out_y)
        else:
            self.prev_y_list.append(self.out_y)

       # print(abs(self.eyeopen - self.past_blink))
        blink_vec = min(abs(self.eyeopen - self.past_blink), 1) #clamp to 1

        if blink_vec >= 0.1 or blink_vec == 0.0 and (self.out_y - self.prev_y) < 0.0:
            #if blink_vec >= 0.1 or blink_vec == 0.0 and (self.out_y - self.prev_y) < 0.0:
           # self.out_x = sum(self.prev_x_list) / len(self.prev_x_list)
            self.out_y = sum(self.prev_y_list) / len(self.prev_y_list)
         #   print('AVG', self.out_y, len(self.prev_y_list))

        self.past_blink = self.eyeopen
        self.prev_x = self.out_x
        self.prev_y = self.out_y

        self.output_images_and_update(
            self.thresh,
            EyeInfo(self.current_algo, self.out_x, self.out_y, 0, self.eyeopen),
        )
        if self.settings.gui_RANSACBLINK and self.eyeopen == 0.0:
            pass
        else:
            self.eyeopen = 0.9


    def BLINKM(self):
        self.eyeopen = BLINK(self)

    def LEAPM(self):
        self.thresh = self.current_image_gray.copy()
        self.current_image_gray, self.rawx, self.rawy, self.eyeopen = self.er_leap.run(self.current_image_gray) #TODO: make own self var and LEAP toggle
        self.thresh = self.current_image_gray.copy()
        self.out_x, self.out_y = cal.cal_osc(self, self.rawx, self.rawy)
        self.current_algorithm = EyeInfoOrigin.LEAP

    def DADDYM(self):
        # todo: We should have a proper variable for drawing.
        #self.thresh = self.current_image_gray.copy()
        self.thresh = self.current_image_gray.copy()
        self.rawx, self.rawy, self.radius = self.er_daddy.run(
            self.current_image_gray
        )
        # Daddy also uses a one euro filter, so I'll have to use it twice, but I'm not going to think too much about it.
        self.out_x, self.out_y = cal.cal_osc(self, self.rawx, self.rawy)
        self.current_algorithm = EyeInfoOrigin.DADDY

    def HSRACM(self):
        if self.eye_id in [EyeId.LEFT] and self.settings.gui_circular_crop_left:
            self.current_image_gray, self.cct = circle_crop(
                self.current_image_gray, self.xc, self.yc, self.cc_radius, self.cct
            )
        else:
            pass
        if self.eye_id in [EyeId.RIGHT] and self.settings.gui_circular_crop_right:
            self.current_image_gray, self.cct = circle_crop(
                self.current_image_gray, self.xc, self.yc, self.cc_radius, self.cct
            )
        else:
            pass

        self.hasrac_en = True
        # todo: add process to initialise er_hsrac when resolution changes
        self.rawx, self.rawy, self.thresh, self.radius = self.er_hsf.run(
            self.current_image_gray
        )
        self.rawx, self.rawy, self.thresh, ranblink = RANSAC3D(self, True)
        if self.settings.gui_RANSACBLINK: #might be redundant
            self.eyeopen = ranblink

        # print(self.radius)
        # if self.prev_x is None:
        #   self.prev_x = self.rawx
        #  self.prev_y = self.rawy
        self.out_x, self.out_y = cal.cal_osc(self, self.rawx, self.rawy)
        self.current_algorithm = EyeInfoOrigin.HSRAC

    def HSFM(self):
        if self.eye_id in [EyeId.LEFT] and self.settings.gui_circular_crop_left:
            self.current_image_gray, self.cct = circle_crop(
                self.current_image_gray, self.xc, self.yc, self.cc_radius, self.cct
            )
        else:
            pass
        if self.eye_id in [EyeId.RIGHT] and self.settings.gui_circular_crop_right:
            self.current_image_gray, self.cct = circle_crop(
                self.current_image_gray, self.xc, self.yc, self.cc_radius, self.cct
            )
        else:
            pass
        # todo: add process to initialise er_hsf when resolution changes
        self.rawx, self.rawy, self.thresh, self.radius = self.er_hsf.run(self.current_image_gray)
        self.out_x, self.out_y = cal.cal_osc(self, self.rawx, self.rawy)
        self.current_algorithm = EyeInfoOrigin.HSF

    def RANSAC3DM(self):
        if self.eye_id in [EyeId.LEFT] and self.settings.gui_circular_crop_left:
            self.current_image_gray, self.cct = circle_crop(
                self.current_image_gray, self.xc, self.yc, self.cc_radius, self.cct
            )
        else:
            pass
        if self.eye_id in [EyeId.RIGHT] and self.settings.gui_circular_crop_right:
            self.current_image_gray, self.cct = circle_crop(
                self.current_image_gray, self.xc, self.yc, self.cc_radius, self.cct
            )
        else:
            pass
        self.hasrac_en = False
        current_image_gray_copy = (
            self.current_image_gray.copy()
        )  # Duplicate before overwriting in RANSAC3D.
        self.rawx, self.rawy, self.thresh, ranblink = RANSAC3D(self, False)
        if self.settings.gui_RANSACBLINK:
            self.eyeopen = ranblink
        self.out_x, self.out_y = cal.cal_osc(self, self.rawx, self.rawy)
        self.current_algorithm = EyeInfoOrigin.RANSAC

    def BLOBM(self):
        if self.eye_id in [EyeId.LEFT] and self.settings.gui_circular_crop_left:
            self.current_image_gray, self.cct = circle_crop(
                self.current_image_gray, self.xc, self.yc, self.cc_radius, self.cct
            )
        else:
            pass
        if self.eye_id in [EyeId.RIGHT] and self.settings.gui_circular_crop_right:
            self.current_image_gray, self.cct = circle_crop(
                self.current_image_gray, self.xc, self.yc, self.cc_radius, self.cct
            )
        else:
            pass
        self.rawx, self.rawy, self.thresh = BLOB(self)

        self.out_x, self.out_y = cal.cal_osc(self, self.rawx, self.rawy)
        self.current_algorithm = EyeInfoOrigin.BLOB

    def ALGOSELECT(self):
        # self.DADDYM()
        if self.failed == 0 and self.firstalgo != None:
            self.firstalgo()
        else:
            self.failed = self.failed + 1

        if (
            self.failed == 1 and self.secondalgo != None
        ):  # send the tracking algos previous fail number, in algo if we pass set to 0, if fail, + 1
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
            self.failed = self.failed + 1

        if self.failed == 4 and self.fithalgo != None:
            self.fithalgo()
        else:
            self.failed = self.failed + 1

        if self.failed == 5 and self.sixthalgo != None:
            self.sixthalgo()

        else:
            self.failed = 0  # we have reached last possible algo and it is disabled, move to first algo

    def run(self):
        # Run the following somewhere
        # self.daddy = External_Run_DADDY()

        self.firstalgo = None
        self.secondalgo = None
        self.thirdalgo = None
        self.fourthalgo = None
        self.fithalgo = None
        self.sixthalgo = None
        algolist = [None, None, None, None, None, None, None]
        # clear HSF values when page is opened to correctly reflect setting changes
        self.er_hsf = None

        # set algo priorities
        if self.settings.gui_HSF:
            if self.er_hsf is None:
                if self.eye_id in [EyeId.LEFT]:
                    self.er_hsf = External_Run_HSF(
                        self.settings.gui_skip_autoradius,
                        self.settings.gui_HSF_radius_left,
                    )
                else:
                    pass
                if self.eye_id in [EyeId.RIGHT]:
                    self.er_hsf = External_Run_HSF(
                        self.settings.gui_skip_autoradius,
                        self.settings.gui_HSF_radius_right,
                    )
                else:
                    pass
            algolist[self.settings.gui_HSFP] = self.HSFM
        else:
            if self.er_hsf is not None:
                self.er_hsf = None

        if self.settings.gui_HSRAC:
            if self.er_hsf is None:

                if self.eye_id in [EyeId.LEFT]:

                    self.er_hsf = External_Run_HSF(
                        self.settings.gui_skip_autoradius,
                        self.settings.gui_HSF_radius_left,
                    )
                else:
                    pass
                if self.eye_id in [EyeId.RIGHT]:
                    self.er_hsf = External_Run_HSF(
                        self.settings.gui_skip_autoradius,
                        self.settings.gui_HSF_radius_right,
                    )
                else:
                    pass
            algolist[self.settings.gui_HSRACP] = self.HSRACM
        else:
            if not self.settings.gui_HSF and self.er_hsf is not None:
                self.er_hsf = None

        if self.settings.gui_DADDY:
            if self.er_daddy is None:
                self.er_daddy = External_Run_DADDY()
            algolist[self.settings.gui_DADDYP] = self.DADDYM
        else:
            if self.er_daddy is not None:
                self.er_daddy = None

        if self.settings.gui_LEAP:
            if self.er_leap is None:
                self.er_leap = External_Run_LEAP()
            algolist[self.settings.gui_LEAP] = self.LEAPM
        else:
            if self.er_leap is not None:
                self.er_leap = None

        if self.settings.gui_RANSAC3D:
            algolist[self.settings.gui_RANSAC3DP] = self.RANSAC3DM

        if self.settings.gui_BLOB:
            algolist[self.settings.gui_BLOBP] = self.BLOBM

        (
            _,
            self.firstalgo,
            self.secondalgo,
            self.thirdalgo,
            self.fourthalgo,
            self.fithalgo,
            self.sixthalgo,
        ) = algolist

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
            if (
                self.camera_model is None
                or self.detector_3d is None
                or self.camera_model.resolution
                != (
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
            self.current_image_gray_clean = (
                self.current_image_gray.copy()
            )  # copy this frame to have a clean image for blink algo

            self.ALGOSELECT()  # run our algos in priority order set in settings
            self.UPDATE()
