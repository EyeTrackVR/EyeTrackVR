from queue import Queue
from time import sleep
from unittest import mock

import pytest

from osc.osc import OSCManager, OSCMessage
from osc.OSCMessage import OSCMessageType
from tests import EyeInfoMock, SimpleUDPClientMock


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
                ("/tracking/eye/EyesClosedAmount", 0.0),
                ("/tracking/eye/LeftRightVec", [0.0, 0.0, 1.0, 0.0, 0.0, 1.0]),
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
                ("/tracking/eye/EyesClosedAmount", 0.0),
                ("/tracking/eye/LeftRightVec", [0.0, 0.0, 1.0, 0.0, 0.0, 1.0]),
            ],
        ),
    ],
)
def test_send_command_native_params_single_eye(main_config_native_params, messages, expected_outcome):
    with mock.patch("EyeTrackApp.osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        msg_queue = Queue()
        client = OSCManager(
            config=main_config_native_params,
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
                ("/tracking/eye/EyesClosedAmount", 0.0),
                ("/tracking/eye/EyesClosedAmount", 0.0),
                # we're expecting 621 as left_y here because that's the default value
                # before the first state update with real data, but that's ok
                # we're gonna be like 10 messages deep before anyone starts playing
                # and if they already are, they won't be able to notice
                ("/tracking/eye/LeftRightVec", [0.0, 621.0, 1.0, 0.0, 0.0, 1.0]),
                ("/tracking/eye/EyesClosedAmount", 0.5),
                ("/tracking/eye/EyesClosedAmount", 0.5),
                ("/tracking/eye/LeftRightVec", [0.0, 5.0, 1.0, 0.0, 0.0, 1.0]),
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
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/LeftRightVec", [0.0, 621.0, 1.0, 0.0, 0.0, 1.0]),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/LeftRightVec", [0.0, 5.0, 1.0, 0.0, 0.0, 1.0]),
            ],
        ),
    ],
)
def test_send_command_native_params_dual_eye(main_config_native_params, eye_data, expected_outcome):
    main_config_native_params.eye_display_id = 2

    with mock.patch("EyeTrackApp.osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        msg_queue = Queue()
        client = OSCManager(
            config=main_config_native_params,
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
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/LeftRightVec", [0.0, 621.0, 1.0, 0.0, 0.0, 1.0]),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/EyesClosedAmount", 1.0),
                ("/tracking/eye/LeftRightVec", [0.0, 5.0, 1.0, 0.0, 0.0, 1.0]),
            ],
        ),
    ],
)
def test_send_command_native_params_eye_outer_side_falloff(main_config_native_params, eye_data, expected_outcome):
    main_config_native_params.eye_display_id = 2
    main_config_native_params.settings.gui_outer_side_falloff = True

    with mock.patch("EyeTrackApp.osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        msg_queue = Queue()
        client = OSCManager(
            config=main_config_native_params,
            osc_message_in_queue=msg_queue,
        )

        client.start()

        for message in eye_data:
            msg_queue.put(message)
            sleep(1)
        client.shutdown()

        assert msg_queue.empty()
        assert client.osc_sender.client.messages == expected_outcome
