"""pyvrcft sends VRCFT Unified Expressions tracking data straight to
VRChat OSC, no VRCFT app or module system required."""

from .avatar import AvatarInfo, AvatarParameter
from .client import VRCFTClient
from .expressions import (
    FACE_V1_KEYS,
    SIMPLE_EXPRESSIONS,
    UNIFIED_EXPRESSIONS,
    UnifiedTrackingData,
    compute_face_v1,
    compute_legacy_outputs,
    compute_outputs,
)

__all__ = [
    "VRCFTClient",
    "AvatarInfo",
    "AvatarParameter",
    "UnifiedTrackingData",
    "compute_outputs",
    "compute_legacy_outputs",
    "compute_face_v1",
    "FACE_V1_KEYS",
    "UNIFIED_EXPRESSIONS",
    "SIMPLE_EXPRESSIONS",
]
__version__ = "0.2.0"
