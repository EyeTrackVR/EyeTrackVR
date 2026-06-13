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

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import logging
import math
import queue
import threading
import time
import numpy as np
import cv2
import onnxruntime
from utils.misc_utils import resource_path
import os

os.environ["OMP_NUM_THREADS"] = (
    "1"  # on slower systems this can cause issues due to slow single core perf. in such cases, it is better to use GPU compute
)
logger = logging.getLogger(__name__)

# Supported model variants. The selector in the GUI picks one of these and the
# matching ONNX file (Models/Eyebrow_<VARIANT>.onnx) is loaded.
MODEL_VARIANTS = ("ETVR", "BSB", "TOBII")
DEFAULT_MODEL_VARIANT = "ETVR"


def model_file_for_variant(variant: str) -> str:
    """Map a variant name (ETVR/BSB/TOBII) to its ONNX file path."""
    variant = (variant or DEFAULT_MODEL_VARIANT).upper()
    if variant not in MODEL_VARIANTS:
        variant = DEFAULT_MODEL_VARIANT
    return f"Models/Eyebrow_{variant}.onnx"
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)
_INV_255 = np.float32(1.0 / 255.0)


class _OneEuroFilter:
    def __init__(self, t0, x0, dx0=0.0, min_cutoff=0.5, beta=0.01, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = float(x0)
        self.dx_prev = float(dx0)
        self.t_prev = float(t0)

    def _sf(self, t_e, cutoff):
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)

    def __call__(self, t, x):
        t_e = t - self.t_prev
        if t_e <= 0:
            return self.x_prev
        a_d = self._sf(t_e, self.d_cutoff)
        dx = (x - self.x_prev) / t_e
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._sf(t_e, cutoff)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat


class EyeBrow:
    """Async per-eye eyebrow tracker using Eyebrow_<variant>.onnx.

    Inference runs on a background thread so it never blocks the tracking loop.
    submit() is non-blocking (drops frames when the worker is busy).
    get_result() returns the latest smoothed value immediately.

    Always uses CPUExecutionProvider — DmlExecutionProvider causes access
    violations when multiple sessions run simultaneously in the same process.
    MobileNetV3-Small is lightweight enough that CPU inference is fast enough
    to keep up at typical camera frame rates.
    """

    def __init__(self, variant: str = DEFAULT_MODEL_VARIANT):
        self.variant = variant
        model_path = resource_path(model_file_for_variant(variant))
        logger.info("EyeBrow: loading %s (CPU)", model_path)
        onnxruntime.disable_telemetry_events()
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.enable_mem_pattern = False
        self._session = onnxruntime.InferenceSession(
            model_path, opts, providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name
        self._filter: _OneEuroFilter | None = None
        self._result: float = 0.0

        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="EyeBrow")
        self._thread.start()

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame_bgr = self._frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if frame_bgr.ndim == 2:
                    # Grayscale (e.g. serial IR JPEG decoded by PIL as 'L')
                    frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
                elif frame_bgr.shape[2] == 1:
                    frame_bgr = cv2.cvtColor(frame_bgr[:, :, 0], cv2.COLOR_GRAY2BGR)
                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_LINEAR)
                tensor = np.asarray(resized, dtype=np.float32)
                tensor *= _INV_255
                tensor = tensor.transpose(2, 0, 1)  # H,W,C -> C,H,W
                tensor = (tensor - _IMAGENET_MEAN) / _IMAGENET_STD
                tensor = tensor[np.newaxis]  # 1,C,H,W
                outputs = self._session.run(None, {self._input_name: tensor})
                val = float(np.clip(outputs[0][0][0], 0.0, 1.0))
                now = time.time()
                if self._filter is None:
                    self._filter = _OneEuroFilter(now, val)
                self._result = float(np.clip(self._filter(now, val), 0.0, 1.0))
            except Exception as e:
                logger.debug("EyeBrow worker error: %s", e)

    def submit(self, frame_bgr: np.ndarray) -> None:
        """Push a frame for inference. Non-blocking — drops if worker is busy."""
        try:
            self._frame_queue.put_nowait(frame_bgr.copy())
        except queue.Full:
            pass

    def get_result(self) -> float:
        """Return the most recent smoothed brow value [0.0, 1.0]."""
        return self._result

    def stop(self) -> None:
        self._stop_event.set()
