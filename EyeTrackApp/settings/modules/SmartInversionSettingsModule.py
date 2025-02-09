from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.CommonFieldValidators import try_convert_to_float
from settings.modules.CommonFieldValidators import try_convert_to_int

class SmartInversionValidationModule(BaseValidationModel):
    gui_smartinversion_enabled:                          bool
    gui_smartinversion_select_right:                     bool
    gui_smartinversion_frame_count:                      Annotated[int, AfterValidator(try_convert_to_int)]
    gui_smartinversion_smoothing_rate:                   Annotated[float, AfterValidator(try_convert_to_float)]
    gui_smartinversion_minthresh:                        Annotated[float, AfterValidator(try_convert_to_float)]
    gui_smartinversion_rotation_clamp:                   Annotated[float, AfterValidator(try_convert_to_float)]

class SmartInversionSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = SmartInversionValidationModule
        self.gui_smartinversion_enabled = f"-gui_smartinversion_enabled{widget_id}-"
        self.gui_smartinversion_select_right = f"-gui_smartinversion_select_right{widget_id}-"
        self.gui_smartinversion_frame_count =f"-gui_smartinversion_frame_count{widget_id}-"
        self.gui_smartinversion_smoothing_rate =f"-gui_smartinversion_smoothing_rate{widget_id}-"
        self.gui_smartinversion_minthresh =f"-gui_smartinversion_minthresh{widget_id}-"
        self.gui_smartinversion_rotation_clamp =f"-gui_smartinversion_rotation_clamp{widget_id}-"

        

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
            ],
            [
                sg.Text("Inwards Look Threshold", background_color=BACKGROUND_COLOR,tooltip=
                        "Sets the minimum distance of looking in that's required before state can chaned to cross-eyed."
                        "\n Lower value will make cross-eye detection more sensitive."
                ),
                sg.InputText(
                    self.config.gui_smartinversion_minthresh,
                    key=self.gui_smartinversion_minthresh,
                    size=(0, 10),
                ),
            ],
            [
                sg.Text("Inversion Trigger Frame Count", background_color=BACKGROUND_COLOR,tooltip=
                        "How long it takes to detect you are cross-eyed, or no longer cross-eyed."
                        "\n Higher number means longer duration before changing in or out of being cross-eyed state."
                ),
                sg.InputText(
                    self.config.gui_smartinversion_frame_count,
                    key=self.gui_smartinversion_frame_count,
                    size=(0, 10),
                ),
            ],
            [
                sg.Text("Smoothing Decay Rate", background_color=BACKGROUND_COLOR,tooltip=
                        "How quickly eye smoothing decays when you enter or leave a cross-eyed state."
                        "\nHigher number = shorter smoothing duration."
                ),
                sg.InputText(
                    self.config.gui_smartinversion_smoothing_rate,
                    key=self.gui_smartinversion_smoothing_rate,
                    size=(0, 10),
                ),
            ],
            [
                sg.Text("Maximum allowed cross-eye", background_color=BACKGROUND_COLOR,tooltip=
                    "Defines the maximum inwards rotation that is output when cross-eyed."
                    "\n0 = will only look straight ahead \n0.5 = will go a little bit cross-eyed \n1 = maximum hurr durr "
                ),
                sg.InputText(
                    self.config.gui_smartinversion_rotation_clamp,
                    key=self.gui_smartinversion_rotation_clamp,
                    size=(0, 10),
                ),
            ],
        ]