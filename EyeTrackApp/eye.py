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

from dataclasses import dataclass
from enum import Enum, IntEnum


class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3
    ALGOSETTINGS = 4
    VRCFTMODULESETTINGS = 5
    GUIOFF = 6
    BSB2E = 7


class EyeInfoOrigin(Enum):
    RANSAC = 1
    FAILURE = 3
    HSF = 4
    HSRAC = 5
    DADDY = 6
    LEAP = 7
    NEXT = 8


@dataclass
class EyeInfo:
    info_type: EyeInfoOrigin
    x: float
    y: float
    pupil_dilation: float
    blink: float
    avg_velocity: float
    eyebrow: float = float("nan")
    squeeze: float = 0.0
    # time.perf_counter() when the camera frame behind this sample was captured.
    capture_ts: float | None = None
    # Calibrated gaze with no smoothing (no median / One-Euro / falloff / snap
    # hold / blink hold), for foveated rendering. x / y above stay the
    # filtered gaze VRChat gets. None when the tracker has no unfiltered tap.
    dfr_x: float | None = None
    dfr_y: float | None = None
