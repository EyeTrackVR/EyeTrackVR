"""Parameter resolution + encoding, replicating VRCFT's semantics.

For each logical VRCFT parameter name (e.g. "v2/JawOpen") an avatar may
declare any combination of:

  * a float parameter whose address ends in "/v2/JawOpen"   -> raw float
  * a bool parameter with that same suffix                  -> value < 0.5
  * bool "bit" parameters "v2/JawOpen1", "...2", "...4" ... -> binary encoding
  * a bool "v2/JawOpenNegative"                             -> sign bit

We match by case-sensitive address suffix with VRCFT's exact regex (the
negative lookbehind stops a legacy name like "JawOpen" from hijacking
"FT/v2/JawOpen"), adopt the avatar's full address, and only emit variants
the avatar declares.
"""

from __future__ import annotations

import re

DEFAULT_PREFIX = "/avatar/parameters/"


def suffix_regex(name: str) -> re.Pattern:
    # C# pattern uses a negative lookbehind. Python needs a fixed width lookbehind.
    # (?<!v\d) covers the single-digit version prefixes in actual use.
    esc = re.escape(name)
    return re.compile(r"(?<!v\d)(/" + esc + r")$|^(" + esc + r")$")


def binary_bits_regex(name: str) -> re.Pattern:
    esc = re.escape(name)
    return re.compile(r"(?<!v\d)/" + esc + r"\d+$|^" + esc + r"\d+$")


def _binary_shift(weight: int):
    """Return the bit shift for a power-of-two weight (1->0, 2->1, 4->2 ...),
    or None if the weight isn't a power of two (VRCFT's GetBinarySteps)."""
    if weight < 1 or weight & (weight - 1):
        return None
    return weight.bit_length() - 1


class OutputSlot:
    """One concrete OSC parameter derived from a logical float value.
    Encodes, deduplicates (send-on-change), and remembers its address."""

    __slots__ = ("address", "_last")

    def __init__(self, address: str):
        self.address = address
        self._last = None

    def encode(self, value: float):
        raise NotImplementedError

    def update(self, value: float):
        """Return the wire value if it changed since last send, else None."""
        wire = self.encode(value)
        if wire == self._last:
            return None
        self._last = wire
        return wire


class FloatSlot(OutputSlot):
    def encode(self, value: float):
        return float(value)


class BoolSlot(OutputSlot):
    """VRCFT's EParam bool variant: true when value < threshold."""

    __slots__ = ("threshold",)

    def __init__(self, address: str, threshold: float = 0.5):
        super().__init__(address)
        self.threshold = threshold

    def encode(self, value: float):
        return value < self.threshold


class BinaryBitSlot(OutputSlot):
    """One bit of VRCFT's binary decomposition (param "<name><2^shift>")."""

    __slots__ = ("shift", "max_int", "has_negative")

    def __init__(self, address: str, shift: int, max_int: int, has_negative: bool):
        super().__init__(address)
        self.shift = shift
        self.max_int = max_int
        self.has_negative = has_negative

    def encode(self, value: float):
        # Exact port of BinaryBaseParameter.ProcessBinary
        if not self.has_negative and value < 0:
            return False
        value = abs(value)
        if value > 0.99999:
            return True
        return (int(value * self.max_int) >> self.shift) & 1 == 1


class NegativeSlot(OutputSlot):
    def encode(self, value: float):
        return value < 0


def resolve_slots(name: str, avatar_params, bool_threshold: float = 0.5):
    """Build the output slots for one logical param against an avatar's
    declared parameters. Returns [] if the avatar doesn't use this param."""
    slots = []
    exact = suffix_regex(name)

    for p in avatar_params:
        if not exact.search(p.address):
            continue
        if p.type is float:
            slots.append(FloatSlot(p.address))
        elif p.type is bool:
            slots.append(BoolSlot(p.address, bool_threshold))

    # Binary decomposition: collect valid power-of-two bit params.
    bits_pat = binary_bits_regex(name)
    bits = {}  # shift -> address
    for p in avatar_params:
        if p.type is not bool or not bits_pat.search(p.address):
            continue
        digits = re.search(r"(\d+)$", p.name)
        if not digits:
            continue
        shift = _binary_shift(int(digits.group(1)))
        if shift is not None:
            bits.setdefault(shift, p.address)

    negative_pat = suffix_regex(name + "Negative")
    negative = next(
        (p for p in avatar_params if p.type is bool and negative_pat.search(p.address)), None
    )

    if bits:
        max_int = 2 ** len(bits)
        for shift, address in sorted(bits.items()):
            slots.append(BinaryBitSlot(address, shift, max_int, negative is not None))
    if negative is not None:
        slots.append(NegativeSlot(negative.address))

    return slots
