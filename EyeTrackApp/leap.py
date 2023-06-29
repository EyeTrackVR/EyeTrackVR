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

frames = 0

def run_model(input_queue, output_queue, session):
    while True:
        frame = input_queue.get()
        if frame is None:
            break

       # to_tensor = transforms.ToTensor()
       # img_tensor = to_tensor(frame)
       # img_tensor.unsqueeze_(0)
       # img_np = img_tensor.numpy()
        img_np = np.array(frame)
        # Normalize the pixel values to [0, 1] and convert the data type to float32
        img_np = img_np.astype(np.float32) / 255.0

        # Transpose the dimensions from (height, width, channels) to (channels, height, width)
        img_np = np.transpose(img_np, (2, 0, 1))

        # Add a batch dimension
        img_np = np.expand_dims(img_np, axis=0)
        ort_inputs = {session.get_inputs()[0].name: img_np}
        pre_landmark = session.run(None, ort_inputs)

        pre_landmark = pre_landmark[1]
        pre_landmark = np.reshape(pre_landmark, (22, 2))
        output_queue.put((frame, pre_landmark))




class LEAP_C(object):
    def __init__(self):
        onnxruntime.disable_telemetry_events()
        # Config variables
        self.num_threads = 2  # Number of python threads to use (using ~1 more than needed to acheive wanted fps yeilds lower cpu usage)
        self.queue_max_size = 3  # Optimize for best CPU usage, Memory, and Latency. A maxsize is needed to not create a potential memory leak.
        self.model_path = 'Models/mommy062023.onnx'
        self.interval = 1  # FPS print update rate
        self.low_priority = True  # set process priority to low
        self.print_fps = True
        # Init variables
        self.frames = 0
        self.queues = []
        self.threads = []
        self.model_output = np.zeros((22, 2))
        self.output_queue = Queue(maxsize=self.queue_max_size)
        self.start_time = time.time()

        for _ in range(self.num_threads):
            self.queue = Queue(maxsize=self.queue_max_size)
            self.queues.append(self.queue)

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.optimized_model_filepath = ''
        self.ort_session = onnxruntime.InferenceSession(self.model_path, opts, providers=['CPUExecutionProvider'])

        if self.low_priority:
            process = psutil.Process(os.getpid())  # set process priority to low
            try:
                sys.getwindowsversion()
            except AttributeError:
                process.nice(0)  # UNIX: 0 low 10 high
                process.nice()
            else:
                process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)  # Windows
                process.nice()
                # See https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getpriorityclass#return-value for values
        min_cutoff = 0.04
        beta = 0.9
        # print(np.random.rand(22, 2))
        # noisy_point = np.array([1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1])
        one_euro_filter = OneEuroFilter(
            np.random.rand(22, 2),
            min_cutoff=min_cutoff,
            beta=beta
        )
        self.dmax = 0
        self.dmin = 0
        self.x = 0
        self.y = 0


        self.ort_session1 = onnxruntime.InferenceSession(
            "Models/mommy062023.onnx", opts,
            providers=['CPUExecutionProvider'])
        # ort_session1 = onnxruntime.InferenceSession("C:/Users/beaul/PycharmProjects/EyeTrackVR/EyeTrackApp/Models/mommy062023.onnx", opts, providers=['DmlExecutionProvider'])
        threads = []
        for i in range(self.num_threads):
            thread = threading.Thread(target=run_model, args=(self.queues[i], self.output_queue, self.ort_session1),
                                      name=f"Thread {i}")
            threads.append(thread)
            thread.start()

    def to_numpy(self, tensor):
        return tensor.detach().cpu().numpy() if tensor.requires_grad else tensor.cpu().numpy()



    def run_onnx_model(self, queues, session, frame):
        for i in range(len(queues)):
            if not queues[i].full():
                queues[i].put(frame)
                break
    def leap_run(self):

        img = self.current_image_gray.copy()
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        # img = imutils.rotate(img, angle=320)
        img_height, img_width = img.shape[:2]  # Move outside the loop


        frame = cv2.resize(img, (112, 112))
        self.run_onnx_model(self.queues, self.ort_session1, frame)

        if not self.output_queue.empty():

            frame, pre_landmark = self.output_queue.get()
            # frame = cv2.resize(frame, (112, 112))

            for point in pre_landmark:
                x, y = point
                cv2.circle(img, (int(x * img_width), int(y * img_height)), 2, (0, 0, 50), -1)
            cv2.circle(img, tuple(int(x*112) for x in pre_landmark[4]), 1, (255, 255, 0), -1)
            cv2.circle(img, tuple(int(x*112) for x in pre_landmark[12]), 1, (255, 255, 0), -1)
            cv2.circle(img, tuple(int(x*112) for x in pre_landmark[17]), 1, (255, 255, 255), -1)
        #    print(pre_landmark)
            d = math.dist(pre_landmark[4], pre_landmark[12])

            if d > self.dmax:
                self.dmax = d
            if d < self.dmin:
                self.dmin = d

            try:
                per = (((d - self.dmax)) / (self.dmin - self.dmax))
                per = 1 - per
            except:
                pass
            x = pre_landmark[17][0]
            y = pre_landmark[17][1]
            frame = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            return frame, float(x), float(y), per


        frame = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        return frame, 0, 0, 0

class External_Run_LEAP(object):
    def __init__(self):
        self.algo = LEAP_C()

    def run(self, current_image_gray):
        self.algo.current_image_gray = current_image_gray
        img, x, y, per = self.algo.leap_run()
        return img, x, y, per