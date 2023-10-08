from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.CommonFieldValidators import check_is_float_convertible


class OneEuroFilterValidationModel(BaseValidationModel):
    gui_speed_coefficient: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_min_cutoff: Annotated[str, AfterValidator(check_is_float_convertible)]


class OneEuroSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.gui_speed_coefficient = f"-SPEEDCOEFFICIENT{widget_id}-"
        self.gui_min_cutoff = f"-MINCUTOFF{widget_id}-"
        self.validation_model = OneEuroFilterValidationModel

    def get_layout(self):
        return [
            [
                sg.Text("One Euro Filter Paramaters:", background_color='#242224'),
            ],
            [
                sg.Text("Min Frequency Cutoff", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_min_cutoff,
                    key=self.gui_min_cutoff,
                    size=(0, 10),
                ),
                sg.Text("Speed Coefficient", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_speed_coefficient,
                    key=self.gui_speed_coefficient,
                    size=(0, 10),
                ),
            ],
        ]