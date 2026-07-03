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
import time
import numpy as np
import cv2
import onnxruntime
from one_euro_filter import OneEuroFilter
from utils.misc_utils import resource_path

os.environ["OMP_NUM_THREADS"] = "1"

# Supported model variants. The selector in the GUI picks one of these and the
# matching ONNX file (Models/NEXT_<VARIANT>.onnx) is loaded. The "<BASE> LITE"
# variants load an fp16 build (Models/NEXT_<BASE>.fp16.onnx): smaller and faster,
# at a small precision cost.
MODEL_VARIANTS = ("ETVR", "BSB", "TOBII", "ETVR LITE", "BSB LITE")
DEFAULT_MODEL_VARIANT = "ETVR"
# Suffix that marks an fp16 ("Lite") variant.
_LITE_SUFFIX = " LITE"


def model_file_for_variant(variant: str) -> str:
    """Map a variant name to its ONNX file path.

    ETVR/BSB/TOBII -> Models/NEXT_<VARIANT>.onnx
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


# Flip to True to log every frame the brow gate holds the eyebrow, so you can
# confirm it engaging on real blinks.
_BROW_GATE_DEBUG = True


class BlinkBrowGate:
    """Hold the eyebrow output while the eyelid is closed or in flight.

    Mid-blink frames are out-of-distribution (training data is held poses, so
    no frame shows a descending lid) and the model reads the hooded appearance
    as brows-down. A brow can't physically move much within a ~200 ms blink,
    so freezing it during the blink is lossless. The gate engages when the lid
    is below lid_thresh OR moving faster than vel_thresh (a blink downstroke
    is ~7 units/s; a deliberate squint is ~0.6/s), and releases release_s
    after the lid is back up and slow.

    Ported from LEAPv2_Training/End2End/infer.py. Operates on the raw model
    outputs (before the One-Euro filter) so the blink velocity is read before
    smoothing muddles it."""

    def __init__(self, lid_thresh=0.4, vel_thresh=2.0, release_s=0.10, label=""):
        self.lid_thresh = lid_thresh
        self.vel_thresh = vel_thresh
        self.release_s = release_s
        self.label = label
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
                print(f"[brow-gate {self.label}] HELD   brow_raw={brow:.3f} held={self.held:.3f} "
                      f"lid={lid:.3f} vel={vel:+.2f}")
            return self.held
        if self.t_open is None:
            self.t_open = t
        if t - self.t_open < self.release_s:
            if _BROW_GATE_DEBUG:
                print(f"[brow-gate {self.label}] REL    brow_raw={brow:.3f} held={self.held:.3f} "
                      f"lid={lid:.3f} vel={vel:+.2f}")
            return self.held
        self.held = brow
        if _BROW_GATE_DEBUG:
            print(f"[brow-gate {self.label}] pass   brow_raw={brow:.3f} lid={lid:.3f} vel={vel:+.2f}")
        return brow


class NEXT_cls:
    """End-to-end eye tracker wrapping the ONNX-exported MobileNetV3-Small model.

    Input:  raw BGR frame at any resolution.
    Output: (gaze_x, gaze_y, eyebrow, eyelid, squeeze)
      - gaze_x / gaze_y : tanh range [-1, 1]
      - eyebrow / eyelid / squeeze : sigmoid range [0, 1]
    """

    def __init__(self, variant: str = DEFAULT_MODEL_VARIANT, label: str = ""):
        self.variant = variant
        self.label = label
        onnxruntime.disable_telemetry_events()
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

        ort_session = onnxruntime.InferenceSession(
            resource_path(model_file_for_variant(variant)),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        ort_session.set_providers(["CPUExecutionProvider"])

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

        # Initialize with dummy arrays; updated dynamically in run()
        self.one_euro_filter = OneEuroFilter(
            np.zeros(5, dtype=np.float32), min_cutoff=1.0, beta=0.0
        )

        # Freezes the eyebrow output during blinks (see BlinkBrowGate). Applied
        # to the raw model outputs before the One-Euro filter.
        self.brow_gate = BlinkBrowGate(label=label)

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
        img = img[np.newaxis]  # NCHW batch dim
        # Cast to the model's input dtype (no-op for float32 I/O; fp16 for Lite builds
        # that take half-precision input). Output is coerced back to float32 below.
        img = img.astype(self.input_dtype, copy=False)

        raw = self.ort_session.run(None, {self.input_name: img})[0][0].astype(np.float32)

        if _BROW_GATE_DEBUG:
            # Full model output so we can see what actually moves on a blink:
            # which of eyelid/squeeze reflects closure, and by how much.
            print(f"[NEXT {self.label}] brow={raw[0]:.3f} lid={raw[1]:.3f} "
                  f"sqz={raw[2]:.3f} gx={raw[3]:+.3f} gy={raw[4]:+.3f}")

        # Hold the eyebrow (index 0) steady through blinks, keyed on the raw
        # eyelid (index 1). Gate on the raw values (before the One-Euro filter)
        # so the fast blink downstroke is detected before smoothing damps it.
        # Use a monotonic clock: One-Euro/gate dt must never go backwards.
        raw[0] = self.brow_gate(time.perf_counter(), float(raw[0]), float(raw[1]))

        out = self.one_euro_filter(raw)

        return float(out[3]), float(out[4]), float(out[0]), float(out[1]), float(out[2])
        #       gaze_x         gaze_y         eyebrow        eyelid         squeeze


class External_Run_NEXT:
    def __init__(self, variant: str = DEFAULT_MODEL_VARIANT, label: str = ""):
        self.variant = variant
        self.algo = NEXT_cls(variant, label=label)

    def run(self, bgr_frame: np.ndarray, base_cutoff: float = 0.0004, base_beta: float = 0.9):
        """Run End2End inference on a raw BGR frame.

        Returns (gaze_x, gaze_y, eyebrow, eyelid, squeeze).
        """
        return self.algo.run(bgr_frame, base_cutoff, base_beta)
