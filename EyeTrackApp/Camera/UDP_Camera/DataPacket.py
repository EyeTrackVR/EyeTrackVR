import struct
import numpy as np
import ctypes

class PacketHeader:
    def __init__(self, headerFormat, dataView, rawDataSize):
        self.frame_num: int|None = None
        self.id: int|None = None
        self.image_buf_size: int|None = None

        self.frame_num, self.id, self.image_buf_size = struct.unpack_from(headerFormat, dataView, 0)
