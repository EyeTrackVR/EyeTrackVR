from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.base_module import SettingsModule


class GeneralSettingsModule(SettingsModule):
    def __init__(self, settings, widget_id, **kwargs):
        super().__init__(settings, widget_id, **kwargs)
        self.config = kwargs.get('config')
        self.gui_flip_x_axis_left = f"-FLIPXAXISLEFT{widget_id}-"
        self.gui_flip_x_axis_right = f"-FLIPXAXISRIGHT{widget_id}-"
        self.gui_flip_y_axis = f"-FLIPYAXIS{widget_id}-"
        self.gui_vrc_native = f"-VRCNATIVE{widget_id}-"
        self.gui_eye_falloff = f"-EYEFALLOFF{widget_id}-"
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
                    background_color=BACKGROUND_COLOR,
                    tooltip="Flips the left eye's X axis.",
                ),
                sg.Checkbox(
                    "Flip Right Eye X Axis",
                    default=self.config.gui_flip_x_axis_right,
                    key=self.gui_flip_x_axis_right,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Flips the right eye's X axis.",
                ),
                sg.Checkbox(
                    "Flip Y Axis",
                    default=self.config.gui_flip_y_axis,
                    key=self.gui_flip_y_axis,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Flips the eye's Y axis.",
                ),
            ],
            [
                sg.Checkbox(
                    "VRC Native Eyetracking",
                    default=self.config.gui_vrc_native,
                    key=self.gui_vrc_native,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Toggle VRCFT output or VRC native",
                ),
                sg.Checkbox(
                    "Dual Eye Falloff",
                    default=self.config.gui_eye_falloff,
                    key=self.gui_eye_falloff,
                    background_color=BACKGROUND_COLOR,
                    tooltip="If one eye stops tracking, we send tracking data from your other eye.",
                ),
            ],
            [
                sg.Checkbox(
                    "Check For Updates",
                    default=self.config.gui_update_check,
                    key=self.gui_update_check,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Toggle update check on launch.",
                ),
            ],
        ]
