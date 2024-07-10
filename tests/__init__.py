import dataclasses


@dataclasses.dataclass
class EyeInfoMock:
    x: int
    y: int
    blink: float
    pupil_dilation: float
    avg_velocity: float


class SimpleUDPClientMock:
    def __init__(self, osc_address, port):
        self.osc_address = osc_address
        self.port = port
        self.messages = []

    def send_message(self, address, value):
        self.messages.append((address, value))
