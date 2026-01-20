import numpy as np
import matplotlib.pyplot as plt


class CalibrationEllipse:
    def __init__(self, n_std_devs=2.5):
        self.xs = []
        self.ys = []
        self.n_std_devs = float(n_std_devs)
        self.fitted = False

        self.scale_factor = 0.80

        # --- FLIP SETTINGS ---
        # flip_x=True:  Mirrors the X output. Useful if camera image is mirrored.
        #               (e.g., Eye moves Right on screen, but Left in camera pixel coords)
        # flip_y=False: Standard Cartesian (Looking UP returns Positive Y)
        self.flip_y = False
        self.flip_x = True  # <--- CHANGED TO TRUE

        # Parameters
        self.center = None
        self.axes = None
        self.evecs = None

    def add_sample(self, x, y):
        self.xs.append(float(x))
        self.ys.append(float(y))
        self.fitted = False

    def set_inset_percent(self, percent_smaller=0.0):
        clamped_percent = np.clip(percent_smaller, 0.0, 100.0)
        self.scale_factor = 1.0 - (clamped_percent / 100.0)

    def init_from_save(self, evecs, axes):
        """
        Initialize from save.
        NOTE: We ignore the saved 'evecs' rotation to ensure strict axis alignment.
        """
        try:
            axes_array = np.asarray(axes, dtype=float)

            if axes_array.shape != (2,):
                print(f"[ERROR] Invalid axes shape: {axes_array.shape}.")
                return False

            if np.all(axes_array == 0) or np.any(np.isnan(axes_array)):
                print("[ERROR] Saved data contains zero or NaN values.")
                return False

            # Force Identity Matrix (No Rotation)
            self.evecs = np.eye(2)
            self.axes = axes_array

            self.fitted = True
            return True

        except (ValueError, TypeError) as e:
            print(f"[ERROR] Failed to load calibration data: {e}")
            self.fitted = False
            return False

    def fit_ellipse(self):
        """
        Fits an axis-aligned ellipse (no rotation) using standard deviation.
        """
        N = len(self.xs)
        if N < 2:
            print("Warning: Need >= 2 samples to fit.")
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
        if radius_x < 1e-12: radius_x = 1e-12
        if radius_y < 1e-12: radius_y = 1e-12

        self.axes = np.array([radius_x, radius_y])

        # 3. Force Identity Matrix (Strict Horizontal/Vertical alignment)
        self.evecs = np.eye(2)

        self.fitted = True
        return self.evecs, self.axes

    def normalize(self, pupil_pos, target_pos=None, clip=True):
        if not self.fitted:
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

    def denormalize(self, norm_x, norm_y, target_pos=None):
        if not self.fitted:
            return 0.0, 0.0

        # 1. Reverse the Output Mapping
        nx = -norm_x if self.flip_x else norm_x
        ny = norm_y if self.flip_y else -norm_y

        # 2. Scale back up
        rx, ry = self.axes * self.scale_factor
        dx = nx * rx
        dy = ny * ry

        # 3. Add Center
        if target_pos is None:
            cx, cy = self.center
        else:
            cx, cy = target_pos

        return float(cx + dx), float(cy + dy)

    def fit_and_visualize(self):
        plt.figure(figsize=(10, 8))

        plt.plot(self.xs, self.ys, 'k.', label='Samples', alpha=0.5)
        plt.axis('equal')
        plt.grid(True, alpha=0.3)

        # Invert plot Y axis to match screen coordinates
        plt.gca().invert_yaxis()

        if not self.fitted:
            self.fit_ellipse()

        if self.fitted:
            scaled_axes = self.axes * self.scale_factor
            t = np.linspace(0, 2 * np.pi, 200)

            el_x = self.center[0] + scaled_axes[0] * np.cos(t)
            el_y = self.center[1] + scaled_axes[1] * np.sin(t)

            plt.plot(el_x, el_y, 'b-', linewidth=2, label='Axis-Aligned Fit')
            plt.plot(self.center[0], self.center[1], 'r+', markersize=15, label='Center')

            plt.hlines(self.center[1],
                       self.center[0] - scaled_axes[0],
                       self.center[0] + scaled_axes[0],
                       colors='g', linestyles='-', label='Width (X)')

            plt.vlines(self.center[0],
                       self.center[1] - scaled_axes[1],
                       self.center[1] + scaled_axes[1],
                       colors='m', linestyles='-', label='Height (Y)')

            plt.title(f'Axis-Aligned Calibration (FlipX={self.flip_x})')
        else:
            plt.title("Fit FAILED")

        plt.legend()
        plt.tight_layout()
        plt.show()