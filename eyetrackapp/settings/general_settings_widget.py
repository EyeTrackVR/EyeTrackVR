"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import sys

from config import EyeTrackConfig
from eye import EyeId

from settings.base_settings import BaseSettingsWidget
from settings.modules.advanced_osc_settings_module import AdvancedOSCSettingsModule
from settings.modules.general_settings_module import GeneralSettingsModule
from settings.modules.one_euro_settings_module import OneEuroSettingsModule
from settings.modules.osc_settings_module import OSCSettingsModule


class SettingsWidget(BaseSettingsWidget):
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig):
        settings_modules = [
            GeneralSettingsModule,
            OneEuroSettingsModule,
            OSCSettingsModule,
            AdvancedOSCSettingsModule,
        ]
        super().__init__(widget_id, main_config, settings_modules)

    def advanced_module_types(self) -> tuple:
        return (AdvancedOSCSettingsModule,)

    def build(self, parent):
        frame = super().build(parent)
        if sys.platform == "win32":
            # Live per-game DFR section, just above the Advanced toggle.
            from ovr.dfr import dfr_controller
            from settings.dfr_panel import DfrPanel

            panel = DfrPanel(dfr_controller, self.main_config).build(self.frame)
            if self._advanced_toggle_row is not None:
                panel.pack(fill="x", padx=8, pady=6, anchor="n", before=self._advanced_toggle_row)
            else:
                panel.pack(fill="x", padx=8, pady=6, anchor="n")
        return frame
