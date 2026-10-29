"""Regression tests: OSC output must survive bad settings and bad values.

Every socket here is bound to / sends to 127.0.0.1 only; mDNS/OSCQuery
discovery is disabled wherever the embedded pyVRCFT client is started.
"""

import functools
import logging
import math
import random
import socket
import struct
import threading
from queue import Queue
from time import monotonic, sleep
from unittest import mock

import numpy as np
import pydantic
import pytest

from osc import PyVRCFTSender as pyvrcft_sender_module
from osc.osc import (
    OSCManager,
    SafeOSCClient,
    _DROP,
    _ThrottledLog,
    sanitize_osc_value,
    validate_osc_endpoint,
)
from osc.OSCMessage import OSCMessage, OSCMessageType
from pyvrcft import VRCFTClient
from pyvrcft import osc as pyosc
from pyvrcft.avatar import AvatarInfo, AvatarParameter
from pyvrcft.params import BinaryBitSlot, FloatSlot
from settings.modules.AdvancedOSCSettingsModule import AdvancedOSCValidationModel
from tests import EyeInfoMock, SimpleUDPClientMock

LOCALHOST = "127.0.0.1"


# ----------------------------------------------------------------- helpers


def _wait_until_sent(msg_queue, timeout=5.0):
    deadline = monotonic() + timeout
    while msg_queue.unfinished_tasks and monotonic() < deadline:
        sleep(0.005)
    assert msg_queue.unfinished_tasks == 0, "sender stopped consuming the queue"


def _wait_for(predicate, timeout=3.0):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.01)
    return predicate()


def _free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((LOCALHOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def udp_listener():
    """A local UDP socket standing in for VRChat's OSC input."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCALHOST, 0))
    sock.settimeout(0.2)
    yield sock
    sock.close()


def _drain(sock, settle=0.3):
    """All (address, args) received on sock until it stays quiet for `settle`."""
    out = []
    deadline = monotonic() + settle
    while monotonic() < deadline:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        out.extend(pyosc.parse(data))
        deadline = monotonic() + settle
    return out


def _eye_msg(eye_id=0, **kw):
    fields = dict(x=0.0, y=0.0, blink=1.0, pupil_dilation=0.0, avg_velocity=0.0)
    fields.update(kw)
    return OSCMessage(type=OSCMessageType.EYE_INFO, data=(eye_id, EyeInfoMock(**fields)))


def _started_pyvrcft(manager):
    """The running embedded pyVRCFT client, once its threads are up."""
    client = manager.osc_sender.pyvrcft_sender.client
    return client if client is not None and client._threads else None


def _start_manager(config):
    msg_queue = Queue()
    manager = OSCManager(config=config, osc_message_in_queue=msg_queue)
    manager.start()
    return manager, msg_queue


# --------------------------------------------- 1. OSCSender endpoint validation


@pytest.mark.parametrize(
    "address,port",
    [
        ("127.0.0.1", 70000),  # OverflowError in sendto/getaddrinfo
        ("127.0.0.1", 0),
        ("127.0.0.1", -5),
        ("127.0.0.1", "not-a-port"),
        ("   ", 9000),
        ("", 9000),
    ],
)
def test_validate_osc_endpoint_rejects_bad_values(address, port):
    assert validate_osc_endpoint("test", address, port) is None


def test_validate_osc_endpoint_accepts_and_normalizes():
    assert validate_osc_endpoint("test", " 127.0.0.1 ", "9000") == (LOCALHOST, 9000)
    assert validate_osc_endpoint("test", "localhost", 65535) == ("localhost", 65535)


@pytest.mark.parametrize("port", [70000, 0, "abc"])
def test_sender_survives_invalid_port(main_config_v2_params, port, caplog):
    main_config_v2_params.settings.gui_osc_port = port
    with mock.patch("osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        with caplog.at_level(logging.ERROR, logger="osc.osc"):
            manager, msg_queue = _start_manager(main_config_v2_params)
            try:
                for _ in range(3):
                    msg_queue.put(_eye_msg())
                _wait_until_sent(msg_queue)
                assert manager.osc_sender_thread.is_alive()
                assert manager.osc_sender.vrc_client is None
            finally:
                manager.shutdown()
    assert "not in the range 1-65535" in caplog.text


def test_sender_survives_unresolvable_host(main_config_v2_params, caplog):
    """SimpleUDPClient resolves eagerly; a gaierror used to kill the thread.
    (Patched rather than resolving a real bad name, to avoid DNS traffic.)"""
    main_config_v2_params.settings.gui_osc_address = "no-such-host.invalid"

    def fake_client(address, port):
        if address == "no-such-host.invalid":
            raise socket.gaierror(11001, "getaddrinfo failed")
        return SimpleUDPClientMock(address, port)

    with mock.patch("osc.osc.udp_client.SimpleUDPClient", fake_client):
        with caplog.at_level(logging.ERROR, logger="osc.osc"):
            manager, msg_queue = _start_manager(main_config_v2_params)
            try:
                msg_queue.put(_eye_msg())
                msg_queue.put(
                    OSCMessage(
                        type=OSCMessageType.VRCFT_MODULE_INFO,
                        data={"command": "set", "field": "x", "value": 1},
                    )
                )
                _wait_until_sent(msg_queue)
                assert manager.osc_sender_thread.is_alive()
                assert manager.osc_sender.vrc_client is None
                # The VRCFT module endpoint was valid and keeps working.
                assert manager.osc_sender.vrcft_client.messages == [("/command/set/x/", 1)]
            finally:
                manager.shutdown()
    assert "no-such-host.invalid" in caplog.text


def test_pyvrcft_not_started_with_invalid_endpoint(main_config, caplog):
    main_config.settings.gui_pyvrcft = True
    main_config.settings.gui_osc_port = 99999
    with mock.patch("osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        with caplog.at_level(logging.ERROR, logger="osc.osc"):
            manager, msg_queue = _start_manager(main_config)
            try:
                msg_queue.put(_eye_msg())
                _wait_until_sent(msg_queue)
                assert manager.osc_sender_thread.is_alive()
                assert manager.osc_sender.pyvrcft_sender.client is None
            finally:
                manager.shutdown()
    assert "pyVRCFT sender not started" in caplog.text


# ------------------------------------------------- 2. values at the send boundary


def test_sanitize_converts_numpy_scalars():
    out = sanitize_osc_value(np.float32(0.25))
    assert type(out) is float and out == 0.25
    assert type(sanitize_osc_value(np.int64(3))) is int
    assert type(sanitize_osc_value(np.bool_(True))) is bool
    assert type(sanitize_osc_value(np.array(1.5))) is float
    vec = sanitize_osc_value([np.float32(1.0), np.float64(2.0), 1.0])
    assert vec == [1.0, 2.0, 1.0] and all(type(v) is float for v in vec)
    assert sanitize_osc_value(np.array([1.0, 2.0], dtype=np.float32)) == [1.0, 2.0]
    assert sanitize_osc_value("str") == "str"
    assert sanitize_osc_value(7) == 7


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), -float("inf"), np.float32("nan"), [0.0, float("nan"), 1.0]],
)
def test_sanitize_drops_non_finite(value):
    assert sanitize_osc_value(value) is _DROP


def test_numpy_values_reach_the_wire(main_config_v2_params, udp_listener):
    """Real SimpleUDPClient -> local socket. np.float32 args used to raise
    ValueError inside python-osc and kill the sender thread."""
    main_config_v2_params.settings.gui_osc_port = udp_listener.getsockname()[1]
    manager, msg_queue = _start_manager(main_config_v2_params)
    try:
        msg_queue.put(
            _eye_msg(
                x=np.float32(0.25),
                y=np.int64(1),
                blink=np.float32(1.0),
                pupil_dilation=np.float64(0.5),
                squeeze=np.float32(0.5),
            )
        )
        _wait_until_sent(msg_queue)
        assert manager.osc_sender_thread.is_alive()
        received = dict(_drain(udp_listener))
    finally:
        manager.shutdown()
    assert received["/avatar/parameters/v2/EyeX"] == [0.25]
    assert received["/avatar/parameters/v2/EyeY"] == [1]
    assert received["/avatar/parameters/v2/EyeSquint"] == [0.5]
    assert received["/avatar/parameters/v2/EyeLid"] == [1.0]


def test_nan_values_are_dropped_not_fatal(main_config_v2_params):
    with mock.patch("osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        manager, msg_queue = _start_manager(main_config_v2_params)
        try:
            msg_queue.put(_eye_msg(x=float("nan"), y=0.5, pupil_dilation=float("inf")))
            msg_queue.put(_eye_msg(x=0.1, y=0.2))
            _wait_until_sent(msg_queue)
            assert manager.osc_sender_thread.is_alive()
        finally:
            manager.shutdown()
    sent = manager.osc_sender.vrc_client.messages
    assert all(not (isinstance(v, float) and not math.isfinite(v)) for _, v in sent), sent
    # Non-finite params were skipped (avatar holds last value); the rest of the
    # frame and the next frame still went out.
    assert ("/avatar/parameters/v2/EyeY", 0.5) in sent
    assert ("/avatar/parameters/v2/EyeY", 0.2) in sent
    assert [v for a, v in sent if a == "/avatar/parameters/v2/EyeX"] == [0.1]


def test_handler_exception_does_not_stop_sender(main_config_v2_params, caplog):
    calls = []

    with mock.patch("osc.osc.udp_client.SimpleUDPClient", SimpleUDPClientMock):
        manager, msg_queue = _start_manager(main_config_v2_params)
        vrc_sender = manager.osc_sender.vrc_sender
        real = vrc_sender.output_osc_info

        def flaky(**kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return real(**kwargs)

        vrc_sender.output_osc_info = flaky
        try:
            with caplog.at_level(logging.ERROR, logger="osc.osc"):
                msg_queue.put(_eye_msg(x=0.3))
                msg_queue.put(_eye_msg(x=0.4))
                _wait_until_sent(msg_queue)
            assert manager.osc_sender_thread.is_alive()
        finally:
            manager.shutdown()
    assert len(calls) == 2
    assert ("/avatar/parameters/v2/EyeX", 0.4) in manager.osc_sender.vrc_client.messages
    assert "Failed to send OSC message" in caplog.text


def test_safe_client_survives_sendto_errors_and_throttles(caplog):
    class FailingClient:
        def __init__(self):
            self.calls = 0

        def send_message(self, address, value):
            self.calls += 1
            raise OSError(10051, "unreachable")

    failing = FailingClient()
    safe = SafeOSCClient(failing, "VRChat", _ThrottledLog(interval=60))
    with caplog.at_level(logging.WARNING, logger="osc.osc"):
        for _ in range(200):
            safe.send_message("/avatar/parameters/v2/EyeX", 0.5)
    assert failing.calls == 200
    assert len([r for r in caplog.records if "send of" in r.getMessage()]) == 1


def test_safe_client_without_client_is_noop():
    SafeOSCClient(None, "VRChat", _ThrottledLog()).send_message("/x", 1.0)


# ------------------------------------------------------------- 2b. pyvrcft


def test_binary_slot_handles_non_finite():
    slot = BinaryBitSlot("/avatar/parameters/v2/JawOpen1", 0, 8, False)
    assert slot.encode(float("nan")) is False
    assert slot.update(float("nan")) is None  # skipped, not sent
    assert slot.update(0.5) is not None
    f = FloatSlot("/avatar/parameters/v2/EyeLeftX")
    assert f.update(0.25) == 0.25
    assert f.update(float("inf")) is None  # holds 0.25
    assert f.update(0.25) is None  # still deduped against last good


def test_client_set_ignores_non_finite():
    client = VRCFTClient(use_oscquery=False)
    client.set("JawOpen", 0.4)
    client.set("JawOpen", float("nan"))
    client.set("EyeLeftX", float("inf"))
    assert client._values["v2/JawOpen"] == 0.4
    assert "v2/EyeLeftX" not in client._values
    client.send_direct("/tracking/eye/EyesClosedAmount", 0.2)
    client.send_direct("/tracking/eye/EyesClosedAmount", float("nan"))
    assert client._direct["/tracking/eye/EyesClosedAmount"].pending == 0.2


def _binary_avatar():
    names = ["JawOpen1", "JawOpen2", "JawOpen4"]
    params = [AvatarParameter(name=n, address=f"/avatar/parameters/FT/v2/{n}", type=bool) for n in names]
    params.append(AvatarParameter(name="EyeLeftX", address="/avatar/parameters/FT/v2/EyeLeftX", type=float))
    return AvatarInfo(id="avtr_test", name="test", parameters=params)


def test_pyvrcft_send_loop_survives_nan_in_binary_params(udp_listener):
    client = VRCFTClient(
        send_host=LOCALHOST,
        send_port=udp_listener.getsockname()[1],
        recv_port=_free_udp_port(),
        use_oscquery=False,
    )
    client.avatar = _binary_avatar()
    # Bypass set()'s guard to prove the loop itself cannot be killed by a NaN
    # reaching BinaryBitSlot.encode (int(nan * max_int) -> ValueError).
    with client._lock:
        client._values["v2/JawOpen"] = float("nan")
        client._resolve_one("v2/JawOpen")
    assert client._slots["v2/JawOpen"], "binary slots should resolve"
    client.start()
    try:
        sleep(0.1)
        send_thread = client._threads[0]
        assert send_thread.name == "pyvrcft-send" and send_thread.is_alive()
        client.set("JawOpen", 0.99)
        client.set("EyeLeftX", 0.5)
        received = _drain(udp_listener)
        assert send_thread.is_alive()
    finally:
        client.stop()
    by_addr = {a: v for a, v in received}
    assert by_addr["/avatar/parameters/FT/v2/EyeLeftX"] == [0.5]
    assert by_addr["/avatar/parameters/FT/v2/JawOpen4"] == [True]


def test_pyvrcft_sendto_failure_is_throttled(caplog):
    class FailingSock:
        def sendto(self, data, addr):
            raise OSError(10065, "host unreachable")

        def close(self):
            pass

    client = VRCFTClient(
        send_port=_free_udp_port(),
        recv_port=_free_udp_port(),
        use_oscquery=False,
        force_relevant=True,
    )
    client.start()
    real_sock = client._send_sock
    client._send_sock = FailingSock()
    try:
        with caplog.at_level(logging.ERROR, logger="pyvrcft"):
            for i in range(30):  # ~30 send ticks, each with a changed value
                client.set("JawOpen", i / 100)
                sleep(0.01)
            assert client._threads[0].is_alive()
    finally:
        client.stop()
        real_sock.close()
    failures = [r for r in caplog.records if "OSC send to" in r.getMessage()]
    assert len(failures) == 1


def test_pyvrcft_sender_holds_last_value_on_nan():
    sender = pyvrcft_sender_module.PyVRCFTSender()
    eye = sender.data.eye.left
    info = EyeInfoMock(x=0.2, y=0.1, blink=1.0, pupil_dilation=0.5, avg_velocity=0)
    sender._apply_eye(eye, info, 1.0)
    bad = EyeInfoMock(x=float("nan"), y=float("inf"), blink=1.0, pupil_dilation=float("nan"), avg_velocity=0)
    sender._apply_eye(eye, bad, float("nan"))
    assert (eye.gaze_x, eye.gaze_y, eye.openness, eye.pupil_diameter_mm) == (0.2, 0.1, 1.0, 0.5)
    sender._set_shape("EyeSquintLeft", 0.3)
    sender._set_shape("EyeSquintLeft", float("nan"))
    assert sender.data.shapes["EyeSquintLeft"] == 0.3


# --------------------------------------------- 4. malformed OSC bundle parsing


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


VALID_MSG = pyosc.encode_message("/avatar/change", ["avtr_x"])
HEADER = pyosc.BUNDLE_HEADER + pyosc.IMMEDIATELY


@pytest.mark.parametrize(
    "data,expected",
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
    ],
)
def test_malformed_bundle_parse_terminates(data, expected):
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


def test_recv_thread_survives_malformed_packet():
    port = _free_udp_port()
    client = VRCFTClient(send_port=_free_udp_port(), recv_port=port, use_oscquery=False)
    seen = []
    client.on_message = lambda address, args: seen.append(address)
    client.start()
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        tx.sendto(HEADER + struct.pack(">i", -12) + b"\x00" * 16, (LOCALHOST, port))
        tx.sendto(pyosc.encode_message("/still/alive", [1.0]), (LOCALHOST, port))
        assert _wait_for(lambda: "/still/alive" in seen)
        recv_thread = next(t for t in client._threads if t.name == "pyvrcft-recv")
        assert recv_thread.is_alive()
    finally:
        tx.close()
        client.stop()


# --------------------------------------------- 3. ROSC toggle restarts sender


def test_rosc_is_a_sender_trigger_key():
    assert "gui_ROSC" in OSCManager.SENDER_TRIGGER_KEYS
    assert "gui_ROSC" in OSCManager.RECEIVER_TRIGGER_KEYS


def test_rosc_toggle_releases_and_reclaims_receiver_port(main_config, udp_listener):
    s = main_config.settings
    s.gui_pyvrcft = True
    s.gui_ROSC = False
    s.gui_osc_address = LOCALHOST
    s.gui_osc_port = udp_listener.getsockname()[1]
    s.gui_osc_receiver_port = _free_udp_port()
    s.gui_VRCFTModulePort = _free_udp_port()

    no_mdns = functools.partial(VRCFTClient, use_oscquery=False)
    with mock.patch.object(pyvrcft_sender_module, "VRCFTClient", no_mdns):
        manager, msg_queue = _start_manager(main_config)
        try:
            assert _wait_for(lambda: _started_pyvrcft(manager) is not None)
            first = manager.osc_sender.pyvrcft_sender.client
            assert first.recv_port == s.gui_osc_receiver_port
            assert first._recv_sock is not None  # pyVRCFT owns the port

            # Turn "Receive OSC" on at runtime.
            s.gui_ROSC = True
            manager.update({"gui_ROSC": True})
            assert _wait_for(lambda: _started_pyvrcft(manager) is not None)
            second = manager.osc_sender.pyvrcft_sender.client
            assert second is not first and second.recv_port == 0
            assert manager.osc_receiver is not None
            assert manager.osc_receiver.server is not None, "receiver failed to bind"

            # And off again: the receiver lets go and pyVRCFT reclaims the port.
            s.gui_ROSC = False
            manager.update({"gui_ROSC": False})
            assert manager.osc_receiver is None
            assert _wait_for(lambda: _started_pyvrcft(manager) is not None)
            third = manager.osc_sender.pyvrcft_sender.client
            assert third.recv_port == s.gui_osc_receiver_port
            assert third._recv_sock is not None
        finally:
            manager.shutdown()


# ------------------------------------------------- settings-module validation


def _adv_model(**overrides):
    values = dict(
        gui_osc_port="9000",
        gui_osc_address="127.0.0.1",
        gui_osc_receiver_port="9001",
        gui_osc_recenter_address="/avatar/parameters/etvr_recenter",
        gui_osc_recalibrate_address="/avatar/parameters/etvr_recalibrate",
    )
    values.update(overrides)
    return AdvancedOSCValidationModel(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"gui_osc_port": "70000"},
        {"gui_osc_port": "0"},
        {"gui_osc_receiver_port": "-1"},
        {"gui_osc_port": "abc"},
        {"gui_osc_address": ""},
        {"gui_osc_address": "bad host"},
    ],
)
def test_advanced_osc_settings_reject_invalid(overrides):
    with pytest.raises(pydantic.ValidationError):
        _adv_model(**overrides)


def test_advanced_osc_settings_accept_valid():
    m = _adv_model(gui_osc_address=" localhost ", gui_osc_port="65535")
    assert m.gui_osc_address == "localhost"
    assert m.gui_osc_port == 65535
