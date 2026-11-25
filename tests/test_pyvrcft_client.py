"""The embedded pyVRCFT client (pyvrcft/client.py): which values reach which avatar
address, the event-driven send loop, receive / discovery threads, avatar switches
and the /tracking/face/v1 gate. VRChat is a loopback socket or HTTP server."""

import logging
import socket
import struct
import threading
import time
from unittest import mock

import pytest

from osc.osc import FULL_FACE_ADDRESS
from pyvrcft import UnifiedTrackingData, VRCFTClient
from pyvrcft import client as pyclient
from pyvrcft import expressions as pyexpressions
from pyvrcft import osc as pyosc
from pyvrcft.avatar import AvatarInfo, AvatarParameter
from tests.osc_helpers import (
    collect_stray_garbage,
    LOCALHOST,
    avatar_tree,
    drain,
    free_udp_port,
    receive_until,
    udp_listener,
    vrchat_oscquery,
    wait_for,
    wire,
)

FACE = "/tracking/face/v1"
FT = "/avatar/parameters/FT/v2/"
CLOSED = "/tracking/eye/EyesClosedAmount"


@pytest.fixture(autouse=True, scope="module")
def _main_thread_gc():
    collect_stray_garbage()


def _frame(jaw=1.0):
    data = UnifiedTrackingData()
    data.shapes["JawOpen"] = jaw
    return data


def _avatar(avatar_id="avtr_test", **types):
    params = [AvatarParameter(name=n, address=FT + n, type=t) for n, t in types.items()]
    return AvatarInfo(id=avatar_id, name="test", parameters=params)


@pytest.fixture
def avatars(monkeypatch):
    """avatar id -> AvatarInfo the disk lookup returns (unknown ids: an empty config)."""
    known = {}
    monkeypatch.setattr(pyclient, "load_avatar_config", lambda avatar_id: known.get(avatar_id, AvatarInfo(avatar_id)))
    return known


@pytest.fixture
def client(avatars):
    """A client that is not started: no sockets; ticks are driven with wire()."""
    return VRCFTClient(use_oscquery=False)


# ------------------------------------------------------------ what is sent


def test_values_wait_for_an_avatar_and_go_to_its_addresses(client, avatars):
    client.set("JawOpen", 0.4)
    client.set("MouthClosed", 0.1)
    assert wire(client) == {}  # no avatar yet: nothing resolves
    avatars["avtr_jaw"] = _avatar("avtr_jaw", JawOpen=float)
    changes = []
    client.on_avatar_change = changes.append
    client._dispatch("/avatar/change", ["avtr_jaw"])
    assert [a.id for a in changes] == ["avtr_jaw"]
    assert wire(client) == {FT + "JawOpen": [pytest.approx(0.4)]}  # held value re-resolved and sent
    assert wire(client) == {}  # send-on-change


def test_force_relevant_sends_everything_to_default_addresses(client):
    client.set("JawOpen", 0.25)
    client.set_bool("EyeTrackingActive", True)
    client._dispatch("/vrcft/settings/forceRelevant", [True])
    assert wire(client) == {
        "/avatar/parameters/v2/JawOpen": [0.25],
        "/avatar/parameters/EyeTrackingActive": [True],
    }


def test_status_bools_are_sent_raw_to_matching_bool_params(client, avatars):
    # Status bools are not v2 params: VRCFT avatars declare them outside "v2/".
    avatars["avtr_b"] = AvatarInfo(
        "avtr_b",
        parameters=[
            AvatarParameter("EyeTrackingActive", "/avatar/parameters/FT/EyeTrackingActive", bool),
            AvatarParameter("LipTrackingActive", "/avatar/parameters/FT/LipTrackingActive", float),
        ],
    )
    client._dispatch("/avatar/change", ["avtr_b"])
    data = UnifiedTrackingData()
    data.eye_tracking_active = True
    data.expression_tracking_active = False
    client.update_tracking(data)
    sent = wire(client)
    assert sent["/avatar/parameters/FT/EyeTrackingActive"] == [True]
    assert "/avatar/parameters/FT/LipTrackingActive" not in sent  # a float param is not a status bool


def test_avatar_eye_params_switch_off_the_matching_native_endpoints(client, avatars):
    avatars["avtr_lids"] = _avatar("avtr_lids", EyeLidLeft=float, JawOpen=float)
    client.update_tracking(_frame())
    first = wire(client)
    assert {"/tracking/eye/EyesClosedAmount", "/tracking/eye/LeftRightPitchYaw"} <= set(first)
    client._dispatch("/avatar/change", ["avtr_lids"])
    frame = _frame()
    frame.eye.left.openness = 0.5
    frame.eye.left.gaze = (0.3, 0.0)
    client.update_tracking(frame)
    sent = wire(client)
    assert "/tracking/eye/EyesClosedAmount" not in sent  # the avatar animates its own lids
    assert "/tracking/eye/LeftRightPitchYaw" in sent  # but has no FT gaze params
    assert sent[FT + "EyeLidLeft"] == [pytest.approx(0.375)]


def test_legacy_v1_avatar_gets_v1_eye_params(client, avatars):
    legacy = [AvatarParameter("LeftEyeLidExpandedSqueeze", "/avatar/parameters/LeftEyeLidExpandedSqueeze", float)]
    avatars["avtr_v1"] = AvatarInfo("avtr_v1", parameters=legacy)
    client._dispatch("/avatar/change", ["avtr_v1"])
    client.update_tracking(UnifiedTrackingData())  # open eyes, no widen
    assert wire(client)["/avatar/parameters/LeftEyeLidExpandedSqueeze"] == [pytest.approx(0.8)]


def test_non_finite_values_are_never_stored_or_sent(client, avatars):
    """A NaN/inf set() keeps the last good value: an avatar resolved afterwards
    gets 0.4, not a NaN the slots would have to drop."""
    client.set("JawOpen", 0.4)
    client.set("JawOpen", float("nan"))
    client.set("EyeLeftX", float("inf"))
    client.send_direct(CLOSED, 0.2)
    client.send_direct(CLOSED, float("nan"))
    assert client._direct[CLOSED].pending == 0.2
    avatars["avtr_late"] = _avatar("avtr_late", JawOpen=float, EyeLeftX=float)
    client._dispatch("/avatar/change", ["avtr_late"])
    assert wire(client) == {FT + "JawOpen": [pytest.approx(0.4)], CLOSED: [pytest.approx(0.2)]}
    client.send_direct(CLOSED, float("inf"))
    assert wire(client) == {}  # the avatar holds the last good values
    client.send_direct(CLOSED, 0.3)
    assert wire(client) == {CLOSED: [pytest.approx(0.3)]}


def test_tracking_pipeline_runs_once_per_tick_on_the_latest_frame(avatars, monkeypatch):
    face_calls = []
    real_face = pyexpressions.compute_face_v1
    monkeypatch.setattr(pyexpressions, "compute_face_v1", lambda *a: face_calls.append(1) or real_face(*a))
    outputs_calls = []
    real_outputs = pyclient.compute_outputs
    monkeypatch.setattr(pyclient, "compute_outputs", lambda *a, **k: outputs_calls.append(1) or real_outputs(*a, **k))

    client = VRCFTClient(use_oscquery=False, native_face=False, force_relevant=True)
    client._dispatch(FULL_FACE_ADDRESS, [True])  # avatar takes face/v1, but the option is off
    for jaw in (0.25, 0.75, 1.0, 0.5):  # several eye/brow messages within one tick
        client.update_tracking(_frame(jaw))
    sent = wire(client)

    assert sent["/avatar/parameters/v2/JawOpen"] == [0.5]
    assert len(outputs_calls) == 1
    assert face_calls == []
    assert FACE not in sent


# ------------------------------------------------------- /tracking/face/v1 gate


def test_face_payload_off_until_avatar_reports_full_face(client):
    client.update_tracking(_frame())
    assert FACE not in wire(client)

    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    (payload,) = wire(client)[FACE]
    assert payload[36] == 255  # JawOpen
    # Send-on-change: an identical frame is not resent.
    client.update_tracking(_frame())
    assert FACE not in wire(client)


def test_eye_endpoints_still_sent_alongside_face(client):
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    assert {FACE, "/tracking/eye/LeftRightPitchYaw", CLOSED} <= set(wire(client))


def test_avatar_change_closes_gate_and_false_stays_closed(client):
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client._dispatch("/avatar/change", ["avtr_new"])
    client.update_tracking(_frame())
    assert FACE not in wire(client)

    client._dispatch(FULL_FACE_ADDRESS, [False])
    client.update_tracking(_frame())
    assert FACE not in wire(client)


def test_reopening_gate_resends_unchanged_payload(client):
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    assert FACE in wire(client)
    client._dispatch(FULL_FACE_ADDRESS, [False])
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    assert FACE in wire(client)


def test_oscquery_flag_used_when_osc_did_not_report(client, avatars):
    avatars["avtr_ft"] = AvatarInfo(id="avtr_ft", full_face_tracking=True)
    client._dispatch("/avatar/change", ["avtr_ft"])
    client.update_tracking(_frame())
    assert FACE in wire(client)


def test_osc_flag_beats_stale_oscquery_snapshot(client, monkeypatch):
    """EyeTrackVR's receiver path: the flag can land before the resolve thread."""
    resolved = []

    def slow_config(avatar_id):
        resolved.append(avatar_id)
        return AvatarInfo(id=avatar_id, full_face_tracking=True)  # stale: old avatar's value

    monkeypatch.setattr(pyclient, "load_avatar_config", slow_config)
    with mock.patch.object(pyclient.threading, "Thread") as thread:
        client.notify_avatar_change("avtr_plain")
        client.notify_full_face_tracking(False)
        # Now let the deferred resolve run.
        kwargs = thread.call_args.kwargs
        kwargs["target"](*kwargs["args"], **kwargs["kwargs"])
    assert resolved == ["avtr_plain"]
    client.update_tracking(_frame())
    assert FACE not in wire(client)


def test_native_face_disabled_never_sends(avatars):
    client = VRCFTClient(use_oscquery=False, native_face=False)
    client._dispatch(FULL_FACE_ADDRESS, [True])
    client.update_tracking(_frame())
    assert FACE not in wire(client)


# --------------------------------------------------------------- send loop


def test_send_loop_sends_on_update_but_not_faster_than_the_rate():
    """rate=2: the old fixed timer sent at most every 0.5 s, so an update just after a
    tick waited ~0.4 s for the next one. Needs real time: the cap is the contract."""

    def recv_send(sock):
        """Block for one send (possibly several datagrams); return when it began."""
        sock.settimeout(2.0)
        sock.recvfrom(65535)
        arrived = time.monotonic()
        sock.settimeout(0.05)
        try:
            while True:
                sock.recvfrom(65535)
        except socket.timeout:
            pass
        return arrived

    with udp_listener() as vrchat:
        client = VRCFTClient(
            send_host=LOCALHOST,
            send_port=vrchat.getsockname()[1],
            recv_port=0,
            rate=2.0,
            use_oscquery=False,
            force_relevant=True,
        )
        with client:
            client.update_tracking(_frame(0.1))
            first = recv_send(vrchat)

            # A second update right away still waits out the minimum interval.
            client.update_tracking(_frame(0.2))
            assert recv_send(vrchat) - first >= 0.45

            # Once the interval has passed, an update goes out immediately.
            time.sleep(0.6)
            sent_at = time.monotonic()
            client.update_tracking(_frame(0.3))
            assert recv_send(vrchat) - sent_at < 0.15


def test_unchanged_frames_are_computed_at_most_once_per_interval(monkeypatch):
    calls = []
    real_outputs = pyclient.compute_outputs
    monkeypatch.setattr(pyclient, "compute_outputs", lambda *a, **k: calls.append(1) or real_outputs(*a, **k))
    with udp_listener() as vrchat:
        client = VRCFTClient(send_port=vrchat.getsockname()[1], recv_port=0, rate=20.0, use_oscquery=False)
        frame = _frame(0.5)
        with client:
            started = time.monotonic()
            while time.monotonic() - started < 0.25:  # identical frames, nothing new to send
                client.update_tracking(frame)
                time.sleep(0.001)
            elapsed = time.monotonic() - started
    assert 1 <= len(calls) <= elapsed / client.interval + 2


def test_idle_tick_sends_values_that_became_sendable_without_an_update():
    """forceRelevant (or a re-resolved avatar) makes held values sendable without new
    tracking: the send loop's idle tick must still put them on the wire."""
    with udp_listener() as vrchat:
        client = VRCFTClient(send_port=vrchat.getsockname()[1], recv_port=0, use_oscquery=False)
        with client:
            client.set("JawOpen", 0.3)  # no avatar: nothing to send yet
            assert drain(vrchat, settle=0.15) == []
            client._dispatch("/vrcft/settings/forceRelevant", [True])  # does not wake the loop
            received = receive_until(vrchat, lambda r: r)
    assert received == [("/avatar/parameters/v2/JawOpen", [pytest.approx(0.3)])]


def test_send_loop_survives_nan_in_binary_params():
    with udp_listener() as vrchat:
        client = VRCFTClient(
            send_host=LOCALHOST, send_port=vrchat.getsockname()[1], recv_port=free_udp_port(), use_oscquery=False
        )
        client.avatar = _avatar(JawOpen1=bool, JawOpen2=bool, JawOpen4=bool, EyeLeftX=float)
        # Bypass set()'s guard to prove the loop itself cannot be killed by a NaN
        # reaching the binary encoding (int(nan * max_int) -> ValueError).
        with client._lock:
            client._values["v2/JawOpen"] = float("nan")
            client._resolve_one("v2/JawOpen")
        assert client._slots["v2/JawOpen"], "binary slots should resolve"
        with client:
            send_thread = client._threads[0]
            assert send_thread.name == "pyvrcft-send"
            client.set("JawOpen", 0.99)
            client.set("EyeLeftX", 0.5)
            received = dict(receive_until(vrchat, lambda r: {FT + "EyeLeftX", FT + "JawOpen4"} <= {a for a, _ in r}))
            assert send_thread.is_alive()
    assert received[FT + "EyeLeftX"] == [0.5]
    assert received[FT + "JawOpen4"] == [True]


def test_sendto_failure_is_throttled(caplog):
    class FailingSock:
        def sendto(self, data, addr):
            raise OSError(10065, "host unreachable")

        def close(self):
            pass

    client = VRCFTClient(send_port=free_udp_port(), recv_port=0, use_oscquery=False, force_relevant=True)
    client.start()
    real_sock = client._send_sock
    client._send_sock = FailingSock()
    try:
        with caplog.at_level(logging.ERROR, logger="pyvrcft"):
            for i in range(30):  # ~30 send ticks, each with a changed value
                client.set("JawOpen", i / 100)
                time.sleep(0.01)
            assert client._threads[0].is_alive()
    finally:
        client.stop()
        real_sock.close()
    failures = [r for r in caplog.records if "OSC send to" in r.getMessage()]
    assert len(failures) == 1


# ---------------------------------------------------------- receive thread


def test_receive_thread_handles_avatar_messages_and_survives_garbage(avatars):
    avatars["avtr_rx"] = _avatar("avtr_rx", JawOpen=float)
    port = free_udp_port()
    client = VRCFTClient(send_port=free_udp_port(), recv_port=port, use_oscquery=False)
    seen = []
    client.on_message = lambda address, args: seen.append(address)
    with client, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as vrchat:
        header = pyosc.BUNDLE_HEADER + pyosc.IMMEDIATELY
        vrchat.sendto(header + struct.pack(">i", -12) + b"\x00" * 16, (LOCALHOST, port))
        vrchat.sendto(pyosc.encode_message("/avatar/change", ["avtr_rx"]), (LOCALHOST, port))
        vrchat.sendto(pyosc.encode_message("/still/alive", [1.0]), (LOCALHOST, port))
        assert wait_for(lambda: "/still/alive" in seen)
        assert client.avatar.id == "avtr_rx"
        assert next(t for t in client._threads if t.name == "pyvrcft-recv").is_alive()


def test_failing_callbacks_do_not_stop_message_handling(client, caplog):
    client.on_avatar_change = mock.Mock(side_effect=RuntimeError("callback"))
    client.on_message = mock.Mock(side_effect=RuntimeError("callback"))
    with caplog.at_level(logging.ERROR, logger="pyvrcft"):
        client._dispatch("/avatar/change", ["avtr_cb"])
    assert client.avatar.id == "avtr_cb"
    assert "on_avatar_change callback failed" in caplog.text and "on_message callback failed" in caplog.text


@pytest.mark.parametrize("recv_port", ["taken", 70000])
def test_unbindable_receive_port_falls_back_to_polling(recv_port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other_app:
        other_app.bind((LOCALHOST, 0))
        port = other_app.getsockname()[1] if recv_port == "taken" else recv_port
        with VRCFTClient(send_port=free_udp_port(), recv_port=port, use_oscquery=False) as client:
            assert client._recv_sock is None and client._poll_avatar
            assert [t.name for t in client._threads] == ["pyvrcft-send"]


# ---------------------------------------------------------------- discovery


def test_avatar_switch_is_picked_up_without_a_receive_port(monkeypatch):
    monkeypatch.setattr(pyclient, "AVATAR_POLL_S", 0.02)
    from pyvrcft import avatar as pyavatar

    monkeypatch.setattr(pyavatar, "load_avatar_name", lambda avatar_id: "")
    with vrchat_oscquery(avatar_tree("avtr_old", {"v2/JawOpen": "f"})) as vrchat:
        monkeypatch.setattr(
            pyclient.mdns, "discover_vrchat_oscquery", lambda timeout=3.0, **_: (LOCALHOST, vrchat.server_address[1])
        )
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other_app:
            other_app.bind((LOCALHOST, 0))  # another app owns the receive port
            client = VRCFTClient(send_port=free_udp_port(), recv_port=other_app.getsockname()[1])
            try:
                client.start()
                assert client._recv_sock is None
                assert wait_for(lambda: client.avatar is not None and client.avatar.id == "avtr_old")
                vrchat.body = avatar_tree("avtr_new", {"v2/JawOpen": "f"})
                assert wait_for(lambda: client.avatar.id == "avtr_new")
                started = time.monotonic()
                client.stop()
                assert time.monotonic() - started < 0.5
                polls = len(vrchat.requests)
                time.sleep(0.1)  # proving absence: five poll intervals
                assert len(vrchat.requests) <= polls + 1  # at most one poll already in flight
            finally:
                client.stop()


def test_stop_returns_promptly_during_discovery_backoff(monkeypatch):
    queries = []

    def not_found(timeout=3.0, **_):
        queries.append(1)
        return None

    monkeypatch.setattr(pyclient.mdns, "discover_vrchat_oscquery", not_found)
    client = VRCFTClient(send_port=free_udp_port(), recv_port=0)
    client.start()
    assert wait_for(lambda: queries)
    started = time.monotonic()
    client.stop()
    assert time.monotonic() - started < 0.5


def test_stop_does_not_wait_for_an_mdns_query_in_flight(monkeypatch):
    release = threading.Event()
    in_query = threading.Event()

    def slow_query(timeout=3.0, **_):
        in_query.set()
        release.wait(timeout)
        return None

    monkeypatch.setattr(pyclient.mdns, "discover_vrchat_oscquery", slow_query)
    client = VRCFTClient(send_port=free_udp_port(), recv_port=0)
    client.start()
    try:
        assert in_query.wait(3.0)
        started = time.monotonic()
        client.stop()
        assert time.monotonic() - started < 0.5
    finally:
        release.set()


def test_failed_avatar_fetch_forgets_the_endpoint_and_discovery_runs_again(monkeypatch):
    """~1 s: with an endpoint known, the discovery loop re-checks it once a second
    (a literal in client.py), and the test has to wait for that re-check."""
    queries = []
    monkeypatch.setattr(pyclient, "fetch_avatar_oscquery", lambda host, port: None)

    def found(timeout=3.0, **_):
        queries.append(1)
        return (LOCALHOST, 9100 + len(queries))

    monkeypatch.setattr(pyclient.mdns, "discover_vrchat_oscquery", found)
    client = VRCFTClient(recv_port=0, use_oscquery=False)
    client._oscquery_endpoint = (LOCALHOST, 9100)
    client.avatar = AvatarInfo("avtr_loaded")  # an avatar is loaded: discovery does not fetch on its own

    stop = threading.Event()
    thread = threading.Thread(target=client._discover_loop, args=(stop,), daemon=True)
    thread.start()
    try:
        client._resolve_avatar("")  # e.g. /avatar/change after VRChat restarted
        assert client._oscquery_endpoint is None
        assert wait_for(lambda: client._oscquery_endpoint == (LOCALHOST, 9101))
        assert len(queries) == 1  # endpoint known until then: no mDNS traffic
    finally:
        stop.set()
        thread.join(2.0)
    assert not thread.is_alive()
