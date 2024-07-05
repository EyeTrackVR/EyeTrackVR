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

LEAP by: Prohurtz
Algorithm App Implementation By: Prohurtz

Copyright (c) 2023 EyeTrackVR <3
LICENSE: GNU GPLv3 
------------------------------------------------------------------------------------------------------
"""


"""
DATASET CONTRIBUTIONS:

@article{ICML2021DS,
  title={TEyeD: Over 20 million real-world eye images with Pupil, Eyelid, and Iris 2D and 3D Segmentations, 2D and 3D Landmarks, 3D Eyeball, Gaze Vector, and Eye Movement Types},
  author={Fuhl, Wolfgang and Kasneci, Gjergji and Kasneci, Enkelejda},
  journal={arXiv preprint arXiv:2102.02115},
  year={2021}
}

@inproceedings{tonsen2016labelled,
  title={Labelled pupils in the wild: a dataset for studying pupil detection in unconstrained environments},
  author={Tonsen, Marc and Zhang, Xucong and Sugano, Yusuke and Bulling, Andreas},
  booktitle={Proceedings of the ninth biennial ACM symposium on eye tracking research \& applications},
  pages={139--142},
  year={2016}
}

+ Custom user annotated and submitted data.
"""



#  LEAP = Lightweight Eyelid And Pupil
import os
os.environ["OMP_NUM_THREADS"] = "1"
import onnxruntime
import numpy as np
import cv2
import time
import math
from queue import Queue
import threading
from one_euro_filter import OneEuroFilter
import psutil, os
import sys
from utils.misc_utils import resource_path
from pathlib import Path

frames = 0
models = Path("Models")

class LEAP_C(object):
    def __init__(self):
        onnxruntime.disable_telemetry_events()
        # Config variables
        self.num_threads = 1  # Number of python threads to use (using ~1 more than needed to achieve wanted fps yields lower cpu usage)
        self.queue_max_size = 1  # Optimize for best CPU usage, Memory, and Latency. A maxsize is needed to not create a potential memory leak.
        self.model_path = resource_path(models / 'LEAP062120246epoch.onnx')

        self.low_priority = (
            False  # set process priority to low (may cause issues when unfocusing? reported by one, not reproducable)
        )
        self.low_priority = (
            True  # set process priority to low (may cause issues when unfocusing? reported by one, not reproducable)
        )
        self.print_fps = False
        # Init variables
        self.frames = 0
        self.queues = []
        self.threads = []
        self.model_output = np.zeros((12, 2))
        self.output_queue = Queue(maxsize=self.queue_max_size)
        self.start_time = time.time()

        for _ in range(self.num_threads):
            self.queue = Queue(maxsize=self.queue_max_size)
            self.queues.append(self.queue)

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 4
        opts.intra_op_num_threads = 1
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.optimized_model_filepath = ""

        if self.low_priority:
            try:
                process = psutil.Process(os.getpid())  # set process priority to low
                try:
                    sys.getwindowsversion()
                except AttributeError:
                    process.nice(0)  # UNIX: 0 low 10 high
                    process.nice()
                else:
                    process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)  # Windows
                    process.nice()
            except:
                pass
                # See https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getpriorityclass#return-value for values
        else:
            pass
        #    process = psutil.Process(os.getpid())  # set process priority to low
        #   try:
        #      sys.getwindowsversion()
        # except AttributeError:
        #    process.nice(10)  # UNIX: 0 low 10 high
        # else:
        #    process.nice(psutil.HIGH_PRIORITY_CLASS)  # Windows
        # See https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getpriorityclass#return-value for values

        min_cutoff = 0.1
        beta = 15.0
        self.one_euro_filter = OneEuroFilter(np.random.rand(12, 2), min_cutoff=min_cutoff, beta=beta)

        self.one_euro_filter_float = OneEuroFilter(np.random.rand(1, 2), min_cutoff=5, beta=0.007)
        self.dmax = 0
        self.dmin = 0
        self.openlist = []
        self.x = 0
        self.y = 0
        self.maxlist = []

        self.ort_session1 = onnxruntime.InferenceSession(self.model_path, opts, providers=["CPUExecutionProvider"])

    def run_model(output_queue, session, frame):

        img_np = np.array(frame)
        img_np = img_np.astype(np.float32) / 255.0
        gray_img = 0.299 * img_np[:, :, 0] + 0.587 * img_np[:, :, 1] + 0.114 * img_np[:, :, 2]

        # Add the channel and batch dimensions
        gray_img = np.expand_dims(gray_img, axis=0)  # Add channel dimension
        img_np = np.expand_dims(gray_img, axis=0)  # Add batch dimension
        #  img_np = np.transpose(img_np, (2, 0, 1))
        # img_np = np.expand_dims(img_np, axis=0)
        ort_inputs = {session.get_inputs()[0].name: img_np}
        pre_landmark = session.run(None, ort_inputs)

        #    pre_landmark = pre_landmark[1]
        # pre_landmark = np.reshape(pre_landmark, (12, 2))
        pre_landmark = np.reshape(pre_landmark, (-1, 2))
     #   output_queue.put((frame, pre_landmark))
        return frame, pre_landmark
    def to_numpy(self, tensor):
        return tensor.detach().cpu().numpy() if tensor.requires_grad else tensor.cpu().numpy()

    def leap_run(self):

        img = self.current_image_gray_clean.copy()

        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        img_height, img_width = img.shape[:2]  # Move outside the loop

        frame = cv2.resize(img, (112, 112))
        imgvis = self.current_image_gray.copy()

        frame, pre_landmark = self.run_model(self.ort_session1, frame)

        for point in pre_landmark:
          #  x, y = (point*112).astype(int)

            x, y = point  # Assuming point is a tuple (x, y)

            # Scale the coordinates to image width and height
            x = int(x * img_width)
            y = int(y * img_height)
         #   x, y = int(x), int(y)  # Ensure x and y are integers

            cv2.circle(imgvis, (int(x), int(y)), 2, (255, 255, 0), -1)



        d1 = math.dist(pre_landmark[1], pre_landmark[3])
        # a more fancy method could be used taking into acount the relative size of the landmarks so that weirdness can be acounted for better
        d2 = math.dist(pre_landmark[2], pre_landmark[4])
        d = (d1 + d2) / 2
        # by averaging both sets we can get less error? i think part of why 1 eye was better than the other is because we only considered one offset points.
        # considering both should smooth things out between eyes

        try:
            if d >= np.percentile(
                self.openlist, 80  # do not go above 85, but this value can be tuned
            ):  # an aditional approach could be using the place where on average it is most stable, denoting what distance is the most stable "open"
                self.maxlist.append(d)

            if len(self.maxlist) > 2000:  # i feel that this is very cpu intensive. think of a better method
                self.maxlist.pop(0)

            # this should be the average most open value, the average of top 2000 values in rolling calibration
            # with this we can use it as the "openstate" (0.7, for expanded squeeze)

            # weighted values to shift slightly to max value
            normal_open = ((sum(self.maxlist) / len(self.maxlist)) * 0.90 + max(self.openlist) * 0.10) / (
                0.95 + 0.15
            )

        except:
            normal_open = 0.8

        if len(self.openlist) < 5000:  # TODO expose as setting?
            self.openlist.append(d)
        else:
            self.openlist.pop(0)
            self.openlist.append(d)

        try:
            per = (d - normal_open) / (min(self.openlist) - normal_open)

            oldper = (d - max(self.openlist)) / (
                min(self.openlist) - max(self.openlist)
            )  # TODO: remove when testing is done

            per = 1 - per
            per = per - 0.2  # allow for eye widen? might require a more legit math way but this makes sense.
            per = min(per, 1.0)  # clamp to 1.0 max
            per = max(per, 0.0)  # clamp to 1.0 min

        #   print("new: ", per, "vs old: ", oldper)

        except:
            per = 0.8
            pass

        x = pre_landmark[6][0]
        y = pre_landmark[6][1]

        self.last_lid = per
        calib_array = np.array([per, per]).reshape(1, 2)

        per = self.one_euro_filter_float(calib_array)

        per = per[0][0]
        #  print(per)
        if per <= 0.2:  # TODO: EXPOSE AS SETTING
            per == 0.0
            # this should be tuned, i could make this auto calib based on min from a list of per values.

        return imgvis, float(x), float(y), per



class External_Run_LEAP(object):
    def __init__(self):
        self.algo = LEAP_C()

    def run(self, current_image_gray, current_image_gray_clean):
        self.algo.current_image_gray = current_image_gray
        self.algo.current_image_gray_clean = current_image_gray_clean
        img, x, y, per = self.algo.leap_run()
        return img, x, y, per


