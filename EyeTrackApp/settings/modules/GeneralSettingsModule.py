from config import EyeTrackSettingsConfig
from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import PySimpleGUI as sg


class GeneralSettingsValidationModel(BaseValidationModel):
    gui_flip_x_axis_left: bool
    gui_flip_x_axis_right: bool
    gui_flip_y_axis: bool
    gui_outer_side_falloff: bool
    gui_update_check: bool
    gui_right_eye_dominant: bool
    gui_left_eye_dominant: bool
    gui_eye_dominant_diff_thresh: float


class GeneralSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = GeneralSettingsValidationModel
        self.gui_flip_x_axis_left = f"-FLIPXAXISLEFT{widget_id}-"
        self.gui_flip_x_axis_right = f"-FLIPXAXISRIGHT{widget_id}-"
        self.gui_flip_y_axis = f"-FLIPYAXIS{widget_id}-"
        self.gui_outer_side_falloff = f"-EYEFALLOFF{widget_id}-"
        self.gui_eye_dominant_diff_thresh = f"-DIFFTHRESH{widget_id}-"
        self.gui_left_eye_dominant = f"-LEFTEYEDOMINANT{widget_id}-"
        self.gui_right_eye_dominant = f"-RIGHTEYEDOMINANT{widget_id}-"
        self.gui_update_check = f"-UPDATECHECK{widget_id}-"

    # gui_right_eye_dominant: bool = False
    # gui_left_eye_dominant: bool = False
    # gui_outer_side_falloff: bool = True
    # gui_eye_dominant_diff_thresh: float = 0.3

    def get_layout(self):
        return [
            [
                sg.Text("General Settings:", background_color="#242224"),
            ],
            [
                sg.Checkbox(
                    "Flip Left Eye X Axis",
                    default=self.config.gui_flip_x_axis_left,
                    key=self.gui_flip_x_axis_left,
                    background_color="#424042",
                    tooltip="Flips the left eye's X axis.",
                ),
                sg.Checkbox(
                    "Flip Right Eye X Axis",
                    default=self.config.gui_flip_x_axis_right,
                    key=self.gui_flip_x_axis_right,
                    background_color="#424042",
                    tooltip="Flips the right eye's X axis.",
                ),
                sg.Checkbox(
                    "Flip Y Axis",
                    default=self.config.gui_flip_y_axis,
                    key=self.gui_flip_y_axis,
                    background_color="#424042",
                    tooltip="Flips the eye's Y axis.",
                ),
            ],
            [
                sg.Checkbox(
                    "Check For Updates",
                    default=self.config.gui_update_check,
                    key=self.gui_update_check,
                    background_color="#424042",
                    tooltip="Toggle update check on launch.",
                ),
            ],
            [
                sg.Text("Eye Falloff Settings:", background_color="#242224"),
            ],
            [
                sg.Checkbox(
                    "Outer Eye Falloff",
                    default=self.config.gui_outer_side_falloff,
                    key=self.gui_outer_side_falloff,
                    background_color="#424042",
                    tooltip="If one eye's tracking is past a threshold of difference, we assume the eye looking most outward with lowest average velocity in the past x seconds is correct.",
                ),
                sg.Text("Eye Difference Threshold", background_color="#424042"),
                sg.InputText(
                    self.config.gui_eye_dominant_diff_thresh,
                    key=self.gui_eye_dominant_diff_thresh,
                    size=(0, 10),
                ),
            ],
            [
                sg.Checkbox(
                    "Force Left Eye Dominant",
                    default=self.config.gui_left_eye_dominant,
                    key=self.gui_left_eye_dominant,
                    background_color="#424042",
                    tooltip="If one eye is too different than the other, use left eye data",
                ),
                sg.Checkbox(
                    "Force Right Eye Dominant",
                    default=self.config.gui_right_eye_dominant,
                    key=self.gui_right_eye_dominant,
                    background_color="#424042",
                    tooltip="If one eye is too different than the other, use right eye data",
                ),
            ],
        ]
