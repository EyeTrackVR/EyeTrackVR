from eye import EyeId
from utils.misc_utils import clamp

def smart_inversion(self, var, out_x, out_y):

    #Checks to see if the class already has frame counts, inversion attributes or smoothing attributes
    if not hasattr(self, "smartinversion_inverted_frame_count"):
        self.smartinversion_inverted_frame_count = 0
    if not hasattr(self, "smartinversion_normal_frame_count"):
        self.smartinversion_normal_frame_count = 0
    if not hasattr(self, "smartinversion_is_inverted"):
        self.smartinversion_is_inverted = False
    if not hasattr(self, "smartinversion_smoothing_progress"):
        self.smartinversion_smoothing_progress = 0
    if not hasattr(self, "smartinversion_smoothed_eye_x"):
        self.smartinversion_smoothed_eye_x = 0.0
    if not hasattr(self, "smartinversion_previous_inversion_state"):
        self.smartinversion_previous_inversion_state = False

    #Updates eye positions with latest
    if self.eye_id == EyeId.LEFT:
        var.l_eye_x = out_x
        var.left_y = out_y

    if self.eye_id == EyeId.RIGHT:
        var.r_eye_x = out_x
        var.right_y = out_y

    #Checks if eyes are inverted, and then activates inversion if the conditions have been true for a specified number of frames.
    if (var.l_eye_x > 0 and var.r_eye_x < 0) and (abs(var.l_eye_x - var.r_eye_x) > self.settings.gui_smartinversion_thresh):
        self.smartinversion_inverted_frame_count = min(self.smartinversion_inverted_frame_count + 1, self.settings.gui_smartinversion_frame_count)

        if self.smartinversion_inverted_frame_count == self.settings.gui_smartinversion_frame_count:
            if not self.smartinversion_is_inverted:
                self.smartinversion_is_inverted = True
                self.smartinversion_normal_frame_count = 0
                print(f"Inversion Activated")

    #Checks if the eyes are no longer inverted, and then clears inversion if the conditions haven't been true for a specified number of frames.
    elif self.smartinversion_is_inverted and (
        not (var.l_eye_x > self.settings.gui_smartinversion_minthresh and var.r_eye_x < -self.settings.gui_smartinversion_minthresh) or
        abs(var.l_eye_x - var.r_eye_x) <= self.settings.gui_smartinversion_thresh
        ):

        self.smartinversion_normal_frame_count = min(self.smartinversion_normal_frame_count + 1, self.settings.gui_smartinversion_frame_count)

        if self.smartinversion_normal_frame_count == self.settings.gui_smartinversion_frame_count:
            if self.smartinversion_is_inverted:
                self.smartinversion_is_inverted = False
                self.smartinversion_inverted_frame_count = 0
                print(f"Inversion Cleared")

    #Checks if the inversion state has recently been toggled, and activates smoothing
    if self.smartinversion_previous_inversion_state != self.smartinversion_is_inverted:
        self.smartinversion_smoothing_progress = 1
        self.smartinversion_previous_inversion_state = self.smartinversion_is_inverted

    #Determines which eye is being tracked based off selection and sets values accordingly
    if self.settings.gui_smartinversion_select_right:
        tracked_eye_x = var.r_eye_x
        tracked_eye_y = var.right_y
        recessive_eye = EyeId.LEFT
        dominant_eye = EyeId.RIGHT
    else:
        tracked_eye_x = var.l_eye_x
        tracked_eye_y = var.left_y
        recessive_eye = EyeId.RIGHT
        dominant_eye = EyeId.LEFT

    out_x = tracked_eye_x
    out_y = tracked_eye_y
    
    #Logic if smoothing is activated
    if self.smartinversion_smoothing_progress > 0:
        smartinversion_lerp_factor = (1 - self.smartinversion_smoothing_progress)

        if self.smartinversion_is_inverted and self.eye_id == recessive_eye:
            self.smartinversion_smoothed_eye_x += (-tracked_eye_x - self.smartinversion_smoothed_eye_x) * smartinversion_lerp_factor
        else:
            self.smartinversion_smoothed_eye_x += (tracked_eye_x - self.smartinversion_smoothed_eye_x) * smartinversion_lerp_factor

        self.smartinversion_smoothing_progress = max(self.smartinversion_smoothing_progress - self.settings.gui_smartinversion_smoothing_rate, 0)
        out_x = self.smartinversion_smoothed_eye_x

    #Logic if inversion is active, but smoothing is not active
    elif self.smartinversion_is_inverted and self.eye_id == recessive_eye:
        out_x = -tracked_eye_x

    out_y = tracked_eye_y

    return out_x, out_y
