"""OSCQuery advertising for the OSC receiver, standard library only.

VRChat (2023.3.1+) finds OSC apps over mDNS (``_oscjson._tcp`` for the HTTP
OSCQuery server, ``_osc._udp`` for the OSC port), reads their OSCQuery tree
and then sends ``/avatar/*`` traffic to the advertised UDP port. The receiver
can therefore bind any free port instead of a fixed one such as 9001, so it
coexists with VRCFaceTracking and other OSC apps.

Like VRCFaceTracking we answer mDNS ourselves rather than depend on an LGPL
zeroconf library. We only ever advertise 127.0.0.1: VRChat on the same PC.
See docs/oscquery-receive-investigation.md.
"""

from __future__ import annotations

import json
import logging
import secrets
import socket
import string
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

logger = logging.getLogger(__name__)

MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353
OSCJSON_SERVICE = "_oscjson._tcp.local"
OSC_SERVICE = "_osc._udp.local"
SERVICES_META = "_services._dns-sd._udp.local"
LOOPBACK = "127.0.0.1"

TYPE_A, TYPE_PTR, TYPE_TXT, TYPE_SRV, TYPE_ANY = 1, 12, 16, 33, 255
CLASS_IN = 1
CACHE_FLUSH = 0x8000  # rrclass bit: this record is unique to us
UNICAST_RESPONSE = 0x8000  # qclass bit (QU): asker wants a unicast reply
SHARED_TTL, UNIQUE_TTL, LEGACY_TTL = 4500, 120, 10  # RFC 6762 §10, §6.7
TXT_RDATA = b"\x09txtvers=1"
_MULTICAST_INTERVAL_S = 1.0  # RFC 6762 §6: at most one multicast answer per record per second


def encode_name(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        raw = label.encode("utf-8")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def decode_name(data: bytes, offset: int) -> tuple[str, int]:
    """Decode a possibly compressed DNS name. Returns (name, next_offset)."""
    labels, jumps, end = [], 0, None
    while True:
        length = data[offset]
        if length & 0xC0 == 0xC0:
            if jumps > 20:  # pointer loop in a hostile packet
                raise ValueError("DNS name pointer loop")
            if end is None:
                end = offset + 2
            offset = struct.unpack_from(">H", data, offset)[0] & 0x3FFF
            jumps += 1
            continue
        if length == 0:
            return ".".join(labels), (end if end is not None else offset + 1)
        labels.append(data[offset + 1 : offset + 1 + length].decode("utf-8", errors="replace"))
        offset += 1 + length


def parse_query(packet: bytes) -> tuple[int, list[tuple[str, int, bool]]] | None:
    """(id, [(lower-case name, qtype, wants unicast)]) for a query; None otherwise."""
    if len(packet) < 12:
        return None
    try:
        qid, flags, qdcount = struct.unpack_from(">HHH", packet, 0)
        if flags & 0x8000:  # a response, possibly our own looped back
            return None
        offset, questions = 12, []
        for _ in range(min(qdcount, 64)):
            name, offset = decode_name(packet, offset)
            qtype, qclass = struct.unpack_from(">HH", packet, offset)
            offset += 4
            questions.append((name.lower().rstrip("."), qtype, bool(qclass & UNICAST_RESPONSE)))
        return qid, questions
    except (struct.error, IndexError, ValueError):
        return None


def record(name: str, rtype: int, ttl: int, rdata: bytes, unique: bool) -> bytes:
    rclass = CLASS_IN | (CACHE_FLUSH if unique else 0)
    return encode_name(name) + struct.pack(">HHIH", rtype, rclass, ttl, len(rdata)) + rdata


def build_packet(answers: list[bytes], additionals: list[bytes], qid: int = 0,
                 questions: bytes = b"", qdcount: int = 0) -> bytes:
    header = struct.pack(">HHHHHH", qid, 0x8400, qdcount, len(answers), 0, len(additionals))
    return header + questions + b"".join(answers) + b"".join(additionals)


class MDNSResponder:
    """Answers mDNS queries for our OSCQuery services; announces on start and
    says goodbye (TTL 0) on stop so VRChat drops us promptly."""

    def __init__(self, instance: str, services: dict[str, int]):
        self.instance = instance
        self.host = f"{instance}.local"
        self.services = {service.lower(): port for service, port in services.items()}
        self._sock: socket.socket | None = None
        self._interfaces: list[str] = []
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._last_multicast: dict[tuple[str, int], float] = {}

    def full_name(self, service: str) -> str:
        return f"{self.instance}.{service}"

    # Record sets --------------------------------------------------------
    def _ptr(self, service: str, ttl: int) -> bytes:
        return record(service, TYPE_PTR, ttl, encode_name(self.full_name(service)), unique=False)

    def _srv(self, service: str, ttl: int) -> bytes:
        rdata = struct.pack(">HHH", 0, 0, self.services[service]) + encode_name(self.host)
        return record(self.full_name(service), TYPE_SRV, min(ttl, UNIQUE_TTL), rdata, unique=True)

    def _txt(self, service: str, ttl: int) -> bytes:
        return record(self.full_name(service), TYPE_TXT, ttl, TXT_RDATA, unique=True)

    def _a(self, ttl: int) -> bytes:
        return record(self.host, TYPE_A, min(ttl, UNIQUE_TTL), socket.inet_aton(LOOPBACK), unique=True)

    def all_records(self, ttl: int = SHARED_TTL) -> list[bytes]:
        records = []
        for service in self.services:
            records += [self._ptr(service, ttl), self._srv(service, ttl), self._txt(service, ttl)]
        return records + [self._a(ttl)]

    def answer(self, questions: list[tuple[str, int, bool]], ttl: int = SHARED_TTL):
        """Records answering ``questions``: (answers, additionals, answered question keys)."""
        answers, additionals, keys = [], [], []
        instances = {self.full_name(service).lower(): service for service in self.services}

        def add(target: list[bytes], rec: bytes) -> None:
            if rec not in answers and rec not in additionals:
                target.append(rec)

        for name, qtype, _ in questions:
            if name in self.services and qtype in (TYPE_PTR, TYPE_ANY):
                add(answers, self._ptr(name, ttl))
                add(additionals, self._srv(name, ttl))
                add(additionals, self._txt(name, ttl))
                add(additionals, self._a(ttl))
            elif name == SERVICES_META and qtype in (TYPE_PTR, TYPE_ANY):
                for service in self.services:
                    add(answers, record(SERVICES_META, TYPE_PTR, ttl, encode_name(service), unique=False))
            elif name in instances and qtype in (TYPE_SRV, TYPE_TXT, TYPE_ANY):
                service = instances[name]
                if qtype in (TYPE_SRV, TYPE_ANY):
                    add(answers, self._srv(service, ttl))
                if qtype in (TYPE_TXT, TYPE_ANY):
                    add(answers, self._txt(service, ttl))
                add(additionals, self._a(ttl))
            elif name == self.host.lower() and qtype in (TYPE_A, TYPE_ANY):
                add(answers, self._a(ttl))
            else:
                continue
            keys.append((name, qtype))
        # Additionals that also answer the question would be sent twice.
        additionals = [rec for rec in additionals if rec not in answers]
        return answers, additionals, keys

    # Socket I/O ---------------------------------------------------------
    @staticmethod
    def _candidate_interfaces() -> list[str]:
        found = [LOOPBACK, "0.0.0.0"]
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                found.append(info[4][0])
        except OSError:
            pass
        return list(dict.fromkeys(found))

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            sock.bind(("", MDNS_PORT))
            for iface in self._candidate_interfaces():
                try:
                    membership = socket.inet_aton(MDNS_GROUP) + socket.inet_aton(iface)
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
                    self._interfaces.append(iface)
                except OSError:
                    continue
            if not self._interfaces:
                raise OSError("could not join the mDNS multicast group on any interface")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            sock.settimeout(0.5)
        except OSError:
            sock.close()
            raise
        self._sock = sock
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True, name="oscquery-mdns")
        self._thread.start()

    def stop(self) -> None:
        if not self._running.is_set():
            return
        self._running.clear()
        try:
            self._multicast(build_packet(self.all_records(ttl=0), []))
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _multicast(self, packet: bytes) -> None:
        for iface in self._interfaces:
            try:
                self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
                self._sock.sendto(packet, (MDNS_GROUP, MDNS_PORT))
            except OSError:
                continue

    def _run(self) -> None:
        # RFC 6762 §8.3: announce twice, a second apart, so a VRChat that is
        # already running sees us without having to ask again.
        announce_at = [time.monotonic(), time.monotonic() + 1.0]
        while self._running.is_set():
            if announce_at and time.monotonic() >= announce_at[0]:
                announce_at.pop(0)
                self._multicast(build_packet(self.all_records(), []))
            try:
                packet, (address, port) = self._sock.recvfrom(9000)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                self._handle(packet, address, port)
            except Exception:  # noqa: a hostile packet must never stop the responder
                logger.debug("Ignoring malformed mDNS packet", exc_info=True)

    def _handle(self, packet: bytes, address: str, port: int) -> None:
        parsed = parse_query(packet)
        if parsed is None:
            return
        qid, questions = parsed
        if port != MDNS_PORT:
            # Legacy one-shot querier (RFC 6762 §6.7): echo the ID and questions, unicast back.
            ours = [q for q in questions if self.answer([q])[2]]
            answers, additionals, _ = self.answer(ours, ttl=LEGACY_TTL)
            if answers:
                echoed = b"".join(encode_name(n) + struct.pack(">HH", t, CLASS_IN) for n, t, _ in ours)
                self._sock.sendto(build_packet(answers, additionals, qid, echoed, len(ours)), (address, port))
            return
        unicast = [q for q in questions if q[2]]
        multicast = [q for q in questions if not q[2]]
        if unicast:
            answers, additionals, _ = self.answer(unicast)
            if answers:
                self._sock.sendto(build_packet(answers, additionals), (address, port))
        now = time.monotonic()
        due = [q for q in multicast
               if now - self._last_multicast.get((q[0], q[1]), 0.0) >= _MULTICAST_INTERVAL_S]
        answers, additionals, keys = self.answer(due)
        if answers:
            for key in keys:
                self._last_multicast[key] = now
            self._multicast(build_packet(answers, additionals))


def build_tree(endpoints: dict[str, tuple[str, int, str]]) -> tuple[dict, dict[str, dict]]:
    """OSCQuery tree for {full_path: (TYPE, ACCESS, DESCRIPTION)}: (root, path -> node)."""
    root = {"FULL_PATH": "/", "ACCESS": 0, "CONTENTS": {}}
    index = {"/": root}
    for full_path, (osc_type, access, description) in sorted(endpoints.items()):
        node, path = root, ""
        parts = [part for part in full_path.split("/") if part]
        for depth, part in enumerate(parts):
            path += "/" + part
            child = node.setdefault("CONTENTS", {}).get(part)
            if child is None:
                child = {"FULL_PATH": path, "ACCESS": 0}
                node["CONTENTS"][part] = child
                index[path] = child
            if depth == len(parts) - 1:
                child.update(TYPE=osc_type, ACCESS=access, DESCRIPTION=description)
            node = child
    return root, index


class _Handler(BaseHTTPRequestHandler):
    server_version = "EyeTrackVR-OSCQuery"

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        advertiser = self.server.advertiser
        advertiser.mark_seen()
        parsed = urlsplit(self.path)
        if parsed.query == "HOST_INFO":
            return self._send(200, advertiser.host_info())
        node = advertiser.index.get(unquote(parsed.path).rstrip("/") or "/")
        if node is None:
            return self._send(404, None)
        if not parsed.query:
            return self._send(200, node)
        attribute = parsed.query.upper()
        if attribute not in node:
            return self._send(204, None)
        return self._send(200, {attribute: node[attribute]})

    def _send(self, status: int, body) -> None:
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(status)
        if data:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # http.server logs every request to stderr
        pass


class OSCQueryAdvertiser:
    """Serves the OSCQuery tree on loopback and advertises it with mDNS."""

    def __init__(self, app_name: str = "EyeTrackVR"):
        # Unique per run, like VRCFaceTracking, so a restart is a new service to VRChat.
        suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        self.instance = f"{app_name}-{suffix}"
        self.osc_port = 0
        self.http_port = 0
        self.index: dict[str, dict] = {}
        self._root: dict = {}
        self._http: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._responder: MDNSResponder | None = None
        self._seen = threading.Event()

    @property
    def discovered(self) -> bool:
        """True once anything (normally VRChat) has fetched our OSCQuery data."""
        return self._seen.is_set()

    def mark_seen(self) -> None:
        if not self._seen.is_set():
            self._seen.set()
            logger.info("OSCQuery: %s was queried; VRChat can now find the OSC receiver", self.instance)

    def host_info(self) -> dict:
        return {
            "NAME": self.instance,
            "EXTENSIONS": {"ACCESS": True, "CLIPMODE": False, "RANGE": False, "TYPE": True, "VALUE": False},
            "OSC_IP": LOOPBACK,
            "OSC_PORT": self.osc_port,
            "OSC_TRANSPORT": "UDP",
        }

    def start(self, osc_port: int, endpoints: dict[str, tuple[str, int, str]]) -> None:
        self.osc_port = osc_port
        self._root, self.index = build_tree(endpoints)
        self._http = ThreadingHTTPServer((LOOPBACK, 0), _Handler)
        self._http.daemon_threads = True
        self._http.advertiser = self
        self.http_port = self._http.server_address[1]
        self._http_thread = threading.Thread(target=self._http.serve_forever, daemon=True, name="oscquery-http")
        self._http_thread.start()
        try:
            self._responder = MDNSResponder(self.instance, {OSCJSON_SERVICE: self.http_port, OSC_SERVICE: osc_port})
            self._responder.start()
        except Exception:
            self._responder = None
            self.stop()
            raise
        logger.info("OSCQuery: advertising %s (OSC udp %d, HTTP tcp %d)", self.instance, osc_port, self.http_port)

    def stop(self) -> None:
        if self._responder is not None:
            self._responder.stop()
            self._responder = None
        if self._http is not None:
            self._http.shutdown()
            self._http.server_close()
            self._http = None
        if self._http_thread is not None:
            self._http_thread.join(timeout=2.0)
            self._http_thread = None
