from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.CommonFieldValidators import try_convert_to_float
from settings.modules.CommonFieldValidators import try_convert_to_int

class MirrorTrackValidationModule(BaseValidationModel):
    gui_mirrortrack_enabled:                          bool
    gui_mirrortrack_enable_inv:                       bool
    #gui_mirrortrack_enable_smooth:                    bool
    gui_mirrortrack_select_right:                     bool
    gui_mirrortrack_cycle_count_inv:                  Annotated[int, AfterValidator(try_convert_to_int)]
    gui_mirrortrack_cycle_count_stare:                Annotated[int, AfterValidator(try_convert_to_int)]
    gui_mirrortrack_minthresh:                        Annotated[float, AfterValidator(try_convert_to_float)]
    gui_mirrortrack_rotation_clamp:                   Annotated[float, AfterValidator(try_convert_to_float)]
    gui_mirrortrack_smooth_rate:                      Annotated[float, AfterValidator(try_convert_to_float)]

class MirrorTrackSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = MirrorTrackValidationModule
        self.gui_mirrortrack_enabled = f"-gui_mirrortrack_enabled{widget_id}-"
        self.gui_mirrortrack_enable_inv =f"-gui_mirrortrack_enable_inv{widget_id}-"
        #self.gui_mirrortrack_enable_smooth =f"-gui_mirrortrack_enable_smooth{widget_id}-"
        self.gui_mirrortrack_select_right = f"-gui_mirrortrack_select_right{widget_id}-"
        self.gui_mirrortrack_cycle_count_inv =f"-gui_mirrortrack_cycle_count_inv{widget_id}-"
        self.gui_mirrortrack_cycle_count_stare =f"-gui_mirrortrack_cycle_count_stare{widget_id}-"
        self.gui_mirrortrack_minthresh =f"-gui_mirrortrack_minthresh{widget_id}-"
        self.gui_mirrortrack_rotation_clamp =f"-gui_mirrortrack_rotation_clamp{widget_id}-"
        self.gui_mirrortrack_smooth_rate =f"-gui_mirrortrack_smooth_rate{widget_id}-"
      
    def get_layout(self):
        return [
            [
                sg.Text("MirrorTrack System:", background_color='#242224'),
            ],
            [
                sg.Checkbox(
                "Enable MirrorTrack",
                default=self.config.gui_mirrortrack_enabled,
                key=self.gui_mirrortrack_enabled,
                background_color="#424042",
                tooltip="Enables MirrorTrack System",
                ),
            ],
            [
                sg.Radio(
                "Use Left Eye",
                "mirrortrack_selectedeye",
                default = not self.config.gui_mirrortrack_select_right,
                background_color="#424042",
                tooltip="Uses the left eye as the tracked eye.",
                ),

                sg.Radio(
                "Use Right Eye",
                "mirrortrack_selectedeye",
                default=self.config.gui_mirrortrack_select_right,
                key=self.gui_mirrortrack_select_right,
                background_color="#424042",
                tooltip="Uses the right eye as the tracked eye.",
                )
            ],
            [
                sg.Text("Stare Ahead Detection Duration", background_color=BACKGROUND_COLOR,tooltip=
                        "How long it takes to detect you are staring ahead, or no longer staring ahead."
                        "\n Higher number means longer duration before changing in or out of being in stare ahead state."
                        "\n Exit conditions are half the duration of entry conditions."

                ),
                sg.InputText(
                    self.config.gui_mirrortrack_cycle_count_stare,
                    key=self.gui_mirrortrack_cycle_count_stare,
                    size=(0, 10),
                ),
            ],                
            [
                sg.Checkbox(
                    "Enable Cross-Eye Detection",
                    default=self.config.gui_mirrortrack_enable_inv,
                    key=self.gui_mirrortrack_enable_inv,
                    background_color="#424042",
                    tooltip="Enables cross-eye functionality",
                ),
            ],
            [
                sg.Text("Detection Threshold", background_color=BACKGROUND_COLOR,tooltip=
                        "Sets the minimum distance of looking in that's required before state will changed to cross-eyed."
                        "\n Lower value will make cross-eye detection more sensitive."
                ),
                sg.InputText(
                    self.config.gui_mirrortrack_minthresh,
                    key=self.gui_mirrortrack_minthresh,
                    size=(0, 10),
                ),
            ],
            [
                sg.Text("Detection Duration", background_color=BACKGROUND_COLOR,tooltip=
                        "How long it takes to detect you are cross-eyed, or no longer cross-eyed."
                        "\n Higher number means longer duration before changing in or out of being cross-eyed state."
                        "\n Exit conditions are half the duration of entry conditions."
                ),
                sg.InputText(
                    self.config.gui_mirrortrack_cycle_count_inv,
                    key=self.gui_mirrortrack_cycle_count_inv,
                    size=(0, 10),
                ),
            ],
            [
                sg.Text("Rotation Limit", background_color=BACKGROUND_COLOR,tooltip=
                    "Defines the maximum inwards rotation that is output when cross-eyed."
                    "\n0 = will only look straight ahead \n0.5 = will go a little bit cross-eyed \n1 = maximum hurr durr "
                ),
                sg.InputText(
                    self.config.gui_mirrortrack_rotation_clamp,
                    key=self.gui_mirrortrack_rotation_clamp,
                    size=(0, 10),
                ),
            ],
            [
                #sg.Checkbox(
                #    "Allow cross-eye smoothing",
                #    default=self.config.gui_mirrortrack_enable_smooth,
                #    key=self.gui_mirrortrack_enable_smooth,
                #    background_color="#424042",
                #    tooltip="Enables smoothing when transitioning to cross-eye",
                #),
                sg.Text("Transition Smoothing Rate", background_color=BACKGROUND_COLOR,tooltip=
                        "How quickly smoothing decays when you enter or leave the cross-eyed state."
                        "\nHigher number = shorter smoothing duration, snappier transition."
                        "\nLower number = longer smoothing duration, smoother transition"
                ),
                sg.InputText(
                    self.config.gui_mirrortrack_smooth_rate,
                    key=self.gui_mirrortrack_smooth_rate,
                    size=(0, 10),
                ),
            ],

        ]