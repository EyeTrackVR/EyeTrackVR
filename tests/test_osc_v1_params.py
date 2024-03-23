import dataclasses
from queue import Queue
from time import sleep
from unittest import mock

import pytest

from osc.osc import OSCManager, OSCMessage
from osc.OSCMessage import OSCMessageType


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


@pytest.mark.parametrize(
    "messages,expected_outcome",
    [
        (
            [
                OSCMessage(
                    type=OSCMessageType.EYE_INFO,
                    data=(
                        0,
                        EyeInfoMock(
                            x=0,
                            y=0,
                            blink=1,
                            pupil_dilation=0,
                            avg_velocity=0,
                        ),
                    ),
                ),
            ],
            [
                ("/avatar/parameters/LeftEyeX", 0),
                ("/avatar/parameters/RightEyeX", 0),
                ("/avatar/parameters/EyesY", 0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 1.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 1.0),
            ],
        ),
        (
            [
                OSCMessage(
                    type=OSCMessageType.EYE_INFO,
                    data=(
                        1,
                        EyeInfoMock(
                            x=0,
                            y=0,
                            blink=1,
                            pupil_dilation=0,
                            avg_velocity=0,
                        ),
                    ),
                ),
            ],
            [
                ("/avatar/parameters/LeftEyeX", 0),
                ("/avatar/parameters/RightEyeX", 0),
                ("/avatar/parameters/EyesY", 0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 1.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 1.0),
            ],
        ),
    ],
)
def test_send_command_v1_params_single_eye(main_config_v1_params, messages, expected_outcome):
    with mock.patch("EyeTrackApp.osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        msg_queue = Queue()
        client = OSCManager(
            config=main_config_v1_params,
            osc_message_in_queue=msg_queue,
        )

        client.start()

        for message in messages:
            sleep(0.01)
            msg_queue.put(message)
        client.shutdown()

        assert msg_queue.empty()
        assert client.osc_sender.client.messages == expected_outcome


@pytest.mark.parametrize(
    "eye_data,expected_outcome",
    [
        (
            [
                OSCMessage(
                    type=OSCMessageType.EYE_INFO,
                    data=(
                        0,
                        EyeInfoMock(
                            x=0,
                            y=0,
                            blink=1,
                            pupil_dilation=1,
                            avg_velocity=0,
                        ),
                    ),
                ),
                OSCMessage(
                    type=OSCMessageType.EYE_INFO,
                    data=(
                        1,
                        EyeInfoMock(
                            x=10,
                            y=5,
                            blink=0.5,
                            pupil_dilation=1,
                            avg_velocity=0,
                        ),
                    ),
                ),
            ],
            [
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 1.0),
                ("/avatar/parameters/RightEyeX", 0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 1.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.5),
                ("/avatar/parameters/LeftEyeX", 0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.5),
                ("/avatar/parameters/EyesY", 2.5),
            ],
        ),
        # binary blink
        (
            [
                OSCMessage(
                    type=OSCMessageType.EYE_INFO,
                    data=(
                        0,
                        EyeInfoMock(
                            x=0,
                            y=0,
                            blink=0,
                            pupil_dilation=1,
                            avg_velocity=0,
                        ),
                    ),
                ),
                OSCMessage(
                    type=OSCMessageType.EYE_INFO,
                    data=(
                        1,
                        EyeInfoMock(
                            x=10,
                            y=5,
                            blink=0,
                            pupil_dilation=1,
                            avg_velocity=0,
                        ),
                    ),
                ),
            ],
            [
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeX", 0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeX", 0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/EyesY", 2.5),
            ],
        ),
    ],
)
def test_send_command_v1_params_dual_eye(main_config_v1_params, eye_data, expected_outcome):
    main_config_v1_params.eye_display_id = 2

    with mock.patch("EyeTrackApp.osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        msg_queue = Queue()
        client = OSCManager(
            config=main_config_v1_params,
            osc_message_in_queue=msg_queue,
        )

        client.start()

        for message in eye_data:
            sleep(0.01)
            msg_queue.put(message)
        client.shutdown()

        assert msg_queue.empty()
        assert client.osc_sender.client.messages == expected_outcome


@pytest.mark.parametrize(
    "eye_data,expected_outcome",
    [
        (
            [
                OSCMessage(
                    type=OSCMessageType.EYE_INFO,
                    data=(
                        0,
                        EyeInfoMock(
                            x=0,
                            y=0,
                            blink=0,
                            pupil_dilation=1,
                            avg_velocity=0,
                        ),
                    ),
                ),
                OSCMessage(
                    type=OSCMessageType.EYE_INFO,
                    data=(
                        1,
                        EyeInfoMock(
                            x=10,
                            y=5,
                            blink=0,
                            pupil_dilation=1,
                            avg_velocity=0,
                        ),
                    ),
                ),
            ],
            [
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeX", 0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/RightEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/LeftEyeX", 0),
                ("/avatar/parameters/LeftEyeLidExpandedSqueeze", 0.0),
                ("/avatar/parameters/EyesY", 2.5),
            ],
        ),
    ],
)
def test_send_command_v1_params_eye_outer_side_falloff(main_config_v1_params, eye_data, expected_outcome):
    main_config_v1_params.eye_display_id = 2
    main_config_v1_params.settings.gui_outer_side_falloff = True

    with mock.patch("EyeTrackApp.osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        msg_queue = Queue()
        client = OSCManager(
            config=main_config_v1_params,
            osc_message_in_queue=msg_queue,
        )

        client.start()

        for message in eye_data:
            msg_queue.put(message)
            sleep(1)
        client.shutdown()

        assert msg_queue.empty()
        assert client.osc_sender.client.messages == expected_outcome
