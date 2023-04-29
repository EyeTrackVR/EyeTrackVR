from dataclasses import dataclass
from enum import Enum, IntEnum

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


@dataclass
class EyeInfo:
    info_type: EyeInfoOrigin
    x: float
    y: float
    pupil_dialation: float
    blink: float
