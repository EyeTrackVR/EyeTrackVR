import logging

import numpy as np

logger = logging.getLogger(__name__)


class CalibrationEllipse:
    def __init__(self, n_std_devs=2.5):
        self.xs = []
        self.ys = []
        self.n_std_devs = float(n_std_devs)
        self.fitted = False

        self.scale_factor = 0.80

        self.flip_y = False
        self.flip_x = True

        # Parameters
        self.center = None
        self.axes = None
        self.evecs = None

    def add_sample(self, x, y):
        self.xs.append(float(x))
        self.ys.append(float(y))
        self.fitted = False

    def init_from_save(self, evecs, axes):
        """
        Initialize from save.
        NOTE: We ignore the saved 'evecs' rotation to ensure strict axis alignment.
        """
        try:
            axes_array = np.asarray(axes, dtype=float)

            if axes_array.shape != (2,):
                logger.error("Invalid calibration axes shape: %s.", axes_array.shape)
                return False

            if np.all(axes_array == 0) or np.any(np.isnan(axes_array)):
                logger.error("Saved calibration data contains zero or NaN values.")
                return False

            # Force Identity Matrix (No Rotation)
            self.evecs = np.eye(2)
            self.axes = axes_array

            self.fitted = True
            return True

        except (ValueError, TypeError) as e:
            logger.error("Failed to load calibration data: %s", e)
            self.fitted = False
            return False

    def fit_ellipse(self):
        """
        Fits an axis-aligned ellipse (no rotation) using standard deviation.
        """
        N = len(self.xs)
        if N < 2:
            logger.warning("Need >= 2 samples to fit the calibration ellipse.")
            self.fitted = False
            return 0, 0

        # 1. Calculate Center (Mean)
        mean_x = np.mean(self.xs)
        mean_y = np.mean(self.ys)
        self.center = np.array([mean_x, mean_y])

        # 2. Calculate Axis Lengths (Standard Deviation)
        std_x = np.std(self.xs)
        std_y = np.std(self.ys)

        # Apply sigma multiplier
        radius_x = std_x * self.n_std_devs
        radius_y = std_y * self.n_std_devs

        # Safety clamp
        if radius_x < 1e-12:
            radius_x = 1e-12
        if radius_y < 1e-12:
            radius_y = 1e-12

        self.axes = np.array([radius_x, radius_y])

        # 3. Force Identity Matrix (Strict Horizontal/Vertical alignment)
        self.evecs = np.eye(2)

        self.fitted = True
        return self.evecs, self.axes

    def normalize(self, pupil_pos, target_pos=None, clip=True):
        if (
            not self.fitted
            or self.axes is None
            or np.asarray(self.axes).shape != (2,)
            or not np.all(np.isfinite(self.axes))
            or np.any(np.asarray(self.axes) <= 0)
            or (target_pos is None and self.center is None)
        ):
            return 0.0, 0.0

        x, y = float(pupil_pos[0]), float(pupil_pos[1])

        if target_pos is None:
            cx, cy = self.center
        else:
            cx, cy = target_pos

        # Calculate deltas
        dx = x - cx
        dy = y - cy

        # Get calibration radii
        rx, ry = self.axes * self.scale_factor

        # Normalize
        norm_x = dx / rx
        norm_y = dy / ry

        # --- APPLY FLIPS ---
        # If flip_x is True: Inverts the sign.
        final_x = -norm_x if self.flip_x else norm_x

        # If flip_y is False: Inverts Screen Y (so Up is Positive).
        final_y = norm_y if self.flip_y else -norm_y

        if clip:
            final_x = np.clip(final_x, -1.0, 1.0)
            final_y = np.clip(final_y, -1.0, 1.0)

        return float(final_x), float(final_y)
