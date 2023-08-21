from settings.modules.base_module import SettingsModule, BaseValidationModel
import PySimpleGUI as sg


class OneEuroFilterValidationModel(BaseValidationModel):
    gui_speed_coefficient: str  # GUI lib does not support doubles ;-;
    gui_min_cutoff: str  # or floats ;-;


class OneEuroFilterSettingsModule(SettingsModule):
    def __init__(self, settings, widget_id, **kwargs):
        super().__init__(settings, widget_id, **kwargs)
        self.gui_speed_coefficient = f"-SPEEDCOEFFICIENT{widget_id}-"
        self.gui_min_cutoff = f"-MINCUTOFF{widget_id}-"
        self.config = kwargs.get('config')
        self.validation_model = OneEuroFilterValidationModel

    def get_layout(self):
        return [
            [
                sg.Text("One Euro Filter Paramaters:", background_color='#242224'),
            ],
            [
                sg.Text("Min Frequency Cutoff", background_color='#424042'),
                sg.InputText(
                    self.config.gui_min_cutoff,
                    key=self.gui_min_cutoff,
                    size=(0, 10),
                ),
                sg.Text("Speed Coefficient", background_color='#424042'),
                sg.InputText(
                    self.config.gui_speed_coefficient,
                    key=self.gui_speed_coefficient,
                    size=(0, 10),
                ),
            ],
        ]
