import PySimpleGUI as sg

from threading import Event
from typing import Callable, List

from settings.constants import BACKGROUND_COLOR
from config import EyeTrackConfig
from consts import PageType
from utils.debounce import debounce


class BaseSettings:
    def __init__(self, widget_id: PageType, main_config: EyeTrackConfig, settings_modules=None):
        self.layout_name_key = f"-GENERALSETTINGSLAYOUT{widget_id}-"
        settings_modules: List[Callable] = settings_modules or []
        # Set the event until start is called, otherwise we can block if shutdown is called.
        self.gui_status = "-STATUS-"

        self.main_config = main_config
        self.config = main_config.settings

        self.cancellation_event = Event()
        self.cancellation_event.set()
        self.validation_errors = []

        self.initialized_modules = self._initialize_modules(settings_modules, widget_id=widget_id)
        self.settings_layout = []
        for module in self.initialized_modules:
            self.settings_layout.extend(
                module.get_layout()
            )

        # we define the layout when everything is ready,
        # this should probably become a method at a later time
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
                    key=self.layout_name_key,
                    background_color=BACKGROUND_COLOR,
                ),
            ],
        ]

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

    def _initialize_modules(self, modules, widget_id):
        initialized_modules = []
        for module in modules:
            initialized_modules.append(
                module(settings=self.main_config, config=self.config, widget_id=widget_id)
            )
        return initialized_modules

    @debounce(wait_seconds=1)
    def _update_and_save_config(self, validated_data):
        self.main_config.update(validated_data, save=True)

    @debounce(wait_seconds=1)
    def _print_errors(self, errors):
        print(errors)

    def render(self, window, event, values):
        validated_data, errors = {}, []
        for module in self.initialized_modules:
            module_validated_data, module_errors = module.validate(values)
            if module_validated_data:
                validated_data.update(module_validated_data)
            if errors:
                errors.extend(module_errors)

        if not errors and validated_data:
            self._update_and_save_config(validated_data)

        if errors:
            self._print_errors(errors)
