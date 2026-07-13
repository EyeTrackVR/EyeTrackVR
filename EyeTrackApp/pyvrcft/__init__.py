"""pyvrcft — send VRCFT Unified Expressions tracking data straight to
VRChat OSC, no VRCFT app or module system required."""

from .avatar import AvatarInfo, AvatarParameter
from .client import VRCFTClient
from .expressions import (
    SIMPLE_EXPRESSIONS,
    UNIFIED_EXPRESSIONS,
    UnifiedTrackingData,
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
    "UNIFIED_EXPRESSIONS",
    "SIMPLE_EXPRESSIONS",
]
__version__ = "0.2.0"
