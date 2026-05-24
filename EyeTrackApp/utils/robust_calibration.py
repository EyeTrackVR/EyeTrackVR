"""
Robust eye-tracking calibration pipeline.

Three sequential phases:
  1. EXPRESS  — 9-point calibration; center-anchored asymmetric min-max normalization
  2. BLINK    — closed-eye sclera-ratio threshold (used to scrub pursuit frames)
  3. PURSUIT  — smooth figure-eight data collection → degree-2 polynomial regression

Runtime routing (when phase == DONE):
  - If poly trained (pursuit done): polynomial maps keypoints → gaze (best quality)
  - Else if express calibrated: center-anchored normalization (fast fallback)
  - BS Detector can gate poly vs express fallback in "robust" calib_mode

Why polynomial instead of HOG+SVR:
  The ONNX tracking model already extracts keypoints from the image. The only
  non-linearity left to model is keypoint-space → gaze-space, which is a smooth
  2D→2D function driven by camera placement, eye rotation geometry, and corneal
  refraction. A degree-2 polynomial (6 coefficients per output axis, fit via
  numpy lstsq) captures this with ~30+ frames and no external dependencies.
  It also extrapolates better at gaze extremes than RBF-SVR.
"""

from __future__ import annotations

import logging
import math
import time
from enum import IntEnum
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

NUM_EXPRESS_TARGETS = 9
FRAMES_PER_EXPRESS_TARGET = 30
BLINK_DURATION_S = 3.0
BLINK_END_DELAY_S = 1.0
PURSUIT_DURATION_S = 20.0

# 9 targets: center first (used as origin), then cardinals, then diagonals.
# Must match the overlay's EXPRESS_POS order exactly.
EXPRESS_TARGET_HINTS = [
    "Look straight ahead (center)",
    "Look up",
    "Look right",
    "Look down",
    "Look left",
    "Look to the upper-right corner",
    "Look to the upper-left corner",
    "Look to the lower-right corner",
    "Look to the lower-left corner",
]

_SCLERA_BRIGHT_THRESH = 200
_BLINK_SCRUB_MARGIN = 0.02
# Minimum clean frames to fit the polynomial (6 unknowns per axis; 60 is comfortable).
_MIN_POLY_FRAMES = 60
# Maximum single-frame tracker jump (fraction of express range) before treating
# the frame as a saccade and discarding it during pursuit.
_PURSUIT_SACCADE_FRAC = 0.25

# ── Card calibration parameters ───────────────────────────────────────────────
# IQR multiplier for per-card raw-frame outlier rejection.
# Frames outside median ± k×IQR on either axis are discarded before computing
# the per-card representative raw position.
_CARD_IQR_K: float = 2.5
# L2 regularisation strength for the card-based polynomial fit.
# Small lambda prevents overfitting when only 9 samples are available while
# still allowing the degree-2 polynomial enough freedom to model curvature.
_CARD_RIDGE: float = 0.02
# Per-card gaze-space residual threshold for RANSAC-style rejection.
# After the first pass, cards whose gaze error exceeds this value (in
# normalised ±1 units) are dropped and the polynomial is refit.
_CARD_RANSAC_THRESH: float = 0.25

# Expected gaze targets for each of the 9 express calibration positions.
# Order must match EXPRESS_TARGET_HINTS exactly.
# These are injected as high-weight anchor points during polynomial fitting so
# the polynomial is pinned at the known calibration extremes (preventing divergence
# at angles where the tracker is unreliable).
_EXPRESS_GAZE_TARGETS: list[tuple[float, float]] = [
    ( 0.0,  0.0),   # 0 center
    ( 0.0,  1.0),   # 1 up    (gaze-space: positive Y = up, matching CalibrationEllipse)
    ( 1.0,  0.0),   # 2 right
    ( 0.0, -1.0),   # 3 down
    (-1.0,  0.0),   # 4 left
    ( 1.0,  1.0),   # 5 upper-right
    (-1.0,  1.0),   # 6 upper-left
    ( 1.0, -1.0),   # 7 lower-right
    (-1.0, -1.0),   # 8 lower-left
]


class CalibrationPhase(IntEnum):
    IDLE = 0
    EXPRESS = 1
    BLINK = 2
    BLINK_END = 3
    PURSUIT = 4
    TRAINING = 5
    DONE = 6


# ── Feature helpers ───────────────────────────────────────────────────────────

def calculate_sclera_ratio(eye_crop: np.ndarray) -> float:
    """Fraction of IR-bright pixels in the crop (closed-eye indicator)."""
    if eye_crop is None or eye_crop.size == 0:
        return 0.0
    gray = eye_crop if eye_crop.ndim == 2 else cv2.cvtColor(eye_crop, cv2.COLOR_BGR2GRAY)
    _, bright = cv2.threshold(gray, _SCLERA_BRIGHT_THRESH, 255, cv2.THRESH_BINARY)
    total = float(bright.size)
    return float(np.count_nonzero(bright)) / total if total > 0 else 0.0


def _figure_eight_target(elapsed: float) -> Tuple[float, float]:
    """
    Lissajous figure-eight with targets normalised to [-1, 1] on both axes.
    Must stay in sync with the overlay's normalised send_pursuit_frame values.
    """
    t = (elapsed / PURSUIT_DURATION_S) * 2.0 * math.pi * 2.0
    x = math.sin(t)           # [-1, 1]
    y = math.sin(2.0 * t)     # [-1, 1], phase-shifted → figure-eight
    return float(x), float(y)


# ── Main session class ────────────────────────────────────────────────────────

class RobustCalibrationSession:
    """
    Per-eye calibration session coordinating the three phases and exposing
    runtime inference (center-anchored normalization or polynomial regression).
    """

    def __init__(self) -> None:
        self.phase = CalibrationPhase.IDLE
        self._status: str = ""

        # Express state
        self.express_target_idx: int = 0
        self._express_frame_counts: list[int] = []
        self._express_raw: list[list[Tuple[float, float]]] = []
        self.express_calibrated: bool = False
        # Frames to skip after each target switch (camera latency compensation)
        self._express_settle_remaining: int = 0
        # Per-target median raw positions (stored after express, used as polynomial anchors)
        self._express_target_medians: list[Tuple[float, float]] = []
        # Target 0 (center gaze) is used as the origin for normalization so that
        # "looking straight ahead" maps to (0, 0) regardless of camera placement.
        self.express_center_x: float = 0.0
        self.express_center_y: float = 0.0
        self.express_x_min: float = 0.0
        self.express_x_max: float = 1.0
        self.express_y_min: float = 0.0
        self.express_y_max: float = 1.0

        # Blink state
        self._blink_start: float = 0.0
        self._blink_end_at: float = 0.0
        self._blink_sclera_samples: list[float] = []
        self.blink_threshold: float = 0.05
        self.blink_calibrated: bool = False

        # Pursuit state — stores lightweight tuples, not full images.
        # Each entry: (sclera_ratio, raw_x, raw_y, target_x, target_y)
        self._pursuit_start: float = 0.0
        # None = no overlay frame received yet → fall back to internal figure-eight.
        # Explicitly set to a tuple (including (0,0)) by the overlay handler.
        self.current_pursuit_target: Optional[Tuple[float, float]] = None
        self._pursuit_data: list[Tuple[float, float, float, float, float]] = []
        self._prev_pursuit_raw: Optional[Tuple[float, float]] = None

        # Polynomial model (degree-2, fitted via numpy lstsq)
        self.poly_coeffs_x: Optional[np.ndarray] = None
        self.poly_coeffs_y: Optional[np.ndarray] = None
        self.poly_trained: bool = False

    # ── Status ───────────────────────────────────────────────────────────────

    @property
    def status(self) -> str:
        return self._status

    @property
    def svr_trained(self) -> bool:
        return self.poly_trained

    @property
    def current_target_hint(self) -> str:
        if self.phase == CalibrationPhase.EXPRESS:
            idx = min(self.express_target_idx, NUM_EXPRESS_TARGETS - 1)
            return EXPRESS_TARGET_HINTS[idx]
        return ""

    # ── Triggers ─────────────────────────────────────────────────────────────

    def start_express(self, overlay_driven: bool = False) -> None:
        self.phase = CalibrationPhase.EXPRESS
        self.express_target_idx = 0
        self._express_frame_counts = [0] * NUM_EXPRESS_TARGETS
        self._express_raw = [[] for _ in range(NUM_EXPRESS_TARGETS)]
        self.express_calibrated = False
        self._overlay_driven: bool = overlay_driven
        self._status = EXPRESS_TARGET_HINTS[0]
        logger.info("Robust cal [Express]: started (overlay_driven=%s)", overlay_driven)

    def start_blink(self) -> None:
        self.phase = CalibrationPhase.BLINK
        self._blink_start = time.time()
        self._blink_sclera_samples = []
        self._status = "Close your eyes now"
        logger.info("Robust cal [Blink]: started")

    def start_pursuit(self) -> None:
        self.phase = CalibrationPhase.PURSUIT
        self._pursuit_start = time.time()
        self._pursuit_data = []
        self.current_pursuit_target = None   # set to a tuple by the overlay on each frame
        self._prev_pursuit_raw = None
        self._status = "Follow the moving dot"
        logger.info("Robust cal [Pursuit]: started")

    # ── Per-frame feeds ───────────────────────────────────────────────────────

    def feed_express_frame(self, raw_x: float, raw_y: float) -> bool:
        """
        Record one raw-tracker coordinate during EXPRESS.

        GUI mode: auto-advances after FRAMES_PER_EXPRESS_TARGET frames.
        Overlay-driven mode: index advanced only via set_express_target().
        """
        if self.phase != CalibrationPhase.EXPRESS:
            return False
        idx = self.express_target_idx
        if idx >= NUM_EXPRESS_TARGETS:
            self._finalize_express()
            return True
        # Skip frames during settle period (camera latency compensation after target switch)
        if self._express_settle_remaining > 0:
            self._express_settle_remaining -= 1
            return False
        self._express_raw[idx].append((raw_x, raw_y))
        self._express_frame_counts[idx] += 1
        if not getattr(self, "_overlay_driven", False):
            if self._express_frame_counts[idx] >= FRAMES_PER_EXPRESS_TARGET:
                self.express_target_idx += 1
                if self.express_target_idx >= NUM_EXPRESS_TARGETS:
                    self._finalize_express()
                    return True
                self._status = EXPRESS_TARGET_HINTS[self.express_target_idx]
                return True
        return False

    def set_express_target(self, idx: int) -> None:
        """Overlay-driven: switch to target idx (0-8). idx >= 9 finalizes."""
        if self.phase != CalibrationPhase.EXPRESS:
            return
        if idx >= NUM_EXPRESS_TARGETS:
            self._finalize_express()
            return
        self.express_target_idx = int(idx)
        self._express_settle_remaining = 10  # skip ~10 frames for camera latency
        self._status = EXPRESS_TARGET_HINTS[self.express_target_idx]
        logger.debug("Robust cal [Express]: target → %d", self.express_target_idx)

    def advance_express_target(self) -> None:
        if self.phase != CalibrationPhase.EXPRESS:
            return
        self.express_target_idx += 1
        if self.express_target_idx >= NUM_EXPRESS_TARGETS:
            self._finalize_express()
        else:
            self._status = EXPRESS_TARGET_HINTS[self.express_target_idx]

    def feed_blink_frame(self, eye_crop: Optional[np.ndarray]) -> bool:
        """Record one eye frame during BLINK. Returns True when the window closes."""
        if self.phase != CalibrationPhase.BLINK:
            return False
        if eye_crop is not None and eye_crop.size > 0:
            self._blink_sclera_samples.append(calculate_sclera_ratio(eye_crop))
        if time.time() - self._blink_start >= BLINK_DURATION_S:
            self._finalize_blink()
            return True
        return False

    def check_blink_end_timer(self) -> bool:
        """Call each frame during BLINK_END. Transitions to DONE when delay expires."""
        if self.phase != CalibrationPhase.BLINK_END:
            return False
        if time.time() >= self._blink_end_at:
            self.phase = CalibrationPhase.DONE
            self._status = f"Blink threshold: {self.blink_threshold:.3f} — open your eyes"
            logger.info("Robust cal [Blink]: end delay done, phase → DONE")
            return True
        return False

    def feed_pursuit_frame(
        self,
        eye_crop: Optional[np.ndarray],
        raw_x: float = 0.0,
        raw_y: float = 0.0,
    ) -> bool:
        """
        Record one tracker frame during PURSUIT.

        raw_x, raw_y: tracker keypoint output for this frame (from cal_osc).
        The calibration target is taken from current_pursuit_target when the overlay
        has provided it (even when the dot is at center/zero), or from the internal
        figure-eight when no overlay is running.
        Returns True when the 10-second window closes and fitting begins.
        """
        if self.phase != CalibrationPhase.PURSUIT:
            return False
        elapsed = time.time() - self._pursuit_start

        # Target: use the overlay's exact position if it has sent at least one frame;
        # otherwise fall back to the internal figure-eight (no-overlay GUI mode).
        if self.current_pursuit_target is not None:
            tx, ty = self.current_pursuit_target
        else:
            tx, ty = _figure_eight_target(elapsed)

        # Saccade rejection: discard frames where the tracker jumped more than
        # PURSUIT_SACCADE_FRAC of the express range in a single frame — likely a
        # detection glitch rather than real gaze motion.
        if self._prev_pursuit_raw is not None and self.express_calibrated:
            x_range = max(self.express_x_max - self.express_x_min, 1e-6)
            y_range = max(self.express_y_max - self.express_y_min, 1e-6)
            dx = abs(raw_x - self._prev_pursuit_raw[0]) / x_range
            dy = abs(raw_y - self._prev_pursuit_raw[1]) / y_range
            if dx > _PURSUIT_SACCADE_FRAC or dy > _PURSUIT_SACCADE_FRAC:
                self._prev_pursuit_raw = (raw_x, raw_y)
                logger.debug("Pursuit: saccade rejected (dx=%.2f dy=%.2f)", dx, dy)
                if elapsed >= PURSUIT_DURATION_S:
                    self._fit_polynomial()
                    return True
                return False
        self._prev_pursuit_raw = (raw_x, raw_y)

        sr = 0.0
        if eye_crop is not None and eye_crop.size > 0:
            sr = calculate_sclera_ratio(eye_crop)
        # ty from overlay is already positive-Y-up, matching normalize_express convention.
        self._pursuit_data.append((sr, raw_x, raw_y, tx, ty))

        if elapsed >= PURSUIT_DURATION_S:
            self._fit_polynomial()
            return True
        return False

    # ── Card calibration helpers ──────────────────────────────────────────────

    def _clean_card_samples(
        self, frames: list[Tuple[float, float]]
    ) -> list[Tuple[float, float]]:
        """
        IQR-based per-card outlier rejection.

        Removes raw-tracker frames that lie outside median ± _CARD_IQR_K × IQR
        on either axis.  These come from the ML tracker snapping to the image
        centre when the pupil is partially occluded at an extreme gaze angle.
        Returns the original list unchanged if fewer than 4 clean frames remain.
        """
        if len(frames) < 4:
            return frames
        xs = np.array([x for x, y in frames], dtype=np.float64)
        ys = np.array([y for x, y in frames], dtype=np.float64)

        def _iqr_mask(vals: np.ndarray) -> np.ndarray:
            q1, q3 = float(np.percentile(vals, 25)), float(np.percentile(vals, 75))
            iqr = q3 - q1
            lo, hi = q1 - _CARD_IQR_K * iqr, q3 + _CARD_IQR_K * iqr
            return (vals >= lo) & (vals <= hi)

        mask = _iqr_mask(xs) & _iqr_mask(ys)
        clean = [frames[i] for i in range(len(frames)) if mask[i]]
        n_removed = len(frames) - len(clean)
        if n_removed:
            logger.debug("Card IQR: removed %d/%d outlier frames", n_removed, len(frames))
        return clean if len(clean) >= 4 else frames

    def _fit_poly_from_cards(self) -> bool:
        """
        Fit a degree-2 polynomial from the 9 card median raw positions.

        Unlike the smooth-pursuit fit which trains on many noisy frames, this
        uses a handful of clean, precisely-known gaze positions — like flash
        cards for the polynomial.  Two robustness measures borrowed from the
        CalibrationEllipse approach:

        1. Ridge regularisation (L2, λ=_CARD_RIDGE): prevents overfitting when
           only 9 sample points constrain 6 unknowns per axis.

        2. RANSAC-style card rejection: after the first fit, any card whose
           gaze-space residual exceeds _CARD_RANSAC_THRESH (or 2.5× RMS) is
           flagged as a bad sample and the polynomial is refit without it.
           This mirrors how the ellipse cal discards outlier raw samples.

        Sets poly_coeffs_x/y and poly_trained=True on success.
        Returns True if fitting succeeded.
        """
        meds = self._express_target_medians
        targets = _EXPRESS_GAZE_TARGETS
        if not meds or len(meds) < 6 or len(meds) != len(targets):
            logger.warning("Card poly: not enough medians (%d) — skipping", len(meds) if meds else 0)
            return False

        n = len(meds)
        X = np.array([self._poly_features(rx, ry) for rx, ry in meds], dtype=np.float64)
        yx = np.array([g[0] for g in targets], dtype=np.float64)
        yy = np.array([g[1] for g in targets], dtype=np.float64)

        def _ridge(Xf: np.ndarray, yxf: np.ndarray, yyf: np.ndarray):
            lam = _CARD_RIDGE
            A = Xf.T @ Xf + lam * np.eye(6)
            return np.linalg.solve(A, Xf.T @ yxf), np.linalg.solve(A, Xf.T @ yyf)

        # Pass 1 — fit all cards
        cx, cy = _ridge(X, yx, yy)
        errs = np.sqrt((X @ cx - yx) ** 2 + (X @ cy - yy) ** 2)
        rms1 = float(np.sqrt(np.mean(errs ** 2)))
        logger.info(
            "Card poly [pass 1]: RMS=%.4f  per-card=[%s]",
            rms1, ", ".join(f"{e:.3f}" for e in errs),
        )

        # RANSAC — drop cards whose error is suspiciously large
        thresh = max(_CARD_RANSAC_THRESH, rms1 * 2.5)
        good: np.ndarray = errs < thresh
        n_good = int(good.sum())

        if n_good >= 6 and n_good < n:
            bad_idxs = [i for i in range(n) if not good[i]]
            logger.info(
                "Card poly: RANSAC dropping cards %s (err=[%s]), refitting on %d/%d",
                bad_idxs,
                ", ".join(f"{errs[i]:.3f}" for i in bad_idxs),
                n_good, n,
            )
            cx, cy = _ridge(X[good], yx[good], yy[good])
            errs2 = np.sqrt((X @ cx - yx) ** 2 + (X @ cy - yy) ** 2)
            rms_final = float(np.sqrt(np.mean(errs2[good] ** 2)))
            logger.info(
                "Card poly [pass 2]: RMS=%.4f  per-card=[%s]",
                rms_final, ", ".join(f"{e:.3f}" for e in errs2),
            )
        else:
            if n_good < 6:
                logger.warning(
                    "Card poly: RANSAC would remove too many cards (%d good) — keeping all", n_good
                )
            n_good = n
            rms_final = rms1

        self.poly_coeffs_x = cx
        self.poly_coeffs_y = cy
        self.poly_trained = True
        self._poly_source = "card"
        self._status = (
            f"Card poly — {n_good}/{n} cards, RMS {rms_final:.4f}"
        )
        logger.info(
            "Card poly: fitted on %d/%d cards, RMS=%.4f",
            n_good, n, rms_final,
        )
        return True

    # ── Finalizers ────────────────────────────────────────────────────────────

    def _finalize_express(self) -> None:
        if not any(self._express_raw):
            logger.warning("Robust cal [Express]: no samples — aborting")
            self.phase = CalibrationPhase.DONE
            self._status = "Express failed: no samples collected"
            return

        # Per-target IQR rejection then median.
        # IQR removes frames where the ML tracker snapped to the image centre
        # (pupil occluded at extreme gaze angle) before computing the
        # representative raw position for each card.
        target_meds: list[Tuple[float, float]] = []
        for frames in self._express_raw:
            if frames:
                clean = self._clean_card_samples(frames)
                mx = float(np.median([x for x, y in clean]))
                my = float(np.median([y for x, y in clean]))
                target_meds.append((mx, my))
                if len(clean) < len(frames):
                    logger.debug(
                        "Card IQR: kept %d/%d frames for target %d",
                        len(clean), len(frames), len(target_meds) - 1,
                    )

        if not target_meds:
            logger.warning("Robust cal [Express]: all targets empty — aborting")
            self.phase = CalibrationPhase.DONE
            self._status = "Express failed: no valid targets"
            return

        # Store for polynomial anchor injection during pursuit fitting
        self._express_target_medians = target_meds

        # Target 0 is the center gaze point (user looking straight ahead).
        # Use its median as the normalization origin so forward → (0, 0).
        if self._express_raw[0]:
            center_frames = self._express_raw[0]
            self.express_center_x = float(np.median([x for x, y in center_frames]))
            self.express_center_y = float(np.median([y for x, y in center_frames]))
        else:
            self.express_center_x = target_meds[0][0]
            self.express_center_y = target_meds[0][1]

        # Bounds from per-target medians (min/max across the 9 representative points)
        all_med_x = [m[0] for m in target_meds]
        all_med_y = [m[1] for m in target_meds]
        self.express_x_min = float(min(all_med_x))
        self.express_x_max = float(max(all_med_x))
        self.express_y_min = float(min(all_med_y))
        self.express_y_max = float(max(all_med_y))
        if self.express_x_max - self.express_x_min < 1e-6:
            self.express_x_max = self.express_x_min + 1.0
        if self.express_y_max - self.express_y_min < 1e-6:
            self.express_y_max = self.express_y_min + 1.0
        self.express_calibrated = True
        self.phase = CalibrationPhase.DONE
        logger.info(
            "Robust cal [Express]: center (%.2f, %.2f)  X [%.2f, %.2f]  Y [%.2f, %.2f]",
            self.express_center_x, self.express_center_y,
            self.express_x_min, self.express_x_max,
            self.express_y_min, self.express_y_max,
        )

        # Fit polynomial from card data immediately.
        # This gives a usable poly calibration with clean known-position samples
        # without requiring the smooth-pursuit phase.  The pursuit phase can
        # later refine this polynomial with more data.
        card_ok = self._fit_poly_from_cards()
        if not card_ok:
            self._status = (
                f"Express done — center ({self.express_center_x:.1f}, {self.express_center_y:.1f})"
            )

    def _finalize_blink(self) -> None:
        if self._blink_sclera_samples:
            self.blink_threshold = float(np.mean(self._blink_sclera_samples))
        else:
            self.blink_threshold = 0.05
        self.blink_calibrated = True
        self._blink_end_at = time.time() + BLINK_END_DELAY_S
        self.phase = CalibrationPhase.BLINK_END
        self._status = "Eyes open — blink calibrated"
        logger.info("Robust cal [Blink]: threshold = %.4f", self.blink_threshold)

    def _poly_features(self, x: float, y: float) -> np.ndarray:
        """Degree-2 polynomial feature vector: [1, x, y, x², x·y, y²]."""
        return np.array([1.0, x, y, x * x, x * y, y * y], dtype=np.float64)

    def _fit_polynomial(self) -> None:
        """
        Fit a degree-2 polynomial gaze = f(raw_x, raw_y) from collected pursuit data.

        Two enhancements over plain lstsq:

        1. Velocity-based weighting: frames where the tracker was slow and stable
           (high-confidence positions) receive higher weight than frames captured
           during fast saccades or jitter.

        2. Express anchor injection: the 9 express calibration positions (with their
           known gaze targets) are added as high-weight constraints. This pins the
           polynomial at the known extremes, preventing divergence at gaze angles
           where the tracker is unreliable and pursuit data is sparse.
        """
        self.phase = CalibrationPhase.TRAINING
        self._status = "Fitting polynomial model…"
        total = len(self._pursuit_data)
        logger.info("Robust cal [Pursuit]: %d frames collected, fitting polynomial", total)

        if self.blink_calibrated:
            threshold = self.blink_threshold + _BLINK_SCRUB_MARGIN
            clean = [
                (rx, ry, tx, ty)
                for sr, rx, ry, tx, ty in self._pursuit_data
                if sr > threshold
            ]
            if len(clean) < max(_MIN_POLY_FRAMES, total * 0.2):
                logger.warning(
                    "Robust cal: blink scrub too aggressive (kept %d/%d) — using all frames",
                    len(clean), total,
                )
                clean = [(rx, ry, tx, ty) for _, rx, ry, tx, ty in self._pursuit_data]
            else:
                logger.info("Robust cal: %d/%d frames survived blink scrub", len(clean), total)
        else:
            clean = [(rx, ry, tx, ty) for _, rx, ry, tx, ty in self._pursuit_data]
            logger.info("Robust cal: blink not calibrated — using all %d frames", total)

        if len(clean) < _MIN_POLY_FRAMES:
            logger.warning("Robust cal: only %d clean frames — polynomial not fitted", len(clean))
            self.poly_trained = False
            self.phase = CalibrationPhase.DONE
            self._status = f"Polynomial fit failed — {len(clean)} frames (need {_MIN_POLY_FRAMES})"
            return

        # ── Velocity-based per-sample weights ────────────────────────────────
        # Slow, stable frames → weight near 1.0; fast saccade frames → weight 0.1.
        n_clean = len(clean)
        vels = [0.0]
        for i in range(1, n_clean):
            dx = clean[i][0] - clean[i - 1][0]
            dy = clean[i][1] - clean[i - 1][1]
            vels.append(math.sqrt(dx * dx + dy * dy))
        max_vel = max(vels) if max(vels) > 0 else 1.0
        pursuit_weights = [max(0.1, 1.0 - 0.9 * (v / max_vel)) for v in vels]

        # ── Card anchor injection ─────────────────────────────────────────────
        # Card anchors are CLEAN, precisely-known gaze positions collected during
        # the express card phase.  They receive a much higher weight than the
        # noisy pursuit frames so the polynomial cannot diverge at extreme gaze
        # angles where the pursuit trajectory has sparse, unreliable data.
        #
        # Weight logic (when card poly already exists):
        #   card anchors get weight = max(50, n_clean × 0.15) so they dominate
        #   the fit at the known positions while pursuit data fills the interior.
        # When only express bounds are available (old session without card poly):
        #   fall back to reconstructed anchors with lower weight.
        anchor_meds = self._express_target_medians
        _has_card_poly = getattr(self, "_poly_source", None) == "card"
        if not anchor_meds and self.express_calibrated:
            _cx = self.express_center_x
            _cy = self.express_center_y
            _xn, _xx = self.express_x_min, self.express_x_max
            _yn, _yx = self.express_y_min, self.express_y_max
            anchor_meds = [
                (_cx, _cy),
                (_cx, _yn),
                (_xx, _cy),
                (_cx, _yx),
                (_xn, _cy),
                (_xx, _yn),
                (_xn, _yn),
                (_xx, _yx),
                (_xn, _yx),
            ]
            logger.info(
                "Robust cal [Poly]: reconstructed %d anchors from express bounds",
                len(anchor_meds),
            )
        # Card-quality anchors deserve much higher weight so the pursuit data
        # refines rather than overrides the known positions.
        if _has_card_poly:
            _anchor_w = max(50.0, n_clean * 0.15)
        else:
            _anchor_w = max(5.0, n_clean * 0.02)
        anchors: list[tuple[float, float, float, float]] = []
        for i, (raw_x, raw_y) in enumerate(anchor_meds):
            if i >= len(_EXPRESS_GAZE_TARGETS):
                break
            gx, gy = _EXPRESS_GAZE_TARGETS[i]
            anchors.append((raw_x, raw_y, gx, gy))
        logger.info(
            "Robust cal [Poly]: %d pursuit frames + %d card anchors (w=%.1f, card_prior=%s)",
            n_clean, len(anchors), _anchor_w, _has_card_poly,
        )

        # ── Weighted least-squares ────────────────────────────────────────────
        n_total = n_clean + len(anchors)
        X_mat = np.zeros((n_total, 6), dtype=np.float64)
        yx_vec = np.zeros(n_total, dtype=np.float64)
        yy_vec = np.zeros(n_total, dtype=np.float64)
        w_vec = np.zeros(n_total, dtype=np.float64)

        for i, (rx, ry, tx, ty) in enumerate(clean):
            X_mat[i] = self._poly_features(rx, ry)
            yx_vec[i] = tx
            yy_vec[i] = ty
            w_vec[i] = pursuit_weights[i]

        for j, (rx, ry, gx, gy) in enumerate(anchors):
            idx = n_clean + j
            X_mat[idx] = self._poly_features(rx, ry)
            yx_vec[idx] = gx
            yy_vec[idx] = gy
            w_vec[idx] = _anchor_w

        sqW = np.sqrt(w_vec)
        Xw = X_mat * sqW[:, np.newaxis]
        coeffs_x, _, _, _ = np.linalg.lstsq(Xw, yx_vec * sqW, rcond=None)
        coeffs_y, _, _, _ = np.linalg.lstsq(Xw, yy_vec * sqW, rcond=None)

        self.poly_coeffs_x = coeffs_x
        self.poly_coeffs_y = coeffs_y
        self.poly_trained = True
        self._poly_source = "pursuit"
        self.phase = CalibrationPhase.DONE

        # Residual on pursuit data only (anchors have zero residual by design)
        X_pursuit = X_mat[:n_clean]
        pred_x = X_pursuit @ coeffs_x
        pred_y = X_pursuit @ coeffs_y
        rms = float(np.sqrt(np.mean((pred_x - yx_vec[:n_clean]) ** 2 + (pred_y - yy_vec[:n_clean]) ** 2)))
        src = "card+pursuit" if _has_card_poly else "pursuit"
        self._status = f"Poly [{src}] — {n_clean} frames + {len(anchors)} anchors, RMS {rms:.3f}"
        logger.info(
            "Robust cal [Poly (%s)]: fitted on %d frames + %d anchors, RMS=%.4f",
            src, n_clean, len(anchors), rms,
        )

    # ── Runtime inference ─────────────────────────────────────────────────────

    def normalize_express(
        self, raw_x: float, raw_y: float, clamp: bool = True
    ) -> Tuple[float, float]:
        """
        Center-anchored asymmetric min-max normalization.
        Target 0 (center gaze) → (0, 0).  Each half-axis is scaled independently
        so off-center cameras and asymmetric eye ranges still map cleanly.
        """
        if not self.express_calibrated:
            return raw_x, raw_y
        cx = self.express_center_x
        cy = self.express_center_y

        x_pos = max(self.express_x_max - cx, 1e-6)
        x_neg = max(cx - self.express_x_min, 1e-6)
        y_pos = max(self.express_y_max - cy, 1e-6)
        y_neg = max(cy - self.express_y_min, 1e-6)

        nx = (raw_x - cx) / x_pos if raw_x >= cx else (raw_x - cx) / x_neg
        # Image-space Y increases downward; negate so positive = up (matches CalibrationEllipse).
        ny = -(raw_y - cy) / y_pos if raw_y >= cy else -(raw_y - cy) / y_neg

        if clamp:
            nx = float(np.clip(nx, -1.0, 1.0))
            ny = float(np.clip(ny, -1.0, 1.0))
        return float(nx), float(ny)

    def predict_poly(
        self, raw_x: float, raw_y: float, clamp: bool = True
    ) -> Optional[Tuple[float, float]]:
        """
        Evaluate the polynomial calibration model.
        clamp=True for VRChat (±1), clamp=False for DFR (unclamped).
        """
        if not self.poly_trained or self.poly_coeffs_x is None:
            return None
        feat = self._poly_features(raw_x, raw_y)
        gx = float(np.dot(feat, self.poly_coeffs_x))
        gy = float(np.dot(feat, self.poly_coeffs_y))
        if clamp:
            return float(np.clip(gx, -1.0, 1.0)), float(np.clip(gy, -1.0, 1.0))
        return float(gx), float(gy)

    def predict_svr(self, eye_crop) -> Optional[Tuple[float, float]]:
        """Legacy stub — SVR replaced by predict_poly. Always returns None."""
        return None

    # ── Persistence ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d: dict = {
            "express_calibrated": self.express_calibrated,
            "express_center_x": self.express_center_x,
            "express_center_y": self.express_center_y,
            "express_x_min": self.express_x_min,
            "express_x_max": self.express_x_max,
            "express_y_min": self.express_y_min,
            "express_y_max": self.express_y_max,
            "blink_threshold": self.blink_threshold,
            "blink_calibrated": self.blink_calibrated,
            "poly_trained": self.poly_trained,
            "svr_trained": self.poly_trained,  # compat
        }
        if self._express_target_medians:
            d["express_target_medians"] = list(self._express_target_medians)
        if self.poly_trained and self.poly_coeffs_x is not None:
            d["poly_coeffs_x"] = self.poly_coeffs_x.tolist()
            d["poly_coeffs_y"] = self.poly_coeffs_y.tolist()
        if hasattr(self, "_poly_source"):
            d["poly_source"] = self._poly_source
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RobustCalibrationSession":
        sess = cls()
        sess.express_calibrated = bool(d.get("express_calibrated", False))
        sess.express_x_min = float(d.get("express_x_min", 0.0))
        sess.express_x_max = float(d.get("express_x_max", 1.0))
        sess.express_y_min = float(d.get("express_y_min", 0.0))
        sess.express_y_max = float(d.get("express_y_max", 1.0))
        # Center: loaded explicitly when stored; falls back to range midpoint for old saves.
        sess.express_center_x = float(d.get("express_center_x",
            (sess.express_x_min + sess.express_x_max) / 2.0))
        sess.express_center_y = float(d.get("express_center_y",
            (sess.express_y_min + sess.express_y_max) / 2.0))
        sess.blink_threshold = float(d.get("blink_threshold", 0.05))
        sess.blink_calibrated = bool(d.get("blink_calibrated", False))
        sess.poly_trained = bool(d.get("poly_trained", d.get("svr_trained", False)))
        if "express_target_medians" in d:
            try:
                sess._express_target_medians = [
                    (float(x), float(y)) for x, y in d["express_target_medians"]
                ]
            except Exception:
                pass
        if sess.poly_trained and "poly_coeffs_x" in d:
            try:
                sess.poly_coeffs_x = np.array(d["poly_coeffs_x"], dtype=np.float64)
                sess.poly_coeffs_y = np.array(d["poly_coeffs_y"], dtype=np.float64)
                sess._poly_source = d.get("poly_source", "unknown")
            except Exception as e:
                logger.warning("Polynomial coefficient load failed: %s", e)
                sess.poly_trained = False
        if sess.express_calibrated or sess.poly_trained:
            sess.phase = CalibrationPhase.DONE
        return sess
