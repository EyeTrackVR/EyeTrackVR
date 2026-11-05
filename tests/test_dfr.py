"""Per-game DFR (ovr/dfr.py): off until enabled per game, remembered, live on/off and
quality through the FR-Utility registry mode, one attach per game process, anti-cheat
games never attached. Plus the SteamVR game monitor's socket protocol."""

import json
from pathlib import Path
import socket
import sys
import threading
import time
import tomllib
import types
from types import SimpleNamespace

import pytest

from config import EyeTrackSettingsConfig
from ovr import dfr, dfr_monitor

LANG_EN = Path(__file__).resolve().parents[1] / "eyetrackapp" / "lang" / "en.toml"


class FakeRegistry:
    def __init__(self):
        self.writes = []

    def set_mode(self, mode):
        self.writes.append(mode)

    def get_mode(self):
        return self.writes[-1] if self.writes else None


class FakeConfig:
    def __init__(self, tool_dir=""):
        self.settings = SimpleNamespace(gui_dfr_tool_dir=tool_dir, gui_dfr_games={}, gui_foveation_gaze=True)
        self.saves = 0

    def update(self, data, save=False):
        for k, v in data.items():
            setattr(self.settings, k, v)
        self.saves += int(save)


@pytest.fixture()
def tool(tmp_path):
    d = tmp_path / "PimaxMagic4All"
    d.mkdir()
    for name in dfr.TOOL_FILES:
        (d / name).write_bytes(b"x" + name.encode())
    return d


def make(tool_dir, *, steamvr=True, dfr_ui=False, system_ok=True):
    attaches = []
    c = dfr.DfrController(
        config=FakeConfig(str(tool_dir)),
        registry=FakeRegistry(),
        attach=lambda d, pid: attaches.append(pid) or True,
        steamvr_running=lambda: steamvr,
        dfr_ui_running=lambda: dfr_ui,
        system_files_ok=lambda d: system_ok,
    )
    c._ensure_monitor = lambda running: None  # no real monitor process in tests
    c.PROCESS_CHECK_S = 0.0
    return c, attaches


def scene(c, pid, key="steam.app.546560", name="Half-Life: Alyx", exe=""):
    c.on_monitor_message({"type": "scene", "pid": pid, "key": key, "name": name, "exe": exe})


# ------------------------------------------------------------------ decisions


def test_steamvr_off_touches_nothing(tool):
    c, attaches = make(tool, steamvr=False)
    assert c.tick().state == dfr.STEAMVR_OFF
    assert c.registry.writes == [] and attaches == []


def test_new_game_is_off_and_never_touched(tool):
    c, attaches = make(tool)
    scene(c, 100)
    st = c.status()
    assert (st.state, st.game_name, st.enabled, st.mode) == (dfr.OFF, "Half-Life: Alyx", False, "balanced")
    assert c.registry.writes == [] and attaches == []


def test_enable_attaches_once_and_writes_quality_live(tool):
    c, attaches = make(tool)
    scene(c, 100)
    c.set_game("steam.app.546560", enabled=True)
    assert c.status().state == dfr.ATTACHED
    assert attaches == [100] and c.registry.writes == [dfr.MODES["balanced"]]
    entry = c.config.settings.gui_dfr_games["steam.app.546560"]
    assert entry == {"enabled": True, "mode": "balanced", "name": "Half-Life: Alyx"} and c.config.saves == 1

    c.set_game("steam.app.546560", mode="maximum")  # live quality change, no re-attach
    assert attaches == [100] and c.registry.writes[-1] == dfr.MODES["maximum"]

    c.set_game("steam.app.546560", enabled=False)  # live off
    assert c.status().state == dfr.OFF and c.registry.writes[-1] == dfr.MODE_OFF
    c.set_game("steam.app.546560", enabled=True)  # same process: already injected
    assert attaches == [100] and c.registry.writes[-1] == dfr.MODES["maximum"]

    for _ in range(3):
        c.tick()
    assert attaches == [100] and c.registry.writes.count(dfr.MODES["maximum"]) == 2  # no rewrite spam


def test_remembered_game_attaches_again_after_restart_and_others_are_off(tool):
    c, attaches = make(tool)
    scene(c, 100)
    c.set_game("steam.app.546560", enabled=True, mode="minimum")
    scene(c, 0)
    assert c.status().state == dfr.NO_GAME and c.registry.writes[-1] == dfr.MODE_OFF
    scene(c, 200)  # the game restarted: new process
    assert attaches == [100, 200] and c.registry.writes[-1] == dfr.MODES["minimum"]
    scene(c, 300, key="steam.app.111", name="Other Game")  # not enabled
    assert c.status().state == dfr.OFF and c.registry.writes[-1] == dfr.MODE_OFF and attaches == [100, 200]


def test_anti_cheat_games_are_never_attached(tool, tmp_path):
    c, attaches = make(tool)
    scene(c, 100, key="steam.app.438100", name="VRChat")
    c.set_game("steam.app.438100", enabled=True)
    assert c.status().state == dfr.BLOCKED and "Easy Anti-Cheat" in c.status().detail
    assert attaches == [] and c.registry.writes == []

    game = tmp_path / "SomeGame"
    (game / "EasyAntiCheat").mkdir(parents=True)
    (game / "bin").mkdir()
    scene(c, 101, key="steam.app.222", name="EAC Game", exe=str(game / "bin" / "game.exe"))
    c.set_game("steam.app.222", enabled=True)
    assert c.status().state == dfr.BLOCKED and attaches == []


def test_setup_states(tool, tmp_path):
    c, attaches = make(tmp_path / "missing")
    scene(c, 100)
    assert c.status().state == dfr.TOOL_MISSING
    c, attaches = make(tool, system_ok=False)
    scene(c, 100)
    c.set_game("steam.app.546560", enabled=True)
    assert c.status().state == dfr.NEEDS_SYSTEM_FILES and attaches == []
    c, attaches = make(tool, dfr_ui=True)
    scene(c, 100)
    c.set_game("steam.app.546560", enabled=True)
    assert c.status().state == dfr.DFR_UI_RUNNING and attaches == []


def test_one_time_setup_shows_while_steamvr_is_closed(tool, tmp_path):
    # Installing the system files needs SteamVR closed, so the step can't hide then.
    c, _ = make(tool, steamvr=False, system_ok=False)
    st = c.tick()
    assert st.state == dfr.NEEDS_SYSTEM_FILES and not st.steamvr
    c, _ = make(tmp_path / "missing", steamvr=False)
    assert c.tick().state == dfr.TOOL_MISSING
    c, _ = make(tool, steamvr=False)
    assert c.tick().state == dfr.STEAMVR_OFF
    c, _ = make(tool)
    st = c.tick()
    assert st.state == dfr.NO_GAME and st.steamvr


def test_failed_attach_is_not_retried_every_tick(tool):
    calls = []
    c, _ = make(tool)
    c._attach = lambda d, pid: calls.append(pid) and False
    scene(c, 100)
    c.set_game("steam.app.546560", enabled=True)
    c.tick()
    assert c.status().state == dfr.ATTACH_FAILED and calls == [100] and c.registry.writes == []


def test_steamvr_itself_is_not_a_game(tool):
    c, _ = make(tool)
    scene(c, 50, key="system.vrdashboard", name="Dashboard")
    assert c.status().state == dfr.NO_GAME
    c.set_game("system.vrdashboard", enabled=True)
    assert c.config.settings.gui_dfr_games == {}


def test_stop_turns_dfr_off_only_if_it_was_on(tool):
    c, _ = make(tool)
    scene(c, 100)
    c.stop()
    assert c.registry.writes == []
    c.set_game("steam.app.546560", enabled=True)
    c.stop()
    assert c.registry.writes[-1] == dfr.MODE_OFF


def test_settings_model_keeps_per_game_choices():
    s = EyeTrackSettingsConfig(
        gui_dfr_tool_dir="C:\\tools\\pm4a", gui_dfr_games={"steam.app.1": {"enabled": True, "mode": "debug"}}
    )
    again = EyeTrackSettingsConfig(**json.loads(s.model_dump_json()))
    assert again.gui_dfr_games == {"steam.app.1": {"enabled": True, "mode": "debug"}}
    assert EyeTrackSettingsConfig().gui_dfr_games == {} and EyeTrackSettingsConfig().gui_dfr_tool_dir == ""


# ------------------------------------------------------------------ helpers


def test_tool_and_system_file_checks(tool, tmp_path):
    assert dfr.tool_missing_files(str(tool)) == []
    (tool / "MagicAttach_x64.exe").unlink()
    assert dfr.tool_missing_files(str(tool)) == ["MagicAttach_x64.exe"]
    assert dfr.tool_missing_files("") == list(dfr.TOOL_FILES)

    system32 = tmp_path / "System32"
    system32.mkdir()
    assert not dfr.system_files_installed(str(tool), system32)
    for name in dfr.SYSTEM_FILES:
        (system32 / name).write_bytes((tool / name).read_bytes())
    assert dfr.system_files_installed(str(tool), system32)
    (system32 / "VarjoLib.dll").write_bytes(b"older copy")
    assert not dfr.system_files_installed(str(tool), system32)


def test_anti_cheat_detection(tmp_path):
    assert dfr.anti_cheat_reason("steam.app.546560", "") == ""
    clean = tmp_path / "Clean" / "game.exe"
    clean.parent.mkdir()
    assert dfr.anti_cheat_reason("k", str(clean)) == ""
    be = tmp_path / "BE" / "Binaries" / "Win64" / "game.exe"
    be.parent.mkdir(parents=True)
    (tmp_path / "BE" / "BattlEye").mkdir()
    assert dfr.anti_cheat_reason("k", str(be)) == "BattlEye"


# ------------------------------------------------------------------ monitor protocol


def test_controller_reads_monitor_lines_over_a_socket(tool):
    c, attaches = make(tool)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    fake_process = SimpleNamespace(poll=lambda: None, wait=lambda timeout=None: 0, kill=lambda: None)
    c._monitor = fake_process
    reader = threading.Thread(target=c._read_monitor, args=(fake_process, listener))
    reader.start()

    client = socket.create_connection(("127.0.0.1", port))
    client.sendall(
        (json.dumps({"type": "scene", "pid": 77, "key": "steam.app.546560", "name": "HL:A", "exe": ""}) + "\n").encode()
    )
    deadline = time.monotonic() + 3
    while c.status().game_key != "steam.app.546560" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert c.status().game_name == "HL:A"
    client.close()  # monitor exited: the game is gone
    reader.join(3)
    assert c.status().state == dfr.NO_GAME


def _fake_openvr(polls_before_quit=3):
    vr = types.ModuleType("openvr")
    vr.VRApplication_Background = 3
    vr.VREvent_Quit = 700
    vr.VRApplicationProperty_Name_String = 2000
    state = {"polls": 0}

    class Event:
        eventType = 0

    class Apps:
        def getCurrentSceneProcessId(self):
            return 4242

        class function_table:  # the raw OpenVR call the monitor uses first
            @staticmethod
            def getApplicationKeyByProcessId(pid, buffer, size):
                buffer.value = b"steam.app.546560"
                return 0

        def getApplicationKeyByProcessId(self, pid):
            raise AssertionError("pyopenvr's wrapper is only the fallback")

        def getApplicationPropertyString(self, key, prop):
            return "Half-Life: Alyx"

    class System:
        def pollNextEvent(self, event):
            state["polls"] += 1
            if state["polls"] > polls_before_quit and event.eventType != vr.VREvent_Quit:
                event.eventType = vr.VREvent_Quit
                return True
            return False

        def acknowledgeQuit_Exiting(self):
            state["acked"] = True

    vr.init = lambda kind: None
    vr.shutdown = lambda: state.__setitem__("shutdown", True)
    vr.VRApplications = Apps
    vr.VRSystem = System
    vr.VREvent_t = Event
    return vr, state


def test_monitor_reports_the_game_then_quits_with_steamvr(monkeypatch):
    vr, state = _fake_openvr()
    monkeypatch.setitem(sys.modules, "openvr", vr)
    monkeypatch.setattr(dfr_monitor, "POLL_S", 0.01)
    monkeypatch.setattr(dfr_monitor, "process_image_path", lambda pid: "C:\\Games\\hlvr.exe")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("rc", dfr_monitor.run(listener.getsockname()[1])))
    t.start()
    conn, _ = listener.accept()
    lines = [json.loads(line) for line in conn.makefile("r", encoding="utf-8")]
    t.join(3)
    listener.close()
    assert lines[0] == {
        "type": "scene",
        "pid": 4242,
        "key": "steam.app.546560",
        "name": "Half-Life: Alyx",
        "exe": "C:\\Games\\hlvr.exe",
    }
    assert lines[-1] == {"type": "quit"}
    assert result["rc"] == 0 and state.get("acked") and state.get("shutdown")


def test_monitor_exits_when_the_app_closes_the_socket(monkeypatch):
    vr, state = _fake_openvr(polls_before_quit=10**9)
    monkeypatch.setitem(sys.modules, "openvr", vr)
    monkeypatch.setattr(dfr_monitor, "POLL_S", 0.01)
    monkeypatch.setattr(dfr_monitor, "process_image_path", lambda pid: "")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    t = threading.Thread(target=dfr_monitor.run, args=(listener.getsockname()[1],))
    t.start()
    conn, _ = listener.accept()
    conn.makefile("r").readline()
    conn.close()
    t.join(3)
    listener.close()
    assert not t.is_alive() and state.get("shutdown")


@pytest.mark.parametrize(
    "state",
    [
        dfr.UNSUPPORTED,
        dfr.STEAMVR_OFF,
        dfr.NO_GAME,
        dfr.TOOL_MISSING,
        dfr.NEEDS_SYSTEM_FILES,
        dfr.DFR_UI_RUNNING,
        dfr.BLOCKED,
        dfr.OFF,
        dfr.ATTACHED,
        dfr.ATTACH_FAILED,
    ],
)
def test_panel_shows_every_state(state, monkeypatch):
    tk = pytest.importorskip("tkinter")
    from settings import dfr_panel

    # The real strings: a state without one raises KeyError instead of showing its key.
    with open(LANG_EN, "rb") as file:
        strings = tomllib.load(file)["dfr"]
    monkeypatch.setattr(dfr_panel, "tr", lambda key, **fmt: strings[key.split(".")[1]].format(**fmt))

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("needs a display")
    root.withdraw()
    status = dfr.Status(state, game_key="steam.app.1", game_name="Game", enabled=True, mode="minimum", detail="EAC")
    controller = types.SimpleNamespace(status=lambda: status, tool_dir=lambda: "")
    config = types.SimpleNamespace(settings=types.SimpleNamespace(gui_foveation_gaze=False))
    try:
        panel = dfr_panel.DfrPanel(controller, config)
        panel.build(root)
        panel._refresh()
        assert panel.enabled_var.get() is True
        assert panel.status_label.cget("text").strip()
        expected = "disabled" if state == dfr.BLOCKED else "normal"
        assert str(panel.enabled_cb.cget("state")) == expected
    finally:
        root.destroy()
