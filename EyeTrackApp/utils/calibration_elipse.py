import numpy as np
import matplotlib.pyplot as plt


class CalibrationEllipse:
    def __init__(self, n_std_devs=2.5):
        self.xs = []
        self.ys = []
        self.n_std_devs = float(n_std_devs)
        self.fitted = False

        self.scale_factor = 0.80

        self.flip_y = False  # Set to True if up/down are backwards
        self.flip_x = False  # Adjust if left/right are backwards

        # Ellipse parameters
        self.center = None  # Mean pupil position (ellipse center)
        self.axes = None  # Semi-axes (std_dev based)
        self.rotation = None  # Rotation angle
        self.evecs = None  # Eigenvectors

    def add_sample(self, x, y):
        self.xs.append(float(x))
        self.ys.append(float(y))
        self.fitted = False

    def set_inset_percent(self, percent_smaller=0.0):
        clamped_percent = np.clip(percent_smaller, 0.0, 100.0)
        self.scale_factor = 1.0 - (clamped_percent / 100.0)

    def init_from_save(self, evecs, axes):
        """Initialize calibration from saved data with validation"""
        try:
            evecs_array = np.asarray(evecs, dtype=float)
            axes_array = np.asarray(axes, dtype=float)

            # Validate evecs shape
            if evecs_array.shape != (2, 2):
                print(
                    f"\033[91m[ERROR] Invalid evecs shape in saved data: {evecs_array.shape}. Expected (2, 2).\033[0m")
                self.fitted = False
                return False

            # Validate axes shape
            if axes_array.shape != (2,):
                print(f"\033[91m[ERROR] Invalid axes shape in saved data: {axes_array.shape}. Expected (2,).\033[0m")
                self.fitted = False
                return False

            # Check for zero or invalid values
            if np.all(axes_array == 0) or np.any(np.isnan(axes_array)) or np.any(np.isnan(evecs_array)):
                print("\033[91m[ERROR] Saved calibration data contains zero or NaN values.\033[0m")
                self.fitted = False
                return False

            self.evecs = evecs_array
            self.axes = axes_array
            self.fitted = True
            return True

        except (ValueError, TypeError) as e:
            print(f"\033[91m[ERROR] Failed to load calibration data: {e}\033[0m")
            self.fitted = False
            return False

    def fit_ellipse(self):
        N = len(self.xs)
        if N < 2:
            print("Warning: Need >= 2 samples to fit PCA. Fit failed.")
            self.fitted = False
            return 0, 0

        points = np.column_stack([self.xs, self.ys])
        self.center = np.mean(points, axis=0)
        centered_points = points - self.center

        cov = np.cov(centered_points, rowvar=False)

        try:
            evals_cov, evecs_cov = np.linalg.eigh(cov)
        except np.linalg.LinAlgError as e:
            self.fitted = False
            return 0, 0

        # Sort eigenvectors by alignment with screen axes (X, Y)
        x_alignment = np.abs(evecs_cov[0, :])  # How much each evec points in X direction

        if x_alignment[0] > x_alignment[1]:
            # evec 0 is more X-aligned, evec 1 is more Y-aligned
            self.evecs = evecs_cov
            std_devs = np.sqrt(evals_cov)
        else:
            # evec 1 is more X-aligned, swap them
            self.evecs = evecs_cov[:, [1, 0]]
            std_devs = np.sqrt(evals_cov[[1, 0]])

        # --- FIX STARTS HERE ---
        # 1. Ensure the X-aligned eigenvector points Right (Positive X)
        if self.evecs[0, 0] < 0:
            self.evecs[:, 0] *= -1

        # 2. Ensure Y-aligned eigenvector maintains a Right-Handed Coordinate System.
        #    Instead of checking Y-sign independently, check the Determinant.
        #    In screen coords (Y down), X=(1,0) and Y=(0,1) gives det = 1.
        #    If det < 0, the axes are mirrored; we flip Y to fix it.
        det = (self.evecs[0, 0] * self.evecs[1, 1]) - (self.evecs[0, 1] * self.evecs[1, 0])

        if det < 0:
            self.evecs[:, 1] *= -1
        # --- FIX ENDS HERE ---

        self.axes = std_devs * self.n_std_devs

        if self.axes[0] < 1e-12: self.axes[0] = 1e-12
        if self.axes[1] < 1e-12: self.axes[1] = 1e-12

        major_index = np.argmax(std_devs)
        major_vec = self.evecs[:, major_index]
        self.rotation = np.arctan2(major_vec[1], major_vec[0])

        self.fitted = True
        return self.evecs, self.axes

    def fit_and_visualize(self):
        plt.figure(figsize=(10, 8))
        plt.plot(self.xs, self.ys, 'k.', label='Calibration Samples', alpha=0.5, markersize=8)
        plt.axis('equal')
        plt.grid(True, alpha=0.3)
        plt.xlabel('Pupil X (pixels)')
        plt.ylabel('Pupil Y (pixels)')

        if not self.fitted:
            self.fit_ellipse()

        if self.fitted:
            scaled_axes = self.axes * self.scale_factor

            t = np.linspace(0, 2 * np.pi, 200)
            local_coords = np.column_stack([scaled_axes[0] * np.cos(t),
                                            scaled_axes[1] * np.sin(t)])
            world_coords = (self.evecs @ local_coords.T).T + self.center

            plt.plot(world_coords[:, 0], world_coords[:, 1], 'b-',
                     linewidth=2, label=f'Calibration Ellipse ({self.scale_factor * 100:.0f}% scale)')
            plt.plot(self.center[0], self.center[1], 'r+',
                     markersize=15, markeredgewidth=3, label='Ellipse Center (Mean)')

            # Draw principal axes
            for i, (axis_len, color, name) in enumerate([(scaled_axes[0], 'g', 'Major'),
                                                         (scaled_axes[1], 'm', 'Minor')]):
                axis_vec = self.evecs[:, i] * axis_len
                plt.arrow(self.center[0], self.center[1], axis_vec[0], axis_vec[1],
                          head_width=5, head_length=7, fc=color, ec=color, alpha=0.6,
                          label=f'{name} Axis')

            plt.title(f'Eye Tracking Calibration Ellipse (PCA, {self.n_std_devs}σ)')
        else:
            plt.title("Ellipse Fit FAILED (Not enough points)")

        plt.legend()
        plt.tight_layout()
        plt.show()

    def normalize(self, pupil_pos, target_pos=None, clip=True):
        if not self.fitted:
            return 0.0, 0.0

        if self.evecs is None or self.axes is None:
            print("\033[91m[ERROR] Calibration data (evecs/axes) is None. Please calibrate.\033[0m")
            return 0.0, 0.0

        if not isinstance(self.evecs, np.ndarray) or self.evecs.shape != (2, 2):
            print(f"\033[91m[ERROR] Invalid evecs shape. Expected (2, 2). Please recalibrate.\033[0m")
            return 0.0, 0.0

        if not isinstance(self.axes, np.ndarray) or self.axes.shape != (2,):
            print(f"\033[91m[ERROR] Invalid axes shape. Expected (2,). Please recalibrate.\033[0m")
            return 0.0, 0.0

        if np.all(self.axes == 0) or np.any(np.isnan(self.axes)):
            print("\033[91m[ERROR] Calibration axes are zero or invalid. Please recalibrate.\033[0m")
            return 0.0, 0.0

        x, y = float(pupil_pos[0]), float(pupil_pos[1])
        p = np.array([x, y], dtype=float)

        if target_pos is None:
            reference = self.center
        else:
            reference = np.asarray(target_pos, dtype=float)

        p_centered = p - reference

        try:
            p_rot = self.evecs.T @ p_centered
        except (ValueError, TypeError) as e:
            print(f"\033[91m[ERROR] Matrix multiplication failed in normalize: {e}. Please recalibrate.\033[0m")
            return 0.0, 0.0

        scaled_axes = self.axes * self.scale_factor
        scaled_axes[scaled_axes < 1e-12] = 1e-12

        norm = p_rot / scaled_axes

        norm_x = -norm[0] if self.flip_x else norm[0]
        norm_y = norm[1] if self.flip_y else -norm[1]

        if clip:
            norm_x = np.clip(norm_x, -1.0, 1.0)
            norm_y = np.clip(norm_y, -1.0, 1.0)

        return float(norm_x), float(norm_y)

    def denormalize(self, norm_x, norm_y, target_pos=None):
        if not self.fitted:
            print("ERROR: Ellipse not fitted yet.")
            return 0.0, 0.0

        nx = -norm_x if self.flip_x else norm_x
        ny = norm_y if self.flip_y else -norm_y

        scaled_axes = self.axes * self.scale_factor
        p_rot = np.array([nx, ny]) * scaled_axes

        p_centered = self.evecs @ p_rot
        reference = self.center if target_pos is None else np.asarray(target_pos, dtype=float)
        p = p_centered + reference

        return float(p[0]), float(p[1])