"""pyVRCFT sender: EyeTrackVR's v2/EyeLid-scale lid value -> UE openness + EyeWide."""

from types import SimpleNamespace

import pytest

from eye import EyeId
from osc.osc_message import OSCMessage, OSCMessageType
from osc.pyvrcft_sender import PyVRCFTSender, lid_to_unified
from pyvrcft import UnifiedTrackingData, compute_outputs


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


def _sender():
    sender = PyVRCFTSender.__new__(PyVRCFTSender)
    sender.data = UnifiedTrackingData()
    sender.client = SimpleNamespace(update_tracking=lambda data: None)
    sender.is_single_eye = False
    return sender


def _send(sender, eye_id, blink, invert=False, display_id=EyeId.BOTH):
    info = SimpleNamespace(x=0.0, y=0.0, blink=blink, squeeze=0.0, pupil_dilation=0.5)
    sender.output_osc_info(
        OSCMessage(OSCMessageType.EYE_INFO, data=(eye_id, info)),
        SimpleNamespace(eye_display_id=display_id),
        SimpleNamespace(osc_invert_eye_close=invert),
    )


def test_normal_open_is_fully_open_and_wide_drives_eyewide():
    sender = _sender()
    _send(sender, EyeId.LEFT, 0.75)
    _send(sender, EyeId.RIGHT, 0.95)
    assert sender.data.eye.left.openness == pytest.approx(1.0)
    assert sender.data.shapes["EyeWideLeft"] == pytest.approx(0.0)
    assert sender.data.eye.right.openness == pytest.approx(1.0)
    assert sender.data.shapes["EyeWideRight"] == pytest.approx(1.0)


def test_closed_eye_is_zero():
    sender = _sender()
    _send(sender, EyeId.LEFT, 0.0)
    assert sender.data.eye.left.openness == 0.0
    assert sender.data.shapes["EyeWideLeft"] == 0.0


def test_nan_lid_holds_last_values():
    sender = _sender()
    _send(sender, EyeId.LEFT, 0.9)
    before = (sender.data.eye.left.openness, sender.data.shapes["EyeWideLeft"])
    _send(sender, EyeId.LEFT, float("nan"))
    assert (sender.data.eye.left.openness, sender.data.shapes["EyeWideLeft"]) == before
