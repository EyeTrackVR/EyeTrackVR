import dataclasses
from enum import IntEnum
from typing import Any


class OSCMessageType(IntEnum):
    EYE_INFO = 1
    VRCFT_MODULE_INFO = 2


@dataclasses.dataclass
class OSCMessage:
    type: OSCMessageType
    data: Any
