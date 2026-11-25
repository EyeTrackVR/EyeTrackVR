"""OSCManager / OSCSender: the send boundary (endpoint validation, value
sanitising, failure isolation), message routing, and restarts on settings changes."""

import logging
import socket
from unittest import mock

import numpy as np
import pytest

from eye import EyeId
from osc import osc as osc_module
from osc.osc import (
    SafeOSCClient,
    _DROP,
    _ThrottledLog,
    sanitize_osc_value,
    validate_osc_endpoint,
)
from osc.osc_message import OSCMessage, OSCMessageType
from tests import SimpleUDPClientMock
from tests.osc_helpers import (
    collect_stray_garbage,
    LOCALHOST,
    eye_msg,
    fast_server_shutdown,
    isolate_gaze_outputs,
    no_multicast,
    no_pyvrcft_discovery,
    run_messages,
    running_manager,
    udp_listener,
    use_free_ports,
    wait_for,
    wait_until_sent,
)


@pytest.fixture(autouse=True, scope="module")
def _main_thread_gc():
    collect_stray_garbage()


@pytest.fixture(autouse=True)
def _private_gaze_outputs(monkeypatch, tmp_path):
    isolate_gaze_outputs(monkeypatch, tmp_path)
    fast_server_shutdown(monkeypatch)


def _module_msg(**data):
    return OSCMessage(type=OSCMessageType.VRCFT_MODULE_INFO, data=data)


# ------------------------------------------------------- endpoint validation


@pytest.mark.parametrize(
    "address, port",
    [
        ("127.0.0.1", 70000),  # OverflowError in sendto/getaddrinfo
        ("127.0.0.1", 0),
        ("127.0.0.1", -5),
        ("127.0.0.1", "not-a-port"),
        ("127.0.0.1", None),
        ("   ", 9000),
        ("", 9000),
        (None, 9000),
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
    with caplog.at_level(logging.ERROR, logger="osc.osc"):
        manager = run_messages(main_config_v2_params, [eye_msg()] * 3)
    assert manager.osc_sender.vrc_client is None
    assert "not in the range 1-65535" in caplog.text


def test_sender_survives_unresolvable_host(main_config_v2_params, caplog):
    """SimpleUDPClient resolves eagerly; a gaierror used to kill the thread.
    (Patched rather than resolving a real bad name, to avoid DNS traffic.)"""
    main_config_v2_params.settings.gui_osc_address = "no-such-host.invalid"

    def fake_client(address, port):
        if address == "no-such-host.invalid":
            raise socket.gaierror(11001, "getaddrinfo failed")
        return SimpleUDPClientMock(address, port)

    with mock.patch("osc.osc.udp_client.SimpleUDPClient", fake_client), caplog.at_level(logging.ERROR, "osc.osc"):
        with running_manager(main_config_v2_params, mock_udp=False) as (manager, msg_queue):
            msg_queue.put(eye_msg())
            msg_queue.put(_module_msg(command="set", field="x", value=1))
            wait_until_sent(msg_queue)
            assert manager.osc_sender_thread.is_alive()
    assert manager.osc_sender.vrc_client is None
    # The VRCFT module endpoint was valid and keeps working.
    assert manager.osc_sender.vrcft_client.messages == [("/command/set/x/", 1)]
    assert "no-such-host.invalid" in caplog.text


def test_pyvrcft_not_started_with_invalid_endpoint(main_config, caplog):
    main_config.settings.gui_pyvrcft = True
    main_config.settings.gui_osc_port = 99999
    with caplog.at_level(logging.ERROR, logger="osc.osc"):
        manager = run_messages(main_config, [eye_msg()])
    assert manager.osc_sender.pyvrcft_sender.client is None
    assert "pyVRCFT sender not started" in caplog.text


def test_pyvrcft_start_failure_leaves_the_sender_running(main_config, caplog):
    main_config.settings.gui_pyvrcft = True
    with (
        mock.patch("osc.pyvrcft_sender.VRCFTClient.start", side_effect=OSError("no sockets")),
        caplog.at_level(logging.ERROR, logger="osc.osc"),
    ):
        manager = run_messages(main_config, [eye_msg(x=0.3)])
    assert "Failed to start pyVRCFT sender" in caplog.text
    # No fallback to the classic params either: pyVRCFT replaces them.
    assert manager.osc_sender.vrc_client.messages == []


# ------------------------------------------------- values at the send boundary


def test_sanitize_converts_numpy_scalars():
    out = sanitize_osc_value(np.float32(0.25))
    assert type(out) is float and out == 0.25
    assert type(sanitize_osc_value(np.int64(3))) is int
    assert type(sanitize_osc_value(np.bool_(True))) is bool
    assert type(sanitize_osc_value(np.array(1.5))) is float
    vec = sanitize_osc_value([np.float32(1.0), np.float64(2.0), 1.0])
    assert vec == [1.0, 2.0, 1.0] and all(type(v) is float for v in vec)
    assert sanitize_osc_value((np.float32(1.0), 2)) == (1.0, 2)
    assert sanitize_osc_value(np.array([1.0, 2.0], dtype=np.float32)) == [1.0, 2.0]
    assert sanitize_osc_value("str") == "str"
    assert sanitize_osc_value(7) == 7


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), -float("inf"), np.float32("nan"), [0.0, float("nan"), 1.0]],
)
def test_sanitize_drops_non_finite(value):
    assert sanitize_osc_value(value) is _DROP


def test_handler_exception_does_not_stop_sender(main_config_v2_params, caplog):
    calls = []
    real = osc_module.VRChatOSCSender.output_osc_info

    def flaky(self, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return real(self, **kwargs)

    with (
        mock.patch.object(osc_module.VRChatOSCSender, "output_osc_info", flaky),
        caplog.at_level(logging.ERROR, logger="osc.osc"),
    ):
        manager = run_messages(main_config_v2_params, [eye_msg(x=0.3), eye_msg(x=0.4)])
    assert len(calls) == 2
    assert ("/avatar/parameters/v2/EyeX", 0.4) in manager.osc_sender.vrc_client.messages
    assert "Failed to send OSC message" in caplog.text


def test_message_without_a_handler_is_logged_and_skipped(main_config_v2_params, caplog):
    unknown = OSCMessage(type="not-a-type", data=None)
    with caplog.at_level(logging.WARNING, logger="osc.osc"):
        manager = run_messages(main_config_v2_params, [unknown, eye_msg(x=0.4)])
    assert "without a handler" in caplog.text
    assert ("/avatar/parameters/v2/EyeX", 0.4) in manager.osc_sender.vrc_client.messages


def test_safe_client_survives_sendto_errors_and_throttles(caplog, monkeypatch):
    class FailingClient:
        def __init__(self):
            self.calls = 0

        def send_message(self, address, value):
            self.calls += 1
            raise OSError(10051, "unreachable")

    now = [100.0]
    monkeypatch.setattr(osc_module.time, "monotonic", lambda: now[0])
    failing = FailingClient()
    safe = SafeOSCClient(failing, "VRChat", _ThrottledLog(interval=60))
    with caplog.at_level(logging.WARNING, logger="osc.osc"):
        for _ in range(200):
            safe.send_message("/avatar/parameters/v2/EyeX", 0.5)
        assert failing.calls == 200
        assert [r.getMessage() for r in caplog.records if "send of" in r.getMessage()] == [
            "VRChat OSC send of /avatar/parameters/v2/EyeX failed: [Errno 10051] unreachable"
        ]
        now[0] += 61  # next interval: one line, with how many were held back
        safe.send_message("/avatar/parameters/v2/EyeX", 0.5)
    assert caplog.records[-1].getMessage().endswith("(199 similar suppressed)")


# ------------------------------------------------------------------- routing


def test_vrcft_module_mode_routes_eye_params_to_the_module(main_config_v2_params):
    main_config_v2_params.settings.gui_use_module = True
    manager = run_messages(main_config_v2_params, [eye_msg(x=0.4)])
    sender = manager.osc_sender
    assert ("/avatar/parameters/v2/EyeX", 0.4) in sender.vrcft_client.messages
    assert sender.vrc_client.messages == []


def test_vrcft_module_commands_need_command_field_and_value(main_config_v2_params):
    manager = run_messages(
        main_config_v2_params,
        [
            _module_msg(command="set", field="threshold", value=0),  # 0 is a value
            _module_msg(command="set", field="threshold"),
            _module_msg(field="threshold", value=1),
            _module_msg(command="set", value=1),
        ],
    )
    assert manager.osc_sender.vrcft_client.messages == [("/command/set/threshold/", 0)]


# ----------------------------------------------------------------- restarts


SENDER_CHANGES = [
    ("gui_osc_port", 9100, lambda s: s.vrc_client.port == 9100),
    ("gui_osc_address", "localhost", lambda s: s.vrc_client.osc_address == "localhost"),
    ("gui_VRCFTModulePort", 9101, lambda s: s.vrcft_client.port == 9101),
    ("gui_VRCFTModuleIPAddress", "localhost", lambda s: s.vrcft_client.osc_address == "localhost"),
    ("gui_use_module", True, lambda s: s.vrcft_client.messages and not s.vrc_client.messages),
    ("gui_foveation_gaze", False, lambda s: s.foveation_client is None),
    # Read only when pyVRCFT starts (native face / its receive port): the restart is the contract.
    ("gui_pyvrcft_native_face", False, lambda s: True),
    ("gui_osc_receiver_port", 9102, lambda s: True),
]


@pytest.mark.parametrize("key, value, applied", SENDER_CHANGES, ids=[c[0] for c in SENDER_CHANGES])
def test_changed_output_setting_restarts_the_sender(main_config_v2_params, key, value, applied):
    s = main_config_v2_params.settings
    with running_manager(main_config_v2_params) as (manager, msg_queue):
        msg_queue.put(eye_msg())
        wait_until_sent(msg_queue)
        old_sender, old_thread = manager.osc_sender, manager.osc_sender_thread

        manager.update({key: getattr(s, key)})  # named but unchanged: no restart
        manager.update({"gui_osc_recenter_address": "/x"})  # unrelated setting
        assert manager.osc_sender is old_sender

        setattr(s, key, value)
        manager.update({key: value})
        assert manager.osc_sender is not old_sender
        assert not old_thread.is_alive()
        msg_queue.put(eye_msg())
        wait_until_sent(msg_queue)
        assert applied(manager.osc_sender)


@pytest.mark.parametrize(
    "key, value",
    [("gui_osc_oscquery", False), ("gui_osc_receiver_port", None), ("gui_osc_address", "localhost")],
)
def test_changed_receive_setting_rebinds_the_receiver(main_config, monkeypatch, key, value):
    no_multicast(monkeypatch)
    s = main_config.settings
    use_free_ports(s)
    s.gui_ROSC = True
    with running_manager(main_config) as (manager, _queue):
        old = manager.osc_receiver
        assert old.server is not None
        if value is None:
            use_free_ports(s)
            value = s.gui_osc_receiver_port
        setattr(s, key, value)
        manager.update({key: value})
        assert manager.osc_receiver is not old and manager.osc_receiver.server is not None
        if key == "gui_osc_oscquery":
            assert manager.osc_receiver.advertiser is None
            assert manager.osc_receiver.server.server_address[1] == s.gui_osc_receiver_port
        s.gui_ROSC = False
        manager.update({"gui_ROSC": False})
        assert manager.osc_receiver is None


def test_rosc_toggle_releases_and_reclaims_receiver_port(main_config, monkeypatch):
    """pyVRCFT binds the receive port only while ROSC is off; toggling ROSC at
    runtime must hand the port over in both directions."""
    no_pyvrcft_discovery(monkeypatch)
    no_multicast(monkeypatch)
    s = main_config.settings
    s.gui_pyvrcft = True
    s.gui_ROSC = False
    use_free_ports(s)

    def started_client():
        client = manager.osc_sender.pyvrcft_sender.client
        return client if client is not None and client._threads else None

    with udp_listener() as vrchat:
        s.gui_osc_port = vrchat.getsockname()[1]
        with running_manager(main_config, mock_udp=False) as (manager, _queue):
            assert wait_for(lambda: started_client() is not None)
            first = started_client()
            assert first.recv_port == s.gui_osc_receiver_port
            assert first._recv_sock is not None  # pyVRCFT owns the port

            s.gui_ROSC = True
            manager.update({"gui_ROSC": True})
            assert wait_for(lambda: started_client() is not None)
            second = started_client()
            assert second is not first and second.recv_port == 0
            assert manager.osc_receiver is not None
            assert manager.osc_receiver.server is not None, "receiver failed to bind"

            s.gui_ROSC = False
            manager.update({"gui_ROSC": False})
            assert manager.osc_receiver is None
            assert wait_for(lambda: started_client() is not None)
            third = started_client()
            assert third.recv_port == s.gui_osc_receiver_port
            assert third._recv_sock is not None


def test_manager_forwards_avatar_signals_to_pyvrcft(main_config):
    """EyeTrackVR's receiver owns the input port, so pyVRCFT hears avatar switches
    and the full-face flag only through these listeners."""
    events = []

    class Client:
        def notify_avatar_change(self, avatar_id):
            events.append(("change", avatar_id))

        def notify_full_face_tracking(self, value):
            events.append(("face", value))

    manager = osc_module.OSCManager(config=main_config, osc_message_in_queue=None)

    def deliver(address, data):
        for listener in manager.listeners[address]:
            listener(OSCMessage(type=OSCMessageType.EYE_INFO, data=data))

    deliver(osc_module.AVATAR_CHANGE_ADDRESS, "avtr_early")  # no sender yet: ignored
    manager.osc_sender = mock.Mock(pyvrcft_sender=mock.Mock(client=Client()))
    deliver(osc_module.AVATAR_CHANGE_ADDRESS, "avtr_test")
    deliver(osc_module.AVATAR_CHANGE_ADDRESS, 3)  # wrong type: ignored
    deliver(osc_module.FULL_FACE_ADDRESS, True)
    deliver(osc_module.FULL_FACE_ADDRESS, "yes")  # wrong type: ignored
    assert events == [("change", "avtr_test"), ("face", True)]


def test_eyebrows_go_to_pyvrcft_in_pyvrcft_mode(main_config, monkeypatch):
    no_pyvrcft_discovery(monkeypatch)
    s = main_config.settings
    s.gui_pyvrcft = True
    use_free_ports(s)
    main_config.eye_display_id = EyeId.BOTH
    brow = OSCMessage(type=OSCMessageType.EYEBROW_INFO, data=(EyeId.LEFT, 1.0))
    with running_manager(main_config) as (manager, msg_queue):
        msg_queue.put(brow)
        wait_until_sent(msg_queue)
        shapes = manager.osc_sender.pyvrcft_sender.data.shapes
        assert (shapes["BrowInnerUpLeft"], shapes["BrowInnerUpRight"]) == (1.0, 0.0)
    assert manager.osc_sender.vrc_client.messages == []
