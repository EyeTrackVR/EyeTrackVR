# calibration_module.py
import numpy as np
class CalibrationProcessor:
    def __init__(self):
        self.left_eye_data = None
        self.right_eye_data = None
        self.P_left = None
        self.P_right = None
        self.gt_3d = np.array([
    (0.8, 0.8, 1), (0, 0.8, 1), (-0.8, 0.8, 1), (0.8, 0, 1), (0, 0, 1),
    (-0.8, 0, 1), (0.8, -0.8, 1), (0, -0.8, 1), (-0.8, -0.8, 1)
])

    def estimate_projection_matrix(self, eye_data, gt_3d):
        # Ensure the input data is a numpy array
        eye_data = np.array(eye_data)
        gt_3d = np.array(gt_3d)

        # Append ones for homogeneous coordinates
        gt_3d_h = np.hstack((gt_3d, np.ones((gt_3d.shape[0], 1))))
        eye_data_h = np.hstack((eye_data, np.ones((eye_data.shape[0], 1))))

        # Debug: Print the shapes of the matrices
        print("Shape of gt_3d_h:", gt_3d_h.shape)
        print("Shape of eye_data_h:", eye_data_h.shape)

        # Solve for the projection matrix using least squares
        P, _, _, _ = np.linalg.lstsq(gt_3d_h, eye_data_h, rcond=None)
        return P



    def receive_calibration_data(self, eye_id, data):
        if eye_id == 1:
            self.left_eye_data = data
        elif eye_id == 0:
            self.right_eye_data = data

       # print('receive',len(self.left_eye_data), self.left_eye_data, self.right_eye_data, data, eye_id)
        # Check if both sets of data have been received
        if self.left_eye_data is not None and self.right_eye_data is not None:
            if len(self.left_eye_data) == 8 and len(self.right_eye_data) == 8:
                self.process_calibration_data()

    def process_calibration_data(self):
        # Ensure both data are present
        if self.left_eye_data is None or self.right_eye_data is None:
            raise ValueError("Calibration data for both eyes must be provided")


        print("Processing calibration data for both eyes...")
        print(f"Left Eye Data: {self.left_eye_data}")
        print(f"Right Eye Data: {self.right_eye_data}")

        self.left_eye_data = np.array(self.left_eye_data)
        self.right_eye_data = np.array(self.right_eye_data)
        if len(self.left_eye_data) != len(self.gt_3d):
            raise ValueError(
                f"Number of left eye points ({len(self.left_eye_data)}) does not match number of 3D points ({len(self.gt_3d)}).")
        if len(self.right_eye_data) != len(self.gt_3d):
            raise ValueError(
                f"Number of right eye points ({len(self.right_eye_data)}) does not match number of 3D points ({len(self.gt_3d)}).")



        # After processing, reset the data
       # self.left_eye_data = None
      #  self.right_eye_data = None

    # Function to compute the 3D gaze direction from 2D points
    def compute_gaze_direction(self, P, point_2d):
        print(P, point_2d)
        # Convert 2D point to homogeneous coordinates
        point_2d_h = np.append(point_2d, 1)
        # Solve for 3D direction (Ax = b, where A is the projection matrix and b is the 2D point)
        direction, _, _, _ = np.linalg.lstsq(P[:, :-1], point_2d_h, rcond=None)
        direction /= np.linalg.norm(direction)
        return direction


    # Compute the convergence point given 2D points for both eyes
    def compute_convergence_point(self, left_point_2d, right_point_2d, P_left, P_right, IPD):
        left_eye_pos = np.array([-IPD / 2, 0, 0])
        right_eye_pos = np.array([IPD / 2, 0, 0])

        gaze_left = self.compute_gaze_direction(P_left, left_point_2d)
        gaze_right = self.compute_gaze_direction(P_right, right_point_2d)

        # Parameterize the gaze directions as lines
        def line_parametric_form(point, direction, t):
            return point + t * direction

        # Find the closest point between two lines
        t_values = np.linspace(-10, 10, 1000)
        min_distance = float('inf')
        best_point = None

        for t1 in t_values:
            for t2 in t_values:
                point1 = line_parametric_form(left_eye_pos, gaze_left, t1)
                point2 = line_parametric_form(right_eye_pos, gaze_right, t2)
                distance = np.linalg.norm(point1 - point2)
                if distance < min_distance:
                    min_distance = distance
                    best_point = (point1 + point2) / 2

        return best_point

    def set_P(self):
        self.P_left = self.estimate_projection_matrix(self.left_eye_data, self.gt_3d)
        self.P_right = self.estimate_projection_matrix(self.right_eye_data, self.gt_3d)



# Global instance of CalibrationProcessor
calibration_processor = CalibrationProcessor()

def receive_calibration_data(data, eye_id):
    global calibration_processor
    calibration_processor.receive_calibration_data(eye_id, data)

def converge_3d():
    IPD = 0.058
    left_point_2d = (120, 100)
    right_point_2d = (118, 65)
   # estimate_projection_matrix
    calibration_processor.set_P()
    convergence_point = calibration_processor.compute_convergence_point(left_point_2d, right_point_2d, calibration_processor.P_left, calibration_processor.P_right, IPD)

    print(f"Convergence Point: {convergence_point}")