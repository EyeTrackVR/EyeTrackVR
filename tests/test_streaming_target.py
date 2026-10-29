"""The "auto" OSC address: finding the PC a Steam Frame streams from."""

import types

import pytest

from osc import streaming_target as st

# Shaped like ~/.local/share/Steam/logs/vrlink.txt on a retail Frame (2026-10).
SESSION_USB = """\
Sat Oct 24 2026 10:51:51.866085 [Info] - Starting session with ID: 01c574ff
Sat Oct 24 2026 10:51:51.866496 [Info] - SVLDataLinkUber::AddAndInitLinkTransfer 10.0.0.50 / PEERED: false
Sat Oct 24 2026 10:51:51.867107 [Info] - SVLDataLinkUber::AddAndInitLinkTransfer 10.35.78.1 / PEERED: false
Sat Oct 24 2026 10:51:51.867620 [Info] - SVLDataLinkTransferUDP::SetPeer 10.86.200.233 -> 10.86.200.234 (Connect: 0 / Resource temporarily unavailable)
Sat Oct 24 2026 10:51:51.867757 [Info] - SVLDataLinkUber::AddAndInitLinkTransfer 10.86.200.233 / PEERED: true
Sat Oct 24 2026 10:51:51.874058 [Info] - Output stream (-1) state changed: connecting
Sat Oct 24 2026 10:51:52.191505 [Info] - Output stream (176) state changed: streaming
Sat Oct 24 2026 10:51:54.244834 [Info] - Input stream (182) state changed: unconnected
"""
SESSION_HOTSPOT = """\
Thu Oct 15 2026 21:26:03.242288 [Info] - Starting session with ID: 01d87b6a
Thu Oct 15 2026 21:26:03.248276 [Info] - SVLDataLinkTransferUDP::SetPeer 10.35.78.1 -> 10.35.78.29 (Connect: 0 / Resource temporarily unavailable)
Thu Oct 15 2026 21:26:03.248382 [Info] - SVLDataLinkUber::AddAndInitLinkTransfer 10.35.78.1 / PEERED: true
Thu Oct 15 2026 21:26:03.589401 [Info] - Output stream (191) state changed: streaming
"""
ENDED = "Sat Oct 24 2026 10:52:39.469341 [Info] - Output stream (176) state changed: unconnected\n"

REMOTE = """\
[2026-10-24 12:10:08] Received broadcast message from client 4353674097254835025 (SMALL): 10.86.200.234:27036
[2026-10-24 12:47:27] Received broadcast message from client 4353674097254835025 (SMALL): 4353674097254835025:27036
[2026-10-24 12:47:31] Received broadcast message from client 4353674097254835025 (SMALL): 10.0.0.79:27036
[2026-10-24 12:47:32] SoftAP: Disabled streaming mode
"""


def test_live_session_gives_the_peered_link():
    # The input stream dropping is not the end of the session; the output is.
    assert st.vrlink_peer(SESSION_USB) == "10.86.200.234"
    assert st.vrlink_peer(SESSION_HOTSPOT) == "10.35.78.29"


def test_only_the_newest_session_counts():
    assert st.vrlink_peer(SESSION_HOTSPOT + ENDED + SESSION_USB) == "10.86.200.234"
    assert st.vrlink_peer(SESSION_USB + SESSION_HOTSPOT) == "10.35.78.29"


def test_an_ended_or_unpeered_session_gives_nothing():
    assert st.vrlink_peer(SESSION_USB + ENDED) is None
    assert st.vrlink_peer(SESSION_USB.replace("PEERED: true", "PEERED: false")) is None
    assert st.vrlink_peer("") is None


def test_remote_play_takes_the_newest_ip_broadcast():
    assert st.remote_play_peer(REMOTE) == "10.0.0.79"
    assert st.remote_play_peer(REMOTE.replace("10.0.0.79", "10.0.0.255")) == "10.86.200.234"
    assert st.remote_play_peer("") is None


def _logs(tmp_path, vrlink="", remote=""):
    (tmp_path / "vrlink.txt").write_text(vrlink, encoding="utf-8")
    (tmp_path / "remote_connections.txt").write_text(remote, encoding="utf-8")
    return str(tmp_path)


def test_resolve_order(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "mdns_vrchat_host", lambda: "10.0.0.42")
    assert st.resolve(_logs(tmp_path, SESSION_USB, REMOTE)) == ("10.86.200.234", "Steam Link VR session")
    assert st.resolve(_logs(tmp_path, SESSION_USB + ENDED, REMOTE)) == ("10.0.0.79", "Steam remote play")
    assert st.resolve(_logs(tmp_path)) == ("10.0.0.42", "VRChat mDNS")
    assert st.resolve(_logs(tmp_path), use_mdns=False) == ("127.0.0.1", "no streaming PC found")
    assert st.resolve(str(tmp_path / "missing"), use_mdns=False)[0] == "127.0.0.1"


def test_is_auto():
    assert st.is_auto(" Auto ") and not st.is_auto("127.0.0.1") and not st.is_auto("")


# ------------------------------------------------------------- OSC manager


@pytest.fixture
def manager(monkeypatch):
    import osc.osc as osc_mod

    settings = types.SimpleNamespace(gui_osc_address="auto")
    m = osc_mod.OSCManager.__new__(osc_mod.OSCManager)
    m.settings = settings
    m._auto_address = None
    restarts = []
    m.stop_sender = lambda *a, **k: restarts.append("stop")
    m.setup_sender = lambda: restarts.append("setup")
    import threading

    m._restart_lock = threading.Lock()
    m._auto_stop = threading.Event()
    return m, settings, restarts, osc_mod


def test_manager_resolves_auto_and_keeps_typed_addresses(manager, monkeypatch):
    m, settings, _restarts, osc_mod = manager
    calls = []

    def resolve(use_mdns=True):
        calls.append(use_mdns)
        return "10.86.200.234", "Steam Link VR session"

    monkeypatch.setattr(osc_mod.streaming_target, "resolve", resolve)
    assert m.osc_target_address() == "10.86.200.234"
    assert calls == [False]  # startup never waits on mDNS
    settings.gui_osc_address = " 192.168.1.20 "
    assert m.osc_target_address() == "192.168.1.20"


def test_watcher_restarts_the_sender_only_when_the_pc_changes(manager, monkeypatch):
    m, _settings, restarts, osc_mod = manager
    answers = iter(
        [
            ("10.0.0.79", "Steam remote play"),
            ("10.0.0.79", "Steam remote play"),
            ("10.86.200.234", "Steam Link VR session"),
        ]
    )
    m._auto_address = "10.0.0.79"

    def resolve(use_mdns=True):
        try:
            return next(answers)
        except StopIteration:
            m._auto_stop.set()
            return "10.86.200.234", "Steam Link VR session"

    monkeypatch.setattr(osc_mod.streaming_target, "resolve", resolve)
    monkeypatch.setattr(osc_mod.OSCManager, "AUTO_CHECK_INTERVAL", 0.001)
    m._watch_auto_target()
    assert restarts == ["stop", "setup"] and m._auto_address == "10.86.200.234"
