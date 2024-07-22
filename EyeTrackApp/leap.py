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
     #  img_np = np.transpose(img_np, (2, 0, 1))
       # img_np = np.expand_dims(img_np, axis=0)
        ort_inputs = {session.get_inputs()[0].name: img_np}
        pre_landmark = session.run(None, ort_inputs)

    #    pre_landmark = pre_landmark[1]
       # pre_landmark = np.reshape(pre_landmark, (12, 2))
        pre_landmark = np.reshape(pre_landmark, (-1, 2))
        output_queue.put((frame, pre_landmark))


def run_onnx_model(queues, session, frame):
    for i in range(len(queues)):
        if not queues[i].full():
            queues[i].put(frame)
            break


def calculate_velocity_vectors(old_matrix, current_matrix, time_difference):
    # Check if both matrices have the same number of points
    if len(old_matrix) != len(current_matrix):
        raise ValueError("Both matrices must have the same number of points")

    # Indices of the points to be considered
    indices = [1, 2, 4, 5]

    velocity_vectors = []

    for i in indices:
        old_y = old_matrix[i]
        current_y = current_matrix[i]

        # Calculate displacement and velocity using the y-values
        displacement_y = current_y - old_y
        velocity_y = displacement_y / time_difference

        velocity_vectors.append(velocity_y)

    # Calculate the total velocity as the mean of the absolute values of the velocity vectors
    total_velocity = np.mean([abs(velocity) for velocity in velocity_vectors])

    return total_velocity


def to_numpy(tensor):
    return tensor.detach().cpu().numpy() if tensor.requires_grad else tensor.cpu().numpy()


class LEAP_C(object):
    def __init__(self):
        self.last_lid = None
        self.current_image_gray = None
        self.current_image_gray_clean = None
        onnxruntime.disable_telemetry_events()
        # Config variables
        self.num_threads = 1  # Number of python threads to use (using ~1 more than needed to achieve wanted fps yields lower cpu usage)
        self.queue_max_size = 1  # Optimize for best CPU usage, Memory, and Latency. A maxsize is needed to not create a potential memory leak.
        self.model_path = resource_path(models / 'LEAP071024_E16.onnx')

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
        opts.intra_op_num_threads = 1  # big perf hit
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
        self.previous_time = None
        self.old_matrix = None
        self.total_velocity_new = 0
        self.total_velocity_avg = 0
        self.total_velocity_old = 0
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


            #  x1, y1 = pre_landmark[1]
            #  x2, y2 = pre_landmark[3]

            #  x3, y3 = pre_landmark[4]
            #  x4, y4 = pre_landmark[2]

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
                normal_open = np.percentile(self.openlist, 70) #((sum(self.maxlist) / len(self.maxlist)) * 0.90 + max(self.openlist) * 0.10) / (
              #      0.95 + 0.15
              #  )
#
            except:
                normal_open = 0.8

            if len(self.openlist) < 5000:  # TODO expose as setting?
                self.openlist.append(d)
            else:
                self.openlist.pop(0)
                self.openlist.append(d)

            try:
                per = (d - normal_open) / (np.percentile(self.openlist, 2) - normal_open)

            #     oldper = (d - max(self.openlist)) / (
            #       min(self.openlist) - max(self.openlist)
            #    )  # TODO: remove when testing is done

                per = 1 - per
                per = per - 0.2  # allow for eye widen? might require a more legit math way but this makes sense.
                per = min(per, 1.0)  # clamp to 1.0 max
                per = max(per, 0.0)  # clamp to 1.0 min

            except:
                per = 0.8
                pass

            x = pre_landmark[6][0]
            y = pre_landmark[6][1]

            current_time = time.time()  # Get the current time
            # Extract current matrix
            current_matrix = [point[1] for point in pre_landmark]

            # Calculate time difference
            if self.previous_time is not None:
                time_difference = current_time - self.previous_time

                # Calculate velocity vectors if we have old data
                if self.old_matrix is not None:
                    self.total_velocity_new = calculate_velocity_vectors(self.old_matrix, current_matrix, time_difference)
                   # print(f"Velocity Vectors:", total_velocity)

            # Update old matrix and previous time for the next iteration
            self.old_matrix = [point[1] for point in pre_landmark]
            self.previous_time = current_time

            self.last_lid = per
            calib_array = np.array([per, per]).reshape(1, 2)

            per = self.one_euro_filter_float(calib_array)

            per = per[0][0]

            if per <= 0.25:  # TODO: EXPOSE AS SETTING
                per = 0.0

            #print(per)

            self.total_velocity_avg = (self.total_velocity_new + self.total_velocity_old) / 2
            self.total_velocity_old = self.total_velocity_new

            print(self.total_velocity_avg)
            if self.last_lid == 0.0:
                if self.total_velocity_avg > 1:
                    pass
                else:
                    per = 0.0

            if self.total_velocity_avg > 1.5:
                per = 0.0
                # this should be tuned, i could make this auto calib based on min from a list of per values.

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