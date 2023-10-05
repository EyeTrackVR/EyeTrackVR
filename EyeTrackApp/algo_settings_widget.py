import PySimpleGUI as sg

from config import EyeTrackConfig
from osc import EyeId

from settings.BaseSettings import BaseSettingsWidget
from settings.modules.AdvancedTrackingAlgoSettingsModule import (
    AdvancedTrackingAlgoSettingsModule,
)
from settings.modules.BlinkAlgoModule import BlinkAlgoSettingsModule
from settings.modules.TrackingAlgorithmModule import TrackingAlgorithmModule


class AlgoSettingsWidget(BaseSettingsWidget):
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig):
        settings_modules = [
            TrackingAlgorithmModule,
            BlinkAlgoSettingsModule,
            AdvancedTrackingAlgoSettingsModule,
        ]
        super().__init__(widget_id, main_config, settings_modules)
