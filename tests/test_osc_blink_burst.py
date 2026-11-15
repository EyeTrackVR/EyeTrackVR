"""A closed eye is resent as a 5x burst at most once per BLINK_BURST_INTERVAL_S per eye,
not on every closed-eye frame."""

from types import SimpleNamespace

from eye import EyeId
from osc import vrchat_osc_sender
from osc.osc_message import OSCMessage, OSCMessageType
from osc.vrchat_osc_sender import BLINK_BURST_INTERVAL_S, VRChatOSCSender
from tests import EyeInfoMock, SimpleUDPClientMock


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _closed(eye_id):
    info = EyeInfoMock(x=0, y=0, blink=0.0, pupil_dilation=1, avg_velocity=0)
    return OSCMessage(type=OSCMessageType.EYE_INFO, data=(eye_id, info))


def _count(client, address):
    n = sum(1 for a, _ in client.messages if a == address)
    client.messages.clear()
    return n


def test_dual_eye_burst_is_rate_limited_per_eye(main_config_v2_params, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(vrchat_osc_sender, "time", SimpleNamespace(monotonic=clock))
    main_config_v2_params.eye_display_id = EyeId.BOTH
    sender, client = VRChatOSCSender(), SimpleUDPClientMock("127.0.0.1", 9000)
    send = lambda eye_id: sender.output_osc_info(  # noqa: E731
        _closed(eye_id), client, main_config_v2_params, main_config_v2_params.settings
    )
    right = "/avatar/parameters/v2/EyeLidRight"

    send(EyeId.RIGHT)
    assert _count(client, right) == 6  # burst + the per-frame send
    clock.now += BLINK_BURST_INTERVAL_S / 2
    send(EyeId.RIGHT)
    assert _count(client, right) == 1  # still closed, inside the interval: no burst
    send(EyeId.LEFT)  # the other eye has its own timer
    assert _count(client, "/avatar/parameters/v2/EyeLidLeft") == 6
    clock.now += BLINK_BURST_INTERVAL_S
    send(EyeId.RIGHT)
    assert _count(client, right) == 6


def test_native_single_eye_closed_sends_every_frame_and_bursts_rarely(main_config_native_params, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(vrchat_osc_sender, "time", SimpleNamespace(monotonic=clock))
    sender, client = VRChatOSCSender(), SimpleUDPClientMock("127.0.0.1", 9000)
    closed = "/tracking/eye/EyesClosedAmount"

    counts = []
    for _ in range(3):
        sender.output_osc_info(
            _closed(EyeId.RIGHT), client, main_config_native_params, main_config_native_params.settings
        )
        counts.append(_count(client, closed))
        clock.now += 0.033
    assert counts == [5, 1, 1]
