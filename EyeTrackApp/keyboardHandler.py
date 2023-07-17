from pynput import keyboard
from utils.eye_utils import trigger_recalibration, trigger_recenter


class KeyboardHandler:

    # TODO inherit after the GlobalHotkeys and setup your own threads with thread handling
    def __init__(self, eye_widgets):
        # since we're modifying the eye widgets settings directly
        self.eye_widgets = eye_widgets
        self.shortcut_map = {
            "settings-recalibrate": trigger_recalibration,
            "settings-recenter": trigger_recenter,
        }

    def process_shortcuts(self):
        # TODO implement it, with settings and stuff
        raise NotImplementedError
        return {}

    def run(self):
        # handle events here too
        shortcuts = self.process_shortcuts()

        with keyboard.GlobalHotKeys(
            **shortcuts,
        ) as global_shortcuts:
            global_shortcuts.join()