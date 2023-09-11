from dataclasses import dataclass

from consts import EyeInfoOrigin


@dataclass
class EyeInfo:
    info_type: EyeInfoOrigin
    x: float
    y: float
    pupil_dialation: float
    blink: float
