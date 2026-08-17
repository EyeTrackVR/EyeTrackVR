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

NEXT Stereo End-to-End Model.

A single ONNX forward pass that takes BOTH eyes at once and returns per-eye
expression outputs plus one shared gaze. This is the dual-eye sibling of
next_model.py (which is per-eye / mono). The mono model is used when only one
eye is connected; this one takes over as soon as both eyes are streaming.

ONNX contract (self-describing via metadata; see
E2E_ETVR_Stereo/src/export_onnx_stereo.py):
  input  'input'  : float32 [1, 6*T, H, W], raw RGB 0..255 (normalization baked
                    into the graph). Channels per time step = left-eye RGB (3)
                    then right-eye RGB (3); time steps oldest -> newest.
  output 'output' : float32 [1, 8] =
                    [eyebrow_l, eyelid_l, squeeze_l,
                     eyebrow_r, eyelid_r, squeeze_r,
                     gaze_x, gaze_y]
                    expressions sigmoid [0,1] (per eye); gaze tanh [-1,1] (shared).
  metadata        : missing_eye='black-frame', camera_timing='independent-latest',
                    gaze_y_axis='down'|'up', temporal_frames, frame_stride.

CAMERA TIMING (the part the host app owns). The ETVR stereo model is trained to
be desync aware, but the timing decision itself is made out here, because frame
age is observable at capture time and ambiguous in pixels. Mirroring
E2E_ETVR_Stereo/src/infer_stereo.py, no inference path ever waits for the
slower camera; on every new frame from either eye:

  - both eyes fresh and within _SYNC_WINDOW_S: binocular gaze;
  - timestamp-skewed but nearly stationary: still binocular, because lag does
    not change a held gaze and the second view is more accurate;
  - timestamp-skewed and moving: black out the older eye, follow the newest;
  - older than _STALE_AFTER_S: that eye is treated as missing (black frame).

Black frames are the trained missing-eye sentinel, so the model's own monocular
gaze head takes over without any host-side special casing. Temporal histories
are kept per eye, so one camera stuttering never corrupts or stalls the other.

Algorithm App Implementation By: Prohurtz

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import os
import logging
import threading
import time
from collections import deque

import numpy as np
import cv2
import onnxruntime

from eye import EyeId
from one_euro_filter import OneEuroFilter
from utils.misc_utils import resource_path
from utils.onnx_runtime import DML_INFERENCE_LOCK, create_inference_session

logger = logging.getLogger(__name__)

os.environ["OMP_NUM_THREADS"] = "1"

# Same running-median jitter reject as the mono model (see next_model.py): a
# short causal median kills single-frame spikes before the One-Euro derivative
# term can amplify them. Applied to the two eyebrows and the shared gaze.
_BROW_MEDIAN_WINDOW = 5
_GAZE_MEDIAN_WINDOW = 3

# Per-output One-Euro multipliers, in the model's 8-output order. Mirrors the
# mono ordering intent: eyebrows filtered most, gaze & squeeze next, eyelids
# least, duplicated across the left/right expression triples.
#          ebL  elidL  sqL   ebR  elidR  sqR   gx   gy
_FILTER_MUL = np.array(
    [1.0, 10.0, 5.0, 1.0, 10.0, 5.0, 0.1, 0.1], dtype=np.float32
)

# ImageNet normalization constants (CHW), only used for the (not expected)
# legacy case where an export didn't bake normalization into the graph.
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)

# Timing policy, matching the defaults of E2E_ETVR_Stereo/src/infer_stereo.py.
# Max capture-time skew that still fuses two moving eyes binocularly.
_SYNC_WINDOW_S = 0.035
# Age at which a camera is considered gone and its eye is blacked out.
_STALE_AFTER_S = 0.25
# Mean normalized frame delta below which an eye counts as stationary, in which
# case a skewed pair is still fused (lag cannot change a held gaze).
_STABLE_MOTION = 0.012
# Downscale used for that motion estimate.
_MOTION_SIZE = 48
# How long the peer eye may be silent before the caller drops back to the mono
# model. Deliberately much longer than _STALE_AFTER_S: a short stutter is
# absorbed inside the stereo pass (peer blacked out, monocular head), and only a
# camera that is really gone flips the whole tracker back to mono. Prevents
# mode flapping around the staleness boundary.
_PEER_ACTIVE_S = 1.0

# Suffix marking an fp16 ("Lite") variant, shared with next_model.py.
_LITE_SUFFIX = " LITE"

_OTHER_EYE = {EyeId.LEFT: EyeId.RIGHT, EyeId.RIGHT: EyeId.LEFT}


def stereo_variant_key(variant: str) -> tuple:
    """(base variant, fp16) for a GUI model-variant string."""
    value = str(variant or "ETVR").upper()
    if value.endswith(_LITE_SUFFIX):
        return value[: -len(_LITE_SUFFIX)].strip(), True
    return value, False


def stereo_model_file(variant: str):
    """The stereo ONNX for a GUI model variant, or None when that variant has
    no stereo build on disk (then the caller stays on the mono model).

    fp16 (the 'Lite' precision) falls back to the full-precision stereo model
    if the half-precision build isn't shipped."""
    base, fp16 = stereo_variant_key(variant)
    if fp16:
        lite = f"Models/NEXT_{base}_STEREO.fp16.onnx"
        if os.path.exists(resource_path(lite)):
            return lite
    full = f"Models/NEXT_{base}_STEREO.onnx"
    if os.path.exists(resource_path(full)):
        return full
    return None


class _Frame:
    """One captured eye frame plus its lazily computed derivatives.

    Preprocessing is deferred so that frames submitted while the tracker is
    still running the mono model (peer not up yet) cost nothing beyond the
    append."""

    __slots__ = ("ts", "bgr", "chw", "thumb", "motion")

    def __init__(self, ts: float, bgr: np.ndarray):
        self.ts = float(ts)
        self.bgr = bgr
        self.chw = None
        self.thumb = None
        self.motion = None


class NEXT_Stereo_cls:
    """Wraps the stereo ONNX session + One-Euro/median smoothing on 8 outputs."""

    def __init__(self, model_path: str, use_gpu: bool = False):
        self.model_path = model_path
        self.use_gpu = bool(use_gpu)
        onnxruntime.disable_telemetry_events()
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.enable_mem_pattern = False

        ort_session, self.uses_directml = create_inference_session(
            resource_path(model_path),
            options,
            use_gpu=self.use_gpu,
            component="NEXT Stereo",
            logger=logger,
        )
        self.ort_session = ort_session

        model_input = ort_session.get_inputs()[0]
        self.input_name = model_input.name
        # fp16 stereo exports keep float32 I/O (keep_io_types=True), so this is
        # float32 in practice; honor whatever the graph declares regardless.
        self.input_dtype = np.float16 if "float16" in model_input.type else np.float32
        self.input_size = int(model_input.shape[-1])

        meta = ort_session.get_modelmeta().custom_metadata_map
        # Stereo exports bake /255 + ImageNet normalization into the graph.
        self.raw_input = meta.get("preprocess") == "rgb-raw-0-255"
        # Temporal stereo stacks T left/right PAIRS channel-wise (6*T), oldest
        # -> newest, frame_stride camera frames apart.
        self.temporal_frames = max(1, int(meta.get("temporal_frames", 1)))
        self.frame_stride = max(1, int(meta.get("frame_stride", 2)))
        # Gaze Y is normalized to the app's convention, which is the one the
        # deployed mono NEXT exports use. Those predate the axis stamp and are
        # +Y up downstream, same as the BSB stereo model's declared
        # gaze_y_axis=up, so an export declaring 'down' (the ETVR stereo model,
        # trained on the newer screen-space contract) is the one that gets
        # negated. Without this, switching between the mono and the stereo
        # model would flip Y mid-session.
        self.gaze_y_sign = -1.0 if meta.get("gaze_y_axis") == "down" else 1.0

        # Trained missing-eye sentinel: a spatially constant black frame, in
        # whatever input space this export expects.
        black = np.zeros((3, self.input_size, self.input_size), dtype=np.float32)
        self.black = black if self.raw_input else ((black - _MEAN) / _STD)

        self.one_euro_filter = OneEuroFilter(
            np.zeros(8, dtype=np.float32), min_cutoff=1.0, beta=0.0
        )
        self._brow_l_window = deque(maxlen=_BROW_MEDIAN_WINDOW)
        self._brow_r_window = deque(maxlen=_BROW_MEDIAN_WINDOW)
        self._gaze_x_window = deque(maxlen=_GAZE_MEDIAN_WINDOW)
        self._gaze_y_window = deque(maxlen=_GAZE_MEDIAN_WINDOW)
        # Last raw expression triple each eye produced while it was actually
        # fed to the model (see postprocess).
        self._last_expr = {EyeId.LEFT: None, EyeId.RIGHT: None}

    def chw(self, frame: _Frame) -> np.ndarray:
        """One BGR eye frame -> [3, H, W] float32 (raw 0..255 RGB, or normalized
        for the legacy non-baked case). Cached on the frame."""
        if frame.chw is None:
            img = cv2.resize(
                frame.bgr,
                (self.input_size, self.input_size),
                interpolation=cv2.INTER_LINEAR,
            )
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
            img = img.transpose(2, 0, 1)
            if not self.raw_input:
                img = (img / 255.0 - _MEAN) / _STD
            frame.chw = img
        return frame.chw

    def thumb(self, frame: _Frame) -> np.ndarray:
        """Small grayscale copy used for the stationary-eye test."""
        if frame.thumb is None:
            small = cv2.resize(
                frame.bgr, (_MOTION_SIZE, _MOTION_SIZE), interpolation=cv2.INTER_AREA
            )
            frame.thumb = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        return frame.thumb

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Raw 8-vector for one prepared [1, 6*T, H, W] input."""
        x = x.astype(self.input_dtype, copy=False)
        if self.uses_directml:
            with DML_INFERENCE_LOCK:
                result = self.ort_session.run(None, {self.input_name: x})
        else:
            result = self.ort_session.run(None, {self.input_name: x})
        return result[0][0].astype(np.float32)

    def postprocess(
        self, raw: np.ndarray, valid: dict, base_cutoff: float, base_beta: float
    ) -> np.ndarray:
        """Axis normalization, missing-eye expression hold, median spike reject
        and One-Euro smoothing. Returns the filtered 8-vector in model order."""
        self.one_euro_filter.min_cutoff[:] = base_cutoff * _FILTER_MUL
        self.one_euro_filter.beta[:] = base_beta * _FILTER_MUL

        raw[7] *= self.gaze_y_sign

        # An eye fed a black frame has its expressions zeroed by design, which
        # downstream would read as a blink plus a dropped eyebrow. Gaze is
        # meant to follow the newest eye, but expressions are not: hold that
        # eye's last real values instead, so a lagging or stuttering camera
        # can't fake a blink. The zeros never reach the smoothing state either.
        for eye, base in ((EyeId.LEFT, 0), (EyeId.RIGHT, 3)):
            if valid.get(eye, True):
                self._last_expr[eye] = raw[base:base + 3].copy()
            elif self._last_expr[eye] is not None:
                raw[base:base + 3] = self._last_expr[eye]

        # Running-median spike reject on the two eyebrows and the shared gaze.
        self._brow_l_window.append(float(raw[0]))
        raw[0] = float(np.median(self._brow_l_window))
        self._brow_r_window.append(float(raw[3]))
        raw[3] = float(np.median(self._brow_r_window))
        self._gaze_x_window.append(float(raw[6]))
        raw[6] = float(np.median(self._gaze_x_window))
        self._gaze_y_window.append(float(raw[7]))
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
    """Shared across both eye threads: owns the single stereo session, the two
    per-eye frame histories and the no-wait timing policy.

    Each eye thread submit()s every frame it captures (cheap: the frame is only
    stored), asks peer_active() whether a stereo pass is warranted at all, and
    then calls run() to get its slice of the result. run() never waits for the
    peer camera: it always infers from whatever each eye has right now, with the
    older/stale eye replaced by the trained black-frame sentinel when keeping it
    would smear a moving gaze."""

    def __init__(self, model_path: str, use_gpu: bool = False):
        self.runner = NEXT_Stereo_cls(model_path, use_gpu)
        self._state_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        keep = max(2, (self.runner.temporal_frames - 1) * self.runner.frame_stride + 2)
        self._hist = {
            EyeId.LEFT: deque(maxlen=keep),
            EyeId.RIGHT: deque(maxlen=keep),
        }
        self._ver = {EyeId.LEFT: 0, EyeId.RIGHT: 0}
        self._result = None  # latest filtered 8-vector
        self._result_ver = None  # (left_ver, right_ver) it was computed from
        # Capture timestamp each eye actually contributed to _result, None when
        # that eye was blacked out. Used to skip a redundant second pass.
        self._result_ts = {EyeId.LEFT: None, EyeId.RIGHT: None}
        self.last_mode = "none"
        self.last_skew_ms = 0.0

    def submit(self, eye_id, bgr_frame: np.ndarray, capture_ts: float) -> None:
        """Publish this eye's newest frame. Cheap by design: no preprocessing
        happens until a stereo pass actually consumes the frame."""
        # Capture timestamps come from the camera thread's perf_counter, the
        # same clock the timing policy compares against.
        if capture_ts is None:
            capture_ts = time.perf_counter()
        with self._state_lock:
            history = self._hist[eye_id]
            # A gap longer than the staleness window means the temporal history
            # would splice pre-gap frames into the stack. Start that eye over.
            if history and capture_ts - history[-1].ts > _STALE_AFTER_S:
                history.clear()
            history.append(_Frame(capture_ts, bgr_frame))
            self._ver[eye_id] += 1

    def peer_active(self, eye_id) -> bool:
        """True when the other eye is streaming, i.e. two eyes are connected and
        the stereo model should be driving both of them."""
        with self._state_lock:
            history = self._hist[_OTHER_EYE[eye_id]]
            last_ts = history[-1].ts if history else None
        return last_ts is not None and (time.perf_counter() - last_ts) <= _PEER_ACTIVE_S

    def run(self, eye_id, base_cutoff: float, base_beta: float):
        """Run (or reuse) one stereo pass and return this eye's
        (gaze_x, gaze_y, eyebrow, eyelid, squeeze)."""
        # One session, one inference at a time. The waiting eye re-reads the
        # state afterwards and skips its own pass if the peer's pass already
        # consumed this eye's newest frame. Two eyes on one camera (bigscreen)
        # therefore cost exactly one pass per frame, and a CPU-bound session
        # with two independent cameras degrades to one pass per pair instead of
        # queueing up.
        with self._infer_lock:
            with self._state_lock:
                version = (self._ver[EyeId.LEFT], self._ver[EyeId.RIGHT])
                if self._result is not None and self._covered_locked(eye_id, version):
                    return slice_stereo_result(self._result, eye_id)
                snapshot = {
                    EyeId.LEFT: list(self._hist[EyeId.LEFT]),
                    EyeId.RIGHT: list(self._hist[EyeId.RIGHT]),
                }

            # Preprocessing and inference run outside the state lock so the
            # peer eye thread can keep publishing frames meanwhile.
            valid, skew, mode = self._policy(snapshot, time.perf_counter())
            x = self._build_input(snapshot, valid)
            raw = self.runner.forward(x)

            with self._state_lock:
                out = self.runner.postprocess(raw, valid, base_cutoff, base_beta)
                self._result = out
                self._result_ver = version
                for eye in (EyeId.LEFT, EyeId.RIGHT):
                    self._result_ts[eye] = (
                        snapshot[eye][-1].ts if valid[eye] and snapshot[eye] else None
                    )
                self.last_mode = mode
                self.last_skew_ms = skew * 1000.0
        return slice_stereo_result(out, eye_id)

    def _covered_locked(self, eye_id, version) -> bool:
        """True when the stored result already answers this eye's newest frame:
        either nothing changed at all since it was computed, or the pass that
        produced it fed in a frame of this eye with the same capture time."""
        if self._result_ver == version:
            return True
        history = self._hist[eye_id]
        used_ts = self._result_ts[eye_id]
        return bool(history) and used_ts is not None and used_ts == history[-1].ts

    def _motion(self, history: list) -> float:
        """Mean normalized frame-to-frame delta for one eye, cached per frame."""
        if len(history) < 2:
            return 0.0
        newest = history[-1]
        if newest.motion is None:
            previous = self.runner.thumb(history[-2])
            current = self.runner.thumb(newest)
            newest.motion = float(np.mean(np.abs(current - previous)) / 255.0)
        return newest.motion

    def _policy(self, snapshot: dict, now: float):
        """Decide which eyes feed this pass. Returns (valid, skew_s, mode)."""
        left, right = snapshot[EyeId.LEFT], snapshot[EyeId.RIGHT]
        fresh_l = bool(left) and (now - left[-1].ts) <= _STALE_AFTER_S
        fresh_r = bool(right) and (now - right[-1].ts) <= _STALE_AFTER_S
        if not (fresh_l and fresh_r):
            mode = (
                "left-only" if fresh_l else "right-only" if fresh_r else "none"
            )
            return {EyeId.LEFT: fresh_l, EyeId.RIGHT: fresh_r}, 0.0, mode

        ts_l, ts_r = left[-1].ts, right[-1].ts
        skew = abs(ts_l - ts_r)
        if skew <= _SYNC_WINDOW_S:
            return {EyeId.LEFT: True, EyeId.RIGHT: True}, skew, "both-synced"
        # Skewed. A stationary pair is still worth fusing: the lag cannot have
        # changed a held gaze, and two views are more accurate than one.
        if max(self._motion(left), self._motion(right)) <= _STABLE_MOTION:
            return {EyeId.LEFT: True, EyeId.RIGHT: True}, skew, "both-stable"
        newest_is_left = ts_l > ts_r
        return (
            {EyeId.LEFT: newest_is_left, EyeId.RIGHT: not newest_is_left},
            skew,
            "left-fresh" if newest_is_left else "right-fresh",
        )

    def _eye_stack(self, history: list, usable: bool) -> list:
        """This eye's T time steps, oldest -> newest. An unusable eye becomes
        the trained black-frame sentinel at every step."""
        frames = self.runner.temporal_frames
        if not usable or not history:
            return [self.runner.black] * frames
        stride = self.runner.frame_stride
        return [
            self.runner.chw(
                history[max(0, len(history) - 1 - (frames - 1 - k) * stride)]
            )
            for k in range(frames)
        ]

    def _build_input(self, snapshot: dict, valid: dict) -> np.ndarray:
        """[1, 6*T, H, W], left then right within each time step."""
        left = self._eye_stack(snapshot[EyeId.LEFT], valid[EyeId.LEFT])
        right = self._eye_stack(snapshot[EyeId.RIGHT], valid[EyeId.RIGHT])
        steps = [part for k in range(self.runner.temporal_frames)
                 for part in (left[k], right[k])]
        return np.ascontiguousarray(np.concatenate(steps, axis=0))[np.newaxis]


_coordinator: StereoNextCoordinator | None = None
_coordinator_key = None
_coordinator_lock = threading.Lock()


def get_stereo_coordinator(variant: str, use_gpu: bool = False):
    """Process-wide stereo coordinator (one ONNX session shared by both eyes),
    or None when the selected model variant ships no stereo build or its
    session could not be created. A None result means "stay on mono NEXT".

    Rebuilt when the variant, precision or execution device changes."""
    global _coordinator, _coordinator_key
    base, fp16 = stereo_variant_key(variant)
    key = (base, fp16, bool(use_gpu))
    with _coordinator_lock:
        if _coordinator_key == key:
            return _coordinator
        path = stereo_model_file(variant)
        coordinator = None
        if path is None:
            logger.info(
                "No stereo NEXT model for variant %s; using the mono model for "
                "both eyes.", base,
            )
        else:
            try:
                coordinator = StereoNextCoordinator(path, use_gpu)
                logger.info("NEXT Stereo model loaded: %s", path)
            except Exception as exc:
                logger.warning(
                    "NEXT Stereo session unavailable (%s); falling back to the "
                    "mono model.", exc,
                )
        # Cached even when None so a missing model isn't retried every frame.
        _coordinator_key = key
        _coordinator = coordinator
        return coordinator
