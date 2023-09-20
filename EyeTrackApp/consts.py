from enum import Enum, IntEnum


class CaptureSourceType(IntEnum):
    NONE = 0
    INDEXED = 1
    COM = 2
    HTTP = 3
    TEST_VIDEO = 4


class PageType(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3
    ALGO_SETTINGS = 4


class EyeInfoOrigin(Enum):
    RANSAC = 1
    BLOB = 2
    FAILURE = 3
    HSF = 4
    HSRAC = 5
    DADDY = 6
    LEAP = 7


RANSAC_CALIBRATION_STEPS_START: int = 500
RANSAC_CALIBRATION_STEPS_STOP = 0

SUPPORTED_VIDEO_FORMATS = [
    "mp4",
]

calibration_max_axis_value = 69420