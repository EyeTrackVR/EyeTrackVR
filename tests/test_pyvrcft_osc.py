"""pyVRCFT's OSC 1.0 codec (pyvrcft/osc.py): what goes on the wire to VRChat, and
a parser that never hangs or raises on hostile packets (it runs on the receive thread)."""

import random
import struct
import threading

import pytest

from pyvrcft import osc as pyosc

FACE = "/tracking/face/v1"
VALID_MSG = pyosc.encode_message("/avatar/change", ["avtr_x"])
HEADER = pyosc.BUNDLE_HEADER + pyosc.IMMEDIATELY


def test_every_argument_type_round_trips():
    args = [0.5, -3, "avtr_x", True, False, b"\x01\x02\x03"]
    encoded = pyosc.encode_message("/a/b", args)
    assert encoded[8:16] == b",fisTFb\x00"  # address "/a/b\0" padded to 8, then the tags
    assert len(encoded) % 4 == 0
    assert pyosc.parse(encoded) == [("/a/b", args)]


def test_unsupported_argument_type_raises():
    with pytest.raises(TypeError):
        pyosc.encode_message("/a", [None])


def test_doubles_are_read_and_unknown_tags_keep_earlier_args():
    double = pyosc._osc_string("/d") + pyosc._osc_string(",dfX") + struct.pack(">df", 2.5, 1.0) + b"\x00" * 4
    assert pyosc.parse(double) == [("/d", [2.5, 1.0])]


def test_blob_encodes_size_and_padding_and_round_trips():
    payload = bytes(range(102))
    encoded = pyosc.encode_message(FACE, [payload])
    # address(20) + ",b\0\0"(4) + int32 size(4) + 102 data + 2 pad
    assert len(encoded) == 20 + 4 + 4 + 104
    assert encoded[20:24] == b",b\x00\x00"
    assert pyosc.parse(encoded) == [(FACE, [payload])]


def test_blob_with_bad_size_is_dropped_not_raised():
    encoded = bytearray(pyosc.encode_message(FACE, [b"\x01\x02"]))
    encoded[24:28] = (999).to_bytes(4, "big")
    assert pyosc.parse(bytes(encoded)) == [(FACE, [])]


def test_bundles_split_at_the_send_buffer_size():
    messages = [pyosc.encode_message(f"/avatar/parameters/p{i:03}", [float(i)]) for i in range(300)]
    bundles = pyosc.pack_bundles(messages, max_size=1024)
    assert len(bundles) > 1 and all(len(b) <= 1024 for b in bundles)
    parsed = [m for b in bundles for m in pyosc.parse(b)]
    assert parsed == [(f"/avatar/parameters/p{i:03}", [float(i)]) for i in range(300)]
    assert pyosc.pack_bundles([]) == []


def _parse_with_timeout(data, timeout=2.0):
    result = {}

    def target():
        try:
            result["out"] = pyosc.parse(data)
        except BaseException as exc:  # noqa
            result["exc"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    assert not t.is_alive(), "parse() did not terminate"
    assert "exc" not in result, result.get("exc")
    return result["out"]


@pytest.mark.parametrize(
    "data, expected",
    [
        (HEADER + struct.pack(">i", -12) + b"\x00" * 16, []),
        (HEADER + struct.pack(">i", -4) + b"\x00" * 4, []),
        (HEADER + struct.pack(">i", 0) * 8, []),
        (HEADER + struct.pack(">i", 4096) + VALID_MSG, []),  # size past end
        (
            HEADER + struct.pack(">i", len(VALID_MSG)) + VALID_MSG + struct.pack(">i", -8) + b"\x00" * 8,
            [("/avatar/change", ["avtr_x"])],
        ),
        (HEADER + struct.pack(">i", len(VALID_MSG)) + VALID_MSG, [("/avatar/change", ["avtr_x"])]),
        (b"no-slash\x00\x00\x00\x00,f\x00\x00", []),
        (b"/unterminated", []),
    ],
)
def test_malformed_packet_parse_terminates(data, expected):
    assert _parse_with_timeout(data) == expected


def test_parse_random_garbage_never_hangs_or_raises():
    rng = random.Random(1234)
    packets = []
    for _ in range(500):
        body = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 64)))
        packets += [HEADER + body, body]
    errors = []

    def target():
        for data in packets:
            try:
                pyosc.parse(data)
            except BaseException as exc:  # noqa
                errors.append((data, exc))

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(5.0)
    assert not t.is_alive(), "parse() did not terminate on random input"
    assert errors == []
