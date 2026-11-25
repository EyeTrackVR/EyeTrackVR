"""OSC receiver: binds where VRChat can reach it (OSCQuery-advertised free port on
this PC, the fixed port otherwise), delivers to listeners, and follows edits to
the recenter / recalibrate addresses without an app restart."""

import logging
import socket
import threading
import time
import urllib.request
from queue import Queue
from types import SimpleNamespace

import pytest
from pythonosc.udp_client import SimpleUDPClient

from osc.osc import AVATAR_CHANGE_ADDRESS, FULL_FACE_ADDRESS, OSCManager, OSCReceiver
from osc.oscquery import MDNSResponder
from tests.osc_helpers import (
    collect_stray_garbage,
    LOCALHOST,
    fast_server_shutdown,
    free_udp_port,
    no_multicast,
    wait_for,
)


@pytest.fixture(autouse=True, scope="module")
def _main_thread_gc():
    collect_stray_garbage()


@pytest.fixture(autouse=True)
def _fast_shutdown(monkeypatch):
    fast_server_shutdown(monkeypatch)


@pytest.fixture
def receiver_config(main_config):
    main_config.settings.gui_osc_receiver_port = free_udp_port()
    return main_config


@pytest.fixture
def running_receiver():
    """Start an OSCReceiver's run loop; always stopped and joined afterwards."""
    started = []

    def start(config, listeners):
        cancel = threading.Event()
        receiver = OSCReceiver(cancel, config, listeners)
        thread = threading.Thread(target=receiver.run)
        thread.start()
        started.append((receiver, cancel, thread))
        return receiver

    yield start
    for receiver, cancel, thread in started:
        cancel.set()
        thread.join(5)
        assert not thread.is_alive()
        if receiver.server is not None:
            receiver.server.server_close()


@pytest.mark.parametrize(
    "address, expected",
    [
        ("127.0.0.1", "127.0.0.1"),
        (" 127.0.0.1 ", "127.0.0.1"),
        ("127.0.0.2", "127.0.0.2"),
        ("localhost", "localhost"),
        ("192.168.1.50", "0.0.0.0"),  # VRChat on another PC
        ("vr-pc.local", "0.0.0.0"),
        ("auto", "0.0.0.0"),
    ],
)
def test_bind_address_follows_where_vrchat_runs(address, expected):
    fake = SimpleNamespace(config=SimpleNamespace(gui_osc_address=address))
    assert OSCReceiver._bind_address(fake) == expected


def test_receiver_advertises_a_free_port_and_receives(receiver_config, running_receiver, monkeypatch):
    no_multicast(monkeypatch)
    settings = receiver_config.settings  # VRChat on this PC (127.0.0.1)
    received = []
    manager = OSCManager(config=receiver_config, osc_message_in_queue=Queue())
    manager.register_setting_listeners("gui_osc_recenter_address", [received.append])
    receiver = running_receiver(receiver_config, manager.listeners)

    host, port = receiver.server.server_address
    assert host == LOCALHOST and port != settings.gui_osc_receiver_port
    advertiser = receiver.advertiser
    assert advertiser.osc_port == port
    for address in (AVATAR_CHANGE_ADDRESS, FULL_FACE_ADDRESS, settings.gui_osc_recenter_address):
        assert address in advertiser.index
    SimpleUDPClient(LOCALHOST, port).send_message(settings.gui_osc_recenter_address, True)
    assert wait_for(lambda: received)
    assert received[0].data is True


def test_receiver_stop_withdraws_the_advertisement_and_frees_the_port(receiver_config, monkeypatch):
    no_multicast(monkeypatch)
    cancel = threading.Event()
    receiver = OSCReceiver(cancel, receiver_config, {})
    thread = threading.Thread(target=receiver.run)
    thread.start()
    http_port = receiver.advertiser.http_port
    osc_port = receiver.server.server_address[1]
    cancel.set()
    thread.join(5)
    assert not thread.is_alive() and receiver.advertiser is None
    with pytest.raises(OSError):
        urllib.request.urlopen(f"http://{LOCALHOST}:{http_port}/", timeout=2)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rebind:
        rebind.bind((LOCALHOST, osc_port))  # free for a restarted pyVRCFT sender


def test_receiver_falls_back_to_fixed_port_when_mdns_fails(receiver_config, monkeypatch):
    def unavailable(self):
        raise OSError("mDNS port unavailable")

    monkeypatch.setattr(MDNSResponder, "start", unavailable)
    receiver = OSCReceiver(threading.Event(), receiver_config, {})
    try:
        assert receiver.advertiser is None
        assert receiver.server.server_address[1] == receiver_config.settings.gui_osc_receiver_port
    finally:
        receiver.server.server_close()


def test_auto_port_turned_off_uses_the_fixed_port(receiver_config):
    receiver_config.settings.gui_osc_oscquery = False
    receiver = OSCReceiver(threading.Event(), receiver_config, {})
    try:
        assert receiver.advertiser is None
        assert receiver.server.server_address[1] == receiver_config.settings.gui_osc_receiver_port
    finally:
        receiver.server.server_close()


def test_vrchat_on_another_pc_uses_the_fixed_port_on_every_interface(receiver_config):
    # OSCQuery listens on this PC only, which a remote VRChat can't reach; binding
    # the remote IP itself fails and silently ends in-VR recenter.
    settings = receiver_config.settings
    settings.gui_osc_address = "192.0.2.10"  # TEST-NET-1: never this machine
    receiver = OSCReceiver(threading.Event(), receiver_config, {})
    try:
        assert receiver.advertiser is None
        assert receiver.server.server_address == ("0.0.0.0", settings.gui_osc_receiver_port)
    finally:
        receiver.server.server_close()


def test_fixed_port_in_use_logs_and_runs_without_receiving(receiver_config, caplog):
    settings = receiver_config.settings
    settings.gui_osc_oscquery = False
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other_app:
        other_app.bind((LOCALHOST, 0))
        settings.gui_osc_receiver_port = other_app.getsockname()[1]
        with caplog.at_level(logging.ERROR, logger="osc.osc"):
            receiver = OSCReceiver(threading.Event(), receiver_config, {})
    assert receiver.server is None
    assert "Failed to start OSC receiver" in caplog.text
    started = time.monotonic()
    receiver.run()  # returns at once instead of waiting for a cancel
    assert time.monotonic() - started < 1.0


def test_auto_port_is_the_default():
    from config import EyeTrackSettingsConfig

    assert EyeTrackSettingsConfig().gui_osc_oscquery is True


# ------------------------------------------------- editable listen addresses


def _manager(main_config, oscquery=False):
    s = main_config.settings
    s.gui_ROSC = True
    s.gui_osc_oscquery = oscquery
    s.gui_osc_receiver_port = free_udp_port()
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

        client = SimpleUDPClient(LOCALHOST, receiver.server.server_address[1])
        client.send_message(old, False)  # handled first: the server is one thread, in order
        client.send_message("/avatar/parameters/my_recenter", True)
        assert wait_for(lambda: received)
        assert [m.data for m in received] == [True]
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
    no_multicast(monkeypatch)
    s = main_config.settings
    manager, _received = _manager(main_config, oscquery=True)
    try:
        assert manager.osc_receiver.advertiser is not None
        s.gui_osc_recenter_address = "/avatar/parameters/my_recenter"
        manager.update({"gui_osc_recenter_address": s.gui_osc_recenter_address})
        assert "/avatar/parameters/my_recenter" in manager.osc_receiver.advertiser.index
    finally:
        manager.stop_receiver(timeout=5)
