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

Algorithm App Implementations By: Prohurtz

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import os
import onnxruntime
import numpy as np
import cv2
import time
import math
from queue import Queue
import threading
from config import EyeTrackCameraConfig, EyeTrackConfig
from one_euro_filter import OneEuroFilter
import psutil
from utils.misc_utils import resource_path
from pathlib import Path
import sys

os.environ["OMP_NUM_THREADS"] = (
    "1"  # on slower systems this can cause issues due to slow single core perf. in such cases, it is better to use GPU compute
)

frames = 0
models = Path("Models")
LEAP_LID_METRIC_VERSION = 1
# Global lock to prevent DML race conditions between eye threads
dml_lock = threading.Lock()

if sys.platform.startswith("linux"):
    # Detect if we are already in the right path to avoid infinite loops
    cuda_path = "/usr/local/cuda/lib64"
    current_ld = os.environ.get("LD_LIBRARY_PATH", "")

    if cuda_path not in current_ld:
        os.environ["LD_LIBRARY_PATH"] = f"/usr/lib:{cuda_path}:{current_ld}"

        # IMPORTANT: Linux caches LD_LIBRARY_PATH when the process starts.
        # To make it "take effect" inside the same script, we often have to
        # re-execute the script once if the path was missing.
        if "RESTART_FOR_CUDA" not in os.environ:
            os.environ["RESTART_FOR_CUDA"] = "1"
            os.execv(sys.executable, [sys.executable] + sys.argv)


def run_model(input_queue, output_queue, session):
    while True:
        frame = input_queue.get()
        if frame is None:
            break

        if frame.ndim == 2:
            gray_img = frame.astype(np.float32)
            gray_img *= 1.0 / 255.0
        else:
            img_np = np.asarray(frame, dtype=np.float32)
            img_np *= 1.0 / 255.0
            gray_img = (
                0.299 * img_np[:, :, 0]
                + 0.587 * img_np[:, :, 1]
                + 0.114 * img_np[:, :, 2]
            )

        gray_img = np.expand_dims(np.expand_dims(gray_img, axis=0), axis=0)

        ort_inputs = {session.get_inputs()[0].name: gray_img}
        with dml_lock:
            pre_landmark = session.run(None, ort_inputs)
        pre_landmark = np.reshape(pre_landmark, (-1, 2))
        output_queue.put((frame, pre_landmark))


def run_onnx_model(queues, session, frame):
    for queue in queues:
        if not queue.full():
            queue.put(frame)
            break


class LEAP_C:
    def __init__(self, eye_config: EyeTrackCameraConfig, config: EyeTrackConfig):
        self.last_lid = None
        self.current_image_gray = None
        self.current_image_gray_clean = None
        onnxruntime.disable_telemetry_events()
        self.num_threads = 1
        self.queue_max_size = 1
        self.model_path = resource_path(models / "pfld-sim.onnx")

        self.print_fps = False
        self.frames = 0
        self.queues = [
            Queue(maxsize=self.queue_max_size) for _ in range(self.num_threads)
        ]
        self.threads = []
        self.model_output = np.zeros((12, 2))
        self.output_queue = Queue(maxsize=self.queue_max_size)
        self.start_time = time.time()

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        opts.enable_mem_pattern = False

        self.one_euro_filter_float = OneEuroFilter(
            np.random.rand(1, 2), min_cutoff=0.0004, beta=0.9
        )
        self.dmax = 0
        self.dmin = 0
        self.openlist = []
        self.maxlist = []
        self.previous_time = None
        self.old_matrix = None
        self.total_velocity_new = 0
        self.total_velocity_avg = 0
        self.total_velocity_old = 0
        self.old_per = 0.0
        self.delta_per_neg = 0.0

        self.eye_config: EyeTrackCameraConfig = eye_config
        self.config: EyeTrackConfig = config
        self.ort_session_cpu = onnxruntime.InferenceSession(
            self.model_path, opts, providers=["CPUExecutionProvider"]
        )

        available_providers = onnxruntime.get_available_providers()
        preferred_order = [
            "CUDAExecutionProvider",
            "OpenVINOExecutionProvider",
            "ROCMExecutionProvider",
            "DmlExecutionProvider",
            "CoreMLExecutionProvider",
        ]

        providers = []
        for p in preferred_order:
            if p in available_providers:
                if p == "DmlExecutionProvider":
                    providers.append((p, {"enable_share_strategy": True}))
                else:
                    providers.append(p)

        print(f"Active ONNX GPU Providers for this session: {providers}")

        self.ort_session_gpu = onnxruntime.InferenceSession(
            self.model_path, opts, providers=providers
        )
        for i in range(self.num_threads):
            if self.config.settings.gui_use_gpu:
                thread = threading.Thread(
                    target=run_model,
                    args=(self.queues[i], self.output_queue, self.ort_session_gpu),
                    name=f"Thread {i}",
                )
            else:
                thread = threading.Thread(
                    target=run_model,
                    args=(self.queues[i], self.output_queue, self.ort_session_cpu),
                    name=f"Thread {i}",
                )
            self.threads.append(thread)
            thread.start()

    def leap_run(self):
        img_height, img_width = self.current_image_gray_clean.shape[:2]
        frame = cv2.resize(self.current_image_gray_clean, (112, 112))
        if self.config.settings.gui_use_gpu:
            run_onnx_model(self.queues, self.ort_session_gpu, frame)
        else:
            run_onnx_model(self.queues, self.ort_session_cpu, frame)

        if not self.output_queue.empty():
            frame, pre_landmark = self.output_queue.get()
            imgvis = self.current_image_gray.copy()

            for point in pre_landmark:
                x, y = point
                x = int(x * img_width)
                y = int(y * img_height)
                cv2.circle(imgvis, (x, y), 3, (255, 255, 0), -1)
                cv2.circle(imgvis, (x, y), 1, (0, 0, 255), -1)

            if self.eye_config.leap_lid_metric_version != LEAP_LID_METRIC_VERSION:
                self.calib = 0
                self.eye_config.leap_lid_metric_version = LEAP_LID_METRIC_VERSION
                self.eye_config.leap_calibrated = False

            if self.calib == 0:
                self.calib = time.time()
                self.openlist = []
                self.eye_config.leap_calibrated = False

            d1 = math.dist(pre_landmark[1], pre_landmark[3])
            d2 = math.dist(pre_landmark[2], pre_landmark[4])
            d = (d1 + d2) / 2

            if not self.eye_config.leap_calibrated:
                self.openlist.append(d)
                if len(self.openlist) >= 10:
                    open_percentile = float(np.percentile(self.openlist, 90))
                    closed_percentile = float(np.percentile(self.openlist, 2))
                else:
                    open_percentile = 0.8
                    closed_percentile = 0.8
                calibration_span = open_percentile - closed_percentile
                self.eye_config.leap_calibration_percentile_90 = open_percentile
                self.eye_config.leap_calibration_percentile_2 = (
                    closed_percentile - open_percentile
                )
                if (
                    isinstance(self.calib, float)
                    and time.time() - self.calib
                    >= self.config.settings.leap_calibration_duration
                ):
                    min_span = float(self.config.settings.leap_lid_min_calibration_span)
                    eye_name = (
                        "Left" if self.eye_config is self.config.left_eye else "Right"
                    )
                    sample_count = len(self.openlist)
                    if calibration_span >= min_span:
                        self.eye_config.leap_calibrated = True
                        self.config.save()
                        print(
                            f"[INFO] {eye_name} eye LEAP lid calibrated: "
                            f"samples={sample_count}, open_p90={open_percentile:.4f}, "
                            f"closed_p2={closed_percentile:.4f}, "
                            f"span={calibration_span:.4f}, min_span={min_span:.4f}"
                        )
                    else:
                        self.calib = 0
                        self.openlist = []
                        self.eye_config.leap_calibration_percentile_90 = 0
                        self.eye_config.leap_calibration_percentile_2 = 0
                        print(
                            f"[WARN] {eye_name} eye LEAP lid calibration rejected: "
                            f"samples={sample_count}, open_p90={open_percentile:.4f}, "
                            f"closed_p2={closed_percentile:.4f}, "
                            f"span={calibration_span:.4f}, min_span={min_span:.4f}"
                        )

            try:
                if len(self.openlist) > 0 or self.eye_config.leap_calibrated:
                    per = (
                        d - self.eye_config.leap_calibration_percentile_90
                    ) / self.eye_config.leap_calibration_percentile_2
                    per = 1 - per
                    per = np.clip(per, 0.0, 1.0)
                else:
                    per = 0.8
            except:
                per = 0.8

            x = pre_landmark[6][0]
            y = pre_landmark[6][1]

            self.last_lid = per
            calib_array = np.array([per, per]).reshape(1, 2)
            per = self.one_euro_filter_float(calib_array)[0][0]

            return imgvis, float(x * img_width), float(y * img_height), per

        return self.current_image_gray, 0, 0, 0


class External_Run_LEAP:
    def __init__(self, eye_config: EyeTrackCameraConfig, config: EyeTrackConfig):
        self.algo = LEAP_C(eye_config, config)

    def run(self, current_image_gray, current_image_gray_clean, calib, use_gpu):
        self.algo.current_image_gray = current_image_gray
        self.algo.current_image_gray_clean = current_image_gray_clean
        self.algo.calib = calib
        self.use_gpu = use_gpu
        img, x, y, per = self.algo.leap_run()
        return img, x, y, per
