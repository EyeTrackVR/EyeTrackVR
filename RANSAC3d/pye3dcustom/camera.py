from typing import Tuple, NamedTuple


class CameraModel(NamedTuple):
    focal_length: float
    resolution: Tuple[float, float]
