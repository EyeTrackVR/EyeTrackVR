"""Minimal OSC 1.0 codec (messages + bundles), stdlib only.

Supports the types VRChat/VRCFT actually use on the wire:
float ('f'), int ('i'), string ('s'), bool ('T'/'F').
"""

from __future__ import annotations

import struct

BUNDLE_HEADER = b"#bundle\x00"
IMMEDIATELY = struct.pack(">Q", 1)  # OSC time tag "immediately"


def _pad4(data: bytes) -> bytes:
    return data + b"\x00" * (-len(data) % 4)


def _osc_string(s: str) -> bytes:
    return _pad4(s.encode("utf-8") + b"\x00")


def encode_message(address: str, args) -> bytes:
    """Encode one OSC message. `args` is a list/tuple of values."""
    tags = ","
    payload = b""
    for arg in args:
        if isinstance(arg, bool):  # must precede int check
            tags += "T" if arg else "F"
        elif isinstance(arg, float):
            tags += "f"
            payload += struct.pack(">f", arg)
        elif isinstance(arg, int):
            tags += "i"
            payload += struct.pack(">i", arg)
        elif isinstance(arg, str):
            tags += "s"
            payload += _osc_string(arg)
        else:
            raise TypeError(f"unsupported OSC arg type: {type(arg)!r}")
    return _osc_string(address) + _osc_string(tags) + payload


def encode_bundle(encoded_messages) -> bytes:
    """Wrap already-encoded messages in a #bundle with the 'immediately' tag."""
    out = BUNDLE_HEADER + IMMEDIATELY
    for msg in encoded_messages:
        out += struct.pack(">i", len(msg)) + msg
    return out


def pack_bundles(encoded_messages, max_size: int = 4096):
    """Pack messages into as few bundles as possible, each <= max_size bytes.

    Mirrors VRCFT's fti_osc.create_osc_bundle loop (4096-byte send buffer).
    """
    bundles = []
    current: list[bytes] = []
    size = len(BUNDLE_HEADER) + len(IMMEDIATELY)
    for msg in encoded_messages:
        need = 4 + len(msg)
        if current and size + need > max_size:
            bundles.append(encode_bundle(current))
            current = []
            size = len(BUNDLE_HEADER) + len(IMMEDIATELY)
        current.append(msg)
        size += need
    if current:
        bundles.append(encode_bundle(current))
    return bundles


def _read_string(data: bytes, offset: int):
    end = data.index(b"\x00", offset)
    s = data[offset:end].decode("utf-8", errors="replace")
    end += 1
    end += -(end) % 4
    return s, end


def parse(data: bytes):
    """Parse an OSC packet into a list of (address, [args]) tuples.

    Handles messages and (nested) bundles; unknown arg types abort that
    message's remaining args but keep what was parsed.
    """
    out = []
    _parse_into(data, out)
    return out


def _parse_into(data: bytes, out: list) -> None:
    if data.startswith(BUNDLE_HEADER):
        offset = len(BUNDLE_HEADER) + 8  # skip time tag
        while offset + 4 <= len(data):
            (size,) = struct.unpack_from(">i", data, offset)
            offset += 4
            _parse_into(data[offset : offset + size], out)
            offset += size
        return

    try:
        address, offset = _read_string(data, 0)
        if not address.startswith("/"):
            return
        tags, offset = _read_string(data, offset)
    except (ValueError, IndexError):
        return

    args = []
    for tag in tags.lstrip(","):
        try:
            if tag == "f":
                (v,) = struct.unpack_from(">f", data, offset)
                offset += 4
            elif tag == "i":
                (v,) = struct.unpack_from(">i", data, offset)
                offset += 4
            elif tag == "s":
                v, offset = _read_string(data, offset)
            elif tag == "T":
                v = True
            elif tag == "F":
                v = False
            elif tag == "d":
                (v,) = struct.unpack_from(">d", data, offset)
                offset += 8
            else:
                break  # unknown tag; can't know its size
        except (struct.error, ValueError, IndexError):
            break
        args.append(v)
    out.append((address, args))
