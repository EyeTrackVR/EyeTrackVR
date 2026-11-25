"""PyVRCFTSender: EyeTrackVR eye/brow samples -> the embedded pyVRCFT client's tracking
frame (lid scale, invert setting, brows, non-finite input) and how it starts the client."""

from types import SimpleNamespace
from unittest import mock

import pytest

from eye import EyeId
from osc.osc_message import OSCMessage, OSCMessageType
from osc.pyvrcft_sender import PyVRCFTSender, lid_to_unified
from pyvrcft import FACE_V1_KEYS, UnifiedTrackingData, VRCFTClient, compute_outputs
from tests import EyeInfoMock
from tests.osc_helpers import wire

CLOSED_AMOUNT = "/tracking/eye/EyesClosedAmount"
FACE = "/tracking/face/v1"
V2 = "/avatar/parameters/v2/"
BOTH = SimpleNamespace(eye_display_id=EyeId.BOTH)
NOT_INVERTED = SimpleNamespace(osc_invert_eye_close=False)


def _eye(eye_id, blink, **kw):
    fields = dict(x=0.0, y=0.0, blink=blink, pupil_dilation=0.5, avg_velocity=0.0)
    fields.update(kw)
    return OSCMessage(OSCMessageType.EYE_INFO, data=(eye_id, EyeInfoMock(**fields)))


@pytest.fixture
def sender():
    """A sender whose client is built but not started (no sockets, no threads);
    force_relevant so every value is visible at its default address."""
    sender = PyVRCFTSender()
    sender.client = VRCFTClient(use_oscquery=False, force_relevant=True)
    return sender


# ------------------------------------------------------------------ eyelids


@pytest.mark.parametrize(
    "lid, openness, wide",
    [
        (0.0, 0.0, 0.0),
        (0.375, 0.5, 0.0),
        (0.75, 1.0, 0.0),
        (0.85, 1.0, 0.5),
        (0.95, 1.0, 1.0),
        (1.2, 1.0, 1.0),
        (-0.1, 0.0, 0.0),
    ],
)
def test_lid_to_unified(lid, openness, wide):
    assert lid_to_unified(lid) == pytest.approx((openness, wide))


@pytest.mark.parametrize("lid", [0.0, 0.3, 0.75, 0.9])
def test_v2_eyelid_round_trips_below_full_wide(lid):
    # VRCFT's v2/EyeLid = openness*0.75 + wide*0.25 should give back the lid
    # value EyeTrackVR's own v2 mode sends (exact up to 0.75; the widen span
    # is stretched so 0.95 reaches EyeWide 1, so above it reads slightly high).
    openness, wide = lid_to_unified(lid)
    data = UnifiedTrackingData()
    data.eye.left.openness = data.eye.right.openness = openness
    data.shapes["EyeWideLeft"] = data.shapes["EyeWideRight"] = wide
    out, _native = compute_outputs(data)
    expected = lid if lid <= 0.75 else 0.75 + (lid - 0.75) * 0.25 / 0.20
    assert out["v2/EyeLidLeft"] == pytest.approx(expected)
    assert out["v2/EyeOpenLeft"] == pytest.approx(openness)


def test_normal_open_is_fully_open_and_wide_drives_eyewide(sender):
    sender.output_osc_info(_eye(EyeId.LEFT, 0.75), BOTH, NOT_INVERTED)
    sender.output_osc_info(_eye(EyeId.RIGHT, 0.95), BOTH, NOT_INVERTED)
    sent = wire(sender.client)
    assert sent[V2 + "EyeOpenLeft"] == [pytest.approx(1.0)] and sent[V2 + "EyeWideLeft"] == [0.0]
    assert sent[V2 + "EyeOpenRight"] == [pytest.approx(1.0)] and sent[V2 + "EyeWideRight"] == [pytest.approx(1.0)]
    assert sent[V2 + "EyeLidLeft"] == [pytest.approx(0.75)]  # what the classic v2 mode would send


def test_single_eye_drives_both_eyes(sender):
    single = SimpleNamespace(eye_display_id=EyeId.RIGHT)
    sender.output_osc_info(_eye(EyeId.RIGHT, 0.0, x=0.5, squeeze=0.3), single, NOT_INVERTED)
    sent = wire(sender.client)
    for side in ("Left", "Right"):
        assert sent[V2 + f"EyeOpen{side}"] == [0.0] and sent[V2 + f"EyeWide{side}"] == [0.0]
        assert sent[V2 + f"Eye{side}X"] == [0.5]
        assert sent[V2 + f"EyeSquint{side}"] == [pytest.approx(0.3)]


def test_two_eye_mode_mirrors_the_only_reporting_eye_until_the_other_shows_up(sender):
    both = SimpleNamespace(eye_display_id=EyeId.BOTH)
    sender.output_osc_info(_eye(EyeId.RIGHT, 0.75, x=0.5), both, NOT_INVERTED)
    sender.output_eyebrow_info(EyeId.RIGHT, 1.0, both)
    left, right = sender.data.eye.left, sender.data.eye.right
    assert left.gaze_x == right.gaze_x == 0.5
    assert sender.data.shapes["BrowInnerUpLeft"] == sender.data.shapes["BrowInnerUpRight"] == 1.0

    sender.output_osc_info(_eye(EyeId.LEFT, 0.75, x=-0.2), both, NOT_INVERTED)
    sender.output_osc_info(_eye(EyeId.RIGHT, 0.75, x=0.9), both, NOT_INVERTED)
    assert (left.gaze_x, right.gaze_x) == (-0.2, 0.9)


@pytest.mark.parametrize("invert", [False, True])
@pytest.mark.parametrize(
    "blink, closed_amount",
    [(0.0, 1.0), (0.75, 0.0)],  # raw lid: 0 closed, 0.75 normally open
)
def test_native_eyes_closed_amount_ignores_the_invert_setting(sender, invert, blink, closed_amount):
    """/tracking/eye/EyesClosedAmount and /tracking/face/v1 EyeClosed* mean 1 = closed in
    VRChat; osc_invert_eye_close is for avatar parameters only (the classic native
    sender ignores it too). Avatar openness still honours it."""
    sender.client._dispatch("/avatar/avatarfullfacetracking", [True])
    config = SimpleNamespace(osc_invert_eye_close=invert)
    sender.output_osc_info(_eye(EyeId.LEFT, blink), BOTH, config)
    sender.output_osc_info(_eye(EyeId.RIGHT, blink), BOTH, config)

    sent = wire(sender.client)
    assert sent[CLOSED_AMOUNT] == [pytest.approx(closed_amount)]
    face = sent[FACE][0]
    for key in ("EyeClosedLeft", "EyeClosedRight"):
        assert face[FACE_V1_KEYS.index(key)] == round(closed_amount * 255)
    avatar_lid = 1.0 - blink if invert else blink
    expected_open = min(avatar_lid / 0.75, 1.0)
    assert sent[V2 + "EyeOpenLeft"] == [pytest.approx(expected_open)]
    assert sent[V2 + "EyeOpenRight"] == [pytest.approx(expected_open)]


def test_non_finite_eye_values_hold_the_last_good_ones(sender):
    inverted = SimpleNamespace(osc_invert_eye_close=True)
    sender.output_osc_info(_eye(EyeId.LEFT, 0.1, x=0.2, y=0.1, squeeze=0.3), BOTH, inverted)
    eye, shapes = sender.data.eye.left, sender.data.shapes
    before = (eye.gaze, eye.openness, eye.native_openness, eye.pupil_diameter_mm, shapes["EyeWideLeft"])
    nan = float("nan")
    bad = _eye(EyeId.LEFT, nan, x=nan, y=float("inf"), pupil_dilation=nan, squeeze=nan)
    sender.output_osc_info(bad, BOTH, inverted)
    assert (eye.gaze, eye.openness, eye.native_openness, eye.pupil_diameter_mm, shapes["EyeWideLeft"]) == before
    assert shapes["EyeSquintLeft"] == 0.3


def test_eye_samples_are_ignored_until_started():
    sender = PyVRCFTSender()
    sender.output_osc_info(_eye(EyeId.LEFT, 0.0), BOTH, NOT_INVERTED)
    sender.output_eyebrow_info(EyeId.LEFT, 1.0, BOTH)
    assert sender.data.eye.left.openness == 1.0 and sender.data.shapes["BrowInnerUpLeft"] == 0.0


# --------------------------------------------------------------------- brows


@pytest.mark.parametrize(
    "brow, expr, up, down",
    [(0.0, -1.0, 0.0, 1.0), (0.5, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.0), (0.25, -0.5, 0.0, 0.5)],
)
def test_brow_reaches_both_ends(sender, brow, expr, up, down):
    sender.output_eyebrow_info(EyeId.LEFT, brow, BOTH)
    sender.output_eyebrow_info(EyeId.RIGHT, brow, BOTH)
    sent = wire(sender.client)
    assert sent[V2 + "BrowExpression"] == [pytest.approx(expr)]
    assert sent[V2 + "BrowUp"] == [pytest.approx(up)]
    assert sent[V2 + "BrowDown"] == [pytest.approx(down)]


def test_single_eye_brow_drives_both_sides_and_nan_holds(sender):
    single = SimpleNamespace(eye_display_id=EyeId.LEFT)
    sender.output_eyebrow_info(EyeId.LEFT, 0.25, single)  # half lowered
    before = dict(sender.data.shapes)
    assert before["BrowLowererLeft"] == before["BrowLowererRight"] == 0.5
    sender.output_eyebrow_info(EyeId.LEFT, float("nan"), single)
    assert sender.data.shapes == before  # not a full raise


# ------------------------------------------------------------------- start


@pytest.mark.parametrize(
    "overrides, recv_port",
    [
        ({}, 9001),
        ({"gui_ROSC": True}, 0),  # EyeTrackVR's own receiver owns the port
        ({"gui_osc_receiver_port": "abc"}, 0),
        ({"gui_osc_receiver_port": 70000}, 0),
    ],
)
def test_start_builds_the_client_from_settings(eyetrack_settings_config, overrides, recv_port):
    settings = eyetrack_settings_config
    settings.gui_pyvrcft_native_face = False
    for key, value in overrides.items():
        setattr(settings, key, value)
    sender = PyVRCFTSender()
    with mock.patch.object(VRCFTClient, "start"):
        sender.start(settings, send_host="10.0.0.5")
    client = sender.client
    assert (client.send_host, client.send_port, client.recv_port) == ("10.0.0.5", settings.gui_osc_port, recv_port)
    assert client.native_face is False
    assert (sender.data.gaze_yaw_max_deg, sender.data.gaze_pitch_up_deg) == (
        settings.gui_gaze_yaw_max_deg,
        settings.gui_gaze_pitch_up_deg,
    )
    with mock.patch.object(VRCFTClient, "stop"):
        sender.stop()
    assert sender.client is None
