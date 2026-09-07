"""Unified Expressions pipeline that fully ports the VRCFT parameter table.

Feed raw tracking data (UE shape weights + per-eye gaze/openness/pupil +
head pose) into :class:`UnifiedTrackingData`, and :func:`compute_outputs`
produces the complete v2 parameter set VRCFT would send, including every base shape,
the 8 "simple" blends, and all combined/compacted shapes, plus the
VRChat-native eye endpoints.

Formulas are ported 1:1 from:
  VRCFaceTracking.Core/Params/Expressions/UnifiedExpressionsParameters.cs
  VRCFaceTracking.Core/Params/Expressions/UnifiedSimpleExpressions.cs
  VRCFaceTracking.Core/Params/Expressions/UnifiedHeadParameters.cs
  VRCFaceTracking.Core/Params/Data/UnifiedData.cs   (eye Combined())
  VRCFaceTracking.Core/Types/Vector2.cs             (gaze -> pitch/yaw)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# The UnifiedExpressions enum (VRCFT's ~70 base shapes), same names.
# ("Max" is a C# sentinel, not a real shape, and is omitted.)
UNIFIED_EXPRESSIONS = (
    # Eye
    "EyeSquintRight", "EyeSquintLeft", "EyeWideRight", "EyeWideLeft",
    # Eyebrow
    "BrowPinchRight", "BrowPinchLeft", "BrowLowererRight", "BrowLowererLeft",
    "BrowInnerUpRight", "BrowInnerUpLeft", "BrowOuterUpRight", "BrowOuterUpLeft",
    # Nose
    "NasalDilationRight", "NasalDilationLeft", "NasalConstrictRight", "NasalConstrictLeft",
    # Cheek
    "CheekSquintRight", "CheekSquintLeft", "CheekPuffRight", "CheekPuffLeft",
    "CheekSuckRight", "CheekSuckLeft",
    # Jaw
    "JawOpen", "JawRight", "JawLeft", "JawForward", "JawBackward",
    "JawClench", "JawMandibleRaise", "MouthClosed",
    # Lip push/pull
    "LipSuckUpperRight", "LipSuckUpperLeft", "LipSuckLowerRight", "LipSuckLowerLeft",
    "LipSuckCornerRight", "LipSuckCornerLeft",
    "LipFunnelUpperRight", "LipFunnelUpperLeft", "LipFunnelLowerRight", "LipFunnelLowerLeft",
    "LipPuckerUpperRight", "LipPuckerUpperLeft", "LipPuckerLowerRight", "LipPuckerLowerLeft",
    # Upper lip raiser
    "MouthUpperUpRight", "MouthUpperUpLeft", "MouthUpperDeepenRight", "MouthUpperDeepenLeft",
    "NoseSneerRight", "NoseSneerLeft",
    # Lower lip depressor
    "MouthLowerDownRight", "MouthLowerDownLeft",
    # Mouth direction
    "MouthUpperRight", "MouthUpperLeft", "MouthLowerRight", "MouthLowerLeft",
    # Smile
    "MouthCornerPullRight", "MouthCornerPullLeft",
    "MouthCornerSlantRight", "MouthCornerSlantLeft",
    # Sad
    "MouthFrownRight", "MouthFrownLeft", "MouthStretchRight", "MouthStretchLeft",
    "MouthDimpleRight", "MouthDimpleLeft",
    "MouthRaiserUpper", "MouthRaiserLower",
    "MouthPressRight", "MouthPressLeft", "MouthTightenerRight", "MouthTightenerLeft",
    # Tongue
    "TongueOut", "TongueUp", "TongueDown", "TongueRight", "TongueLeft",
    "TongueRoll", "TongueBendDown", "TongueCurlUp", "TongueSquish", "TongueFlat",
    "TongueTwistRight", "TongueTwistLeft",
    # Throat/neck
    "SoftPalateClose", "ThroatSwallow", "NeckFlexRight", "NeckFlexLeft",
)

_UNIFIED_EXPRESSION_SET = frozenset(UNIFIED_EXPRESSIONS)

SIMPLE_EXPRESSIONS = (
    "BrowUpRight", "BrowUpLeft", "BrowDownRight", "BrowDownLeft",
    "MouthSmileRight", "MouthSmileLeft", "MouthSadRight", "MouthSadLeft",
)


class ShapeWeights(dict):
    """UE shape name -> float weight. Unset shapes read as 0.0; setting an
    unknown name raises immediately so typos don't silently do nothing."""

    def __missing__(self, key):
        if key not in _UNIFIED_EXPRESSION_SET:
            raise KeyError(f"unknown Unified Expression shape: {key!r}")
        return 0.0

    def __setitem__(self, key, value):
        if key not in _UNIFIED_EXPRESSION_SET:
            raise KeyError(f"unknown Unified Expression shape: {key!r}")
        super().__setitem__(key, float(value))


@dataclass
class SingleEyeData:
    """One eye. Gaze is VRCFT's normalized vector: x right, y up, [-1, 1]."""

    gaze_x: float = 0.0
    gaze_y: float = 0.0
    pupil_diameter_mm: float = 0.0
    openness: float = 1.0

    @property
    def gaze(self):
        return (self.gaze_x, self.gaze_y)

    @gaze.setter
    def gaze(self, value):
        self.gaze_x, self.gaze_y = value

    def gaze_pitch(self) -> float:
        """Degrees, positive looking down (Vector2.ToPitch)."""
        return -math.degrees(math.atan(self.gaze_y))

    def gaze_yaw(self) -> float:
        """Degrees, positive looking right (Vector2.ToYaw)."""
        return math.degrees(math.atan(self.gaze_x))


class EyeData:
    """Both eyes plus VRCFT's stateful pupil-dilation normalization
    (UnifiedEyeData.Combined): running min/max of the average diameter,
    updated only on frames where a diameter actually changed."""

    def __init__(self):
        self.left = SingleEyeData()
        self.right = SingleEyeData()
        self._max_dilation = 0.0
        self._min_dilation = 999.0
        self._left_diameter = 0.0
        self._right_diameter = 0.0

    def combined(self) -> SingleEyeData:
        average = (self.left.pupil_diameter_mm + self.right.pupil_diameter_mm) / 2.0
        left_diff = self._left_diameter != self.left.pupil_diameter_mm
        right_diff = self._right_diameter != self.right.pupil_diameter_mm

        if left_diff or right_diff:
            if average > self._max_dilation:
                self._max_dilation = average
            elif average < self._min_dilation:
                self._min_dilation = average
        if left_diff:
            self._left_diameter = self.left.pupil_diameter_mm
        if right_diff:
            self._right_diameter = self.right.pupil_diameter_mm

        span = self._max_dilation - self._min_dilation
        normalized = (average - self._min_dilation) / span if span > 0 else 0.5

        return SingleEyeData(
            gaze_x=(self.left.gaze_x + self.right.gaze_x) / 2.0,
            gaze_y=(self.left.gaze_y + self.right.gaze_y) / 2.0,
            openness=(self.left.openness + self.right.openness) / 2.0,
            pupil_diameter_mm=normalized,
        )


@dataclass
class HeadData:
    """Normalized [-1, 1]: yaw + = right, pitch + = down, roll + = tilt left;
    positions are ~meters/2 from origin (see UnifiedHeadData docs)."""

    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0


class UnifiedTrackingData:
    """Python equivalent of VRCFT's UnifiedTrackingData: fill in whatever
    your tracker produces, then pass to VRCFTClient.update_tracking()."""

    def __init__(self):
        self.shapes = ShapeWeights()
        self.eye = EyeData()
        self.head = HeadData()
        # None = don't send the corresponding *TrackingActive bool at all
        # (VRCFT only sends these once the module is initialized).
        self.eye_tracking_active = None
        self.expression_tracking_active = None
        # Optional true-FOV angular scale for the native /tracking/eye/
        # LeftRightPitchYaw endpoint. By default (all None) a unit gaze is
        # treated as a tangent, so full gaze (+-1) maps to +-45 deg. When a
        # tracker feeds *normalized* gaze whose +-1 means "edge of the tracked
        # FOV" (e.g. EyeTrackVR), set these to the real FOV half-angles and the
        # native output becomes atan(gaze * tan(max)) -> full gaze reflects the
        # actual headset/calibration FOV instead of 45 deg. Yaw is symmetric;
        # pitch caps are asymmetric (up vs down) to match typical oculomotor
        # range. Only the native PitchYaw endpoint uses these; the normalized
        # v2/v1 gaze params are unaffected.
        self.gaze_yaw_max_deg = None
        self.gaze_pitch_up_deg = None
        self.gaze_pitch_down_deg = None


# --------------------------------------------------------------------------
# Simple expressions (UnifiedSimplifier.ExpressionMap)

def compute_simple(w: ShapeWeights) -> dict:
    return {
        "BrowUpRight": w["BrowOuterUpRight"] * 0.60 + w["BrowInnerUpRight"] * 0.40,
        "BrowUpLeft": w["BrowOuterUpLeft"] * 0.60 + w["BrowInnerUpLeft"] * 0.40,
        "BrowDownRight": w["BrowLowererRight"] * 0.75 + w["BrowPinchRight"] * 0.25,
        "BrowDownLeft": w["BrowLowererLeft"] * 0.75 + w["BrowPinchLeft"] * 0.25,
        "MouthSmileRight": w["MouthCornerPullRight"] * 0.8 + w["MouthCornerSlantRight"] * 0.2,
        "MouthSmileLeft": w["MouthCornerPullLeft"] * 0.8 + w["MouthCornerSlantLeft"] * 0.2,
        "MouthSadRight": max(w["MouthFrownRight"], w["MouthStretchRight"]),
        "MouthSadLeft": max(w["MouthFrownLeft"], w["MouthStretchLeft"]),
    }


# --------------------------------------------------------------------------
# Full v2 output set (UnifiedExpressionsParameters + UnifiedHeadParameters)

def compute_outputs(data: UnifiedTrackingData):
    """Compute VRCFT's complete output for one frame.

    Returns (params, native):
      params contains {"v2/<name>": float} for every base, simple, combined, and
               head parameter (the client resolves which ones the avatar
               actually declares and how to encode them)
      native contains {"/tracking/eye/...": tuple} for VRChat-native eye endpoints
               (send these only when the avatar has no FT eye params;
               VRCFTClient.update_tracking handles that condition)
    """
    w = data.shapes
    simple = compute_simple(w)
    left, right = data.eye.left, data.eye.right
    combined = data.eye.combined()

    out = {}

    # Base shapes: v2/<EnumName> for every UnifiedExpressions member
    for name in UNIFIED_EXPRESSIONS:
        out["v2/" + name] = w[name]
    # Simple expressions are also emitted as their own v2 params
    for name, value in simple.items():
        out["v2/" + name] = value

    # --- Eye gaze
    out["v2/EyeX"] = combined.gaze_x
    out["v2/EyeY"] = combined.gaze_y
    out["v2/EyeLeftX"] = left.gaze_x
    out["v2/EyeLeftY"] = left.gaze_y
    out["v2/EyeRightX"] = right.gaze_x
    out["v2/EyeRightY"] = right.gaze_y

    # --- Pupils
    out["v2/PupilDilation"] = combined.pupil_diameter_mm  # normalized 0-1
    out["v2/PupilDiameterLeft"] = left.pupil_diameter_mm * 0.1
    out["v2/PupilDiameterRight"] = right.pupil_diameter_mm * 0.1
    out["v2/PupilDiameter"] = (left.pupil_diameter_mm + right.pupil_diameter_mm) * 0.05

    # --- Openness
    avg_open = (left.openness + right.openness) / 2.0
    out["v2/EyeOpenLeft"] = left.openness
    out["v2/EyeOpenRight"] = right.openness
    out["v2/EyeOpen"] = avg_open
    out["v2/EyeClosedLeft"] = 1 - left.openness
    out["v2/EyeClosedRight"] = 1 - right.openness
    out["v2/EyeClosed"] = 1 - avg_open

    # --- Widen / lids / squint
    out["v2/EyeWide"] = max(w["EyeWideLeft"], w["EyeWideRight"])
    out["v2/EyeLidLeft"] = left.openness * 0.75 + w["EyeWideLeft"] * 0.25
    out["v2/EyeLidRight"] = right.openness * 0.75 + w["EyeWideRight"] * 0.25
    out["v2/EyeLid"] = avg_open * 0.75 + (w["EyeWideRight"] + w["EyeWideLeft"]) / 2.0 * 0.25
    out["v2/EyeSquint"] = max(w["EyeSquintLeft"], w["EyeSquintRight"])
    out["v2/EyesSquint"] = out["v2/EyeSquint"]

    # --- Eyebrows compacted
    out["v2/BrowUp"] = (simple["BrowUpRight"] + simple["BrowUpLeft"]) * 0.5
    out["v2/BrowDown"] = (simple["BrowDownRight"] + simple["BrowDownLeft"]) * 0.5
    out["v2/BrowInnerUp"] = (w["BrowInnerUpLeft"] + w["BrowInnerUpRight"]) / 2.0
    out["v2/BrowOuterUp"] = (w["BrowOuterUpLeft"] + w["BrowOuterUpRight"]) / 2.0
    # -1 = 'Angry', +1 = 'Worried'
    out["v2/BrowExpressionRight"] = (
        min(1, w["BrowInnerUpRight"] * 0.5 + w["BrowOuterUpRight"] * 0.5)
        - simple["BrowDownRight"]
    )
    out["v2/BrowExpressionLeft"] = (
        min(1, w["BrowInnerUpLeft"] * 0.5 + w["BrowOuterUpLeft"] * 0.5)
        - simple["BrowDownLeft"]
    )
    out["v2/BrowExpression"] = (
        min(1, (w["BrowInnerUpRight"] + w["BrowOuterUpRight"]) * 0.5)
        - simple["BrowDownRight"]
        + min(1, (w["BrowInnerUpLeft"] + w["BrowOuterUpLeft"]) * 0.5)
        - simple["BrowDownLeft"]
    ) * 0.5

    # --- Jaw
    out["v2/JawX"] = w["JawRight"] - w["JawLeft"]
    out["v2/JawZ"] = w["JawForward"] - w["JawBackward"]

    # --- Cheeks
    out["v2/CheekSquint"] = (w["CheekSquintLeft"] + w["CheekSquintRight"]) / 2.0
    out["v2/CheekPuffSuckLeft"] = w["CheekPuffLeft"] - w["CheekSuckLeft"]
    out["v2/CheekPuffSuckRight"] = w["CheekPuffRight"] - w["CheekSuckRight"]
    out["v2/CheekPuffSuck"] = (
        (w["CheekPuffRight"] + w["CheekPuffLeft"]) / 2.0
        - (w["CheekSuckRight"] + w["CheekSuckLeft"]) / 2.0
    )
    out["v2/CheekSuck"] = (w["CheekSuckLeft"] + w["CheekSuckRight"]) / 2.0

    # --- Mouth direction
    out["v2/MouthUpperX"] = w["MouthUpperRight"] - w["MouthUpperLeft"]
    out["v2/MouthLowerX"] = w["MouthLowerRight"] - w["MouthLowerLeft"]
    out["v2/MouthX"] = (
        (w["MouthUpperRight"] + w["MouthLowerRight"]) / 2.0
        - (w["MouthUpperLeft"] + w["MouthLowerLeft"]) / 2.0
    )

    # --- Lips
    suck_upper = (w["LipSuckUpperRight"] + w["LipSuckUpperLeft"]) / 2.0
    suck_lower = (w["LipSuckLowerRight"] + w["LipSuckLowerLeft"]) / 2.0
    funnel_upper = (w["LipFunnelUpperRight"] + w["LipFunnelUpperLeft"]) / 2.0
    funnel_lower = (w["LipFunnelLowerRight"] + w["LipFunnelLowerLeft"]) / 2.0
    out["v2/LipSuckUpper"] = suck_upper
    out["v2/LipSuckLower"] = suck_lower
    out["v2/LipSuck"] = (suck_upper + suck_lower) / 2.0
    out["v2/LipFunnelUpper"] = funnel_upper
    out["v2/LipFunnelLower"] = funnel_lower
    out["v2/LipFunnel"] = (funnel_upper + funnel_lower) / 2.0
    out["v2/LipPuckerUpper"] = (w["LipPuckerUpperRight"] + w["LipPuckerUpperLeft"]) / 2.0
    out["v2/LipPuckerLower"] = (w["LipPuckerLowerRight"] + w["LipPuckerLowerLeft"]) / 2.0
    out["v2/LipPuckerRight"] = (w["LipPuckerUpperRight"] + w["LipPuckerLowerRight"]) / 2.0
    out["v2/LipPuckerLeft"] = (w["LipPuckerUpperLeft"] + w["LipPuckerLowerLeft"]) / 2.0
    out["v2/LipPucker"] = (
        w["LipPuckerUpperRight"] + w["LipPuckerUpperLeft"]
        + w["LipPuckerLowerRight"] + w["LipPuckerLowerLeft"]
    ) / 4.0
    # Compacted
    out["v2/LipSuckFunnelUpper"] = suck_upper - funnel_upper
    out["v2/LipSuckFunnelLower"] = suck_lower - funnel_lower
    out["v2/LipSuckFunnelLowerLeft"] = w["LipSuckLowerLeft"] - w["LipFunnelLowerLeft"]
    out["v2/LipSuckFunnelLowerRight"] = w["LipSuckLowerRight"] - w["LipFunnelLowerRight"]
    out["v2/LipSuckFunnelUpperLeft"] = w["LipSuckUpperLeft"] - w["LipFunnelUpperLeft"]
    out["v2/LipSuckFunnelUpperRight"] = w["LipSuckUpperRight"] - w["LipFunnelUpperRight"]

    # --- Mouth combined
    out["v2/MouthUpperUp"] = w["MouthUpperUpRight"] * 0.5 + w["MouthUpperUpLeft"] * 0.5
    out["v2/MouthLowerDown"] = w["MouthLowerDownRight"] * 0.5 + w["MouthLowerDownLeft"] * 0.5
    out["v2/MouthOpen"] = (
        w["MouthUpperUpRight"] * 0.25 + w["MouthUpperUpLeft"] * 0.25
        + w["MouthLowerDownRight"] * 0.25 + w["MouthLowerDownLeft"] * 0.25
    )
    out["v2/MouthStretch"] = (w["MouthStretchRight"] + w["MouthStretchLeft"]) / 2.0
    out["v2/MouthTightener"] = (w["MouthTightenerRight"] + w["MouthTightenerLeft"]) / 2.0
    out["v2/MouthPress"] = (w["MouthPressRight"] + w["MouthPressLeft"]) / 2.0
    out["v2/MouthDimple"] = (w["MouthDimpleRight"] + w["MouthDimpleLeft"]) / 2.0
    out["v2/NoseSneer"] = (w["NoseSneerRight"] + w["NoseSneerLeft"]) / 2.0
    # Compacted
    out["v2/MouthTightenerStretch"] = out["v2/MouthTightener"] - out["v2/MouthStretch"]
    out["v2/MouthTightenerStretchLeft"] = w["MouthTightenerLeft"] - w["MouthStretchLeft"]
    out["v2/MouthTightenerStretchRight"] = w["MouthTightenerRight"] - w["MouthStretchRight"]

    # --- Lip corners
    out["v2/MouthCornerYLeft"] = w["MouthCornerSlantLeft"] - w["MouthFrownLeft"]
    out["v2/MouthCornerYRight"] = w["MouthCornerSlantRight"] - w["MouthFrownRight"]
    out["v2/MouthCornerY"] = (
        w["MouthCornerSlantLeft"] - w["MouthFrownLeft"]
        + w["MouthCornerSlantRight"] - w["MouthFrownRight"]
    ) * 0.5
    out["v2/SmileFrownRight"] = simple["MouthSmileRight"] - w["MouthFrownRight"]
    out["v2/SmileFrownLeft"] = simple["MouthSmileLeft"] - w["MouthFrownLeft"]
    out["v2/SmileFrown"] = (
        simple["MouthSmileRight"] * 0.5 + simple["MouthSmileLeft"] * 0.5
        - w["MouthFrownRight"] * 0.5 - w["MouthFrownLeft"] * 0.5
    )
    out["v2/SmileSadRight"] = simple["MouthSmileRight"] - simple["MouthSadRight"]
    out["v2/SmileSadLeft"] = simple["MouthSmileLeft"] - simple["MouthSadLeft"]
    out["v2/SmileSad"] = (
        (simple["MouthSmileLeft"] + simple["MouthSmileRight"]) / 2.0
        - (simple["MouthSadLeft"] + simple["MouthSadRight"]) / 2.0
    )

    # --- Tongue
    out["v2/TongueX"] = w["TongueRight"] - w["TongueLeft"]
    out["v2/TongueY"] = w["TongueUp"] - w["TongueDown"]
    out["v2/TongueArchY"] = w["TongueCurlUp"] - w["TongueBendDown"]
    out["v2/TongueShape"] = w["TongueFlat"] - w["TongueSquish"]

    # --- Head
    out["v2/Head/Yaw"] = data.head.yaw
    out["v2/Head/Pitch"] = data.head.pitch
    out["v2/Head/Roll"] = data.head.roll
    out["v2/Head/PosX"] = data.head.pos_x
    out["v2/Head/PosY"] = data.head.pos_y
    out["v2/Head/PosZ"] = data.head.pos_z

    lp, ly = _native_pitch_yaw(left, data)
    rp, ry = _native_pitch_yaw(right, data)
    native = {
        "/tracking/eye/LeftRightPitchYaw": (lp, ly, rp, ry),
        "/tracking/eye/EyesClosedAmount": (1 - combined.openness,),
    }
    return out, native


def _native_pitch_yaw(eye: SingleEyeData, data: "UnifiedTrackingData"):
    """(pitch, yaw) degrees for one eye's native endpoint.

    Default with no FOV scale set uses VRCFT's tangent convention based on atan(gaze), so
    full normalized gaze = 45 deg. With a FOV scale set on `data`, normalized
    gaze is mapped through the real FOV half-angle: atan(gaze * tan(max)), so
    +-1 lands on the true edge angle (yaw symmetric; pitch asymmetric up/down).
    Sign/monotonicity match the plain gaze_pitch()/gaze_yaw() exactly."""
    yaw_max = data.gaze_yaw_max_deg
    if yaw_max is None:
        yaw = eye.gaze_yaw()
    else:
        yaw = math.degrees(math.atan(eye.gaze_x * math.tan(math.radians(yaw_max))))

    up, down = data.gaze_pitch_up_deg, data.gaze_pitch_down_deg
    if up is None or down is None:
        pitch = eye.gaze_pitch()
    else:
        # gaze_y is up-positive; pick the cap for the direction being looked.
        cap = up if eye.gaze_y >= 0.0 else down
        pitch = -math.degrees(math.atan(eye.gaze_y * math.tan(math.radians(cap))))
    return pitch, yaw


# --------------------------------------------------------------------------
# VRCFT v1 (legacy / SRanipal-era) eye parameters
#
# Avatars built before Unified Expressions declare a flat, non-"v2/" parameter
# set. compute_outputs covers the v2 namespace; this covers v1 so the same
# tracking frame also drives legacy avatars. The client resolves each name
# against the avatar and sends only the ones it actually declares, so emitting
# the full set alongside the v2 set (and the native endpoints) is safe.
#
# Openness is 1 = open, 0 = closed. The packed "*LidExpandedSqueeze" params are
# driven here with plain openness rather than the SRanipal widen/squeeze packing
# This matches how EyeTrackVR's own v1 output has always driven them, so v1
# avatars tuned against EyeTrackVR behave identically under this port.

def compute_legacy_outputs(data: UnifiedTrackingData) -> dict:
    """Compute VRCFT v1 (legacy) eye parameters for one frame.

    Returns {"<Name>": float} with bare (non-"v2/") logical names; feed to
    VRCFTClient.set_many(..., v2=False)."""
    w = data.shapes
    left, right = data.eye.left, data.eye.right
    # combined() is idempotent within a frame (its running min/max only moves
    # when a diameter actually changes), so calling it after compute_outputs
    # returns the same normalized pupil value without disturbing that state.
    combined = data.eye.combined()
    avg_open = (left.openness + right.openness) / 2.0

    widen_left = w["EyeWideLeft"]
    widen_right = w["EyeWideRight"]
    squint_left = w["EyeSquintLeft"]
    squint_right = w["EyeSquintRight"]

    return {
        # --- Gaze (x right, y up, [-1, 1])
        "EyesX": combined.gaze_x,
        "EyesY": combined.gaze_y,
        "CombinedEyeX": combined.gaze_x,
        "CombinedEyeY": combined.gaze_y,
        "LeftEyeX": left.gaze_x,
        "LeftEyeY": left.gaze_y,
        "RightEyeX": right.gaze_x,
        "RightEyeY": right.gaze_y,
        # --- Eyelids / openness (1 = open)
        "LeftEyeLid": left.openness,
        "RightEyeLid": right.openness,
        "CombinedEyeLid": avg_open,
        "LeftEyeLidExpanded": left.openness,
        "RightEyeLidExpanded": right.openness,
        "CombinedEyeLidExpanded": avg_open,
        "LeftEyeLidExpandedSqueeze": left.openness,
        "RightEyeLidExpandedSqueeze": right.openness,
        "CombinedEyeLidExpandedSqueeze": avg_open,
        # --- Widen / squeeze
        "LeftEyeWiden": widen_left,
        "RightEyeWiden": widen_right,
        "EyesWiden": max(widen_left, widen_right),
        "LeftEyeSqueeze": squint_left,
        "RightEyeSqueeze": squint_right,
        "EyesSqueeze": (squint_left + squint_right) / 2.0,
        # --- Pupil (normalized 0-1)
        "EyesDilation": combined.pupil_diameter_mm,
        "EyesPupilDiameter": combined.pupil_diameter_mm,
    }


# --------------------------------------------------------------------------
# Native-endpoint relevance (NativeParameter conditions)
#
# VRCFT only sends the native endpoints when the avatar has no FT eye
# params of the corresponding kind. (VRCFT additionally cross-checks that
# the matched avatar params are known VRCFT names; the name test alone is
# a close, slightly more conservative approximation.)

def native_gaze_relevant(avatar_params) -> bool:
    return not any(
        "Eye" in p.name and ("X" in p.name or "Y" in p.name) for p in avatar_params
    )


def native_eyelids_relevant(avatar_params) -> bool:
    return not any(
        "Eye" in p.name and ("Open" in p.name or "Lid" in p.name) for p in avatar_params
    )
