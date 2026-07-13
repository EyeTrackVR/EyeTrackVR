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

NEXT BSB (stereo) End-to-End Model.

A single ONNX forward pass that takes BOTH eyes at once and returns per-eye
expression outputs plus one shared gaze. This is the BigScreen-Beyond stereo
sibling of next_model.py (which is per-eye/mono).

ONNX contract (self-describing via metadata; see E2E_BSB_Stereo/export_onnx_stereo.py):
  input  'input'  : float32 [1, 6*T, H, W], raw RGB 0..255 (normalization baked
                    into the graph). Channels per time step = left-eye RGB (3)
                    then right-eye RGB (3); time steps oldest -> newest (T=1 for
                    the current static export).
  output 'output' : float32 [1, 8] =
                    [eyebrow_l, eyelid_l, squeeze_l,
                     eyebrow_r, eyelid_r, squeeze_r,
                     gaze_x, gaze_y]
                    expressions sigmoid [0,1] (per eye); gaze tanh [-1,1] (shared).

Because EyeTrackVR processes each eye in its own thread, StereoNextCoordinator
owns the single shared ONNX session and pairs the two eyes' latest frames by
capture time: each eye thread submit()s its frame, and whichever call completes
a fresh left+right pair runs exactly one inference; both threads then read their
slice of the result. One session, one inference per synced pair.

Algorithm App Implementation By: Prohurtz

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import os
import threading
from collections import deque

import numpy as np
import cv2
import onnxruntime

from eye import EyeId
from one_euro_filter import OneEuroFilter
from utils.misc_utils import resource_path

os.environ["OMP_NUM_THREADS"] = "1"

# Same running-median jitter reject as the mono model (see next_model.py): a
# short causal median kills single-frame spikes before the One-Euro derivative
# term can amplify them. Applied to the two eyebrows and the shared gaze.
_BROW_MEDIAN_WINDOW = 5
_GAZE_MEDIAN_WINDOW = 3

# Per-output One-Euro multipliers, in the model's 8-output order. Mirrors the
# mono ordering intent: eyebrows filtered most, gaze & squeeze next, eyelids
# least — duplicated across the left/right expression triples.
#          ebL  elidL  sqL   ebR  elidR  sqR   gx   gy
_FILTER_MUL = np.array(
    [1.0, 10.0, 5.0, 1.0, 10.0, 5.0, 0.1, 0.1], dtype=np.float32
)

# ImageNet normalization constants (CHW), only used for the (not expected)
# legacy case where an export didn't bake normalization into the graph.
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)

_STEREO_BASE = "Models/NEXT_BSB_STEREO.onnx"
_STEREO_FP16 = "Models/NEXT_BSB_STEREO.fp16.onnx"


def stereo_model_file(fp16: bool) -> str:
    """The stereo ONNX to load. fp16 (the 'Lite' precision) falls back to the
    full-precision model if the half-precision build isn't on disk."""
    if fp16 and os.path.exists(resource_path(_STEREO_FP16)):
        return _STEREO_FP16
    return _STEREO_BASE


class NEXT_Stereo_cls:
    """Wraps the stereo ONNX session + One-Euro/median smoothing on 8 outputs."""

    def __init__(self, fp16: bool = False):
        self.fp16 = fp16
        onnxruntime.disable_telemetry_events()
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

        ort_session = onnxruntime.InferenceSession(
            resource_path(stereo_model_file(fp16)),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        ort_session.set_providers(["CPUExecutionProvider"])
        self.ort_session = ort_session

        model_input = ort_session.get_inputs()[0]
        self.input_name = model_input.name
        # fp16 stereo exports keep float32 I/O (keep_io_types=True), so this is
        # float32 in practice; honor whatever the graph declares regardless.
        self.input_dtype = np.float16 if "float16" in model_input.type else np.float32
        self.input_size = int(model_input.shape[-1])

        meta = ort_session.get_modelmeta().custom_metadata_map
        # Stereo exports always bake /255 + ImageNet normalization into the graph.
        self.raw_input = meta.get("preprocess") == "rgb-raw-0-255"
        # Temporal stereo stacks T left/right PAIRS channel-wise (6*T). The
        # current static export is T=1, but keep the history buffer so a future
        # temporal export self-configures with no code change.
        self.temporal_frames = int(meta.get("temporal_frames", 1))
        self.frame_stride = int(meta.get("frame_stride", 2))
        self._pair_history = deque(
            maxlen=(self.temporal_frames - 1) * self.frame_stride + 1
        )

        self.one_euro_filter = OneEuroFilter(
            np.zeros(8, dtype=np.float32), min_cutoff=1.0, beta=0.0
        )
        self._brow_l_window = deque(maxlen=_BROW_MEDIAN_WINDOW)
        self._brow_r_window = deque(maxlen=_BROW_MEDIAN_WINDOW)
        self._gaze_x_window = deque(maxlen=_GAZE_MEDIAN_WINDOW)
        self._gaze_y_window = deque(maxlen=_GAZE_MEDIAN_WINDOW)

    def _preprocess_eye(self, bgr_frame: np.ndarray) -> np.ndarray:
        """One BGR eye frame -> [3, H, W] float32 (raw 0..255 RGB, or normalized
        for the legacy non-baked case)."""
        img = cv2.resize(
            bgr_frame, (self.input_size, self.input_size), interpolation=cv2.INTER_LINEAR
        )
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = img.transpose(2, 0, 1)
        if not self.raw_input:
            img = (img / 255.0 - _MEAN) / _STD
        return img

    def run(
        self,
        left_bgr: np.ndarray,
        right_bgr: np.ndarray,
        base_cutoff: float = 0.0004,
        base_beta: float = 0.9,
    ) -> np.ndarray:
        """Run one stereo pass. Returns the filtered 8-vector in model order
        (gaze up-positive / native, NOT yet Y-flipped for OSC)."""
        self.one_euro_filter.min_cutoff[:] = base_cutoff * _FILTER_MUL
        self.one_euro_filter.beta[:] = base_beta * _FILTER_MUL

        # Left eye first, then right — the channel order the model was trained on.
        pair = np.concatenate(
            (self._preprocess_eye(left_bgr), self._preprocess_eye(right_bgr)), axis=0
        )  # [6, H, W]

        if self.temporal_frames > 1:
            self._pair_history.append(pair)
            h = self._pair_history
            pair = np.concatenate(
                [
                    h[max(0, len(h) - 1 - (self.temporal_frames - 1 - k) * self.frame_stride)]
                    for k in range(self.temporal_frames)
                ],
                axis=0,
            )

        x = pair[np.newaxis].astype(self.input_dtype, copy=False)
        raw = self.ort_session.run(None, {self.input_name: x})[0][0].astype(np.float32)

        # Running-median spike reject on the two eyebrows and the shared gaze.
        self._brow_l_window.append(float(raw[0]))
        raw[0] = float(np.median(self._brow_l_window))
        self._brow_r_window.append(float(raw[3]))
        raw[3] = float(np.median(self._brow_r_window))
        self._gaze_x_window.append(float(raw[6]))
        raw[6] = float(np.median(self._gaze_x_window))
        # NEXT BSB Stereo's Y orientation is opposite the mono NEXT model.
        # Negate it here, then let the unchanged shared NEXT post-processing
        # apply its normal Y negation. The two negations give Stereo the correct
        # final orientation without changing the already-correct mono path.
        self._gaze_y_window.append(float(-raw[7]))
        raw[7] = float(np.median(self._gaze_y_window))

        return self.one_euro_filter(raw).astype(np.float32)


def slice_stereo_result(result: np.ndarray, eye_id) -> tuple:
    """Extract one eye's (gaze_x, gaze_y, eyebrow, eyelid, squeeze) from the
    8-output stereo result. Gaze is shared; expressions are per eye."""
    ebL, elidL, sqL, ebR, elidR, sqR, gx, gy = (float(v) for v in result)
    if eye_id == EyeId.LEFT:
        return gx, gy, ebL, elidL, sqL
    return gx, gy, ebR, elidR, sqR


class StereoNextCoordinator:
    """Shared across both eye threads: owns the single stereo session and pairs
    the two eyes' latest frames by capture time.

    Each eye thread calls submit() with its frame, then get_slice() to obtain
    its portion of the result. Inference runs once per fresh left+right pair
    (claimed by whichever thread first sees both eyes advanced), so the single
    CPU session is never entered concurrently for the same pair."""

    def __init__(self, fp16: bool = False):
        self.runner = NEXT_Stereo_cls(fp16)
        self.fp16 = fp16
        self._state_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        # eye_id -> (bgr_frame, capture_ts, version)
        self._frames: dict = {}
        self._ver = {EyeId.LEFT: 0, EyeId.RIGHT: 0}
        self._claimed = (0, 0)  # (left_ver, right_ver) of the last claimed pair
        self._result = None  # latest filtered 8-vector
        self.last_skew_s = 0.0  # |ts_left - ts_right| of the last inferred pair

    def submit(self, eye_id, bgr_frame: np.ndarray, capture_ts: float) -> None:
        with self._state_lock:
            self._ver[eye_id] += 1
            self._frames[eye_id] = (bgr_frame, capture_ts, self._ver[eye_id])

    def get_slice(self, eye_id, base_cutoff: float, base_beta: float):
        """Trigger a stereo inference if a fresh pair is available, then return
        this eye's (gaze_x, gaze_y, eyebrow, eyelid, squeeze), or None if no
        result exists yet (e.g. the other eye hasn't produced a frame)."""
        run_inputs = None
        with self._state_lock:
            left = self._frames.get(EyeId.LEFT)
            right = self._frames.get(EyeId.RIGHT)
            if left is not None and right is not None:
                l_ver, r_ver = left[2], right[2]
                claimed_l, claimed_r = self._claimed
                # Run only when BOTH eyes have a newer frame than the last pair
                # we ran — dedupes to ~one inference per synced pair and lets the
                # non-claiming thread fall through to the cached result.
                if l_ver > claimed_l and r_ver > claimed_r:
                    self._claimed = (l_ver, r_ver)
                    run_inputs = (left[0], right[0], abs(left[1] - right[1]))

        if run_inputs is not None:
            left_bgr, right_bgr, skew = run_inputs
            # Serialize the single session; runs outside _state_lock so the other
            # eye thread isn't blocked for the full inference.
            with self._infer_lock:
                out = self.runner.run(left_bgr, right_bgr, base_cutoff, base_beta)
            with self._state_lock:
                self._result = out
                self.last_skew_s = skew

        with self._state_lock:
            result = self._result
        if result is None:
            return None
        return slice_stereo_result(result, eye_id)


_coordinator: StereoNextCoordinator | None = None
_coordinator_lock = threading.Lock()


def get_stereo_coordinator(fp16: bool = False) -> StereoNextCoordinator:
    """Process-wide stereo coordinator (one ONNX session shared by both eyes).
    Rebuilt if the requested precision changes."""
    global _coordinator
    with _coordinator_lock:
        if _coordinator is None or _coordinator.fp16 != fp16:
            _coordinator = StereoNextCoordinator(fp16)
        return _coordinator
