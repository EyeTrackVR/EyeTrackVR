import numpy as np
import matplotlib.pyplot as plt

class CalibrationEllipse:
    def __init__(self, n_std_devs=2.5):
        self.xs = []
        self.ys = []
        self.n_std_devs = float(n_std_devs)
        self.fitted = False

        self.scale_factor = 0.85 #TODO Test different values

        # Ellipse parameters
        self.center = None        # (x0,y0) - mean of the point cloud
        self.axes = None          # (a, b) semi-axes (N*std_dev AT 100% SCALE)
        self.rotation = None      # angle in radians (from PCA)
        self.evecs = None         # Eigenvectors (principal axes directions)

    def add_sample(self, x, y):
        self.xs.append(float(x))
        self.ys.append(float(y))
        self.fitted = False

    def set_inset_percent(self, percent_smaller=0.0):
        clamped_percent = np.clip(percent_smaller, 0.0, 100.0)
        self.scale_factor = 1.0 - (clamped_percent / 100.0)
        print(f"Set inset to {clamped_percent}%. New scale_factor: {self.scale_factor}")


    def fit_ellipse(self):

        N = len(self.xs)
        if N < 2:
            print("Warning: Need >= 2 samples to fit PCA. Fit failed.")
            self.fitted = False
            return

        points = np.column_stack([self.xs, self.ys])

        self.center = np.mean(points, axis=0)

        centered_points = points - self.center

        cov = np.cov(centered_points, rowvar=False)

        try:
            evals_cov, evecs_cov = np.linalg.eigh(cov)
        except np.linalg.LinAlgError as e:
            print(f"PCA Eigen-decomposition failed: {e}")
            self.fitted = False
            return

        self.evecs = evecs_cov

        std_devs = np.sqrt(evals_cov)
        self.axes = std_devs * self.n_std_devs

        if self.axes[0] < 1e-12: self.axes[0] = 1e-12
        if self.axes[1] < 1e-12: self.axes[1] = 1e-12

        major_index = np.argmax(evals_cov)
        major_vec = self.evecs[:, major_index]
        self.rotation = np.arctan2(major_vec[1], major_vec[0])

        self.fitted = True

    def fit_and_visualize(self): # Helper function for debug
        plt.figure(figsize=(10, 8))
        plt.plot(self.xs, self.ys, 'k.', label='All Samples', alpha=0.3)
        plt.axis('equal')
        plt.grid(True)
        plt.xlabel('X')
        plt.ylabel('Y')

        if not self.fitted:
            self.fit_ellipse()

        if self.fitted:
            scaled_axes = self.axes * self.scale_factor

            t = np.linspace(0, 2 * np.pi, 200)
            local_coords = np.column_stack([scaled_axes[0] * np.cos(t),
                                            scaled_axes[1] * np.sin(t)])
            world_coords = (self.evecs @ local_coords.T).T + self.center

            plt.plot(world_coords[:, 0], world_coords[:, 1], 'b-', linewidth=2, label=f'Fitted Ellipse ({self.scale_factor*100:.0f}% size)')
            plt.plot(self.center[0], self.center[1], 'b+', markersize=15, label=f'Fitted Center (Mean)')
            plt.title(f'Successful Robust Fit (PCA, {self.n_std_devs} std devs)')
        else:
            plt.title("Robust Fit FAILED (Not enough points)")

        plt.legend()
        plt.show()

    def normalize(self, point, center_point, clip=True):
        if not self.fitted:
            print("Ellipse not fitted yet. Call fit_ellipse() or fit_and_visualize().")
            return 0,0

        x, y = float(point[0]), float(point[1])
        p = np.array([x, y], dtype=float)

        p_centered = p - np.asarray(center_point, dtype=float)

        p_rot = self.evecs.T @ p_centered

        scaled_axes = self.axes * self.scale_factor

        scaled_axes[scaled_axes < 1e-12] = 1e-12

        norm = p_rot / scaled_axes

        if clip:
            norm = np.clip(norm, -1.0, 1.0)

        return float(norm[0]), float(norm[1])