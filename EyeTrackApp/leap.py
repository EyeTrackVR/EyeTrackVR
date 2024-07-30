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

def run_model(input_queue, output_queue, session):
    while True:
        frame = input_queue.get()
        if frame is None:
            break

        img_np = np.array(frame)
        img_np = img_np.astype(np.float32) / 255.0
        gray_img = 0.299 * img_np[:, :, 0] + 0.587 * img_np[:, :, 1] + 0.114 * img_np[:, :, 2]

        # Add the channel and batch dimensions
        gray_img = np.expand_dims(gray_img, axis=0)  # Add channel dimension
        img_np = np.expand_dims(gray_img, axis=0)  # Add batch dimension

        ort_inputs = {session.get_inputs()[0].name: img_np}
        pre_landmark = session.run(None, ort_inputs)

        pre_landmark = np.reshape(pre_landmark, (-1, 2))
        output_queue.put((frame, pre_landmark))


def run_onnx_model(queues, session, frame):
    for i in range(len(queues)):
        if not queues[i].full():
            queues[i].put(frame)
            break




def to_numpy(tensor):
    return tensor.detach().cpu().numpy() if tensor.requires_grad else tensor.cpu().numpy()


class LEAP_C(object):
    def __init__(self):
        self.last_lid = None
        self.current_image_gray = None
        self.current_image_gray_clean = None
        onnxruntime.disable_telemetry_events()
        # Config variables
        self.num_threads = 2  # Number of python threads to use (using ~1 more than needed to achieve wanted fps yields lower cpu usage)
        self.queue_max_size = 1  # Optimize for best CPU usage, Memory, and Latency. A maxsize is needed to not create a potential memory leak.
        self.model_path = resource_path(models / 'LEAP071024_E16.onnx')

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
        opts.intra_op_num_threads = 1  # big perf hit
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.optimized_model_filepath = ""

        self.one_euro_filter_float = OneEuroFilter(np.random.rand(1, 2), min_cutoff=0.0004, beta=0.9) #min_cutoff=5, beta=0.007
        self.dmax = 0
        self.dmin = 0
        self.openlist = []
        self.x = 0
        self.y = 0
        self.maxlist = []
        self.previous_time = None
        self.old_matrix = None
        self.total_velocity_new = 0
        self.total_velocity_avg = 0
        self.total_velocity_old = 0
        self.old_per = 0.0
        self.delta_per_neg = 0.0
        self.ort_session1 = onnxruntime.InferenceSession(self.model_path, opts, providers=["CPUExecutionProvider"])

        threads = []
        for i in range(self.num_threads):
            thread = threading.Thread(
                target=run_model,
                args=(self.queues[i], self.output_queue, self.ort_session1),
                name=f"Thread {i}",
            )
            threads.append(thread)
            thread.start()

    def leap_run(self):
        img = self.current_image_gray_clean.copy()

        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        img_height, img_width = img.shape[:2]  # Move outside the loop

        frame = cv2.resize(img, (112, 112))
        imgvis = self.current_image_gray.copy()
        run_onnx_model(self.queues, self.ort_session1, frame)

        if not self.output_queue.empty():
            frame, pre_landmark = self.output_queue.get()

            for point in pre_landmark:
                x, y = point  # Assuming point is a tuple (x, y)

                # Scale the coordinates to image width and height
                x = int(x * img_width)
                y = int(y * img_height)

                cv2.circle(imgvis, (int(x), int(y)), 3, (255, 255, 0), -1)
                cv2.circle(imgvis, (int(x), int(y)), 1, (0, 0, 255), -1)


            d1 = math.dist(pre_landmark[1], pre_landmark[3])
            # a more fancy method could be used taking into acount the relative size of the landmarks so that
            # weirdness can be acounted for better
            d2 = math.dist(pre_landmark[2], pre_landmark[4])
            d = (d1 + d2) / 2
            # by averaging both sets we can get less error?
            # considering both point sets should smooth things out between l&r eyes

            try:
                if d >= np.percentile(
                    self.openlist, 80  # do not go above 85, but this value can be tuned
                ):  # an additional approach could be using the place where on average it is most stable, denoting
                    # what distance is the most stable "open"
                    self.maxlist.append(d)

                if len(self.maxlist) > 2000:  # I feel that this is very cpu intensive. think of a better method
                    self.maxlist.pop(0)

                # this should be the average most open value, the average of top 2000 values in rolling calibration
                # with this we can use it as the "open state" (0.7, for expanded squeeze)

                # weighted values to shift slightly to max value
                normal_open = np.percentile(self.openlist, 70)

            except:
                normal_open = 0.8

            if len(self.openlist) < 5000:  # TODO expose as setting?
                self.openlist.append(d)
            else:
                self.openlist.pop(0)
                self.openlist.append(d)

            try:
                per = (d - normal_open) / (np.percentile(self.openlist, 1.7) - normal_open)
                per = 1 - per
                per = per - 0.2  # allow for eye widen? might require a more legit math way but this makes sense.
                per = np.clip(per, 0.0, 1.0)

            except:
                per = 0.8
                pass

            x = pre_landmark[6][0]
            y = pre_landmark[6][1]

            self.last_lid = per
            calib_array = np.array([per, per]).reshape(1, 2)

            per = self.one_euro_filter_float(calib_array)

            per = per[0][0]

            if per <= 0.25:  # TODO: EXPOSE AS SETTING
                per = 0.0

            return imgvis, float(x), float(y), per

        imgvis = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        return imgvis, 0, 0, 0


class External_Run_LEAP(object):
    def __init__(self):
        self.algo = LEAP_C()

    def run(self, current_image_gray, current_image_gray_clean):
        self.algo.current_image_gray = current_image_gray
        self.algo.current_image_gray_clean = current_image_gray_clean
        img, x, y, per = self.algo.leap_run()

        return img, x, y, per