from config import EyeTrackConfig
from consts import PageType
from settings.base_settings import BaseSettings
from settings.modules.tracking_algorithm_module import TrackingAlgorithmsModule


class AlgoSettingsWidget(BaseSettings):
    def __init__(
            self,
            widget_id: PageType,
            main_config: EyeTrackConfig
    ):
        __settings_modules = [
            TrackingAlgorithmsModule,
        ]

        super().__init__(widget_id, main_config=main_config, settings_modules=__settings_modules)
