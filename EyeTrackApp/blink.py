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

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Summer Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

from collections import deque

import numpy as np

_FILTER_MAXLEN = 300


def BLINK(self):

    if self.blink_clear == True:
        self.max_ints = []
        self.max_int = 0
        self.frames = 0

    intensity = np.sum(self.current_image_gray_clean)

    # Reset filter on (re)calibration. Use a bounded deque so append is O(1).
    if self.calibration_start_time is not None or not isinstance(
        getattr(self, "filterlist", None), deque
    ):
        self.filterlist = deque(maxlen=_FILTER_MAXLEN)
    self.filterlist.append(intensity)

    # Single sort for both percentile bounds, instead of two np.percentile calls.
    if len(self.filterlist) >= 2:
        lo, hi = np.percentile(self.filterlist, (1, 99))
    else:
        lo, hi = -np.inf, np.inf

    min_max_int = min(self.max_ints) if self.max_ints else None

    if (intensity >= hi) or (intensity <= lo and min_max_int is not None):
        if min_max_int is not None:
            intensity = min_max_int

    self.frames = self.frames + 1
    if intensity > self.max_int:
        self.max_int = intensity
        if self.frames > 300:  # TODO: test this number more (make it a setting??)
            self.max_ints.append(self.max_int)
            min_max_int = self.max_int if min_max_int is None else min(min_max_int, self.max_int)
    if intensity < self.min_int:
        self.min_int = intensity

    if min_max_int is not None and len(self.max_ints) > 1:
        return 0.0 if intensity > min_max_int else 0.8
    return 0.8


# print(self.blinkvalue, self.max_int, self.min_int, self.frames, intensity)
