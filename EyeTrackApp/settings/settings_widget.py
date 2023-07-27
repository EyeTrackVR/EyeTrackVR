from typing import Callable

import PySimpleGUI as sg

from config import EyeTrackConfig
from EyeTrackApp.consts import PageType

from settings.constants import BACKGROUND_COLOR
from settings.modules.general_settings_module import GeneralSettingsModule
from settings.modules.keyboard_shortcuts_module import KeyboardShortcutsModule
from settings.modules.osc_module import OSCSettingsModule
from settings.modules.tracking_algorithm_module import TrackingAlgorithmsModule


class SettingsWidget:
    def __init__(
        self,
        widget_id: PageType,
        main_config: EyeTrackConfig,
    ):
        self.gui_status = "-STATUS-"
        self.gui_general_settings_layout = f"-GENERALSETTINGSLAYOUT{widget_id}-"

        self.main_config = main_config
        self.config = main_config.settings

        self.validation_errors = []

        settings_modules: Callable = [
            GeneralSettingsModule,
            TrackingAlgorithmsModule,
            KeyboardShortcutsModule,
            OSCSettingsModule,
        ]
        self.initialized_modules = self._initialize_modules(settings_modules, widget_id=widget_id)

        self.settings_layout = []

        for module in self.initialized_modules:
            self.settings_layout.extend(
                module.get_layout()
            )

        self.widget_layout = [
            [
                sg.StatusBar(
                    self.validation_errors,
                    size=(1, 1),
                    key=self.gui_status,
                    background_color=BACKGROUND_COLOR,
                )
            ],
            [
                sg.Column(
                    self.settings_layout,
                    key=self.gui_general_settings_layout,
                    background_color=BACKGROUND_COLOR,
                ),
            ],
        ]

    def _initialize_modules(self, modules, widget_id):
        initialized_modules = []
        for module in modules:
            initialized_modules.append(
                module(settings=self.main_config, config=self.config, widget_id=widget_id)
            )
        return initialized_modules

    def render(self, window, event, values):
        validated_data, errors = {}, []
        for module in self.initialized_modules:
            module_validated_data, module_errors = module.validate(values)
            if module_validated_data:
                validated_data.update(module_validated_data)
            if errors:
                errors.extend(module_errors)

        if not errors and validated_data:
            # TODO add debounce for saving
            self.main_config.update(validated_data)
            self.main_config.save()

        if errors:
            # TODO add debounce for printing errors
            print(event)
