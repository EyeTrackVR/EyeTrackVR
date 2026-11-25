"""pyVRCFT's Unified Expressions pipeline (pyvrcft/expressions.py): the v2 and
legacy v1 parameter values and VRChat's native eye and /tracking/face/v1 payloads
computed from one tracking frame."""

import pytest

from pyvrcft import FACE_V1_KEYS, UnifiedTrackingData, compute_face_v1, compute_outputs
from pyvrcft.avatar import AvatarParameter
from pyvrcft.expressions import (
    ShapeWeights,
    compute_legacy_outputs,
    native_eyelids_relevant,
    native_gaze_relevant,
)


def _byte(name, payload):
    return payload[FACE_V1_KEYS.index(name)]


def test_unknown_shape_names_fail_loudly():
    weights = ShapeWeights()
    assert weights["JawOpen"] == 0.0
    with pytest.raises(KeyError):
        weights["JawOpn"] = 1.0
    with pytest.raises(KeyError):
        weights["JawOpn"]


# ------------------------------------------------------------- eyes, v2 / v1


@pytest.mark.parametrize(
    "openness, wide, lid",
    [(0.0, 0.0, 0.0), (0.5, 0.0, 0.375), (1.0, 0.0, 0.75), (1.0, 1.0, 1.0)],
)
def test_v2_eyelid_packs_openness_and_widen(openness, wide, lid):
    data = UnifiedTrackingData()
    data.eye.left.openness = data.eye.right.openness = openness
    data.shapes["EyeWideLeft"] = data.shapes["EyeWideRight"] = wide
    out, native = compute_outputs(data)
    assert out["v2/EyeLidLeft"] == out["v2/EyeLid"] == pytest.approx(lid)
    assert out["v2/EyeOpenLeft"] == pytest.approx(openness)
    assert out["v2/EyeClosed"] == pytest.approx(1 - openness)
    assert native["/tracking/eye/EyesClosedAmount"] == (pytest.approx(1 - openness),)


@pytest.mark.parametrize(
    "openness, wide, squint, expanded, squeeze",
    [
        (1.0, 0.0, 1.0, 0.8, 0.8),  # normal open sits at 0.8; an open eye isn't squeezed
        (1.0, 1.0, 0.0, 1.0, 1.0),  # full widen reaches 1
        (0.5, 0.0, 1.0, 0.4, 0.4 - (1 - 0.5**0.15)),  # squint bites as the eye closes
        (0.0, 0.0, 1.0, 0.0, -1.0),
    ],
)
def test_legacy_v1_lids_use_sranipal_packing(openness, wide, squint, expanded, squeeze):
    data = UnifiedTrackingData()
    data.eye.left.openness = openness
    data.shapes["EyeWideLeft"] = wide
    data.shapes["EyeSquintLeft"] = squint
    out = compute_legacy_outputs(data)
    assert out["LeftEyeLidExpanded"] == pytest.approx(expanded)
    assert out["LeftEyeLidExpandedSqueeze"] == pytest.approx(squeeze)
    assert out["LeftEyeLid"] == openness
    assert (out["LeftEyeWiden"], out["LeftEyeSqueeze"]) == (wide, squint)
    assert out["EyesWiden"] == wide and out["EyesSqueeze"] == squint / 2


def test_gaze_is_per_eye_and_combined():
    data = UnifiedTrackingData()
    data.eye.left.gaze = (-0.4, 0.2)
    data.eye.right.gaze = (0.2, 0.4)
    out, _ = compute_outputs(data)
    legacy = compute_legacy_outputs(data)
    assert (out["v2/EyeLeftX"], out["v2/EyeRightY"]) == (-0.4, 0.4)
    assert (out["v2/EyeX"], out["v2/EyeY"]) == pytest.approx((-0.1, 0.3))
    assert (legacy["EyesX"], legacy["CombinedEyeY"], legacy["RightEyeX"]) == pytest.approx((-0.1, 0.3, 0.2))


def test_native_pitch_yaw_follows_the_configured_fov():
    data = UnifiedTrackingData()
    data.eye.left.gaze = data.eye.right.gaze = (1.0, 1.0)  # full right, full up
    _, native = compute_outputs(data)
    pitch, yaw = native["/tracking/eye/LeftRightPitchYaw"][:2]
    assert (pitch, yaw) == pytest.approx((-45.0, 45.0))  # VRCFT default: gaze is a tangent
    data.gaze_yaw_max_deg, data.gaze_pitch_up_deg, data.gaze_pitch_down_deg = 40.0, 15.0, 30.0
    _, native = compute_outputs(data)
    assert native["/tracking/eye/LeftRightPitchYaw"][:2] == pytest.approx((-15.0, 40.0))
    data.eye.left.gaze = (0.0, -1.0)  # full down uses the down cap
    _, native = compute_outputs(data)
    assert native["/tracking/eye/LeftRightPitchYaw"][0] == pytest.approx(30.0)


def test_avatars_with_their_own_eye_params_get_no_native_eye_endpoints():
    def params(*names):
        return [AvatarParameter(n, "/avatar/parameters/FT/v2/" + n, float) for n in names]

    assert native_gaze_relevant(params("JawOpen")) and native_eyelids_relevant(params("JawOpen"))
    assert not native_gaze_relevant(params("EyeLeftX"))
    assert native_eyelids_relevant(params("EyeLeftX"))
    assert not native_eyelids_relevant(params("EyeLidLeft"))
    assert not native_eyelids_relevant(params("EyeOpenRight"))


def test_brow_shapes_drive_the_compacted_brow_params():
    data = UnifiedTrackingData()
    for side in ("Left", "Right"):
        data.shapes[f"BrowInnerUp{side}"] = data.shapes[f"BrowOuterUp{side}"] = 1.0
    out, _ = compute_outputs(data)
    assert (out["v2/BrowExpression"], out["v2/BrowUp"], out["v2/BrowDown"]) == pytest.approx((1.0, 1.0, 0.0))
    data = UnifiedTrackingData()
    for side in ("Left", "Right"):
        data.shapes[f"BrowLowerer{side}"] = data.shapes[f"BrowPinch{side}"] = 1.0
    out, _ = compute_outputs(data)
    assert (out["v2/BrowExpression"], out["v2/BrowUp"], out["v2/BrowDown"]) == pytest.approx((-1.0, 0.0, 1.0))


# ----------------------------------------------------------- /tracking/face/v1


def test_key_order_matches_vrchat_docs():
    assert len(FACE_V1_KEYS) == 102
    assert FACE_V1_KEYS[0] == "EyeLookOutRight"
    assert FACE_V1_KEYS[8:10] == ("EyeClosedRight", "EyeClosedLeft")
    assert FACE_V1_KEYS.index("JawOpen") == 36  # the docs' worked example
    assert FACE_V1_KEYS[-1] == "NeckFlexLeft"


def test_neutral_frame_is_open_eyes_and_zeros():
    payload = compute_face_v1(UnifiedTrackingData())
    assert payload == bytes(102)


def test_face_v1_is_left_out_when_not_wanted():
    _, native = compute_outputs(UnifiedTrackingData(), face_v1=False)
    assert "/tracking/face/v1" not in native


def test_gaze_splits_into_look_halves_per_eye():
    data = UnifiedTrackingData()
    for eye in (data.eye.left, data.eye.right):
        eye.gaze = (1.0, -0.5)  # right and down
    p = compute_face_v1(data)
    # Looking right: right eye looks out, left eye looks in.
    assert _byte("EyeLookOutRight", p) == 255 and _byte("EyeLookInRight", p) == 0
    assert _byte("EyeLookInLeft", p) == 255 and _byte("EyeLookOutLeft", p) == 0
    assert _byte("EyeLookDownRight", p) == _byte("EyeLookDownLeft", p) == 128
    assert _byte("EyeLookUpRight", p) == _byte("EyeLookUpLeft", p) == 0


def test_openness_and_shapes_map_through():
    data = UnifiedTrackingData()
    data.eye.left.openness = 0.0
    data.eye.right.openness = 0.6
    data.shapes["JawOpen"] = 1.0
    data.shapes["EyeSquintLeft"] = 2.0  # clamped
    data.shapes["BrowInnerUpRight"] = -1.0  # clamped
    p = compute_face_v1(data)
    assert _byte("EyeClosedLeft", p) == 255
    assert _byte("EyeClosedRight", p) == 102
    assert p[36] == 255
    assert _byte("EyeSquintLeft", p) == 255
    assert _byte("BrowInnerUpRight", p) == 0


def test_native_openness_overrides_openness_for_native_endpoints_only():
    data = UnifiedTrackingData()
    data.eye.left.openness = data.eye.right.openness = 1.0  # what avatar params see
    data.eye.left.native_openness = data.eye.right.native_openness = 0.0
    out, native = compute_outputs(data)
    assert out["v2/EyeOpen"] == 1.0
    assert native["/tracking/eye/EyesClosedAmount"] == (1.0,)
    assert _byte("EyeClosedLeft", native["/tracking/face/v1"][0]) == 255


def test_non_finite_values_become_zero():
    data = UnifiedTrackingData()
    data.eye.right.gaze = (float("nan"), float("inf"))
    p = compute_face_v1(data)
    assert _byte("EyeLookOutRight", p) == 0
    assert _byte("EyeLookUpRight", p) == 0


def test_pupil_drives_dilation_above_midpoint_and_constrict_below():
    data = UnifiedTrackingData()
    # Running max/min (VRCFT updates the min only below the current max).
    for mm in (6.0, 2.0):
        data.eye.left.pupil_diameter_mm = data.eye.right.pupil_diameter_mm = mm
        data.eye.combined()
    data.eye.left.pupil_diameter_mm = data.eye.right.pupil_diameter_mm = 5.0  # 0.75
    p = compute_face_v1(data)
    assert _byte("EyeDilationLeft", p) == _byte("EyeDilationRight", p) == 128
    assert _byte("EyeConstrictLeft", p) == 0
    data.eye.left.pupil_diameter_mm = data.eye.right.pupil_diameter_mm = 3.0  # 0.25
    p = compute_face_v1(data)
    assert _byte("EyeConstrictLeft", p) == _byte("EyeConstrictRight", p) == 128
    assert _byte("EyeDilationLeft", p) == 0
    assert compute_outputs(data)[0]["v2/PupilDilation"] == pytest.approx(0.25)
