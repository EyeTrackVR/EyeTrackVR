from typing import Iterable
import PySimpleGUI as sg
from settings.modules.BaseModule import BaseValidationModel, BaseSettingsModule


class OutputMultiplicationValidationModel(BaseValidationModel):
    gui_osc_output_multiplier_combine_left_x: bool
    gui_osc_output_multiplier_combine_left_y: bool

    gui_osc_output_multiplier_positive_left_x: float
    gui_osc_output_multiplier_negative_left_x: float
    gui_osc_output_multiplier_positive_left_y: float
    gui_osc_output_multiplier_negative_left_y: float

    gui_osc_output_multiplier_combine_right_x: bool
    gui_osc_output_multiplier_combine_right_y: bool

    gui_osc_output_multiplier_positive_right_x: float
    gui_osc_output_multiplier_negative_right_x: float
    gui_osc_output_multiplier_positive_right_y: float
    gui_osc_output_multiplier_negative_right_y: float


class OutputMultiplicationSettingsModule(BaseSettingsModule):

    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = OutputMultiplicationValidationModel
        self.gui_osc_mirror_left_eye_multiplier = f"OSC_OUTPUT_MULTIPLIER_MIRROR{widget_id}-"
        self.gui_osc_output_multiplier_combine_left_x = f"OSC_OUTPUT_MULTIPLIER_COMBINE_LEFT_X_{widget_id}-"
        self.gui_osc_output_multiplier_combine_left_y = f"OSC_OUTPUT_MULTIPLIER_COMBINE_LEFT_Y_{widget_id}-"

        self.gui_osc_output_multiplier_positive_left_x = f"OSC_OUTPUT_MULTIPLIER_POS_LEFT_X{widget_id}-"
        self.gui_osc_output_multiplier_negative_left_x = f"OSC_OUTPUT_MULTIPLIER_NEG_LEFT_X{widget_id}-"
        self.gui_osc_output_multiplier_positive_left_y = f"OSC_OUTPUT_MULTIPLIER_POS_LEFT_Y{widget_id}-"
        self.gui_osc_output_multiplier_negative_left_y = f"OSC_OUTPUT_MULTIPLIER_NEG_LEFT_Y{widget_id}-"

        self.gui_osc_output_multiplier_combine_right_x = f"OSC_OUTPUT_MULTIPLIER_COMBINE_RIGHT_X_{widget_id}-"
        self.gui_osc_output_multiplier_combine_right_y = f"OSC_OUTPUT_MULTIPLIER_COMBINE_RIGHT_Y_{widget_id}-"
        self.gui_osc_output_multiplier_positive_right_x = f"OSC_OUTPUT_MULTIPLIER_POS_RIGHT_X{widget_id}-"
        self.gui_osc_output_multiplier_negative_right_x = f"OSC_OUTPUT_MULTIPLIER_NEG_RIGHT_X{widget_id}-"
        self.gui_osc_output_multiplier_positive_right_y = f"OSC_OUTPUT_MULTIPLIER_POS_RIGHT_Y{widget_id}-"
        self.gui_osc_output_multiplier_negative_right_y = f"OSC_OUTPUT_MULTIPLIER_NEG_RIGHT_Y{widget_id}-"

    def get_layout(self) -> Iterable:
        return [
            [sg.Text("Output Multiplier Settings:", background_color="#242224")],
            [
                sg.Checkbox(
                    "Copy multiplier settings to the right eye.",
                    default=self.config.gui_osc_mirror_left_eye_multiplier,
                    key=self.gui_osc_mirror_left_eye_multiplier,
                    background_color="#424042",
                    tooltip="Copies the multiplier settings to the right eye.",
                ),
            ],
            # spacer to make the UI easier to read
            [
                sg.Text("", background_color="#424042"),
            ],
            [
                sg.Text("Left Eye Output Adjustment:", background_color="#424042"),
            ],
            [
                sg.Checkbox(
                    "Single sided X axis mode (combined)",
                    default=self.config.gui_osc_output_multiplier_combine_left_x,
                    key=self.gui_osc_output_multiplier_combine_left_x,
                    background_color="#424042",
                    tooltip="Ignores the second value and uses the first one for both calculations. Only -X is taken into account in this case",
                ),
                sg.Checkbox(
                    "Single sided Y axis mode (combined)",
                    default=self.config.gui_osc_output_multiplier_combine_left_y,
                    key=self.gui_osc_output_multiplier_combine_left_y,
                    background_color="#424042",
                    tooltip="Ignores the second value and uses the first one for both calculations. Only -X is taken into account in this case",
                ),
            ],
            [
                sg.Text("-X", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.1,
                    default_value=self.config.gui_osc_output_multiplier_negative_left_x,
                    orientation="h",
                    key=self.gui_osc_output_multiplier_negative_left_x,
                    background_color="#424042",
                    tooltip="Controls the `power` of the output from the left side to center. Can be swapped with flix X axis option.",
                ),
                sg.Text("+X", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.1,
                    default_value=self.config.gui_osc_output_multiplier_positive_left_x,
                    orientation="h",
                    key=self.gui_osc_output_multiplier_positive_left_x,
                    background_color="#424042",
                    tooltip="Controls the `power` of the output from the center to the right side. Can be swapped with flix X axis option",
                ),
            ],
            [
                sg.Text("-Y", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.1,
                    default_value=self.config.gui_osc_output_multiplier_negative_left_y,
                    orientation="h",
                    key=self.gui_osc_output_multiplier_negative_left_y,
                    background_color="#424042",
                    tooltip="Controls the `power` of the output from the top side to the center. Can be swapped with flix Y axis option",
                ),
                sg.Text("+Y", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.1,
                    default_value=self.config.gui_osc_output_multiplier_positive_left_y,
                    orientation="h",
                    key=self.gui_osc_output_multiplier_positive_left_y,
                    background_color="#424042",
                    tooltip="Controls the `power` of the output from the center side to the bottom. Can be swapped with flix Y axis option",
                ),
            ],
            # spacer to make the UI easier to read
            [
                sg.Text("", background_color="#424042"),
            ],
            [
                sg.Text("Right Eye Output Adjustment:", background_color="#424042"),
            ],
            [
                sg.Checkbox(
                    "Single sided X axis mode (combined)",
                    default=self.config.gui_osc_output_multiplier_combine_right_x,
                    key=self.gui_osc_output_multiplier_combine_right_x,
                    background_color="#424042",
                    tooltip="Ignores the second value and uses the first one for both calculations. Only -X is taken into account in this case",
                ),
                sg.Checkbox(
                    "Single sided Y axis mode (combined)",
                    default=self.config.gui_osc_output_multiplier_combine_right_y,
                    key=self.gui_osc_output_multiplier_combine_right_y,
                    background_color="#424042",
                    tooltip="Ignores the second value and uses the first one for both calculations. Only -Y is taken into account in this case",
                ),
            ],
            [
                sg.Text("-X", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.1,
                    default_value=self.config.gui_osc_output_multiplier_negative_right_x,
                    orientation="h",
                    key=self.gui_osc_output_multiplier_negative_right_x,
                    background_color="#424042",
                    tooltip="Controls the `power` of the output from the left side to center. Can be swapped with flix X axis option",
                ),
                sg.Text("+X", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.1,
                    default_value=self.config.gui_osc_output_multiplier_positive_right_x,
                    orientation="h",
                    key=self.gui_osc_output_multiplier_positive_right_x,
                    background_color="#424042",
                    tooltip="Controls the `power` of the output from the center to the left side. Can be swapped with flix X axis option",
                ),
            ],
            [
                sg.Text("-Y", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.1,
                    default_value=self.config.gui_osc_output_multiplier_negative_right_y,
                    orientation="h",
                    key=self.gui_osc_output_multiplier_negative_right_y,
                    background_color="#424042",
                    tooltip="Controls the `power` of the output from the top side to the center. Can be swapped with flix Y axis option",
                ),
                sg.Text("+Y", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.1,
                    default_value=self.config.gui_osc_output_multiplier_positive_right_y,
                    orientation="h",
                    key=self.gui_osc_output_multiplier_positive_right_y,
                    background_color="#424042",
                    tooltip="Controls the `power` of the output from the center to the bottom side. Can be swapped with flix Y axis option",
                ),
            ],
        ]
