"""pyVRCFT parameter resolution and encoding (pyvrcft/params.py), VRCFT's rules:
which of an avatar's parameters a logical value drives, and float / bool /
binary-bit / sign-bit encoding with send-on-change."""

import pytest

from pyvrcft.avatar import AvatarParameter
from pyvrcft.params import BinaryBitSlot, BoolSlot, FloatSlot, NegativeSlot, resolve_slots

FT = "/avatar/parameters/FT/v2/"


def _params(**types):
    return [AvatarParameter(name=n, address=FT + n, type=t) for n, t in types.items()]


def _encode_all(slots, value):
    return {slot.address.rsplit("/", 1)[-1]: slot.encode(value) for slot in slots}


def test_float_and_bool_variants_take_the_avatars_own_address():
    float_slots = resolve_slots("v2/JawOpen", _params(JawOpen=float))
    assert [(type(s), s.address) for s in float_slots] == [(FloatSlot, FT + "JawOpen")]
    [bool_slot] = resolve_slots("v2/JawOpen", _params(JawOpen=bool), bool_threshold=0.3)
    assert isinstance(bool_slot, BoolSlot)
    # VRCFT's EParam bool: true below the threshold.
    assert (bool_slot.encode(0.2), bool_slot.encode(0.3)) == (True, False)


def test_suffix_match_is_exact_and_legacy_names_do_not_hijack_v2():
    params = [
        AvatarParameter("JawOpenSuffix", FT + "JawOpenSuffix", float),
        AvatarParameter("JawOpen", "/avatar/parameters/v2/JawOpen", float),
        AvatarParameter("JawOpen", "/avatar/parameters/JawOpen", float),
    ]
    assert [s.address for s in resolve_slots("v2/JawOpen", params)] == ["/avatar/parameters/v2/JawOpen"]
    # The bare legacy name must not claim ".../v2/JawOpen".
    assert [s.address for s in resolve_slots("JawOpen", params)] == ["/avatar/parameters/JawOpen"]
    assert resolve_slots("v2/JawOpen", []) == []


@pytest.mark.parametrize(
    "value, bits",
    [
        (0.0, {"JawOpen1": False, "JawOpen2": False, "JawOpen4": False}),
        (0.25, {"JawOpen1": False, "JawOpen2": True, "JawOpen4": False}),  # int(0.25 * 8) = 2
        (0.7, {"JawOpen1": True, "JawOpen2": False, "JawOpen4": True}),  # int(0.7 * 8) = 5
        (1.0, {"JawOpen1": True, "JawOpen2": True, "JawOpen4": True}),  # > 0.99999: all set
        (-0.5, {"JawOpen1": False, "JawOpen2": False, "JawOpen4": False}),  # no sign bit declared
    ],
)
def test_binary_bits_encode_the_value_as_an_integer(value, bits):
    slots = resolve_slots("v2/JawOpen", _params(JawOpen1=bool, JawOpen2=bool, JawOpen4=bool, JawOpen3=bool))
    assert all(isinstance(s, BinaryBitSlot) for s in slots)
    assert _encode_all(slots, value) == bits  # JawOpen3 is not a power of two: ignored


def test_negative_bit_carries_the_sign_and_bits_the_magnitude():
    slots = resolve_slots("v2/JawX", _params(JawX1=bool, JawX2=bool, JawXNegative=bool, JawX8=float))
    assert [type(s) for s in slots] == [BinaryBitSlot, BinaryBitSlot, NegativeSlot]
    assert _encode_all(slots, -0.5) == {"JawX1": False, "JawX2": True, "JawXNegative": True}
    assert _encode_all(slots, 0.5) == {"JawX1": False, "JawX2": True, "JawXNegative": False}


def test_slots_send_only_changes_and_skip_non_finite():
    slot = FloatSlot(FT + "EyeLeftX")
    assert slot.update(0.25) == 0.25
    assert slot.update(0.25) is None  # unchanged
    assert slot.update(float("inf")) is None  # holds 0.25
    assert slot.update(0.25) is None  # still deduped against the last good value
    bit = BinaryBitSlot(FT + "JawOpen1", 0, 8, False)
    assert bit.encode(float("nan")) is False  # int(nan * 8) would raise
    assert bit.update(float("nan")) is None
    assert bit.update(0.5) is False and bit.update(0.6) is None  # same bit: not resent
    assert bit.update(0.2) is True
