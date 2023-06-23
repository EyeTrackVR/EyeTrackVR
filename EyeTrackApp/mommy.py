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

MOMMY by: Prohurtz
Algorithm App Implementation By: Prohurtz

Copyright (c) 2023 EyeTrackVR <3
------------------------------------------------------------------------------------------------------
"""
#  MOMMY = Model for Observing Mindful Movement of Your Eyes
import os
os.environ["OMP_NUM_THREADS"] = "1"
import onnxruntime
import numpy as np
from PIL import Image
import torchvision.transforms as transforms
import cv2
import time
import math
from queue import Queue
import threading
from one_euro_filter import OneEuroFilter
frame_count = 0
start_time = time.time()




frames = 0


def run_model(input_queue, output_queue, session):
    while True:
        frame = input_queue.get()
        if frame is None:
            break

        to_tensor = transforms.ToTensor()
        img_tensor = to_tensor(frame)
        img_tensor.unsqueeze_(0)
        img_np = img_tensor.numpy()
        ort_inputs = {session.get_inputs()[0].name: img_np}
        pre_landmark = session.run(None, ort_inputs)

        pre_landmark = pre_landmark[1]
        pre_landmark = np.reshape(pre_landmark, (22, 2))
        output_queue.put((frame, pre_landmark))




class MOMMY_C(object):
    def __init__(self):
        onnxruntime.disable_telemetry_events()
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 4
        opts.intra_op_num_threads = 1  # 1 = 30fps 2 =60 fps #TODO: add to settings page

        # ort_session = onnxruntime.InferenceSession("pfld.onnx")
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.ort_session = onnxruntime.InferenceSession("Models/mommy062023.onnx", opts, providers=['CPUExecutionProvider'])
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
        self.num_threads = 2
        self.output_queue = Queue(maxsize=self.num_threads + 4)  # can be adjusted
        self.queues = []

        self.num_threads = 2
        self.output_queue = Queue(maxsize=self.num_threads + 4)  # can be adjusted

        for _ in range(self.num_threads):
            self.queue = Queue(maxsize=self.num_threads + 4)
            self.queues.append(self.queue)

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.optimized_model_filepath = ''
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

        cap = cv2.VideoCapture('DikablisSA_2_1.mp4')
        frames = 0
        start_time = time.time()
        interval = 1  # Time interval in seconds

    def to_numpy(self, tensor):
        return tensor.detach().cpu().numpy() if tensor.requires_grad else tensor.cpu().numpy()



    def run_onnx_model(self, queues, session, frame):
        for i in range(len(queues)):
            if not queues[i].full():
                queues[i].put(frame)
                break
    def mommy_run(self):

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
            return frame, x, y, per


        frame = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        return frame, 0, 0, 0

class External_Run_MOMMY(object):
    def __init__(self):
        self.algo = MOMMY_C()

    def run(self, current_image_gray):
        self.algo.current_image_gray = current_image_gray
        img, x, y, per = self.algo.mommy_run()
        return img, x, y, per