"""
BS (Bad-Sample) Detector for real-time eye tracking quality gating.

Two independent checks determine whether the primary pupil-tracker's output
is trustworthy enough to use as-is (Express path) or whether the SVR fallback
should be invoked instead:

  A. Intensity check
     Under IR illumination the pupil is nearly black (< ~40 DN).
     If the 5×5 pixel patch around the reported position has a mean
     intensity > 60 DN, the tracker latched onto sclera or skin instead.

  B. Velocity anomaly check
     Human saccades are physically bounded (~700 °/s peak).
     A gaze jump covering > 40 % of the eye-ROI width in a single frame
     (~16 ms) is physically impossible and signals a tracking glitch.
"""

from __future__ import annotations

import math
import time
from typing import Optional

import numpy as np

_INTENSITY_TRIGGER: int = 60
_PATCH_HALF: int = 2            # → 5×5 patch
_MAX_VELOCITY_FRAC: float = 0.40
_MAX_DT_S: float = 0.10         # ignore velocity check after a long frame gap


class BSDetector:
    """
    Per-eye BS Detector.

    Call ``check(frame_gray, raw_x, raw_y)`` every frame with the primary
    tracker's pixel-coordinate output and the grayscale eye crop.
    Returns True when tracking looks valid, False when BS is detected.
    """

    def __init__(self) -> None:
        self._prev_x: Optional[float] = None
        self._prev_y: Optional[float] = None
        self._prev_t: Optional[float] = None

    def check(
        self,
        frame_gray: Optional[np.ndarray],
        raw_x: float,
        raw_y: float,
    ) -> bool:
        """
        Return True (tracking valid) or False (BS detected).

        Parameters
        ----------
        frame_gray:
            Grayscale eye-crop in which ``raw_x``/``raw_y`` are defined.
            May be None — checks that require it are skipped gracefully.
        raw_x, raw_y:
            Raw pixel coordinates reported by the primary pupil tracker,
            within the coordinate space of ``frame_gray``.
        """
        now = time.perf_counter()
        valid = True

        # ── Check A: Intensity ────────────────────────────────────────────────
        if frame_gray is not None and frame_gray.ndim == 2 and frame_gray.size > 0:
            h, w = frame_gray.shape
            px = int(round(float(raw_x)))
            py = int(round(float(raw_y)))
            x0 = max(0, px - _PATCH_HALF)
            x1 = min(w, px + _PATCH_HALF + 1)
            y0 = max(0, py - _PATCH_HALF)
            y1 = min(h, py + _PATCH_HALF + 1)
            patch = frame_gray[y0:y1, x0:x1]
            if patch.size > 0 and float(np.mean(patch)) > _INTENSITY_TRIGGER:
                valid = False

        # ── Check B: Velocity anomaly ─────────────────────────────────────────
        if (
            valid
            and self._prev_x is not None
            and self._prev_t is not None
            and frame_gray is not None
            and frame_gray.size > 0
        ):
            dt = now - self._prev_t
            if 0.0 < dt <= _MAX_DT_S:
                h, w = frame_gray.shape[:2]
                dx_frac = abs(raw_x - self._prev_x) / max(float(w), 1.0)
                dy_frac = abs(raw_y - self._prev_y) / max(float(h), 1.0)
                if math.sqrt(dx_frac * dx_frac + dy_frac * dy_frac) > _MAX_VELOCITY_FRAC:
                    valid = False

        self._prev_x = raw_x
        self._prev_y = raw_y
        self._prev_t = now
        return valid

    def reset(self) -> None:
        """Clear per-frame state. Call when tracking restarts."""
        self._prev_x = None
        self._prev_y = None
        self._prev_t = None
