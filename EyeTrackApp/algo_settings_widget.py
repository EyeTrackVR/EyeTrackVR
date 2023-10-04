import PySimpleGUI as sg

from config import EyeTrackConfig
from osc import EyeId
from queue import Queue
from threading import Event


class AlgoSettingsWidget:
    def __init__(
        self, widget_id: EyeId, main_config: EyeTrackConfig
    ):
        self.gui_general_settings_layout = f"-GENERALSETTINGSLAYOUT{widget_id}-"
        self.main_config = main_config
        self.config = main_config.settings

        # Define the window's contents
        self.general_settings_layout = [
        ]

        self.widget_layout = [
            [
                sg.Text(
                    "Tracking Algorithm Order Settings:", background_color="#242224"
                ),
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
        self.image_queue = Queue()

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

    def render(self, window, event, values):
        # If anything has changed in our configuration settings, change/update those.
        changed = False

        if changed:
            self.main_config.save()
