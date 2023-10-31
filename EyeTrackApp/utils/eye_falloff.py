import numpy as np
from enum import IntEnum


class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3


def velocity_falloff(self, var, out_x, out_y):

    if self.eye_id in [EyeId.LEFT]:
        var.l_eye_velocity = var.average_velocity
        if self.settings.gui_outer_side_falloff:
            dist = abs(
                np.sqrt(
                    abs(np.square(out_x - var.r_eye_x) - np.square(out_y - var.right_y))
                )
            )
            # print(dist)  # TODO remove once testing is done
            if dist > self.settings.gui_eye_dominant_diff_thresh:
                falloff = True
                if (
                    not self.settings.gui_left_eye_dominant
                    and not self.settings.gui_right_eye_dominant
                ):
                    if var.l_eye_velocity < var.r_eye_velocity:
                        var.r_eye_x = out_x
                        var.right_y = out_y
                    else:
                        eye_x = var.l_eye_x
                        eye_y = var.left_y
                elif self.settings.gui_left_eye_dominant:
                    var.r_eye_x = out_x
                    var.right_y = out_y
                    falloff = False
            else:
                var.l_eye_x = out_x
                var.left_y = out_y
                falloff = False

    if self.eye_id == EyeId.RIGHT:
        var.r_eye_velocity = var.average_velocity
        if self.settings.gui_outer_side_falloff:
            dist = abs(
                np.sqrt(
                    abs(np.square(var.l_eye_x - out_x) - np.square(var.left_y - out_y))
                )
            )
            #  print(dist, "r")  # TODO remove once testing is done
            if dist > self.settings.gui_eye_dominant_diff_thresh:
                falloff = True
                if (
                    not self.settings.gui_left_eye_dominant
                    and not self.settings.gui_right_eye_dominant
                ):
                    if var.l_eye_velocity < var.r_eye_velocity:
                        var.r_eye_x = out_x
                        var.right_y = out_y
                    else:
                        var.l_eye_x = out_x
                        var.left_y = out_y  # need to make sure we send these values... might re think the whole file
                elif self.settings.gui_right_eye_dominant:
                    var.l_eye_x = out_x
                    var.left_y = out_y
                    falloff = False

            else:
                falloff = False
                var.r_eye_x = out_x
                var.right_y = out_y

    if self.eye_id == EyeId.LEFT and falloff:
        out_x = var.r_eye_x
        out_y = var.right_y
    if self.eye_id == EyeId.RIGHT and falloff:
        out_x = var.l_eye_x
        out_y = (
            var.left_y
        )  # needs to not be in this file lol... well if we want proper visualization..

    return out_x, out_y
