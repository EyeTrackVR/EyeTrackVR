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
     #   print(f"Set inset to {clamped_percent}%. New scale_factor: {self.scale_factor}")

    def init_from_save(self, evecs, axes):
        """Initialize calibration from saved data with validation"""
        try:
            evecs_array = np.asarray(evecs, dtype=float)
            axes_array = np.asarray(axes, dtype=float)
            
            # Validate evecs shape
            if evecs_array.shape != (2, 2):
                print(f"\033[91m[ERROR] Invalid evecs shape in saved data: {evecs_array.shape}. Expected (2, 2).\033[0m")
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
            return 0,0

        points = np.column_stack([self.xs, self.ys])
        self.center = np.mean(points, axis=0)
        centered_points = points - self.center

        cov = np.cov(centered_points, rowvar=False)

        try:
            evals_cov, evecs_cov = np.linalg.eigh(cov)
        except np.linalg.LinAlgError as e:
   #         print(f"PCA Eigen-decomposition failed: {e}")
            self.fitted = False
            return 0,0

        # Sort eigenvectors by alignment with screen axes (X, Y), not by magnitude
        # evecs_cov[:, 0] is eigenvector for first eigenvalue, evecs_cov[:, 1] for second
        # We want [0] to be X-axis aligned, [1] to be Y-axis aligned

        # Determine which eigenvector is more X-aligned vs Y-aligned
        x_alignment = np.abs(evecs_cov[0, :])  # How much each evec points in X direction
        y_alignment = np.abs(evecs_cov[1, :])  # How much each evec points in Y direction

        if x_alignment[0] > x_alignment[1]:
            # evec 0 is more X-aligned, evec 1 is more Y-aligned - keep as is
            self.evecs = evecs_cov
            std_devs = np.sqrt(evals_cov)
        else:
            # evec 1 is more X-aligned, evec 0 is more Y-aligned - swap them
            self.evecs = evecs_cov[:, [1, 0]]
            std_devs = np.sqrt(evals_cov[[1, 0]])

        # Ensure each eigenvector points in the positive direction of its dominant axis
        # For the X-aligned eigenvector (column 0), ensure it points in +X
        # For the Y-aligned eigenvector (column 1), ensure it points in +Y
        if self.evecs[0, 0] < 0:
            self.evecs[:, 0] *= -1
        if self.evecs[1, 1] < 0:
            self.evecs[:, 1] *= -1

        self.axes = std_devs * self.n_std_devs

        if self.axes[0] < 1e-12: self.axes[0] = 1e-12
        if self.axes[1] < 1e-12: self.axes[1] = 1e-12

        major_index = np.argmax(std_devs)
        major_vec = self.evecs[:, major_index]
        self.rotation = np.arctan2(major_vec[1], major_vec[0])

        self.fitted = True
        return self.evecs, self.axes


        # Scale by ellipse axes (with scale factor for margins)
        scaled_axes = self.axe
    #    print(f"Ellipse fitted: center={self.center}, axes={self.axes}, rotation={np.degrees(self.rotation):.1f}°")

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
        #    print("ERROR: Ellipse not fitted yet. Call fit_ellipse() first.")
            return 0.0, 0.0

        # Validate calibration data before matrix operations
        if self.evecs is None or self.axes is None:
            print("\033[91m[ERROR] Calibration data (evecs/axes) is None. Please calibrate.\033[0m")
            return 0.0, 0.0
        
        # Check if evecs has valid shape
        if not isinstance(self.evecs, np.ndarray) or self.evecs.shape != (2, 2):
            print(f"\033[91m[ERROR] Invalid evecs shape: {self.evecs.shape if isinstance(self.evecs, np.ndarray) else type(self.evecs)}. Expected (2, 2). Please recalibrate.\033[0m")
            return 0.0, 0.0
        
        # Check if axes has valid shape and is not zero
        if not isinstance(self.axes, np.ndarray) or self.axes.shape != (2,):
            print(f"\033[91m[ERROR] Invalid axes shape: {self.axes.shape if isinstance(self.axes, np.ndarray) else type(self.axes)}. Expected (2,). Please recalibrate.\033[0m")
            return 0.0, 0.0
        
        # Check if axes contains valid non-zero values
        if np.all(self.axes == 0) or np.any(np.isnan(self.axes)):
            print("\033[91m[ERROR] Calibration axes are zero or invalid. Please recalibrate.\033[0m")
            return 0.0, 0.0

        # Current pupil position
        x, y = float(pupil_pos[0]), float(pupil_pos[1])
        p = np.array([x, y], dtype=float)

        # Reference point (where we're measuring FROM)
        # If no target specified, use ellipse center (neutral gaze position)
        if target_pos is None:
            reference = self.center
        else:
            reference = np.asarray(target_pos, dtype=float)

        # Vector from reference to current pupil position
        p_centered = p - reference
        
        # If evecs was loaded from an older version, it might be (2,2) but transposed.
        # But we now consistently store eigenvectors as COLUMNS.
        # To rotate into ellipse space, we multiply by evecs.T (which has basis vectors as ROWS).
        # p_rot = B.T @ p_centered

        # Rotate into ellipse principal axes space
        try:
            p_rot = self.evecs.T @ p_centered
        except (ValueError, TypeError) as e:
            print(f"\033[91m[ERROR] Matrix multiplication failed in normalize: {e}. Please recalibrate.\033[0m")
            return 0.0, 0.0

        # Scale by ellipse axes (with scale factor for margins)
        scaled_axes = self.axes * self.scale_factor
        scaled_axes[scaled_axes < 1e-12] = 1e-12

        # Normalize: pupil offset / ellipse radius in that direction
        norm = p_rot / scaled_axes

        # Apply coordinate flips for eye tracking conventions
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

        # Apply inverse flips
        nx = -norm_x if self.flip_x else norm_x
        ny = norm_y if self.flip_y else -norm_y

        # Scale by ellipse axes
        scaled_axes = self.axes * self.scale_factor
        p_rot = np.array([nx, ny]) * scaled_axes

        # Rotate back to world space: v = B @ c (where B has basis vectors as COLUMNS)
        p_centered = self.evecs @ p_rot

        # Add reference point
        reference = self.center if target_pos is None else np.asarray(target_pos, dtype=float)
        p = p_centered + reference

        return float(p[0]), float(p[1])
