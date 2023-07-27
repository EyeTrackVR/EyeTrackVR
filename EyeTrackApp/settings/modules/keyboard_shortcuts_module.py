from typing import Optional, Any

import pydantic

from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.base_module import SettingsModule, BaseValidationModel


class KeyboardShortcutsValidationModel(BaseValidationModel):
    gui_reset_calibration_shortcut: str
    gui_recenter_shortcut: str


class KeyboardShortcutsModule(SettingsModule):
    def __init__(self, settings, widget_id, **kwargs):
        super().__init__(settings, widget_id, **kwargs)
        self.validation_model = KeyboardShortcutsValidationModel

        self.config = kwargs.get('config')
        self.gui_reset_calibration_shortcut = f"-RESETCALIBRATION{widget_id}-"
        self.gui_recenter_shortcut = f"-RECENTER{widget_id}-"


    def get_layout(self):
        return [
            [
                sg.Text("Keyboard Shortcuts Settings:", background_color="#242224"),
            ],
            [
                sg.Text("Reset shortcut:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_reset_calibration_shortcut,
                    key=self.gui_reset_calibration_shortcut,
                    size=(0, 20),
                    tooltip="Keyboard shortcut for resetting the calibration",
                ),
            ],
            [
                sg.Text("Recenter shortcut:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_recenter_shortcut,
                    key=self.gui_recenter_shortcut,
                    size=(0, 10),
                    tooltip="Keyboard shortcut for recentering",
                ),
            ],
        ]
