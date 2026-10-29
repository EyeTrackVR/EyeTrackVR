"""OSCQuery receive: tree, mDNS answers, HTTP server, receiver wiring and fallback."""

import json
import os
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from queue import Queue

import pytest
from pythonosc.udp_client import SimpleUDPClient

from osc import oscquery
from osc.osc import AVATAR_CHANGE_ADDRESS, OSCManager, OSCReceiver
from osc.OSCMessage import OSCMessage, OSCMessageType
from osc.oscquery import (
    MDNSResponder,
    OSCQueryAdvertiser,
    TYPE_A,
    TYPE_PTR,
    TYPE_SRV,
    TYPE_TXT,
    build_tree,
    decode_name,
    encode_name,
    parse_query,
)

ENDPOINTS = {
    "/avatar/change": ("s", 2, "Avatar change"),
    "/avatar/parameters/etvr_recenter": ("T", 2, "recenter"),
}


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


@pytest.fixture
def no_multicast(monkeypatch):
    """HTTP/receiver tests must not depend on binding the shared mDNS port."""
    monkeypatch.setattr(MDNSResponder, "start", lambda self: None)
    monkeypatch.setattr(MDNSResponder, "stop", lambda self: None)


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
    responder = MDNSResponder("EyeTrackVR-TEST01", {oscquery.OSCJSON_SERVICE: 4321, oscquery.OSC_SERVICE: 9123})
    qid, questions = parse_query(_query((oscquery.OSC_SERVICE, TYPE_PTR)))
    answers, additionals, keys = responder.answer(questions)
    records = _records(oscquery.build_packet(answers, additionals))
    assert ("_osc._udp.local", TYPE_PTR, 4500, None) in records
    assert ("EyeTrackVR-TEST01._osc._udp.local", TYPE_SRV, 120, 9123) in records
    assert ("EyeTrackVR-TEST01._osc._udp.local", TYPE_TXT, 4500, None) in records
    assert ("EyeTrackVR-TEST01.local", TYPE_A, 120, None) in records
    # Only the asked-for service: the HTTP port is not leaked into this answer.
    assert all(port != 4321 for *_, port in records)
    assert keys == [("_osc._udp.local", TYPE_PTR)]


def test_unrelated_questions_and_responses_are_ignored():
    responder = MDNSResponder("EyeTrackVR-TEST01", {oscquery.OSCJSON_SERVICE: 4321})
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
        struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + b"\xc0\x0c",
    ):  # pointer loop
        assert parse_query(garbage) is None


def test_goodbye_records_have_zero_ttl():
    responder = MDNSResponder("EyeTrackVR-TEST01", {oscquery.OSCJSON_SERVICE: 4321, oscquery.OSC_SERVICE: 9123})
    records = _records(oscquery.build_packet(responder.all_records(ttl=0), []))
    assert len(records) == 7 and all(ttl == 0 for _, _, ttl, _ in records)


def test_http_serves_host_info_tree_attributes_and_404(no_multicast):
    advertiser = OSCQueryAdvertiser()
    advertiser.start(45678, ENDPOINTS)
    try:
        base = f"http://127.0.0.1:{advertiser.http_port}"
        assert not advertiser.discovered
        host_info = json.load(urllib.request.urlopen(base + "/?HOST_INFO", timeout=5))
        assert host_info["OSC_PORT"] == 45678 and host_info["OSC_IP"] == "127.0.0.1"
        assert host_info["OSC_TRANSPORT"] == "UDP" and host_info["NAME"] == advertiser.instance
        assert advertiser.discovered
        root = json.load(urllib.request.urlopen(base + "/", timeout=5))
        assert set(root["CONTENTS"]["avatar"]["CONTENTS"]) == {"change", "parameters"}
        assert json.load(urllib.request.urlopen(base + "/avatar/change?TYPE", timeout=5)) == {"TYPE": "s"}
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(base + "/avatar/parameters/unknown", timeout=5)
        assert missing.value.code == 404
    finally:
        advertiser.stop()
    with pytest.raises(OSError):
        urllib.request.urlopen(f"http://127.0.0.1:{advertiser.http_port}/", timeout=2)


def test_http_server_is_loopback_only(no_multicast):
    advertiser = OSCQueryAdvertiser()
    advertiser.start(45678, ENDPOINTS)
    try:
        assert advertiser._http.server_address[0] == "127.0.0.1"
    finally:
        advertiser.stop()


def test_receiver_advertises_a_free_port_and_receives(main_config, no_multicast):
    settings = main_config.settings
    settings.gui_osc_oscquery = True
    settings.gui_osc_receiver_port = _free_udp_port()
    received = []
    listeners = {settings.gui_osc_recenter_address: [received.append]}
    cancel = threading.Event()
    receiver = OSCReceiver(cancel, main_config, listeners)
    thread = threading.Thread(target=receiver.run)
    thread.start()
    try:
        host, port = receiver.server.server_address
        assert host == "127.0.0.1" and port != settings.gui_osc_receiver_port
        assert receiver.advertiser.osc_port == port
        assert "/avatar/change" in receiver.advertiser.index
        assert settings.gui_osc_recenter_address in receiver.advertiser.index
        SimpleUDPClient("127.0.0.1", port).send_message(settings.gui_osc_recenter_address, True)
        deadline = time.monotonic() + 3
        while not received and time.monotonic() < deadline:
            time.sleep(0.02)
        assert received and received[0].data is True
    finally:
        cancel.set()
        thread.join(timeout=15)
    assert receiver.advertiser is None


def test_receiver_falls_back_to_fixed_port_when_mdns_fails(main_config, monkeypatch):
    def unavailable(self):
        raise OSError("mDNS port unavailable")

    monkeypatch.setattr(MDNSResponder, "start", unavailable)
    settings = main_config.settings
    settings.gui_osc_oscquery = True
    settings.gui_osc_receiver_port = _free_udp_port()
    receiver = OSCReceiver(threading.Event(), main_config, {})
    try:
        assert receiver.advertiser is None
        assert receiver.server.server_address[1] == settings.gui_osc_receiver_port
    finally:
        receiver.server.server_close()


def test_fixed_mode_is_unchanged(main_config):
    settings = main_config.settings
    settings.gui_osc_oscquery = False
    settings.gui_osc_receiver_port = _free_udp_port()
    receiver = OSCReceiver(threading.Event(), main_config, {})
    try:
        assert receiver.advertiser is None
        assert receiver.server.server_address[1] == settings.gui_osc_receiver_port
    finally:
        receiver.server.server_close()


def test_toggling_oscquery_restarts_the_receiver():
    assert "gui_osc_oscquery" in OSCManager.RECEIVER_TRIGGER_KEYS


def test_avatar_change_is_forwarded_to_pyvrcft(main_config):
    manager = OSCManager(config=main_config, osc_message_in_queue=Queue())
    notified = []

    class Client:
        def notify_avatar_change(self, avatar_id):
            notified.append(avatar_id)

    class Sender:
        pyvrcft_sender = type("PyVRCFT", (), {"client": Client()})()

    message = OSCMessage(type=OSCMessageType.EYE_INFO, data="avtr_test")
    for listener in manager.listeners[AVATAR_CHANGE_ADDRESS]:
        listener(message)  # no sender yet: ignored
    manager.osc_sender = Sender()
    for listener in manager.listeners[AVATAR_CHANGE_ADDRESS]:
        listener(message)
    assert notified == ["avtr_test"]


def test_real_mdns_round_trip_on_loopback():
    """A real multicast query answered by the responder; skipped where the
    environment has no usable multicast (some CI containers)."""
    advertiser = OSCQueryAdvertiser()
    try:
        advertiser.start(45678, ENDPOINTS)
    except OSError as exc:
        pytest.skip(f"cannot bind mDNS here: {exc}")
    try:
        from pyvrcft import mdns

        found = mdns.discover_vrchat_oscquery(timeout=4.0, instance_prefix="EyeTrackVR-")
        if found is None and os.environ.get("CI"):
            pytest.skip("multicast is not delivered in this CI environment")
        assert found == ("127.0.0.1", advertiser.http_port)
    finally:
        advertiser.stop()
