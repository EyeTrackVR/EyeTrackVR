import struct

class DataPacket:
    def __init__(self, buffer, offset, size):
        self.frame_num = None
        self.id = None
        self.buf_size = None
        self.data = None

        if len(buffer) < offset + 12:  # Ensure buffer is large enough for metadata
            return

        self.frame_num, self.id, self.buf_size = struct.unpack_from("iii", buffer, offset)
        current_index = offset + 12

        message_length = size - current_index
        if message_length < 0 or current_index + message_length > len(buffer):
            return

        self.data = buffer[current_index:current_index + message_length]