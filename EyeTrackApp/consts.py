from enum import Enum, IntEnum


class CaptureSourceType(IntEnum):
    NONE = 0
    INDEXED = 1
    COM = 2
    HTTP = 3
    TEST_VIDEO = 4


class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3


class EyeInfoOrigin(Enum):
    RANSAC = 1
    BLOB = 2
    FAILURE = 3
    HSF = 4
    HSRAC = 5
    DADDY = 6


RANSAC_CALIBRATION_STEPS_START: int = 300
RANSAC_CALIBRATION_STEPS_STOP = 0

SUPPORTED_VIDEO_FORMATS = [
    "mp4",
]
