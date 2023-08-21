from config import EyeTrackConfig
from EyeTrackApp.consts import PageType
from settings.base_settings import BaseSettings

from settings.modules.general_settings_module import GeneralSettingsModule
from settings.modules.keyboard_shortcuts_module import KeyboardShortcutsModule
from settings.modules.one_euro_settings_module import OneEuroFilterSettingsModule
from settings.modules.osc_module import OSCSettingsModule


class SettingsWidget(BaseSettings):
    def __init__(
        self,
        widget_id: PageType,
        main_config: EyeTrackConfig,
    ):
        __settings_modules = [
            GeneralSettingsModule,
            OneEuroFilterSettingsModule,
            KeyboardShortcutsModule,
            OSCSettingsModule,
        ]

        super().__init__(widget_id, main_config=main_config, settings_modules=__settings_modules)
