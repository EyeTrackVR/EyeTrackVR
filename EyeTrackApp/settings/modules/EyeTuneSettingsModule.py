from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.CommonFieldValidators import try_convert_to_float

class EyeTuneValidationModule(BaseValidationModel):
    gui_eyetune_maxin:                      Annotated[float, AfterValidator(try_convert_to_float)]
    gui_eyetune_maxout:                     Annotated[float, AfterValidator(try_convert_to_float)]
    gui_eyetune_maxup:                      Annotated[float, AfterValidator(try_convert_to_float)]
    gui_eyetune_maxdown:                    Annotated[float, AfterValidator(try_convert_to_float)]

class EyeTuneSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = EyeTuneValidationModule
        self.gui_eyetune_maxin = f"-gui_eyetune_maxin{widget_id}-"
        self.gui_eyetune_maxout = f"-gui_eyetune_maxout{widget_id}-"
        self.gui_eyetune_maxup =f"-gui_eyetune_maxup{widget_id}-"
        self.gui_eyetune_maxdown =f"-gui_eyetune_maxdown{widget_id}"

        

    def get_layout(self):
        return [
            [
                sg.Text("Eye Tuning (Max Rotation):", background_color='#242224'),
            ],
            [
                sg.Text("In:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_eyetune_maxin,
                    key=self.gui_eyetune_maxin,
                    size=(0, 10),
                    tooltip=(
                        "Sets the maximum allowed inwards rotation"
                        "\nSet between 0 and 1"
                    )
                ),
                sg.Text("Out:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_eyetune_maxout,
                    key=self.gui_eyetune_maxout,
                    size=(0, 10),
                    tooltip=(
                        "Sets the maximum allowed outwards rotation"
                        "\nSet between 0 and 1"
                    )
                ),
                sg.Text("Up:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_eyetune_maxup,
                    key=self.gui_eyetune_maxup,
                    size=(0, 10),
                    tooltip=(
                        "Sets the maximum allowed upwards rotation"
                        "\nSet between 0 and 1"
                    )
                ),
                sg.Text("Down:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_eyetune_maxdown,
                    key=self.gui_eyetune_maxdown,
                    size=(0, 10),
                    tooltip=(
                        "Sets the maximum allowed downwards rotation"
                        "\nSet between 0 and 1"
                    )
                ),
            ],
        ]