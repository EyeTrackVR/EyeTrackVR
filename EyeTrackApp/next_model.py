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

NEXT End-to-End Model — 224x224 RGB input, 5-output regression (gaze, eyebrow, eyelid, squint).
Algorithm App Implementation By: Prohurtz

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import os
import numpy as np
import cv2
import onnxruntime
from one_euro_filter import OneEuroFilter
from utils.misc_utils import resource_path

os.environ["OMP_NUM_THREADS"] = "1"

# Supported model variants. The selector in the GUI picks one of these and the
# matching ONNX file (Models/NEXT_<VARIANT>.onnx) is loaded.
MODEL_VARIANTS = ("ETVR", "BSB", "TOBII")
DEFAULT_MODEL_VARIANT = "ETVR"


def model_file_for_variant(variant: str) -> str:
    """Map a variant name (ETVR/BSB/TOBII) to its ONNX file path."""
    variant = (variant or DEFAULT_MODEL_VARIANT).upper()
    if variant not in MODEL_VARIANTS:
        variant = DEFAULT_MODEL_VARIANT
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

    def __init__(self, variant: str = DEFAULT_MODEL_VARIANT):
        self.variant = variant
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
        self.input_name = ort_session.get_inputs()[0].name

        # Initialize with dummy arrays; updated dynamically in run()
        self.one_euro_filter = OneEuroFilter(
            np.zeros(5, dtype=np.float32), min_cutoff=1.0, beta=0.0
        )

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
        img = cv2.resize(bgr_frame, (224, 224))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        # HWC -> CHW
        img = img.transpose(2, 0, 1)
        img = (img - _MEAN) / _STD
        img = img[np.newaxis]  # NCHW batch dim

        raw = self.ort_session.run(None, {self.input_name: img})[0][0].astype(np.float32)
        out = self.one_euro_filter(raw)

        return float(out[3]), float(out[4]), float(out[0]), float(out[1]), float(out[2])
        #       gaze_x         gaze_y         eyebrow        eyelid         squeeze


class External_Run_NEXT:
    def __init__(self, variant: str = DEFAULT_MODEL_VARIANT):
        self.variant = variant
        self.algo = NEXT_cls(variant)

    def run(self, bgr_frame: np.ndarray, base_cutoff: float = 0.0004, base_beta: float = 0.9):
        """Run End2End inference on a raw BGR frame.

        Returns (gaze_x, gaze_y, eyebrow, eyelid, squeeze).
        """
        return self.algo.run(bgr_frame, base_cutoff, base_beta)
