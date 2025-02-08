from eye import EyeId
from utils.misc_utils import clamp

def smart_inversion(self, var, out_x, out_y):

    #Checks to see if the class already has frame counts or inversion attributes
    if not hasattr(self, "inverted_frame_count"):
        self.inverted_frame_count = 0
    
    if not hasattr(self, "normal_frame_count"):
        self.normal_frame_count = 0

    if not hasattr(self, "is_inverted"):
        self.is_inverted = False

    #Updates eye positions with latest
    if self.eye_id == EyeId.LEFT:
        var.l_eye_x = out_x
        var.left_y = out_y

    if self.eye_id == EyeId.RIGHT:
        var.r_eye_x = out_x
        var.right_y = out_y

    #Checks if eyes are inverted, and then activates inversion if the conditions have been true for a specified number of frames.
    if (var.l_eye_x > 0 and var.r_eye_x < 0) and (abs(var.l_eye_x - var.r_eye_x) > self.settings.gui_smartinversion_thresh):
        self.inverted_frame_count = min(self.inverted_frame_count + 1, self.settings.gui_smartinversion_frame_count)

        if self.inverted_frame_count == self.settings.gui_smartinversion_frame_count:
            self.is_inverted = True
            self.normal_frame_count = 0
            print(f"Inversion Activated")

    #Checks if the eyes are no longer inverted, and then clears inversion if the conditions haven't been true for a specified number of frames.
    elif self.is_inverted and (
        not (var.l_eye_x > 0 and var.r_eye_x < 0) or
        abs(var.l_eye_x - var.r_eye_x) <= self.settings.gui_smartinversion_thresh
        ):

        self.normal_frame_count = min(self.normal_frame_count + 1, self.settings.gui_smartinversion_frame_count)

        if self.normal_frame_count == self.settings.gui_smartinversion_frame_count:
            self.is_inverted = False
            self.inverted_frame_count = 0
            print(f"Inversion Cleared")


    #Determines which eye is being tracked based off selection and sets values accordingly
    if self.settings.gui_smartinversion_select_right:
        tracked_eye_x = var.r_eye_x
        tracked_eye_y = var.right_y
        recessive_eye = EyeId.LEFT
    else:
        tracked_eye_x = var.l_eye_x
        tracked_eye_y = var.left_y
        recessive_eye = EyeId.RIGHT

    out_x = tracked_eye_x
    out_y = tracked_eye_y
    
    #If eyes are inverted, and eye being processed is recessive, invert x value.
    if self.eye_id == recessive_eye:
        if self.is_inverted:
            out_x = -tracked_eye_x
        else:
            out_x = tracked_eye_x
    else:
        out_x = tracked_eye_x

    out_y = tracked_eye_y

    return out_x, out_y
