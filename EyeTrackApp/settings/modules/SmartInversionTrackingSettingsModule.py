from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.CommonFieldValidators import try_convert_to_float


class SmartInversionValidationModule(BaseValidationModel):
    gui_smartinversion_enabled:            bool
    gui_smartinversion_select_right:       bool
    gui_smartinversion_thresh:             Annotated[str, AfterValidator(try_convert_to_float)]


class SmartInversionSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.gui_smartinversion_enabled = f"-gui_smartinversion_enabled{widget_id}-"
        self.gui_smartinversion_select_right = f"-gui_smartinversion_select_right{widget_id}-"
        self.gui_smartinversion_thresh = f"-gui_smartinversion_thresh{widget_id}-"

    def get_layout(self):
        return [
            [
                sg.Text("Smart Inversion Tracking System:", background_color='#242224'),
            ],
            [
                sg.Checkbox(
                "Enable:",
                default=self.config.gui_smartinversion_enabled,
                key=self.gui_smartinversion_enabled,
                background_color="#424042",
                tooltip="Enables Smart Inversion Tracking System",
                ),

                sg.Text("Max. X-Axis Difference", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_smartinversion_thresh,
                    key=self.gui_smartinversion_thresh,
                    size=(0, 10),
                    tooltip="Sets the maximum allowed difference in eye position (x-axis) to determine if the eyes are inverted or not."
                ),
            ],
            [
                sg.Radio(
                "Use Left Eye",
                "smartinversion_selectedeye",
                background_color="#424042",
                tooltip="Uses the left eye as the tracked eye.",
                ),

                sg.Radio(
                "Use Right Eye",
                "smartinversion_selectedeye",
                default=self.config.gui_smartinversion_select_right,
                key=self.gui_smartinversion_select_right,
                background_color="#424042",
                tooltip="Uses the right eye as the tracked eye.",
                )
            ]
        ]