import dataclasses
from enum import IntEnum


class OSCMessageType(IntEnum):
    EYE_INFO = 1
    VRCFT_MODULE_INFO = 2


@dataclasses.dataclass
class OSCMessage:
    type: OSCMessageType
    data: any