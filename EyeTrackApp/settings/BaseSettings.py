from typing import Iterable, Optional

import PySimpleGUI as sg

from config import EyeTrackConfig, EyeTrackSettingsConfig
from threading import Event
from osc import EyeId  # TODO this is bad, fix this


class BaseSettingsWidget:
    def __init__(
        self,
        widget_id: EyeId,
        main_config: EyeTrackConfig,
        settings_modules: Iterable,
    ):
        self.gui_general_settings_layout = f"-GENERALSETTINGSLAYOUT{widget_id}-"
        self.reset_button_key = f"RESET_SETTINGS{widget_id}"
        self.is_saving = False
        self.main_config = main_config
        self.config = main_config.settings

        self.initialized_modules = self._initialize_modules(
            settings_modules=settings_modules, widget_id=widget_id
        )

        self.general_settings_layout = []
        for module in self.initialized_modules:
            self.general_settings_layout.extend(module.get_layout())

        self.widget_layout = [
            [
                sg.Column(
                    self.general_settings_layout,
                    key=self.gui_general_settings_layout,
                    background_color="#424042",
                ),
            ],
            [sg.Text("", background_color="#424042"), ],
            [sg.Button("Reset settings to default", key=self.reset_button_key, button_color="#c40e23")],
        ]

        self.cancellation_event = (
            Event()
        )  # Set the event until start is called, otherwise we can block if shutdown is called.
        self.cancellation_event.set()

    def started(self):
        return not self.cancellation_event.is_set()

    def start(self):
        # If we're already running, bail
        if not self.cancellation_event.is_set():
            return
        self.cancellation_event.clear()

    def stop(self):
        # If we're not running yet, bail
        if self.cancellation_event.is_set():
            return
        self.cancellation_event.set()

    def _update_and_save_config(self, validated_data: dict):
        self.main_config.update(validated_data, save=True)
        self.is_saving = False

    def _handle_errors(self, errors):
        print(errors)

    def render(self, window, event, values):
        validated_data, errors = {}, []
        # we might want to think about event driven architecture here eventually, validate only
        # if anything changes instead of checking for changes
        for module in self.initialized_modules:
            module_validated_data = module.validate(values)
            if module_validated_data.changes:
                validated_data.update(module_validated_data.changes)
            if module_validated_data.errors:
                errors.append(module_validated_data.errors)

        if not errors and validated_data and not self.is_saving:
            self.is_saving = True
            self._update_and_save_config(validated_data)

        if errors:
            self._handle_errors(errors)

        self.handle_events(event, window)

    def _initialize_modules(self, settings_modules, widget_id):
        return [
            module(
                config=self.config,
                settings=self.main_config,
                widget_id=widget_id,
            )
            for module in settings_modules
        ]

    def get_layout(self) -> Iterable:
        return self.widget_layout

    def handle_events(self, event, window):
        if event == "__TIMEOUT__":
            return

        if event == self.reset_button_key:
            self.reset_config(window)

    def reset_config(self, window):

        default_values = {}
        base_settings = EyeTrackSettingsConfig()

        print(f"\033[92m[INFO] Resetting config to defaults\033[0m")
        for module in self.initialized_modules:
            for key in module.get_key_for_panel_defaults():
                default_val = getattr(base_settings, key)
                widget_key = getattr(module, key)
                default_values[key] = default_val
                window[widget_key].update(default_val)
        print(f"\033[92m[INFO] Config reset, saving\033[0m")

        self._update_and_save_config(default_values)
