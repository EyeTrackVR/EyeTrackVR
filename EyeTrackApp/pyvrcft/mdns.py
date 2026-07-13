"""Tiny one-shot mDNS resolver for VRChat's OSCQuery service.

VRChat advertises "VRChat-Client-XXXXXX._oscjson._tcp.local" over mDNS
(224.0.0.251:5353). We send a PTR query and scan responses for the SRV
record to learn the HTTP port of its OSCQuery server. VRChat always runs
on this machine's loopback for our use case, so we return 127.0.0.1.

Stdlib only — just enough DNS packet parsing for PTR/SRV.
"""

from __future__ import annotations

import socket
import struct
import time

MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353
SERVICE = "_oscjson._tcp.local"
_TYPE_PTR = 12
_TYPE_SRV = 33


def _encode_name(name: str) -> bytes:
    out = b""
    for label in name.split("."):
        raw = label.encode("utf-8")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def _build_query(service: str) -> bytes:
    header = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
    return header + _encode_name(service) + struct.pack(">HH", _TYPE_PTR, 1)


def _decode_name(data: bytes, offset: int, depth: int = 0):
    """Decode a possibly-compressed DNS name. Returns (name, next_offset)."""
    labels = []
    jumped = False
    next_offset = offset
    while depth < 20:
        if offset >= len(data):
            break
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:  # compression pointer
            if offset + 1 >= len(data):
                break
            pointer = struct.unpack_from(">H", data, offset)[0] & 0x3FFF
            if not jumped:
                next_offset = offset + 2
                jumped = True
            offset = pointer
            depth += 1
            continue
        labels.append(data[offset + 1 : offset + 1 + length].decode("utf-8", errors="replace"))
        offset += 1 + length
    if not jumped:
        next_offset = offset
    return ".".join(labels), next_offset


def _parse_srv_records(data: bytes):
    """Yield (owner_name, port, target) for every SRV record in the packet."""
    try:
        _, flags, qd, an, ns, ar = struct.unpack_from(">HHHHHH", data, 0)
        offset = 12
        for _ in range(qd):  # skip questions
            _, offset = _decode_name(data, offset)
            offset += 4
        for _ in range(an + ns + ar):
            name, offset = _decode_name(data, offset)
            rtype, _rclass, _ttl, rdlen = struct.unpack_from(">HHIH", data, offset)
            offset += 10
            if rtype == _TYPE_SRV and rdlen >= 6:
                _prio, _weight, port = struct.unpack_from(">HHH", data, offset)
                target, _ = _decode_name(data, offset + 6)
                yield name, port, target
            offset += rdlen
    except (struct.error, IndexError):
        return


def discover_vrchat_oscquery(timeout: float = 3.0, instance_prefix: str = "VRChat-Client"):
    """Return (host, port) of VRChat's OSCQuery HTTP server, or None.

    VRChat advertises 127.0.0.1 in its A record, so we return loopback
    directly (matching VRCFT's local-client behavior).
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", MDNS_PORT))
        except OSError:
            # Port busy without reuse working (rare) — fall back to an
            # ephemeral port; many responders unicast-reply to the source.
            sock.bind(("", 0))
        membership = socket.inet_aton(MDNS_GROUP) + socket.inet_aton("0.0.0.0")
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        except OSError:
            pass
    except OSError:
        return None

    try:
        sock.sendto(_build_query(SERVICE), (MDNS_GROUP, MDNS_PORT))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            sock.settimeout(remaining)
            try:
                data, _addr = sock.recvfrom(4096)
            except socket.timeout:
                return None
            except OSError:
                return None
            for name, port, _target in _parse_srv_records(data):
                if name.startswith(instance_prefix) and SERVICE in name:
                    return "127.0.0.1", port
    finally:
        sock.close()
