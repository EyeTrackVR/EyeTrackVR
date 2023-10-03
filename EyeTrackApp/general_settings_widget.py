import PySimpleGUI as sg

from config import EyeTrackConfig, EyeTrackSettingsConfig
from osc import EyeId
from threading import Event

from settings.modules.GeneralSettingsModule import GeneralSettingsModule
from settings.modules.OneEuroSettingsModule import OneEuroSettingsModule
from settings.modules.OSCSettingsModule import OSCSettingsModule


class SettingsWidget:
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig):
        self.is_saving = False
        self.main_config = main_config
        self.config = main_config.settings

        settings_modules = [
            GeneralSettingsModule,
            OneEuroSettingsModule,
            OSCSettingsModule,
        ]

        self.initialized_modules = self._initialize_modules(
            settings_modules=settings_modules, widget_id=widget_id
        )
        self.gui_general_settings_layout = f"-GENERALSETTINGSLAYOUT{widget_id}-"

        # Define the window's contents
        self.general_settings_layout = []

        for module in self.initialized_modules:
            self.general_settings_layout.extend(module.get_layout())

        self.widget_layout = [
            [
                sg.Text("General Settings:", background_color="#242224"),
            ],
            [
                sg.Column(
                    self.general_settings_layout,
                    key=self.gui_general_settings_layout,
                    background_color="#424042",
                ),
            ],
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

    def _initialize_modules(self, settings_modules, widget_id):
        return [
            module(
                config=self.config,
                settings=self.main_config,
                settings_base_class=EyeTrackSettingsConfig,
                widget_id=widget_id,
            )
            for module in settings_modules
        ]
