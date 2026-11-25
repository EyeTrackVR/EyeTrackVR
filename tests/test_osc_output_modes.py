"""Classic VRChat output modes (VRCFT v1 params, VRCFT v2 params, VRChat native):
exactly what reaches the wire for each eye sample, end to end through OSCManager,
plus the closed-eye burst, eyelid inversion and brows."""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from eye import EyeId
from osc import vrchat_osc_sender
from osc.osc_message import OSCMessage, OSCMessageType
from osc.vrchat_osc_sender import BLINK_BURST_INTERVAL_S, VRChatOSCSender, brow_expression
from tests import SimpleUDPClientMock
from tests.osc_helpers import (
    collect_stray_garbage,
    drain,
    eye_msg,
    isolate_gaze_outputs,
    no_pyvrcft_discovery,
    receive_until,
    run_messages,
    running_manager,
    set_output_mode,
    udp_listener,
    use_free_ports,
    wait_until_sent,
)

V1 = "/avatar/parameters/"
V2 = "/avatar/parameters/v2/"
CLOSED = "/tracking/eye/EyesClosedAmount"
VEC = "/tracking/eye/LeftRightVec"
PITCH_YAW = "/tracking/eye/LeftRightPitchYaw"


@pytest.fixture(autouse=True, scope="module")
def _main_thread_gc():
    collect_stray_garbage()


@pytest.fixture(autouse=True)
def _private_gaze_outputs(monkeypatch, tmp_path):
    isolate_gaze_outputs(monkeypatch, tmp_path)


def _sent(main_config, mode, display, messages, *, falloff=False, invert=False):
    set_output_mode(main_config.settings, mode)
    main_config.eye_display_id = display
    main_config.settings.gui_outer_side_falloff = falloff
    main_config.settings.osc_invert_eye_close = invert
    return run_messages(main_config, messages).osc_sender.vrc_client.messages


# Single-eye mode sends both eyes from whichever camera reports (eye id 0 or 1).
SINGLE_OPEN = {
    "v1": [
        (V1 + "LeftEyeX", 0),
        (V1 + "RightEyeX", 0),
        (V1 + "EyesY", 0),
        (V1 + "EyesDilation", 0),
        (V1 + "LeftEyeLidExpandedSqueeze", 1.0),
        (V1 + "RightEyeLidExpandedSqueeze", 1.0),
    ],
    "v2": [
        (V2 + "EyeX", 0),
        (V2 + "EyeY", 0),
        (V2 + "PupilDilation", 0),
        (V2 + "CheekSquintLeft", 0.0),
        (V2 + "CheekSquintRight", 0.0),
        (V2 + "EyeSquintLeft", 0.0),
        (V2 + "EyeSquintRight", 0.0),
        (V2 + "EyeSquint", 0.0),
        (V2 + "EyeLid", 1.0),
        (V2 + "EyeLid", 1.0),
    ],
    "native": [
        (CLOSED, 0.0),
        (VEC, [0.0, 0.0, 1.0, 0.0, 0.0, 1.0]),
    ],
}


@pytest.mark.parametrize("eye_id", [EyeId.RIGHT, EyeId.LEFT])
@pytest.mark.parametrize("mode", ["v1", "v2", "native"])
def test_single_eye_sends_both_eyes_from_one_camera(main_config, mode, eye_id):
    sent = _sent(main_config, mode, eye_id, [eye_msg(eye_id, x=0, y=0, blink=1, pupil_dilation=0)])
    assert sent == SINGLE_OPEN[mode]


def _mirrored(mode, lid):
    """Dual-eye mode, first frame: only the right eye (x=0, y=0, dilation=1) has
    reported, so it is mirrored to both eyes until the left one shows up."""
    if mode == "v1":
        return [
            (V1 + "LeftEyeX", 0),
            (V1 + "RightEyeX", 0),
            (V1 + "EyesY", 0),
            (V1 + "EyesDilation", 1),
            (V1 + "LeftEyeLidExpandedSqueeze", lid),
            (V1 + "RightEyeLidExpandedSqueeze", lid),
        ]
    if mode == "v2":
        return [
            (V2 + "EyeX", 0),
            (V2 + "EyeY", 0),
            (V2 + "PupilDilation", 1),
            (V2 + "CheekSquintLeft", 0.0),
            (V2 + "CheekSquintRight", 0.0),
            (V2 + "EyeSquintLeft", 0.0),
            (V2 + "EyeSquintRight", 0.0),
            (V2 + "EyeSquint", 0.0),
            (V2 + "EyeLid", lid),
            (V2 + "EyeLid", lid),
            # ... and the per-eye parameters a two-eye avatar reads.
            (V2 + "EyeLeftX", 0),
            (V2 + "EyeLeftY", 0),
            (V2 + "EyeRightX", 0),
            (V2 + "EyeRightY", 0),
            (V2 + "EyeLidLeft", lid),
            (V2 + "EyeLidRight", lid),
        ]
    # native: a closed eye goes out as its 5x burst.
    closed = [(CLOSED, 1.0)] * 5 if lid == 0.0 else [(CLOSED, 1.0 - lid)]
    return closed + [(VEC, [0.0, 0.0, 1.0, 0.0, 0.0, 1.0])]


# Dual-eye: right (id 0) open, then left (id 1) half closed. Each table is the
# mirrored first frame plus what the left eye's frame adds.
DUAL_EYES = [
    eye_msg(EyeId.RIGHT, x=0, y=0, blink=1, pupil_dilation=1),
    eye_msg(EyeId.LEFT, x=10, y=5, blink=0.5, pupil_dilation=1),
]
DUAL = {
    "v1": _mirrored("v1", 1.0)
    + [
        (V1 + "LeftEyeLidExpandedSqueeze", 0.5),
        (V1 + "LeftEyeX", 10),
        (V1 + "EyesY", 2.5),  # both eyes' Y averaged once both have reported
        (V1 + "EyesDilation", 1.0),
    ],
    "v2": _mirrored("v2", 1.0)
    + [
        (V2 + "EyeLidLeft", 0.5),
        (V2 + "EyeLeftX", 10),
        (V2 + "EyeLeftY", 5),
        (V2 + "CheekSquintLeft", 0.0),
        (V2 + "EyeSquintLeft", 0.0),
        (V2 + "PupilDilation", 1.0),
        (V2 + "EyeSquint", 0.0),
    ],
    # Dual-eye native blink is the average of both eyes: 1 - (1.0 + 0.5) / 2.
    "native": _mirrored("native", 1.0) + [(CLOSED, 0.25), (VEC, [10.0, 5.0, 1.0, 0.0, 0.0, 1.0])],
}

# Dual-eye, both closed (binary blink): once both eyes report, a closed eye goes
# out as a 5x burst plus its per-frame send.
DUAL_CLOSED_EYES = [
    eye_msg(EyeId.RIGHT, x=0, y=0, blink=0, pupil_dilation=1),
    eye_msg(EyeId.LEFT, x=10, y=5, blink=0, pupil_dilation=1),
]
DUAL_CLOSED = {
    "v1": _mirrored("v1", 0.0)
    + [(V1 + "LeftEyeLidExpandedSqueeze", 0.0)] * 6
    + [(V1 + "LeftEyeX", 10), (V1 + "EyesY", 2.5), (V1 + "EyesDilation", 1.0)],
    "v2": _mirrored("v2", 0.0)
    + [(V2 + "EyeLidLeft", 0.0)] * 6
    + [
        (V2 + "EyeLeftX", 10),
        (V2 + "EyeLeftY", 5),
        (V2 + "CheekSquintLeft", 0.0),
        (V2 + "EyeSquintLeft", 0.0),
        (V2 + "PupilDilation", 1.0),
        (V2 + "EyeSquint", 0.0),
    ],
    "native": _mirrored("native", 0.0) + [(CLOSED, 1.0)] * 6 + [(VEC, [10.0, 5.0, 1.0, 0.0, 0.0, 1.0])],
}

# Outer-side falloff on: when the other eye is closed too, both lids are resent.
_FALLOFF_V1 = [(V1 + "RightEyeLidExpandedSqueeze", 0.0), (V1 + "LeftEyeLidExpandedSqueeze", 0.0)]
_FALLOFF_V2 = [(V2 + "EyeLidRight", 0.0), (V2 + "EyeLidLeft", 0.0)]
DUAL_CLOSED_FALLOFF = {
    "v1": DUAL_CLOSED["v1"][:-3] + _FALLOFF_V1 + DUAL_CLOSED["v1"][-3:],
    "v2": DUAL_CLOSED["v2"][:-6] + _FALLOFF_V2 + DUAL_CLOSED["v2"][-6:],
    "native": _mirrored("native", 0.0) + [(CLOSED, 1.0)] * 7 + [(VEC, [10.0, 5.0, 1.0, 0.0, 0.0, 1.0])],
}


@pytest.mark.parametrize("mode", ["v1", "v2", "native"])
@pytest.mark.parametrize(
    "messages, table, falloff",
    [
        (DUAL_EYES, DUAL, False),
        (DUAL_CLOSED_EYES, DUAL_CLOSED, False),
        (DUAL_CLOSED_EYES, DUAL_CLOSED_FALLOFF, True),
    ],
    ids=["open-and-half", "both-closed", "both-closed-falloff"],
)
def test_dual_eye_output(main_config, mode, messages, table, falloff):
    assert _sent(main_config, mode, EyeId.BOTH, messages, falloff=falloff) == table[mode]


@pytest.mark.parametrize("mode", ["v1", "v2", "native"])
def test_dual_eye_mirrors_the_only_reporting_eye_every_frame(main_config, mode):
    """Two cameras configured, one never delivers: the working eye keeps driving both."""
    frame = eye_msg(EyeId.RIGHT, x=0, y=0, blink=1, pupil_dilation=1)
    assert _sent(main_config, mode, EyeId.BOTH, [frame] * 3) == _mirrored(mode, 1.0) * 3


@pytest.mark.parametrize(
    "mode, lids",
    [
        ("v1", [V1 + "LeftEyeLidExpandedSqueeze", V1 + "RightEyeLidExpandedSqueeze"]),
        ("v2", [V2 + "EyeLid", V2 + "EyeLid"]),
    ],
    ids=["v1", "v2"],
)
def test_invert_eye_close_flips_avatar_eyelids(main_config, mode, lids):
    sent = _sent(main_config, mode, EyeId.RIGHT, [eye_msg(EyeId.RIGHT, blink=0.2)], invert=True)
    assert [(a, v) for a, v in sent if "Lid" in a] == [(lid, pytest.approx(0.8)) for lid in lids]


def test_native_dual_eye_held_blink_ignores_invert(main_config_native_params):
    """EyesClosedAmount is 1 = closed in VRChat whatever the avatar-param invert
    setting says (the per-frame send used to be inverted to 0 while the burst sent 1)."""
    main_config_native_params.eye_display_id = EyeId.BOTH
    settings = main_config_native_params.settings
    settings.osc_invert_eye_close = True
    sender, client = VRChatOSCSender(), SimpleUDPClientMock("127.0.0.1", 9000)

    def closed(eye_id):
        info = eye_msg(eye_id, blink=0.0)
        sender.output_osc_info(info, client, main_config_native_params, settings)

    closed(EyeId.LEFT)
    client.messages.clear()  # the right eye is still at its default openness
    closed(EyeId.RIGHT)  # both closed: per-frame send plus a burst
    closed(EyeId.LEFT)  # the other eye's burst
    amounts = [v for a, v in client.messages if a == CLOSED]
    assert len(amounts) > 2
    assert set(amounts) == {1.0}


# ------------------------------------------------------------ closed-eye burst


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _count(client, address):
    n = sum(1 for a, _ in client.messages if a == address)
    client.messages.clear()
    return n


@pytest.fixture
def clock(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(vrchat_osc_sender, "time", SimpleNamespace(monotonic=clock))
    return clock


def test_dual_eye_burst_is_rate_limited_per_eye(main_config_v2_params, clock):
    """A closed eye is resent as a 5x burst at most once per BLINK_BURST_INTERVAL_S per eye."""
    main_config_v2_params.eye_display_id = EyeId.BOTH
    sender, client = VRChatOSCSender(), SimpleUDPClientMock("127.0.0.1", 9000)

    def send(eye_id):
        sender.output_osc_info(
            eye_msg(eye_id, blink=0.0), client, main_config_v2_params, main_config_v2_params.settings
        )

    right = V2 + "EyeLidRight"
    send(EyeId.LEFT)  # both eyes reporting: no mirroring
    clock.now += BLINK_BURST_INTERVAL_S * 2
    client.messages.clear()
    send(EyeId.RIGHT)
    assert _count(client, right) == 6  # burst + the per-frame send
    clock.now += BLINK_BURST_INTERVAL_S / 2
    send(EyeId.RIGHT)
    assert _count(client, right) == 1  # still closed, inside the interval: no burst
    send(EyeId.LEFT)  # the other eye has its own timer
    assert _count(client, V2 + "EyeLidLeft") == 6
    clock.now += BLINK_BURST_INTERVAL_S
    send(EyeId.RIGHT)
    assert _count(client, right) == 6


def test_native_single_eye_closed_sends_every_frame_and_bursts_rarely(main_config_native_params, clock):
    sender, client = VRChatOSCSender(), SimpleUDPClientMock("127.0.0.1", 9000)
    counts = []
    for _ in range(3):
        sender.output_osc_info(
            eye_msg(EyeId.RIGHT, blink=0.0), client, main_config_native_params, main_config_native_params.settings
        )
        counts.append(_count(client, CLOSED))
        clock.now += 0.033
    assert counts == [5, 1, 1]


# ---------------------------------------------------------------------- brows


@pytest.mark.parametrize(
    "brow, expected",
    [(0.0, -1.0), (0.25, -0.5), (0.5, 0.0), (0.75, 0.5), (1.0, 1.0), (-0.2, -1.0), (1.3, 1.0)],
)
def test_brow_expression_centres_tracker_neutral(brow, expected):
    # Tracker brow is 0..1 with 0.5 = rest; VRCFT BrowExpression is -1..+1.
    assert brow_expression(brow) == pytest.approx(expected)


def _brow(eye_id, value):
    return OSCMessage(type=OSCMessageType.EYEBROW_INFO, data=(eye_id, value))


@pytest.mark.parametrize(
    "display, messages, expected",
    [
        (EyeId.RIGHT, [_brow(EyeId.RIGHT, 0.75)], [(V2 + "BrowExpression", 0.5)]),
        (
            EyeId.BOTH,
            [_brow(EyeId.LEFT, 0.5), _brow(EyeId.RIGHT, 0.0)],
            [(V2 + "BrowExpressionLeft", 0.0), (V2 + "BrowExpressionRight", -1.0)],
        ),
        # Only the right eye has reported: its brow drives both, like its gaze.
        (
            EyeId.BOTH,
            [eye_msg(EyeId.RIGHT), _brow(EyeId.RIGHT, 0.75)],
            [(V2 + "BrowExpressionLeft", 0.5), (V2 + "BrowExpressionRight", 0.5)],
        ),
        # NaN must not reach the clamp, which would turn it into a full raise.
        (EyeId.BOTH, [_brow(EyeId.LEFT, float("nan")), _brow(EyeId.LEFT, float("inf"))], []),
    ],
    ids=["single-eye", "dual-eye", "dual-eye-one-reporting", "non-finite"],
)
def test_brow_output(main_config_v2_params, display, messages, expected):
    main_config_v2_params.eye_display_id = display
    sent = run_messages(main_config_v2_params, messages).osc_sender.vrc_client.messages
    assert [m for m in sent if "Brow" in m[0]] == expected


# ------------------------------------------------- every mode on the real wire


@pytest.mark.parametrize("mode", ["v1", "v2", "native", "pyvrcft"])
def test_every_mode_sends_plain_finite_values_and_survives_bad_frames(main_config, mode, monkeypatch):
    """Real UDP to a local socket. numpy scalars once raised inside python-osc and
    killed the sender thread; NaN/inf must never reach an avatar (it holds the last
    good value instead) and must not stop the next frame."""
    no_pyvrcft_discovery(monkeypatch)
    s = main_config.settings
    set_output_mode(s, mode)
    use_free_ports(s)
    main_config.eye_display_id = EyeId.RIGHT
    with udp_listener() as vrchat:
        s.gui_osc_port = vrchat.getsockname()[1]
        with running_manager(main_config, mock_udp=False) as (manager, msg_queue):
            # A partly bad frame: the finite values still go out.
            msg_queue.put(eye_msg(x=float("nan"), y=0.5, blink=float("nan"), pupil_dilation=float("inf")))
            msg_queue.put(
                eye_msg(
                    x=np.float32(0.25),
                    y=np.float64(-0.5),
                    blink=np.float32(0.75),
                    pupil_dilation=np.int64(1),
                    squeeze=np.float32(0.5),
                )
            )
            wait_until_sent(msg_queue)
            if mode == "pyvrcft":  # sent from pyVRCFT's own thread: wait for the second frame
                received = receive_until(vrchat, lambda r: any(a == PITCH_YAW and v[1] > 0 for a, v in r))
            else:  # already sent by the time the queue is drained
                received = drain(vrchat, settle=0.1)
            assert manager.osc_sender_thread.is_alive()
    assert received, "nothing reached VRChat"
    for address, args in received:
        assert all(math.isfinite(v) for v in args if isinstance(v, float)), (address, args)

    def values(address):
        return [args for a, args in received if a == address]

    if mode == "v1":
        assert values(V1 + "LeftEyeX") == [[0.25]]
        assert values(V1 + "EyesY") == [[0.5], [-0.5]]
        assert values(V1 + "EyesDilation") == [[1]]
    elif mode == "v2":
        assert values(V2 + "EyeX") == [[0.25]]
        assert values(V2 + "EyeY") == [[0.5], [-0.5]]
        assert values(V2 + "EyeLid") == [[0.75], [0.75]]
        assert values(V2 + "EyeSquint")[-1] == [0.5]
        assert values(V2 + "PupilDilation") == [[1]]
    elif mode == "native":
        assert values(VEC) == [[0.25, -0.5, 1.0, 0.25, -0.5, 1.0]]
    else:
        pitch, yaw = values(PITCH_YAW)[-1][:2]
        assert yaw > 0 and pitch > 0  # right and down
        assert values(CLOSED)[-1] == [0.0]
