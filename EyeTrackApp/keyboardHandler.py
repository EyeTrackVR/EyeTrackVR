from functools import partial

from pynput import keyboard

from config import EyeTrackConfig
from utils.eye_utils import trigger_recalibration, trigger_recenter


class KeyboardHandler:
    def __init__(self, eye_widgets, settings: EyeTrackConfig, event):
        self.eye_widgets = eye_widgets
        self.settings = settings.settings
        self.should_restart = False
        self.event = event
        self.listener = None

    def _trigger_action(self, action):
        for eye in self.eye_widgets:
            action(eye)

    def _get_shortcut_actions(self):
        return {
            self.settings.gui_reset_calibration_shortcut: partial(self._trigger_action, trigger_recalibration),
            self.settings.gui_recenter_shortcut: partial(self._trigger_action, trigger_recenter)
        }

    def _start(self):
        shortcut_actions = self._get_shortcut_actions()
        self.listener = keyboard.GlobalHotKeys(shortcut_actions)

    def _restart(self):
        self.should_restart = False
        self._stop()
        self.listener = None

        self._start()

    def _stop(self):
        self.listener.stop()

    def on_update(self):
        # TODO figure out how to trigger this nicely, maybe observer?
        # Would play nicely with what some users have been suggesting with changes taking immediate effect
        self.should_restart = True

    def run(self):
        self._start()
        while not self.event.is_set():
            if self.should_restart:
                self._restart()

        self._stop()
