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
# matching ONNX file (Models/Eyebrow_<VARIANT>.onnx) is loaded. The "<BASE> LITE"
# variants are the fp16 NEXT builds; the eyebrow model has no fp16 build, so Lite
# falls back to the base variant's eyebrow file here.
MODEL_VARIANTS = ("ETVR", "BSB", "TOBII", "ETVR LITE", "BSB LITE")
DEFAULT_MODEL_VARIANT = "ETVR"
# Suffix that marks an fp16 ("Lite") variant.
_LITE_SUFFIX = " LITE"


def model_file_for_variant(variant: str) -> str:
    """Map a variant name to its eyebrow ONNX path. The eyebrow model has no fp16
    build, so '<BASE> LITE' resolves to the base variant's Eyebrow_<BASE>.onnx."""
    variant = (variant or DEFAULT_MODEL_VARIANT).upper()
    if variant not in MODEL_VARIANTS:
        variant = DEFAULT_MODEL_VARIANT
    if variant.endswith(_LITE_SUFFIX):
        variant = variant[: -len(_LITE_SUFFIX)].strip()
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


# Flip to True to log every frame the brow gate holds the eyebrow, so you can
# confirm it engaging on real blinks.
_BROW_GATE_DEBUG = False


class BlinkBrowGate:
    """Hold the eyebrow output while the eyelid is closed or in flight.

    Mid-blink frames are out-of-distribution (training data is held poses, so
    no frame shows a descending lid) and the model reads the hooded appearance
    as brows-down. A brow can't physically move much within a ~200 ms blink,
    so freezing it during the blink is lossless. The gate engages when the lid
    is below lid_thresh OR moving faster than vel_thresh, and releases release_s
    after the lid is back up and slow.

    Ported from LEAPv2_Training/End2End/infer.py. The standalone eyebrow model
    has no eyelid output, so the lid signal is fed in from the tracking loop
    (see EyeBrow.set_lid). Gate on the raw model value before the One-Euro
    filter so the fast blink downstroke is detected before smoothing damps it."""

    def __init__(self, lid_thresh=0.4, vel_thresh=2.0, release_s=0.10):
        self.lid_thresh = lid_thresh
        self.vel_thresh = vel_thresh
        self.release_s = release_s
        self.t_prev = None
        self.lid_prev = None
        self.held = None
        self.t_open = None

    def __call__(self, t, brow, lid):
        if self.t_prev is None:
            self.t_prev, self.lid_prev, self.held, self.t_open = t, lid, brow, t
            return brow
        dt = max(t - self.t_prev, 1e-6)
        vel = (lid - self.lid_prev) / dt
        self.t_prev, self.lid_prev = t, lid
        if lid < self.lid_thresh or abs(vel) > self.vel_thresh:
            self.t_open = None
            if _BROW_GATE_DEBUG:
                print(f"[brow-gate] HELD  brow_raw={brow:.3f} held={self.held:.3f} "
                      f"lid={lid:.3f} vel={vel:+.2f}")
            return self.held
        if self.t_open is None:
            self.t_open = t
        if t - self.t_open < self.release_s:
            if _BROW_GATE_DEBUG:
                print(f"[brow-gate] hold(release) brow_raw={brow:.3f} "
                      f"held={self.held:.3f} lid={lid:.3f}")
            return self.held
        self.held = brow
        return brow


class EyeBrow:
    """Async per-eye eyebrow tracker using Eyebrow_<variant>.onnx.

    Inference runs on a background thread so it never blocks the tracking loop.
    submit() is non-blocking (drops frames when the worker is busy).
    get_result() returns the latest smoothed value immediately.

    Always uses CPUExecutionProvider: DmlExecutionProvider causes access
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

        # Freezes the eyebrow during blinks. Keyed on the eyelid openness fed in
        # from the tracking loop via set_lid(); default 1.0 (open) so the gate is
        # a no-op until a real lid value arrives. Applied in the worker on the raw
        # model output, before the One-Euro filter (matches infer.py).
        self._brow_gate = BlinkBrowGate()
        self._latest_lid: float = 1.0

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
                # Hold the brow through blinks, keyed on the latest eyelid
                # openness. Gate the raw value before the One-Euro filter so the
                # fast blink downstroke is caught before smoothing damps it.
                val = self._brow_gate(now, val, self._latest_lid)
                if self._filter is None:
                    self._filter = _OneEuroFilter(now, val)
                self._result = float(np.clip(self._filter(now, val), 0.0, 1.0))
            except Exception as e:
                logger.debug("EyeBrow worker error: %s", e)

    def set_lid(self, lid: float) -> None:
        """Feed the current eyelid openness [0=closed, 1=open] for the blink gate.

        Called from the tracking loop each frame. A plain float assignment is
        atomic under the GIL, so the worker can read it without a lock."""
        self._latest_lid = float(lid)

    def submit(self, frame_bgr: np.ndarray) -> None:
        """Push a frame for inference. Non-blocking - drops if worker is busy."""
        try:
            self._frame_queue.put_nowait(frame_bgr.copy())
        except queue.Full:
            pass

    def get_result(self) -> float:
        """Return the most recent smoothed brow value [0.0, 1.0]."""
        return self._result

    def stop(self) -> None:
        self._stop_event.set()
