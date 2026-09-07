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

NEXT End-to-End Model: 224x224 RGB input, 5-output regression (gaze, eyebrow, eyelid, squint).
Algorithm App Implementation By: Prohurtz

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import os
import logging
from collections import deque
import numpy as np
import cv2
import onnxruntime
from one_euro_filter import OneEuroFilter
from utils.misc_utils import resource_path
from utils.onnx_runtime import DML_INFERENCE_LOCK, create_inference_session

logger = logging.getLogger(__name__)

os.environ["OMP_NUM_THREADS"] = "1"

# Median window (frames) applied to the raw eyebrow before the One-Euro filter.
# A running median rejects very fast jitter from single frame spikes and frame to
# frame oscillation that the One Euro speed term would otherwise pass, and it
# costs only ~(N-1)/2 frames of lag, which is negligible for a slow brow signal.
# Odd window so the median is a real sample. Bump higher for stronger rejection.
_BROW_MEDIAN_WINDOW = 5

# Same idea for the two gaze channels. The model under-drives its output range
# (empirically ~±0.6 even at full gaze), so calibration must apply a gain > 1 to
# reach the full ±1 output which also multiplies any raw jitter. A single
# spurious spike frame (observed frame-to-frame gaze jumps up to ~0.46) then gets
# amplified into a jump toward the extremes ("snaps to a corner even when not
# looking there"). A short causal median rejects those isolated spikes before
# they enter the One-Euro derivative term (which would otherwise amplify them).
# Window 3 = only ~1 frame of lag, so gaze stays responsive; bump to 5 for
# stronger rejection at the cost of a touch more lag.
_GAZE_MEDIAN_WINDOW = 3

# Supported model variants. The selector in the GUI picks one of these and the
# matching ONNX file (Models/NEXT_<VARIANT>.onnx) is loaded. The "<BASE> LITE"
# variants load an fp16 build (Models/NEXT_<BASE>.fp16.onnx): smaller and faster,
# at a small precision cost.
MODEL_VARIANTS = ("ETVR", "BSB", "PSVR", "TOBII", "ETVR LITE", "BSB LITE")
DEFAULT_MODEL_VARIANT = "ETVR"
# Suffix that marks an fp16 ("Lite") variant.
_LITE_SUFFIX = " LITE"


def model_file_for_variant(variant: str) -> str:
    """Map a variant name to its ONNX file path.

    ETVR/BSB/PSVR/TOBII -> Models/NEXT_<VARIANT>.onnx
    '<BASE> LITE'  -> Models/NEXT_<BASE>.fp16.onnx (half-precision)

    If a requested fp16 build isn't present on disk, fall back to the full-precision
    base model so the Lite option still tracks (just without the fp16 speedup)."""
    variant = (variant or DEFAULT_MODEL_VARIANT).upper()
    if variant not in MODEL_VARIANTS:
        variant = DEFAULT_MODEL_VARIANT
    if variant.endswith(_LITE_SUFFIX):
        base = variant[: -len(_LITE_SUFFIX)].strip()
        fp16 = f"Models/NEXT_{base}.fp16.onnx"
        if os.path.exists(resource_path(fp16)):
            return fp16
        return f"Models/NEXT_{base}.onnx"
    return f"Models/NEXT_{variant}.onnx"

# ImageNet normalization constants (CHW channel order after BGR->RGB)
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


class NEXT_cls:
    """End-to-end eye tracker wrapping the ONNX-exported MobileNetV3-Small model.

    Input:  raw BGR frame at any resolution.
    Output: (gaze_x, gaze_y, eyebrow, eyelid, squeeze)
      - gaze_x / gaze_y : tanh range [-1, 1]
      - eyebrow / eyelid / squeeze : sigmoid range [0, 1]
    """

    def __init__(self, variant: str = DEFAULT_MODEL_VARIANT, use_gpu: bool = False):
        self.variant = variant
        self.use_gpu = bool(use_gpu)
        onnxruntime.disable_telemetry_events()
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.enable_mem_pattern = False

        ort_session, self.uses_directml = create_inference_session(
            resource_path(model_file_for_variant(variant)),
            options,
            use_gpu=self.use_gpu,
            component=f"NEXT {variant}",
            logger=logger,
        )

        self.ort_session = ort_session
        model_input = ort_session.get_inputs()[0]
        self.input_name = model_input.name
        # fp16 ("Lite") models exported with half-precision I/O need a float16 feed;
        # builds that keep float32 I/O (casting internally) need float32. Match the
        # session's declared input type so either export works without special-casing.
        self.input_dtype = np.float16 if "float16" in model_input.type else np.float32

        # Input resolution comes from the graph, not a hardcoded constant: newer
        # exports (e.g. BSB) run at 160px while ETVR runs at 224px.
        self.input_size = int(model_input.shape[-1])

        # Preprocessing contract comes from the metadata stamped at export. Newer
        # exports bake /255 + ImageNet normalization into the graph and take raw
        # 0..255 RGB; legacy exports (no metadata) expect normalized input, so we
        # apply /255 + normalization here to match. Getting this wrong double- or
        # un-normalizes the input and produces garbage predictions.
        meta = ort_session.get_modelmeta().custom_metadata_map
        self.raw_input = meta.get("preprocess") == "rgb-raw-0-255"

        # Temporal exports stack T frames channel-wise (oldest -> newest,
        # `frame_stride` camera frames apart) and declare it in the metadata.
        # Single-frame models have no such keys and skip the history buffer
        # entirely, so this is fully backward compatible.
        self.temporal_frames = int(meta.get("temporal_frames", 1))
        self.frame_stride = int(meta.get("frame_stride", 2))
        self._frame_history = deque(
            maxlen=(self.temporal_frames - 1) * self.frame_stride + 1
        )

        # Initialize with dummy arrays; updated dynamically in run()
        self.one_euro_filter = OneEuroFilter(
            np.zeros(5, dtype=np.float32), min_cutoff=1.0, beta=0.0
        )

        # Recent raw eyebrow values for the running-median jitter reject (see run()).
        self._brow_window = deque(maxlen=_BROW_MEDIAN_WINDOW)
        # Recent raw gaze values for the same spike reject on x / y (see run()).
        self._gaze_x_window = deque(maxlen=_GAZE_MEDIAN_WINDOW)
        self._gaze_y_window = deque(maxlen=_GAZE_MEDIAN_WINDOW)

    def reset_history(self):
        """Drop the temporal frame stack. Called when this model takes over
        again after the stereo model has been driving (see eye_processor's
        mono/stereo switch): without it the first stacks would splice frames
        from before the handover into the current motion history."""
        self._frame_history.clear()

    def run(self, bgr_frame: np.ndarray, base_cutoff: float = 0.0004, base_beta: float = 0.9):
        # Update filter parameters based on smoothing slider base values
        # Array order: [eyebrow, eyelid, squeeze, gaze_x, gaze_y]
        
        # User requested:
        # - Eyebrows filtered the most (lowest cutoff/beta)
        # - Gaze & Squeeze next
        # - Eyelids the least (highest cutoff/beta)
        
        # We apply multipliers to the base slider values to achieve this ordering.
        _cutoff = np.array([
            base_cutoff * 1.0,   # eyebrow (most)
            base_cutoff * 10.0,  # eyelid (least)
            base_cutoff * 5.0,   # squeeze (next)
            base_cutoff * 0.1,   # gaze_x (next)
            base_cutoff * 0.1,   # gaze_y (next)
        ], dtype=np.float32)

        _beta = np.array([
            base_beta * 1.0,     # eyebrow (most)
            base_beta * 10.0,    # eyelid (least)
            base_beta * 5.0,     # squeeze (next)
            base_beta * 0.1,     # gaze_x (next)
            base_beta * 0.1,     # gaze_y (next)
        ], dtype=np.float32)

        self.one_euro_filter.min_cutoff[:] = _cutoff
        self.one_euro_filter.beta[:] = _beta

        """Return (gaze_x, gaze_y, eyebrow, eyelid, squeeze) for *bgr_frame*."""
        img = cv2.resize(bgr_frame, (self.input_size, self.input_size))
        # Raw 0..255 RGB, HWC -> CHW.
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = img.transpose(2, 0, 1)
        # Legacy exports expect /255 + ImageNet normalization here; newer exports
        # bake it into the graph and take raw 0..255 (see self.raw_input).
        if not self.raw_input:
            img = (img / 255.0 - _MEAN) / _STD
        if self.temporal_frames > 1:
            # Channel-stack the history oldest -> newest at frame_stride
            # spacing; while the buffer is still filling (first few frames
            # after start) pad with the oldest frame available.
            self._frame_history.append(img)
            h = self._frame_history
            img = np.concatenate(
                [h[max(0, len(h) - 1 - (self.temporal_frames - 1 - k) * self.frame_stride)]
                 for k in range(self.temporal_frames)],
                axis=0,
            )
        img = img[np.newaxis]  # NCHW batch dim
        # Cast to the model's input dtype (no-op for float32 I/O; fp16 for Lite builds
        # that take half-precision input). Output is coerced back to float32 below.
        img = img.astype(self.input_dtype, copy=False)

        if self.uses_directml:
            with DML_INFERENCE_LOCK:
                result = self.ort_session.run(None, {self.input_name: img})
        else:
            result = self.ort_session.run(None, {self.input_name: img})
        raw = result[0][0].astype(np.float32)

        # Reject super-fast jitter with a running median before smoothing, so
        # single-frame spikes never enter the One-Euro's derivative term (which
        # would amplify them). Applied to the eyebrow and both gaze channels;
        # eyelid/squeeze are untouched. Gaze uses a shorter window to stay
        # responsive (see _GAZE_MEDIAN_WINDOW). Array order: [eyebrow, eyelid,
        # squeeze, gaze_x, gaze_y].
        self._brow_window.append(float(raw[0]))
        raw[0] = float(np.median(self._brow_window))
        self._gaze_x_window.append(float(raw[3]))
        raw[3] = float(np.median(self._gaze_x_window))
        self._gaze_y_window.append(float(raw[4]))
        raw[4] = float(np.median(self._gaze_y_window))

        out = self.one_euro_filter(raw)

        return float(out[3]), float(out[4]), float(out[0]), float(out[1]), float(out[2])
        #       gaze_x         gaze_y         eyebrow        eyelid         squeeze


class External_Run_NEXT:
    def __init__(self, variant: str = DEFAULT_MODEL_VARIANT, use_gpu: bool = False):
        self.variant = variant
        self.use_gpu = bool(use_gpu)
        self.algo = NEXT_cls(variant, self.use_gpu)

    def run(self, bgr_frame: np.ndarray, base_cutoff: float = 0.0004, base_beta: float = 0.9):
        """Run End2End inference on a raw BGR frame.

        Returns (gaze_x, gaze_y, eyebrow, eyelid, squeeze).
        """
        return self.algo.run(bgr_frame, base_cutoff, base_beta)

    def reset_history(self):
        """Drop the temporal frame stack (see NEXT_cls.reset_history)."""
        self.algo.reset_history()
