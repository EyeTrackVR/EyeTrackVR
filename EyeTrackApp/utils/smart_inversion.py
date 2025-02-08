from eye import EyeId
from utils.misc_utils import clamp

inverted_frames = int
cleared_frames = int

def smart_inversion(self, var, out_x, out_y):

    #Updates eye positions with latest
    if self.eye_id == EyeId.LEFT:
        var.l_eye_x = out_x
        var.left_y = out_y

    if self.eye_id == EyeId.RIGHT:
        var.r_eye_x = out_x
        var.right_y = out_y

    #Checks if eyes are inverted
    if (var.l_eye_x > 0 and var.r_eye_x < 0) and (abs(var.l_eye_x - var.r_eye_x) > self.settings.gui_smartinversion_thresh):
        is_inverted = True
    else:
        is_inverted = False

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
        if is_inverted:
            out_x = -tracked_eye_x
        else:
            out_x = tracked_eye_x
    else:
        out_x = tracked_eye_x

    out_y = tracked_eye_y

    return out_x, out_y
