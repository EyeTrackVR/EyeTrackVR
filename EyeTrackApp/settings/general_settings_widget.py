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

Copyright (c) 2023 EyeTrackVR <3
LICENSE: GNU GPLv3 
------------------------------------------------------------------------------------------------------
"""

from config import EyeTrackConfig
from eye import EyeId

from settings.BaseSettings import BaseSettingsWidget
from settings.modules.GeneralSettingsModule import GeneralSettingsModule
from settings.modules.OneEuroSettingsModule import OneEuroSettingsModule
from settings.modules.OSCSettingsModule import OSCSettingsModule
from settings.modules.EyeTuneSettingsModule import EyeTuneSettingsModule
from settings.modules.SmartInversionSettingsModule import SmartInversionSettingsModule


class SettingsWidget(BaseSettingsWidget):
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig):
        settings_modules = [
            GeneralSettingsModule,
            OneEuroSettingsModule,
            SmartInversionSettingsModule,
            OSCSettingsModule,
            EyeTuneSettingsModule,
        ]
        super().__init__(widget_id, main_config, settings_modules)
