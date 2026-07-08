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

import logging
import os
import onnxruntime
import numpy as np
import cv2
import time
import math
from collections import deque
from queue import Empty, Full, Queue
import threading
from config import EyeTrackCameraConfig, EyeTrackConfig
from one_euro_filter import OneEuroFilter

logger = logging.getLogger(__name__)
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
    # Make CUDA's libs findable for onnxruntime-gpu. Only relevant when a CUDA
    # toolkit is actually installed: CPU-only machines (the packaged release
    # ships CPU onnxruntime) must NOT pay a whole-process re-exec at import
    # time, which is what the LD_LIBRARY_PATH edit requires to take effect.
    cuda_path = "/usr/local/cuda/lib64"
    current_ld = os.environ.get("LD_LIBRARY_PATH", "")

    if os.path.isdir(cuda_path) and cuda_path not in current_ld:
        os.environ["LD_LIBRARY_PATH"] = f"/usr/lib:{cuda_path}:{current_ld}"

        # IMPORTANT: Linux caches LD_LIBRARY_PATH when the process starts.
        # To make it "take effect" inside the same script, we often have to
        # re-execute the script once if the path was missing.
        if "RESTART_FOR_CUDA" not in os.environ:
            os.environ["RESTART_FOR_CUDA"] = "1"
            if getattr(sys, "frozen", False):
                # Frozen app: sys.executable IS the program; argv[0] repeats it.
                os.execv(sys.executable, [sys.executable] + sys.argv[1:])
            else:
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
        # Mirrors eye_config.leap_calib_request_seq; when the config value
        # increments (user pressed "Redo Eyelid Calib"), we reset the sampling
        # window on the next frame. Initialised from the stored value so a
        # restart doesn't trigger a spurious recalibration.
        self._seen_calib_request_seq = int(
            getattr(eye_config, "leap_calib_request_seq", 0)
        )
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
        # Lid-calibration sampling window. The timer below is what actually
        # ends collection; the maxlen is a backstop so the window can never
        # grow without bound (and drag per-frame percentile cost with it)
        # even if the completion check is somehow prevented from firing.
        # Sized for ~130 fps over the configured collection duration.
        self.openlist = deque(
            maxlen=max(
                2000, int(float(config.settings.leap_calibration_duration) * 130)
            )
        )
        # perf_counter timestamp when the current lid-calibration collection
        # window opened; 0.0 means "start a new window on the next frame".
        # LEAP owns this timer: it used to be overwritten every frame with the
        # gaze-calibration start time (None outside gaze calibration), which
        # meant collection could never finish and openlist grew forever.
        self._calib_start = 0.0
        # Throttle for the percentile refresh over openlist (see leap_run).
        self._last_percentile_refresh = 0.0
        self._open_percentile = 0.8
        self._closed_percentile = 0.8
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

        logger.info("Active ONNX GPU providers for this session: %s", providers)

        # Building the GPU session must never take the app down:
        #   - providers=[] (CPU-only machine) makes InferenceSession raise
        #   - CUDAExecutionProvider is listed as "available" whenever
        #     onnxruntime-gpu is installed, but session creation still fails
        #     if the CUDA/cuDNN system libraries are missing (common on Linux)
        # In both cases fall back to the CPU session; runtime provider choice
        # (gui_use_gpu) then simply resolves to CPU.
        self.ort_session_gpu = None
        if providers:
            try:
                # Trailing CPU provider lets ORT place unsupported ops on CPU
                # instead of failing session creation outright.
                self.ort_session_gpu = onnxruntime.InferenceSession(
                    self.model_path,
                    opts,
                    providers=providers + ["CPUExecutionProvider"],
                )
            except Exception as e:
                logger.warning(
                    "GPU ONNX session unavailable (%s); LEAP will run on CPU. "
                    "On Linux this usually means onnxruntime-gpu is installed "
                    "without the CUDA/cuDNN system libraries.",
                    e,
                )
        if self.ort_session_gpu is None:
            self.ort_session_gpu = self.ort_session_cpu
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

    def shutdown(self):
        """Stop the inference worker threads so swapping algorithms doesn't
        leak a blocked thread (plus its ONNX session references) per swap."""
        for q in self.queues:
            try:
                # Workers drain their queue continuously, so a short blocking
                # put is enough to get the sentinel in behind any queued frame.
                q.put(None, timeout=1)
            except Full:
                logger.warning("LEAP worker queue full during shutdown; thread may leak")
        deadline = time.time() + 2.0
        for thread in self.threads:
            # A worker can be blocked publishing a result nobody will read
            # anymore (output_queue.put is blocking and maxsize=1), so keep
            # draining outputs while we wait or it never reaches the sentinel.
            while thread.is_alive() and time.time() < deadline:
                try:
                    self.output_queue.get_nowait()
                except Empty:
                    pass
                thread.join(timeout=0.05)
            if thread.is_alive():
                logger.warning("LEAP worker %s did not exit cleanly", thread.name)
        self.threads = []

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
                self._calib_start = 0.0
                self.eye_config.leap_lid_metric_version = LEAP_LID_METRIC_VERSION
                self.eye_config.leap_calibrated = False

            current_seq = int(
                getattr(self.eye_config, "leap_calib_request_seq", 0)
            )
            if current_seq != self._seen_calib_request_seq:
                # User requested a fresh calibration from the settings UI.
                self._seen_calib_request_seq = current_seq
                self._calib_start = 0.0
                self.eye_config.leap_calibrated = False
                self.eye_config.leap_calibration_percentile_90 = 0
                self.eye_config.leap_calibration_percentile_2 = 0
                eye_name = (
                    "Left" if self.eye_config is self.config.left_eye else "Right"
                )
                logger.info("%s eye LEAP lid calibration restart requested", eye_name)

            d1 = math.dist(pre_landmark[1], pre_landmark[3])
            d2 = math.dist(pre_landmark[2], pre_landmark[4])
            d = (d1 + d2) / 2

            if not self.eye_config.leap_calibrated:
                if self._calib_start == 0.0:
                    self._calib_start = time.time()
                    self.openlist.clear()
                    self._last_percentile_refresh = 0.0
                    self._open_percentile = 0.8
                    self._closed_percentile = 0.8
                self.openlist.append(d)
                now = time.time()
                decision_due = (
                    now - self._calib_start
                    >= self.config.settings.leap_calibration_duration
                )
                # np.percentile over the whole window is O(n) per call, so
                # refresh at most twice a second (and always right before the
                # accept/reject decision) instead of every frame.
                if decision_due or now - self._last_percentile_refresh >= 0.5:
                    self._last_percentile_refresh = now
                    if len(self.openlist) >= 10:
                        self._open_percentile = float(
                            np.percentile(self.openlist, 90)
                        )
                        self._closed_percentile = float(
                            np.percentile(self.openlist, 2)
                        )
                    else:
                        self._open_percentile = 0.8
                        self._closed_percentile = 0.8
                    self.eye_config.leap_calibration_percentile_90 = (
                        self._open_percentile
                    )
                    self.eye_config.leap_calibration_percentile_2 = (
                        self._closed_percentile - self._open_percentile
                    )
                open_percentile = self._open_percentile
                closed_percentile = self._closed_percentile
                calibration_span = open_percentile - closed_percentile
                if decision_due:
                    min_span = float(self.config.settings.leap_lid_min_calibration_span)
                    eye_name = (
                        "Left" if self.eye_config is self.config.left_eye else "Right"
                    )
                    sample_count = len(self.openlist)
                    if calibration_span >= min_span:
                        self.eye_config.leap_calibrated = True
                        self.config.save()
                        logger.info(
                            "%s eye LEAP lid calibrated: samples=%d, "
                            "open_p90=%.4f, closed_p2=%.4f, span=%.4f, min_span=%.4f",
                            eye_name,
                            sample_count,
                            open_percentile,
                            closed_percentile,
                            calibration_span,
                            min_span,
                        )
                    else:
                        self._calib_start = 0.0
                        self.eye_config.leap_calibration_percentile_90 = 0
                        self.eye_config.leap_calibration_percentile_2 = 0
                        logger.warning(
                            "%s eye LEAP lid calibration rejected: samples=%d, "
                            "open_p90=%.4f, closed_p2=%.4f, span=%.4f, min_span=%.4f",
                            eye_name,
                            sample_count,
                            open_percentile,
                            closed_percentile,
                            calibration_span,
                            min_span,
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
            except (ZeroDivisionError, TypeError, ValueError, AttributeError) as e:
                logger.debug("LEAP lid percentile calc fell back to 0.8: %s", e)
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

    def run(self, current_image_gray, current_image_gray_clean, use_gpu):
        self.algo.current_image_gray = current_image_gray
        self.algo.current_image_gray_clean = current_image_gray_clean
        self.use_gpu = use_gpu
        img, x, y, per = self.algo.leap_run()
        return img, x, y, per

    def shutdown(self):
        self.algo.shutdown()
