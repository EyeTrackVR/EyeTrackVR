import numpy as np

from eye import EyeId


def velocity_falloff(self, var, out_x, out_y):

    if (
        self.settings.gui_right_eye_dominant
        or self.settings.gui_left_eye_dominant
        or self.settings.gui_outer_side_falloff
    ):
        # Calculate the distance between the two eyes
        dist = np.sqrt(np.square(var.l_eye_x - var.r_eye_x) + np.square(var.left_y - var.right_y))
        if self.eye_id == EyeId.LEFT:
            var.l_eye_x = out_x
            var.left_y = out_y

        if self.eye_id == EyeId.RIGHT:
            var.r_eye_x = out_x
            var.right_y = out_y

        # Check if the distance is greater than the threshold
        if dist > self.settings.gui_eye_dominant_diff_thresh:

            if self.settings.gui_right_eye_dominant:
                out_x, out_y = var.r_eye_x, var.right_y

            elif self.settings.gui_left_eye_dominant:
                out_x, out_y = var.l_eye_x, var.left_y

            else:
                # If the distance is too large, identify the eye with the lower velocity
                if var.l_eye_velocity < var.r_eye_velocity:
                    # Mirror the position of the eye with lower velocity to the other eye
                    out_x, out_y = var.r_eye_x, var.right_y
                else:
                    # Mirror the position of the eye with lower velocity to the other eye
                    out_x, out_y = var.l_eye_x, var.left_y
        else:
            # If the distance is within the threshold, do not mirror the eyes
            pass
    else:
        pass
    return out_x, out_y
