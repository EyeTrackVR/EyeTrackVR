from config import EyeTrackSettingsConfig
from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import PySimpleGUI as sg


class GeneralSettingsValidationModel(BaseValidationModel):
    gui_flip_x_axis_left: bool
    gui_flip_x_axis_right: bool
    gui_flip_y_axis: bool
    gui_vrc_native: bool
    gui_eye_falloff: bool
    gui_update_check: bool


class GeneralSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = GeneralSettingsValidationModel
        self.gui_flip_x_axis_left = f"-FLIPXAXISLEFT{widget_id}-"
        self.gui_flip_x_axis_right = f"-FLIPXAXISRIGHT{widget_id}-"
        self.gui_flip_y_axis = f"-FLIPYAXIS{widget_id}-"
        self.gui_eye_falloff = f"-EYEFALLOFF{widget_id}-"
        self.gui_vrc_native = f"-VRCNATIVE{widget_id}-"
        self.gui_update_check = f"-UPDATECHECK{widget_id}-"

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
                    "VRC Native Eyetracking",
                    default=self.config.gui_vrc_native,
                    key=self.gui_vrc_native,
                    background_color="#424042",
                    tooltip="Toggle VRCFT output or VRC native",
                ),
                sg.Checkbox(
                    "Dual Eye Falloff",
                    default=self.config.gui_eye_falloff,
                    key=self.gui_eye_falloff,
                    background_color="#424042",
                    tooltip="If one eye stops tracking, we send tracking data from your other eye.",
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
        ]