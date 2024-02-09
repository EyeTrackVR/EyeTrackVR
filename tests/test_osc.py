import dataclasses
import threading
from queue import Queue
from time import sleep
from unittest import mock

import pytest

from EyeTrackApp.osc import VRChatOSC


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
    "eye_id,messages,expected_outcome",
    [
        (
            0,
            [
                EyeInfoMock(
                    x=0,
                    y=0,
                    blink=1,
                    pupil_dilation=0,
                    avg_velocity=0,
                ),
            ],
            [
                ("/avatar/parameters/v2/EyeX", 0),
                ("/avatar/parameters/v2/EyeY", 0),
                ("/avatar/parameters/v2/EyeLid", 1.0),
            ],
        ),
        (
            1,
            [
                EyeInfoMock(
                    x=0,
                    y=0,
                    blink=1,
                    pupil_dilation=0,
                    avg_velocity=0,
                ),
            ],
            [
                ("/avatar/parameters/v2/EyeX", 0),
                ("/avatar/parameters/v2/EyeY", 0),
                ("/avatar/parameters/v2/EyeLid", 1.0),
            ],
        ),
    ],
)
def test_send_command_v2_params_single_eye(main_config_v2_params, eye_id, messages, expected_outcome):
    with mock.patch("EyeTrackApp.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        cancellation_event = threading.Event()
        msg_queue = Queue()
        client = VRChatOSC(
            main_config=main_config_v2_params,
            msg_queue=msg_queue,
            cancellation_event=cancellation_event,
        )

        osc_thread = threading.Thread(target=client.run)
        osc_thread.start()

        for message in messages:
            sleep(0.01)
            msg_queue.put((eye_id, message))

        cancellation_event.set()
        osc_thread.join()

        assert msg_queue.empty()
        assert client.client.messages == expected_outcome


@pytest.mark.parametrize(
    "eye_data,expected_outcome",
    [
        (
            [
                (
                    0,
                    EyeInfoMock(
                        x=0,
                        y=0,
                        blink=1,
                        pupil_dilation=1,
                        avg_velocity=0,
                    ),
                ),
                (
                    1,
                    EyeInfoMock(
                        x=10,
                        y=5,
                        blink=0.5,
                        pupil_dilation=1,
                        avg_velocity=0,
                    ),
                ),
            ],
            [
                ("/avatar/parameters/v2/EyeRightX", 0),
                ("/avatar/parameters/v2/EyeRightY", 0),
                ("/avatar/parameters/v2/EyeLidRight", 1.0),
                ("/avatar/parameters/v2/EyeLeftX", 10),
                ("/avatar/parameters/v2/EyeLeftY", 5),
                ("/avatar/parameters/v2/EyeLidLeft", 0.5),
            ],
        ),
        # binary blink
        (
            [
                (
                    0,
                    EyeInfoMock(
                        x=0,
                        y=0,
                        blink=0,
                        pupil_dilation=1,
                        avg_velocity=0,
                    ),
                ),
                (
                    1,
                    EyeInfoMock(
                        x=10,
                        y=5,
                        blink=0,
                        pupil_dilation=1,
                        avg_velocity=0,
                    ),
                ),
            ],
            [
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeRightX", 0),
                ("/avatar/parameters/v2/EyeRightY", 0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLeftX", 0),
                ("/avatar/parameters/v2/EyeLeftY", 5),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
            ],
        ),
    ],
)
def test_send_command_v2_params_dual_eye(main_config_v2_params, eye_data, expected_outcome):
    main_config_v2_params.eye_display_id = 2

    with mock.patch("EyeTrackApp.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        cancellation_event = threading.Event()
        msg_queue = Queue()
        client = VRChatOSC(
            main_config=main_config_v2_params,
            msg_queue=msg_queue,
            cancellation_event=cancellation_event,
        )

        osc_thread = threading.Thread(target=client.run)
        osc_thread.start()

        for eye_id, message in eye_data:
            sleep(0.01)
            msg_queue.put((eye_id, message))

        cancellation_event.set()
        osc_thread.join()

        assert msg_queue.empty()
        assert client.client.messages == expected_outcome


@pytest.mark.parametrize(
    "eye_data,expected_outcome",
    [
        (
            [
                (
                    0,
                    EyeInfoMock(
                        x=0,
                        y=0,
                        blink=0,
                        pupil_dilation=1,
                        avg_velocity=0,
                    ),
                ),
                (
                    1,
                    EyeInfoMock(
                        x=10,
                        y=5,
                        blink=0,
                        pupil_dilation=1,
                        avg_velocity=0,
                    ),
                ),
            ],
            [
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeRightX", 0),
                ("/avatar/parameters/v2/EyeRightY", 0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLeftX", 0),
                ("/avatar/parameters/v2/EyeLeftY", 5),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
            ],
        ),
        (
            [
                (
                    0,
                    EyeInfoMock(
                        x=0,
                        y=0,
                        blink=0,
                        pupil_dilation=1,
                        avg_velocity=0,
                    ),
                ),
                (
                    1,
                    EyeInfoMock(
                        x=10,
                        y=5,
                        blink=0,
                        pupil_dilation=1,
                        avg_velocity=0,
                    ),
                ),
            ],
            [
                # binary blink
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeRightX", 0),
                ("/avatar/parameters/v2/EyeRightY", 0),
                # side falloff
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                # binary blink again
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
                ("/avatar/parameters/v2/EyeLidRight", 0.0),
                ("/avatar/parameters/v2/EyeLeftX", 0),
                ("/avatar/parameters/v2/EyeLeftY", 5),
                ("/avatar/parameters/v2/EyeLidLeft", 0.0),
            ],
        ),
    ],
)
def test_send_command_v2_params_eye_outer_side_falloff(main_config_v2_params, eye_data, expected_outcome):
    main_config_v2_params.eye_display_id = 2
    main_config_v2_params.settings.gui_outer_side_falloff = True

    with mock.patch("EyeTrackApp.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        cancellation_event = threading.Event()
        msg_queue = Queue()
        client = VRChatOSC(
            main_config=main_config_v2_params,
            msg_queue=msg_queue,
            cancellation_event=cancellation_event,
        )

        osc_thread = threading.Thread(target=client.run)
        osc_thread.start()

        for eye_id, message in eye_data:
            sleep(0.01)
            msg_queue.put((eye_id, message))

        cancellation_event.set()
        osc_thread.join()

        assert msg_queue.empty()
        assert client.client.messages == expected_outcome
