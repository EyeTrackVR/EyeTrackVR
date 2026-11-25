"""OSCQuery advertising (osc/oscquery.py) and pyVRCFT's mDNS lookup of VRChat
(pyvrcft/mdns.py): the tree, mDNS questions and answers, and the HTTP server."""

import errno
import json
import select
import socket
import struct
import types
import urllib.error
import urllib.request

import pytest

from osc import oscquery
from osc.oscquery import (
    MDNSResponder,
    OSCQueryAdvertiser,
    TYPE_A,
    TYPE_ANY,
    TYPE_PTR,
    TYPE_SRV,
    TYPE_TXT,
    build_tree,
    decode_name,
    encode_name,
    parse_query,
)
from pyvrcft import mdns
from tests.osc_helpers import collect_stray_garbage, LOCALHOST, fast_server_shutdown, no_multicast

ENDPOINTS = {
    "/avatar/change": ("s", 2, "Avatar change"),
    "/avatar/parameters/etvr_recenter": ("T", 2, "recenter"),
}
INSTANCE = "EyeTrackVR-TEST01"


@pytest.fixture(autouse=True, scope="module")
def _main_thread_gc():
    collect_stray_garbage()


def _query(*questions, qid=0, unicast=False) -> bytes:
    body = b"".join(encode_name(n) + struct.pack(">HH", t, 1 | (0x8000 if unicast else 0)) for n, t in questions)
    return struct.pack(">HHHHHH", qid, 0, len(questions), 0, 0, 0) + body


def _records(packet: bytes):
    _, _, qd, an, ns, ar = struct.unpack_from(">HHHHHH", packet, 0)
    offset = 12
    for _ in range(qd):
        _, offset = decode_name(packet, offset)
        offset += 4
    out = []
    for _ in range(an + ns + ar):
        name, offset = decode_name(packet, offset)
        rtype, _rclass, ttl, rdlen = struct.unpack_from(">HHIH", packet, offset)
        offset += 10
        port = struct.unpack_from(">HHH", packet, offset)[2] if rtype == TYPE_SRV else None
        out.append((name, rtype, ttl, port))
        offset += rdlen
    return out


def _responder():
    return MDNSResponder(INSTANCE, {oscquery.OSCJSON_SERVICE: 4321, oscquery.OSC_SERVICE: 9123})


def test_tree_nests_paths_and_indexes_every_node():
    root, index = build_tree(ENDPOINTS)
    avatar = root["CONTENTS"]["avatar"]
    assert avatar["FULL_PATH"] == "/avatar" and avatar["ACCESS"] == 0
    leaf = avatar["CONTENTS"]["parameters"]["CONTENTS"]["etvr_recenter"]
    assert leaf == {
        "FULL_PATH": "/avatar/parameters/etvr_recenter",
        "ACCESS": 2,
        "TYPE": "T",
        "DESCRIPTION": "recenter",
    }
    assert index["/avatar/change"]["TYPE"] == "s"
    assert set(index) == {"/", "/avatar", "/avatar/change", "/avatar/parameters", "/avatar/parameters/etvr_recenter"}


def test_ptr_question_gets_full_service_answer():
    qid, questions = parse_query(_query((oscquery.OSC_SERVICE, TYPE_PTR)))
    answers, additionals, keys = _responder().answer(questions)
    records = _records(oscquery.build_packet(answers, additionals))
    assert ("_osc._udp.local", TYPE_PTR, 4500, None) in records
    assert (f"{INSTANCE}._osc._udp.local", TYPE_SRV, 120, 9123) in records
    assert (f"{INSTANCE}._osc._udp.local", TYPE_TXT, 4500, None) in records
    assert (f"{INSTANCE}.local", TYPE_A, 120, None) in records
    # Only the asked-for service: the HTTP port is not leaked into this answer.
    assert all(port != 4321 for *_, port in records)
    assert keys == [("_osc._udp.local", TYPE_PTR)]


@pytest.mark.parametrize(
    "question, expected",
    [
        ((oscquery.SERVICES_META, TYPE_PTR), {("_services._dns-sd._udp.local", TYPE_PTR)}),
        ((f"{INSTANCE}._oscjson._tcp.local", TYPE_SRV), {(f"{INSTANCE}._oscjson._tcp.local", TYPE_SRV)}),
        ((f"{INSTANCE}._oscjson._tcp.local", TYPE_TXT), {(f"{INSTANCE}._oscjson._tcp.local", TYPE_TXT)}),
        (
            (f"{INSTANCE}._oscjson._tcp.local", TYPE_ANY),
            {(f"{INSTANCE}._oscjson._tcp.local", TYPE_SRV), (f"{INSTANCE}._oscjson._tcp.local", TYPE_TXT)},
        ),
        ((f"{INSTANCE}.local", TYPE_A), {(f"{INSTANCE}.local", TYPE_A)}),
    ],
    ids=["service-list", "srv", "txt", "any", "host-a"],
)
def test_direct_questions_are_answered(question, expected):
    _, questions = parse_query(_query(question))
    answers, _additionals, keys = _responder().answer(questions)
    assert {(name, rtype) for name, rtype, _ttl, _port in _records(oscquery.build_packet(answers, []))} == expected
    assert len(keys) == 1


def test_unrelated_questions_and_responses_are_ignored():
    responder = MDNSResponder(INSTANCE, {oscquery.OSCJSON_SERVICE: 4321})
    _, questions = parse_query(
        _query(("_http._tcp.local", TYPE_PTR), ("VRChat-Client-AB12._oscjson._tcp.local", TYPE_SRV))
    )
    assert responder.answer(questions) == ([], [], [])
    response = bytearray(_query((oscquery.OSCJSON_SERVICE, TYPE_PTR)))
    response[2] |= 0x80  # QR: a response, e.g. our own announcement looped back
    assert parse_query(bytes(response)) is None
    for garbage in (
        b"",
        b"\x00" * 11,
        _query((oscquery.OSCJSON_SERVICE, TYPE_PTR))[:20],
        struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + b"\xc0\x0c",  # pointer loop
    ):
        assert parse_query(garbage) is None


def test_goodbye_records_have_zero_ttl():
    records = _records(oscquery.build_packet(_responder().all_records(ttl=0), []))
    assert len(records) == 7 and all(ttl == 0 for _, _, ttl, _ in records)


class _CapturingSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, packet, address):
        self.sent.append((packet, address))

    def setsockopt(self, *args):
        pass


def _handled(responder, packet, port):
    sock = responder._sock = _CapturingSocket()
    responder._interfaces = [LOCALHOST]
    responder._handle(packet, "127.0.0.9", port)
    return sock.sent


def test_one_shot_querier_gets_a_unicast_reply_echoing_its_question():
    responder = _responder()
    packet = _query((oscquery.OSCJSON_SERVICE, TYPE_PTR), ("_other._tcp.local", TYPE_PTR), qid=0x1234)
    [(reply, address)] = _handled(responder, packet, 50000)
    assert address == ("127.0.0.9", 50000)
    qid, flags, qdcount = struct.unpack_from(">HHH", reply, 0)
    assert (qid, flags, qdcount) == (0x1234, 0x8400, 1)  # only our question is echoed
    assert (f"{INSTANCE}._oscjson._tcp.local", TYPE_SRV, 10, 4321) in _records(reply)  # legacy TTL


def test_multicast_answers_are_rate_limited_and_unicast_questions_are_not():
    responder = _responder()
    question = _query((oscquery.OSCJSON_SERVICE, TYPE_PTR))
    first = _handled(responder, question, oscquery.MDNS_PORT)
    again = _handled(responder, question, oscquery.MDNS_PORT)  # within a second
    assert [address for _, address in first] == [(oscquery.MDNS_GROUP, oscquery.MDNS_PORT)]
    assert again == []
    unicast = _handled(responder, _query((oscquery.OSCJSON_SERVICE, TYPE_PTR), unicast=True), oscquery.MDNS_PORT)
    assert [address for _, address in unicast] == [("127.0.0.9", oscquery.MDNS_PORT)]


def test_vrchat_lookup_reads_our_answer():
    """The pyVRCFT resolver's query, answered by the responder, parses back to the
    advertised HTTP port: both halves of the protocol, no network."""
    _, questions = parse_query(mdns._build_query(mdns.SERVICE))
    answers, additionals, _ = _responder().answer(questions)
    found = list(mdns._parse_srv_records(oscquery.build_packet(answers, additionals)))
    assert found == [(f"{INSTANCE}._oscjson._tcp.local", 4321, f"{INSTANCE}.local")]


def test_vrchat_lookup_follows_name_compression_and_survives_truncation():
    srv = struct.pack(">HHIH", TYPE_SRV, 1, 120, 8) + struct.pack(">HHH", 0, 0, 7777) + b"\xc0\x0c"
    packet = struct.pack(">HHHHHH", 0, 0x8400, 1, 1, 0, 0)
    packet += encode_name("VRChat-Client-AB._oscjson._tcp.local") + struct.pack(">HH", TYPE_SRV, 1)
    packet += b"\xc0\x0c" + srv  # owner and target are pointers to the question name
    name = "VRChat-Client-AB._oscjson._tcp.local"
    assert list(mdns._parse_srv_records(packet)) == [(name, 7777, name)]
    for cut in (5, 20, len(packet) - 3):
        assert list(mdns._parse_srv_records(packet[:cut])) in ([], [(name, 7777, name)])


def test_http_serves_host_info_tree_attributes_and_404_on_loopback_only(monkeypatch):
    no_multicast(monkeypatch)
    fast_server_shutdown(monkeypatch)
    advertiser = OSCQueryAdvertiser()
    advertiser.start(45678, ENDPOINTS)
    try:
        assert advertiser._http.server_address[0] == LOCALHOST  # never on the LAN
        base = f"http://{LOCALHOST}:{advertiser.http_port}"
        assert not advertiser.discovered
        host_info = json.load(urllib.request.urlopen(base + "/?HOST_INFO", timeout=5))
        assert host_info["OSC_PORT"] == 45678 and host_info["OSC_IP"] == LOCALHOST
        assert host_info["OSC_TRANSPORT"] == "UDP" and host_info["NAME"] == advertiser.instance
        assert advertiser.discovered
        root = json.load(urllib.request.urlopen(base + "/", timeout=5))
        assert set(root["CONTENTS"]["avatar"]["CONTENTS"]) == {"change", "parameters"}
        assert json.load(urllib.request.urlopen(base + "/avatar/change?TYPE", timeout=5)) == {"TYPE": "s"}
        assert urllib.request.urlopen(base + "/avatar/change?RANGE", timeout=5).status == 204
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(base + "/avatar/parameters/unknown", timeout=5)
        assert missing.value.code == 404
    finally:
        advertiser.stop()
    with pytest.raises(OSError):
        urllib.request.urlopen(f"http://{LOCALHOST}:{advertiser.http_port}/", timeout=2)


# ------------------------------------------------------------- real multicast


def _multicast_loopback_error() -> str | None:
    """Why this process can't send itself an mDNS-group datagram, or None if it can.
    Sandboxes, macOS Local Network privacy and containers without a multicast route
    refuse the send (EPERM / EHOSTUNREACH / ENETUNREACH) or never deliver it."""
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        rx.bind(("", 0))
        membership = socket.inet_aton(mdns.MDNS_GROUP) + socket.inet_aton("0.0.0.0")
        rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        tx.sendto(b"probe", (mdns.MDNS_GROUP, rx.getsockname()[1]))
        if not select.select([rx], [], [], 1.0)[0]:
            return "multicast is not looped back to this host"
        return None
    except OSError as exc:
        return f"multicast unavailable: {errno.errorcode.get(exc.errno, exc.errno)} {exc.strerror}"
    finally:
        rx.close()
        tx.close()


def test_real_mdns_round_trip_on_loopback(monkeypatch):
    """A real multicast query from pyVRCFT's resolver, answered by our responder.
    Matched on this run's own instance name: another test process or a running
    EyeTrackVR answers the same query with its own port."""
    reason = _multicast_loopback_error()
    if reason:
        pytest.skip(reason)
    fast_server_shutdown(monkeypatch)
    advertiser = OSCQueryAdvertiser()
    try:
        advertiser.start(45678, ENDPOINTS)
    except OSError as exc:
        pytest.skip(f"cannot bind mDNS here: {exc}")
    try:
        try:
            found = mdns.discover_vrchat_oscquery(timeout=4.0, instance_prefix=advertiser.instance)
        except OSError as exc:  # see test_vrchat_lookup_returns_none_when_multicast_is_refused
            pytest.skip(f"mDNS query refused mid-test: {exc}")
        assert found == (LOCALHOST, advertiser.http_port)
    finally:
        advertiser.stop()


def test_vrchat_lookup_returns_none_when_multicast_is_refused(monkeypatch):
    class Refused(socket.socket):
        def sendto(self, *args):
            raise PermissionError(errno.EPERM, "Operation not permitted")

    proxy = types.ModuleType("socket")
    proxy.__dict__.update(socket.__dict__)
    proxy.socket = Refused
    monkeypatch.setattr(mdns, "socket", proxy)
    assert mdns.discover_vrchat_oscquery(timeout=0.2) is None
