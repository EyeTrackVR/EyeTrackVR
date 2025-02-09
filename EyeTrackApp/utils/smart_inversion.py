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
    if not hasattr(self, "smartinversion_stare_ahead"):
        self.smartinversion_stare_ahead = False

    #Updates eye positions with latest
    if self.eye_id == EyeId.LEFT:
        var.l_eye_x = out_x
        var.left_y = out_y

    if self.eye_id == EyeId.RIGHT:
        var.r_eye_x = out_x
        var.right_y = out_y

    #Determines which eye is being tracked based off selection and sets values accordingly
    if self.settings.gui_smartinversion_select_right:
        tracked_eye_x = var.r_eye_x
        tracked_eye_y = var.right_y
        is_rec_eye = (self.eye_id == EyeId.LEFT)
        is_dom_eye = (self.eye_id == EyeId.RIGHT)
        
    else:
        tracked_eye_x = var.l_eye_x
        tracked_eye_y = var.left_y
        is_rec_eye = (self.eye_id == EyeId.RIGHT)
        is_dom_eye = (self.eye_id == EyeId.LEFT)

    #Provides some booleans that are a bit easier to use repeatedly
    dom_is_inward = (
        (self.settings.gui_smartinversion_select_right and var.r_eye_x < 0)
        or
        (not self.settings.gui_smartinversion_select_right and var.l_eye_x > 0)
    )
    rec_is_inward = (
        (self.settings.gui_smartinversion_select_right and var.l_eye_x > 0)
        or
        (not self.settings.gui_smartinversion_select_right and var.r_eye_x < 0)
    )
    dom_in_inv_range = (
        (self.settings.gui_smartinversion_select_right and var.r_eye_x < -self.settings.gui_smartinversion_minthresh)
        or
        (not self.settings.gui_smartinversion_select_right and var.l_eye_x > self.settings.gui_smartinversion_minthresh)
    )
    rec_in_inv_range = (
        (self.settings.gui_smartinversion_select_right and var.l_eye_x > self.settings.gui_smartinversion_minthresh)
        or
        (not self.settings.gui_smartinversion_select_right and var.r_eye_x < -self.settings.gui_smartinversion_minthresh)
    )
    looking_same_dir = (var.r_eye_x * var.l_eye_x > 0)
    x_diff = abs(var.r_eye_x - var.l_eye_x)

    #Checks if eyes are straight, and then sets eye gaze forward until inversion threshold is met
    if dom_is_inward and not rec_in_inv_range and (rec_is_inward or x_diff > 0.4):
        if not self.smartinversion_stare_ahead:
            self.smartinversion_smoothing_progress = 1
            self.smartinversion_is_inverted = False
            print(f"Stare Ahead Activated")
            self.smartinversion_stare_ahead = True
        tracked_eye_x = 0
    elif self.smartinversion_stare_ahead:
        print(f"Stare Ahead Deactivated")
        self.smartinversion_stare_ahead = False

    #Checks if eyes are inverted, and then activates inversion if the conditions have been true for a specified number of frames.
    if dom_is_inward and rec_in_inv_range:
        self.smartinversion_inverted_frame_count = min(self.smartinversion_inverted_frame_count + 1, self.settings.gui_smartinversion_frame_count)

        if self.smartinversion_inverted_frame_count == self.settings.gui_smartinversion_frame_count:
            if not self.smartinversion_is_inverted:
                self.smartinversion_smoothing_progress = 1
                self.smartinversion_normal_frame_count = 0
                self.smartinversion_is_inverted = True
                tracked_eye_x = 0
                print(f"Inversion Activated")
    elif self.smartinversion_inverted_frame_count > 0:
        self.smartinversion_inverted_frame_count = 0

    #Checks if the eyes are no longer inverted, and then clears inversion if the conditions haven't been true for a specified number of frames.
    if self.smartinversion_is_inverted and (not (dom_in_inv_range and rec_in_inv_range)):
        self.smartinversion_normal_frame_count = min(self.smartinversion_normal_frame_count + 1, self.settings.gui_smartinversion_frame_count)

        if self.smartinversion_normal_frame_count == self.settings.gui_smartinversion_frame_count:
            if self.smartinversion_is_inverted:
                self.smartinversion_is_inverted = False
                self.smartinversion_inverted_frame_count = 0
                print(f"Inversion Deactivated")

    elif self.smartinversion_normal_frame_count > 0:
        self.smartinversion_normal_frame_count = 0

    out_x = tracked_eye_x
    out_y = tracked_eye_y
    
    #Logic if smoothing is activated
    if self.smartinversion_smoothing_progress > 0:
        lerp_factor = 0.2

        if self.smartinversion_is_inverted:
            if is_rec_eye:
                self.smartinversion_smoothed_eye_x += (-tracked_eye_x - self.smartinversion_smoothed_eye_x) * lerp_factor
    
            else:
                self.smartinversion_smoothed_eye_x += (tracked_eye_x - self.smartinversion_smoothed_eye_x) * lerp_factor
    
        self.smartinversion_smoothing_progress = max(self.smartinversion_smoothing_progress - self.settings.gui_smartinversion_smoothing_rate, 0)
        out_x = self.smartinversion_smoothed_eye_x

    #Logic if inversion is active, but smoothing is not active
    elif self.smartinversion_is_inverted and is_rec_eye:
        out_x = -tracked_eye_x

    #Limits the maximum allowed inwards rotation if detected as cross-eyed
    if self.smartinversion_is_inverted:
        if self.eye_id == EyeId.LEFT:
            clamped_x = min(out_x, self.settings.gui_smartinversion_rotation_clamp)
            out_x = clamped_x
        else:
            clamped_x = max(out_x, -self.settings.gui_smartinversion_rotation_clamp)
            out_x = clamped_x

    return out_x, out_y
