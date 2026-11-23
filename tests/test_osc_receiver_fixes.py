"""OSC receiver: binds where VRChat can reach it, and follows edits to the
recenter / recalibrate addresses without an app restart."""

import socket
import time
from queue import Queue
from types import SimpleNamespace

import pytest
from pythonosc.udp_client import SimpleUDPClient

from osc.osc import OSCManager, OSCReceiver
from osc.oscquery import MDNSResponder


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.mark.parametrize(
    "address,expected",
    [
        ("127.0.0.1", "127.0.0.1"),
        (" 127.0.0.1 ", "127.0.0.1"),
        ("localhost", "localhost"),
        ("192.168.1.50", "0.0.0.0"),  # VRChat on another PC
        ("vr-pc.local", "0.0.0.0"),
        ("auto", "0.0.0.0"),
    ],
)
def test_bind_address_follows_where_vrchat_runs(address, expected):
    fake = SimpleNamespace(config=SimpleNamespace(gui_osc_address=address))
    assert OSCReceiver._bind_address(fake) == expected


def test_remote_target_still_binds_the_receiver(main_config):
    s = main_config.settings
    s.gui_osc_address = "192.0.2.10"  # TEST-NET-1: never an address of this machine
    s.gui_osc_receiver_port = _free_udp_port()
    receiver = OSCReceiver(None, main_config, {})
    try:
        assert receiver.server is not None
        assert receiver.server.server_address == ("0.0.0.0", s.gui_osc_receiver_port)
    finally:
        receiver.server.server_close()


def _manager(main_config, oscquery=False):
    s = main_config.settings
    s.gui_ROSC = True
    s.gui_osc_oscquery = oscquery
    s.gui_osc_receiver_port = _free_udp_port()
    manager = OSCManager(config=main_config, osc_message_in_queue=Queue())
    received = []
    manager.register_setting_listeners("gui_osc_recenter_address", [received.append])
    manager.setup_receiver()
    return manager, received


def test_edited_recenter_address_takes_effect_without_restart(main_config):
    s = main_config.settings
    manager, received = _manager(main_config)
    try:
        old = s.gui_osc_recenter_address
        receiver = manager.osc_receiver
        s.gui_osc_recenter_address = "/avatar/parameters/my_recenter"
        manager.update({"gui_osc_recenter_address": s.gui_osc_recenter_address})
        assert manager.osc_receiver is receiver  # fixed port: no restart needed
        assert old not in manager.listeners

        port = receiver.server.server_address[1]
        client = SimpleUDPClient("127.0.0.1", port)
        client.send_message(old, True)
        client.send_message("/avatar/parameters/my_recenter", True)
        assert _wait_for(lambda: received)
        time.sleep(0.1)
        assert len(received) == 1 and received[0].data is True
    finally:
        manager.stop_receiver(timeout=5)


def test_edited_address_shares_listeners_without_dropping_others(main_config):
    s = main_config.settings
    manager = OSCManager(config=main_config, osc_message_in_queue=Queue())
    recenter, recalibrate = [], []
    s.gui_osc_recalibrate_address = s.gui_osc_recenter_address  # both on one address
    manager.register_setting_listeners("gui_osc_recenter_address", [recenter.append])
    manager.register_setting_listeners("gui_osc_recalibrate_address", [recalibrate.append])
    shared = s.gui_osc_recenter_address

    s.gui_osc_recenter_address = "/avatar/parameters/elsewhere"
    manager.update({"gui_osc_recenter_address": s.gui_osc_recenter_address})
    assert manager.listeners[shared] == [recalibrate.append]
    assert manager.listeners["/avatar/parameters/elsewhere"] == [recenter.append]


def test_edited_address_is_readvertised_over_oscquery(main_config, monkeypatch):
    monkeypatch.setattr(MDNSResponder, "start", lambda self: None)
    monkeypatch.setattr(MDNSResponder, "stop", lambda self: None)
    s = main_config.settings
    manager, _received = _manager(main_config, oscquery=True)
    try:
        assert manager.osc_receiver.advertiser is not None
        s.gui_osc_recenter_address = "/avatar/parameters/my_recenter"
        manager.update({"gui_osc_recenter_address": s.gui_osc_recenter_address})
        advertiser = manager.osc_receiver.advertiser
        assert "/avatar/parameters/my_recenter" in advertiser.index
    finally:
        manager.stop_receiver(timeout=5)
