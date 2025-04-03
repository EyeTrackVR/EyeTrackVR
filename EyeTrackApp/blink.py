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

Binary Intensity Based Blink by: Summer, Prohurtz
Algorithm App Implementations and tweaks By: Prohurtz

Copyright (c) 2025 EyeTrackVR <3
LICENSE: Summer Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import numpy as np


def BLINK(self):

    if self.blink_clear == True:
        self.max_ints = []
        self.max_int = 0
        self.frames = 0

    intensity = np.sum(self.current_image_gray_clean)

    if self.calibration_frame_counter == 300:
        self.filterlist = []  # clear filter
    if len(self.filterlist) < 300:
        self.filterlist.append(intensity)
    else:
        self.filterlist.pop(0)
        self.filterlist.append(intensity)
    if (
        intensity >= np.percentile(self.filterlist, 99)
        or intensity <= np.percentile(self.filterlist, 1)
        and len(self.max_ints) >= 1
    ):  # filter abnormally high values
        try:  # I don't want this here but I cant get python to stop crying when it's not
            intensity = min(self.max_ints)
        except:
            pass

    self.frames = self.frames + 1
    if intensity > self.max_int:
        self.max_int = intensity
        if self.frames > 300:  # TODO: test this number more (make it a setting??)
            self.max_ints.append(self.max_int)
    if intensity < self.min_int:
        self.min_int = intensity

    if len(self.max_ints) > 1:
        if intensity > min(self.max_ints):
            blinkvalue = 0.0
        else:
            blinkvalue = 0.8
    try:
        return blinkvalue
    except:
        return 0.8


# print(self.blinkvalue, self.max_int, self.min_int, self.frames, intensity)
