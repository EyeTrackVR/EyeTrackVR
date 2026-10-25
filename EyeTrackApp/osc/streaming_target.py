"""The ``auto`` OSC address: on a Steam Frame, send to the PC being streamed to.

The app runs on the headset while VRChat runs on the PC that Steam Link streams
from, so 127.0.0.1 reaches nothing. Steam on the headset already knows that PC:

1. Steam Link VR (``logs/vrlink.txt``) logs each session's link. After "Starting
   session", every candidate link logs ``SetPeer <local> -> <peer>`` and the one
   in use logs ``AddAndInitLinkTransfer <local> / PEERED: true``. A session is
   live until its output stream goes "unconnected". Seen links: the USB cable
   (10.86.200.234), the headset's own hotspot (10.35.78.x) and Wi-Fi.
2. Steam remote play (``logs/remote_connections.txt``) logs the PC's discovery
   broadcasts: ``Received broadcast message from client <id> (...): <ip>:27036``.
   These come and go with the PC, not with a stream, so they rank second.
3. VRChat answers OSCQuery (``_oscjson._tcp``) over mDNS. Its records say
   127.0.0.1, but the reply comes from the PC, so its source address is used.

With none of these, ``auto`` sends to 127.0.0.1. Typing an address in the OSC
address field overrides all of it (127.0.0.1 for VRChat running on the headset).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
import time

from pyvrcft.mdns import MDNS_GROUP, MDNS_PORT, SERVICE, _build_query, _parse_srv_records

logger = logging.getLogger(__name__)

AUTO = "auto"
LOOPBACK = "127.0.0.1"
STEAM_LOGS = os.path.expanduser("~/.local/share/Steam/logs")
_TAIL_BYTES = 256 * 1024  # these logs grow for days; the newest entries are at the end

_SESSION_START = re.compile(r"Starting session with ID")
_SET_PEER = re.compile(r"SetPeer (\d+\.\d+\.\d+\.\d+) -> (\d+\.\d+\.\d+\.\d+)")
_PEERED = re.compile(r"AddAndInitLinkTransfer (\d+\.\d+\.\d+\.\d+) / PEERED: true")
_OUTPUT_STATE = re.compile(r"Output stream \(-?\d+\) state changed: (\w+)")
_BROADCAST = re.compile(r"Received broadcast message from client \d+ \([^)]*\): (\d+\.\d+\.\d+\.\d+):27036")


def is_auto(address) -> bool:
    return str(address).strip().lower() == AUTO


def _usable(ip: str) -> bool:
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return not (addr.is_loopback or addr.is_multicast or addr.is_unspecified or ip.endswith(".255"))


def _tail(path: str) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - _TAIL_BYTES))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def vrlink_peer(text: str) -> str | None:
    """The PC of the newest Steam Link VR session, if that session is still live."""
    starts = [m.end() for m in _SESSION_START.finditer(text)]
    if not starts:
        return None
    session = text[starts[-1]:]
    peers = {local: peer for local, peer in _SET_PEER.findall(session)}
    peered = [local for local in _PEERED.findall(session) if local in peers]
    if not peered:
        return None
    states = _OUTPUT_STATE.findall(session)
    if states and states[-1] == "unconnected":
        return None  # the stream ended
    peer = peers[peered[-1]]
    return peer if _usable(peer) else None


def remote_play_peer(text: str) -> str | None:
    """The address the paired PC broadcast most recently."""
    for ip in reversed(_BROADCAST.findall(text)):
        if _usable(ip):
            return ip
    return None


def _own_addresses() -> set[str]:
    own = {LOOPBACK}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            own.add(info[4][0])
    except OSError:
        pass
    return own


def mdns_vrchat_host(timeout: float = 1.5, instance_prefix: str = "VRChat-Client") -> str | None:
    """The address VRChat's OSCQuery mDNS answer came from, if another machine."""
    own = _own_addresses()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return None
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", MDNS_PORT))
        except OSError:
            sock.bind(("", 0))
        try:
            membership = socket.inet_aton(MDNS_GROUP) + socket.inet_aton("0.0.0.0")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        except OSError:
            pass
        sock.sendto(_build_query(SERVICE), (MDNS_GROUP, MDNS_PORT))
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            sock.settimeout(remaining)
            try:
                data, (source, _port) = sock.recvfrom(4096)
            except (socket.timeout, OSError):
                return None
            if source in own or not _usable(source):
                continue
            if any(name.startswith(instance_prefix) for name, _p, _t in _parse_srv_records(data)):
                return source
        return None
    except OSError:
        return None
    finally:
        sock.close()


def resolve(logs_dir: str = STEAM_LOGS, use_mdns: bool = True) -> tuple[str, str]:
    """``(address, source)`` for the ``auto`` OSC target."""
    peer = vrlink_peer(_tail(os.path.join(logs_dir, "vrlink.txt")))
    if peer:
        return peer, "Steam Link VR session"
    peer = remote_play_peer(_tail(os.path.join(logs_dir, "remote_connections.txt")))
    if peer:
        return peer, "Steam remote play"
    if use_mdns:
        peer = mdns_vrchat_host()
        if peer:
            return peer, "VRChat mDNS"
    return LOOPBACK, "no streaming PC found"
