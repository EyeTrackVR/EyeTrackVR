"""Per-game DFR (ovr/dfr.py): off until enabled per game, remembered, live on/off and
quality through the FR-Utility registry values, attach decided by what the game process
really holds, nothing attached before the gaze output is up, anti-cheat games never
attached. Plus the one-step setup (ovr/dfr_setup.py) and the SteamVR game monitor's
socket protocol."""

import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import tomllib
import types
from types import SimpleNamespace
import zipfile

import pytest

from config import EyeTrackSettingsConfig
from ovr import dfr, dfr_monitor, dfr_setup

LANG_EN = Path(__file__).resolve().parents[1] / "eyetrackapp" / "lang" / "en.toml"
GAME = "steam.app.823500"  # a Direct3D 11 OpenVR game with no foveation of its own


class FakeRegistry:
    def __init__(self, **values):
        self.values = dict(values)
        self.writes = []  # "mode" writes, in order

    def set(self, name, value):
        self.values[name] = value
        if name == "mode":
            self.writes.append(value)

    def get(self, name):
        return self.values.get(name)


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


def make(tool_dir, *, steamvr=True, dfr_ui=False, system_ok=True, gaze=True, loads=True, registry=None):
    """``loads``: what the game's module list says after MagicAttach ran. True: the DLLs
    load at once, False: not until the test adds the pid to ``c.injected``, None: the
    process can't be inspected."""
    attaches = []

    def attach(tool_dir, pid):
        attaches.append(pid)
        if loads:
            c.injected.add(pid)
        return True

    def has_module(pid):
        if pid in c.injected:
            return True
        return None if loads is None else False

    c = dfr.DfrController(
        config=FakeConfig(str(tool_dir)),
        registry=registry or FakeRegistry(),
        attach=attach,
        steamvr_running=lambda: steamvr,
        dfr_ui_running=lambda: dfr_ui,
        system_files_ok=lambda d: system_ok,
        gaze_ready=lambda: c.gaze,
        has_module=has_module,
        tracking=lambda exe: c.tracker,
        is_active=lambda pid: c.in_use,
        module_loaded=lambda pid, dll: dll in c.modules,
    )
    c.modules = {"d3d11.dll", "openvr_api.dll"}  # a Direct3D 11 OpenVR game
    c.gaze, c.tracker, c.injected, c.in_use = gaze, dfr.TRACKING_UNKNOWN, set(), True
    c._ensure_monitor = lambda running: None  # no real monitor process in tests
    c.PROCESS_CHECK_S = c.TOOL_CHECK_S = c.SYSTEM_CHECK_S = c.LOG_READ_S = 0.0
    return c, attaches


def scene(c, pid, key=GAME, name="Half-Life: Alyx", exe=""):
    c.on_monitor_message({"type": "scene", "pid": pid, "key": key, "name": name, "exe": exe})


# ------------------------------------------------------------------ decisions


def test_steamvr_off_touches_nothing(tool):
    c, attaches = make(tool, steamvr=False)
    assert c.tick().state == dfr.STEAMVR_OFF
    assert c.registry.values == {} and attaches == []


def test_new_game_is_off_and_never_touched(tool):
    c, attaches = make(tool)
    scene(c, 100)
    st = c.status()
    assert (st.state, st.game_name, st.enabled, st.mode) == (dfr.OFF, "Half-Life: Alyx", False, "balanced")
    assert c.registry.values == {} and attaches == []


def test_enable_attaches_once_and_writes_quality_live(tool):
    c, attaches = make(tool)
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.tick().state == dfr.ATTACHED
    assert attaches == [100] and c.registry.writes == [dfr.MODES["balanced"]]
    entry = c.config.settings.gui_dfr_games[GAME]
    assert entry == {"enabled": True, "mode": "balanced", "name": "Half-Life: Alyx"} and c.config.saves == 1

    c.set_game(GAME, mode="maximum")  # live quality change, no re-attach
    assert attaches == [100] and c.registry.writes[-1] == dfr.MODES["maximum"]

    c.set_game(GAME, enabled=False)  # live off
    assert c.status().state == dfr.OFF and c.registry.writes[-1] == dfr.MODE_OFF
    c.set_game(GAME, enabled=True)  # same process: already injected
    assert attaches == [100] and c.registry.writes[-1] == dfr.MODES["maximum"]

    for _ in range(3):
        c.tick()
    assert attaches == [100] and c.registry.writes.count(dfr.MODES["maximum"]) == 2  # no rewrite spam


def test_settings_are_in_the_registry_before_the_game_is_attached(tool):
    # The injected code reads them as it loads; DFR-UI's "force fixed" must not survive.
    c, _ = make(tool, registry=FakeRegistry(ignore_eye_tracking=1, invert_y_axis=1))
    seen = []
    c._attach = lambda d, pid: seen.append(dict(c.registry.values)) or True
    scene(c, 100)
    c.set_game(GAME, enabled=True, mode="minimum")
    assert seen == [{"ignore_eye_tracking": 0, "invert_y_axis": 0, "mode": dfr.MODES["minimum"]}]
    c.set_game(GAME, invert_y=True)  # per game, live
    assert c.registry.values["invert_y_axis"] == 1 and c.status().invert_y


def test_mode_changed_behind_our_back_is_put_back(tool):
    c, _ = make(tool)
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    c.registry.values["mode"] = dfr.MODES["debug"]  # e.g. DFR-UI opened and closed
    c.tick()
    assert c.registry.values["mode"] == dfr.MODES["balanced"]


def test_remembered_game_attaches_again_after_restart_and_others_are_off(tool):
    c, attaches = make(tool)
    scene(c, 100)
    c.set_game(GAME, enabled=True, mode="minimum")
    scene(c, 0)
    assert c.status().state == dfr.NO_GAME and c.registry.writes[-1] == dfr.MODE_OFF
    scene(c, 200)  # the game restarted: new process
    assert attaches == [100, 200] and c.registry.writes[-1] == dfr.MODES["minimum"]
    scene(c, 300, key="steam.app.111", name="Other Game")  # not enabled
    assert c.status().state == dfr.OFF and c.registry.writes[-1] == dfr.MODE_OFF and attaches == [100, 200]


def test_game_back_in_front_is_not_attached_twice(tool):
    c, attaches = make(tool)
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    scene(c, 0)
    scene(c, 100)  # same process again
    assert attaches == [100] and c.tick().state == dfr.ATTACHED


def test_app_restart_finds_the_game_already_injected(tool):
    # A fresh controller (the app restarted) while the game still runs with the DLLs in.
    c, attaches = make(tool, registry=FakeRegistry(mode=dfr.MODES["maximum"]))
    c.injected.add(100)
    c.config.settings.gui_dfr_games = {GAME: {"enabled": True, "mode": "minimum"}}
    scene(c, 100)
    assert attaches == [] and c.status().state == dfr.ATTACHED
    assert c.registry.values["mode"] == dfr.MODES["minimum"]

    c, attaches = make(tool, registry=FakeRegistry(mode=dfr.MODES["maximum"]))
    c.injected.add(100)
    scene(c, 100)  # this game is off in the app, but the last run left it foveated
    assert c.status().state == dfr.OFF and c.registry.values["mode"] == dfr.MODE_OFF and attaches == []


def test_a_mode_left_by_dfr_ui_is_not_touched_for_a_game_we_never_injected(tool):
    c, _ = make(tool, registry=FakeRegistry(mode=dfr.MODES["maximum"]))
    scene(c, 100)
    assert c.status().state == dfr.OFF and c.registry.writes == []


def test_nothing_is_attached_until_the_gaze_output_is_up(tool):
    # The injected code picks its eye tracker once: attaching early means fixed foveation.
    c, attaches = make(tool, gaze=False)
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.status().state == dfr.GAZE_OFF and attaches == [] and c.registry.values == {}
    c.gaze = True
    c.tick()
    assert attaches == [100]
    c.gaze = False  # gaze going away later does not undo a loaded game
    assert c.tick().state == dfr.ATTACHED


def test_attach_is_confirmed_from_the_games_module_list(tool):
    c, attaches = make(tool, loads=False)
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.status().state == dfr.ATTACHING and c.registry.values["mode"] == dfr.MODES["balanced"]
    c.injected.add(100)
    assert c.tick().state == dfr.ATTACHED and attaches == [100]


def test_injected_but_unused_is_not_reported_as_on(tool):
    # Seen live: attached to a running game, the injected DLL sat there and the game's
    # rendering never went through it. "On" would be untrue.
    c, attaches = make(tool)
    c.in_use = False
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.tick().state == dfr.ATTACHING  # give the game a moment to pick it up
    c.ATTACH_CONFIRM_S = 0.0
    assert c.tick().state == dfr.IDLE and attaches == [100]
    assert c.registry.values["mode"] == dfr.MODES["balanced"]  # kept, in case it starts late
    c.in_use = True
    assert c.tick().state == dfr.ATTACHED
    c.in_use = None  # a process that can no longer be inspected stays as it was
    assert c.tick().state == dfr.ATTACHED


def test_game_that_never_loads_the_dlls_fails_and_can_be_retried(tool):
    c, attaches = make(tool, loads=False)
    c.ATTACH_CONFIRM_S = 0.0
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.tick().state == dfr.ATTACH_FAILED and attaches == [100]
    assert c.registry.values["mode"] == dfr.MODES["balanced"]  # kept: the DLLs may load late
    c.tick()
    assert attaches == [100]  # not retried every tick
    c.retry_attach()
    assert attaches == [100, 100]
    c.injected.add(100)
    assert c.tick().state == dfr.ATTACHED


def test_process_that_cannot_be_inspected_is_trusted_after_magic_attach(tool):
    c, attaches = make(tool, loads=None)  # e.g. an elevated game
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.tick().state == dfr.ATTACHED
    scene(c, 0)
    scene(c, 100)
    assert attaches == [100] and c.status().state == dfr.ATTACHED


def test_status_says_whether_the_game_follows_the_eyes(tool):
    c, _ = make(tool)
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.tick().tracking == dfr.TRACKING_UNKNOWN
    c.tracker = "VRChat OSC (EyeTrackVR)"
    assert c.tick().tracking == "VRChat OSC (EyeTrackVR)"


# ------------------------------------------------------------------ method per game


def test_known_and_detected_methods():
    d3d11_openvr = {"d3d11.dll", "openvr_api.dll"}.__contains__
    assert dfr.detect_method("steam.app.1", "", d3d11_openvr) == (dfr.METHOD_INJECT, "")
    assert dfr.detect_method("steam.app.546560", "", d3d11_openvr) == (dfr.METHOD_NATIVE, "")  # Half-Life: Alyx
    assert dfr.detect_method("steam.app.223750", "", d3d11_openvr) == (dfr.METHOD_OPENXR, "")  # DCS World
    assert dfr.detect_method("pid.7", "D:\\DCS World\\bin\\DCS.exe", d3d11_openvr) == (dfr.METHOD_OPENXR, "")
    openxr = {"d3d11.dll", "openxr_loader.dll"}.__contains__
    assert dfr.detect_method("steam.app.1", "", openxr) == (dfr.METHOD_OPENXR, "")
    both = {"d3d11.dll", "openxr_loader.dll", "openvr_api.dll"}.__contains__  # OpenVR game that ships the loader
    assert dfr.detect_method("steam.app.1", "", both) == (dfr.METHOD_INJECT, "")
    vulkan = {"vulkan-1.dll", "openvr_api.dll"}.__contains__
    assert dfr.detect_method("steam.app.1", "", vulkan) == (dfr.METHOD_NONE, "Vulkan")
    assert dfr.detect_method("steam.app.1", "", lambda dll: None) == (dfr.METHOD_INJECT, "")  # can't inspect


def test_native_and_openxr_games_are_never_injected(tool):
    c, attaches = make(tool)
    c.config.settings.gui_dfr_games = {"steam.app.546560": {"enabled": True, "mode": "maximum"}}
    scene(c, 100, key="steam.app.546560")  # Half-Life: Alyx: it foveates itself
    st = c.status()
    assert (st.state, st.method, st.method_choice) == (dfr.NATIVE, dfr.METHOD_NATIVE, dfr.METHOD_AUTO)
    assert attaches == [] and c.registry.values == {}

    c.modules = {"d3d11.dll", "openxr_loader.dll"}
    scene(c, 200, key="steam.app.999")
    c.set_game("steam.app.999", enabled=True)
    assert c.status().state == dfr.OPENXR and attaches == []

    c.modules = {"vulkan-1.dll", "openvr_api.dll"}
    scene(c, 300, key="steam.app.998")
    c.set_game("steam.app.998", enabled=True)
    assert (c.status().state, c.status().detail) == (dfr.RENDERER, "Vulkan") and attaches == []


def test_method_can_be_overridden_per_game(tool):
    c, attaches = make(tool)
    scene(c, 100, key="steam.app.546560")
    c.set_game("steam.app.546560", enabled=True, method=dfr.METHOD_INJECT)  # the user knows better
    assert c.tick().state == dfr.ATTACHED and attaches == [100]
    assert c.config.settings.gui_dfr_games["steam.app.546560"]["method"] == dfr.METHOD_INJECT
    c.set_game("steam.app.546560", method=dfr.METHOD_NONE)
    assert c.status().state == dfr.DISABLED and c.registry.values["mode"] == dfr.MODE_OFF
    c.set_game("steam.app.546560", method=dfr.METHOD_AUTO)
    assert c.status().state == dfr.NATIVE
    assert "method" not in c.config.settings.gui_dfr_games["steam.app.546560"]  # automatic is not stored


def test_detection_follows_the_game_while_it_starts_then_settles(tool):
    c, attaches = make(tool)
    c.modules = {"vulkan-1.dll"}  # nothing Direct3D yet
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.status().state == dfr.RENDERER and attaches == []
    c.modules = {"vulkan-1.dll", "d3d11.dll", "openvr_api.dll"}  # the renderer came up a moment later
    assert c.tick().state in (dfr.ATTACHING, dfr.ATTACHED) and attaches == [100]
    c.METHOD_SETTLE_S = 0.0
    c.modules = set()
    assert c.tick().method == dfr.METHOD_INJECT  # settled: later module changes don't flip it


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
    c.set_game(GAME, enabled=True)
    assert c.status().state == dfr.NEEDS_SYSTEM_FILES and attaches == []
    c, attaches = make(tool, dfr_ui=True)
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    assert c.status().state == dfr.DFR_UI_RUNNING and attaches == []


def test_nothing_runs_until_setup_is_done(tool, tmp_path):
    # No SteamVR polling and no monitor process for someone who never set DFR up.
    polls, monitors = [], []
    c, _ = make(tmp_path / "missing")
    c._steamvr_running = lambda: polls.append(1) or True
    c._ensure_monitor = monitors.append
    assert c.tick().state == dfr.TOOL_MISSING
    assert polls == [] and monitors == [False]
    c.set_tool_dir(str(tool))
    assert c.status().state == dfr.NO_GAME and polls and monitors[-1] is True


def test_setup_states_show_while_steamvr_is_closed(tool, tmp_path):
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


def test_magic_attach_that_cannot_start_is_not_retried_every_tick(tool):
    calls = []
    c, _ = make(tool)
    c._attach = lambda d, pid: calls.append(pid) and False
    scene(c, 100)
    c.set_game(GAME, enabled=True)
    c.tick()
    assert c.status().state == dfr.ATTACH_FAILED and calls == [100]
    assert c.registry.values["mode"] == dfr.MODE_OFF


def test_steamvr_itself_is_not_a_game(tool):
    c, _ = make(tool)
    scene(c, 50, key="system.vrdashboard", name="Dashboard")
    assert c.status().state == dfr.NO_GAME
    c.set_game("system.vrdashboard", enabled=True)
    assert c.config.settings.gui_dfr_games == {}


def test_junk_from_the_monitor_is_ignored(tool):
    c, _ = make(tool)
    c.on_monitor_message({"type": "scene", "pid": "soon", "key": None})
    assert c.status().state == dfr.NO_GAME


def test_stop_turns_dfr_off_only_if_it_was_on(tool):
    c, _ = make(tool)
    scene(c, 100)
    c.stop()
    assert c.registry.writes == []
    scene(c, 100)
    c.set_game(GAME, enabled=True)
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
    assert not dfr.system_files_installed(str(tool), system32) and not dfr.system_files_present(system32)
    for name in dfr.SYSTEM_FILES:
        (system32 / name).write_bytes((tool / name).read_bytes())
    assert dfr.system_files_installed(str(tool), system32)
    (system32 / "VarjoLib.dll").write_bytes(b"older copy")
    assert not dfr.system_files_installed(str(tool), system32) and dfr.system_files_present(system32)


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe")
def test_system_files_command_copies_into_a_folder_with_spaces(tmp_path):
    source = tmp_path / "Pimax Magic (copy)"
    source.mkdir()
    for name in dfr.SYSTEM_FILES:
        (source / name).write_bytes(b"new " + name.encode())
    system32 = tmp_path / "System 32"
    system32.mkdir()
    (system32 / "VarjoLib.dll").write_bytes(b"old")
    done = subprocess.run("cmd.exe " + dfr.system_files_command(str(source), system32))
    assert done.returncode == 0 and dfr.system_files_installed(str(source), system32)
    with pytest.raises(ValueError):
        dfr.system_files_command(str(tmp_path / "a&b"), system32)


def test_anti_cheat_detection(tmp_path):
    assert dfr.anti_cheat_reason(GAME, "") == ""
    clean = tmp_path / "Clean" / "game.exe"
    clean.parent.mkdir()
    assert dfr.anti_cheat_reason("k", str(clean)) == ""
    be = tmp_path / "BE" / "Binaries" / "Win64" / "game.exe"
    be.parent.mkdir(parents=True)
    (tmp_path / "BE" / "BattlEye").mkdir()
    assert dfr.anti_cheat_reason("k", str(be)) == "BattlEye"


def test_tracking_is_read_from_the_tools_log(tmp_path):
    log = tmp_path / "PvrEmu.log"
    exe = "C:\\g\\a.exe"
    assert dfr.tracking_from_log(exe, log) == dfr.TRACKING_UNKNOWN  # no log yet
    hello = f"2026-11-14 10:00:00 +0100: Hello World from '{exe}'!\n"
    log.write_text(hello)
    assert dfr.tracking_from_log(exe, log) == dfr.TRACKING_UNKNOWN
    log.write_text(hello + "x: Using eye tracking: VRChat OSC (EyeTrackVR)\nx: Foveation is active\n")
    assert dfr.tracking_from_log(exe, log) == "VRChat OSC (EyeTrackVR)"
    assert dfr.tracking_from_log("C:\\g\\other.exe", log) == dfr.TRACKING_UNKNOWN  # another game's log
    log.write_text(hello + "x: No supported eye tracking device found\n")
    assert dfr.tracking_from_log(exe, log) == dfr.TRACKING_NONE


@pytest.mark.skipif(sys.platform != "win32", reason="Windows module list")
def test_module_list_of_a_real_process():
    assert dfr.process_has_module(os.getpid(), ("kernel32.dll",)) is True
    assert dfr.process_has_module(os.getpid(), ("libmagicd3d1164.dll",)) is False
    assert dfr.process_has_module(0) is None


# ------------------------------------------------------------------ one-step setup


def _release_zip(names=dfr.TOOL_FILES, folder="PimaxMagic4All/"):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as bundle:
        for name in names:
            bundle.writestr(folder + name, b"bin " + name.encode())
        bundle.writestr(folder + "DFR-UI.exe", b"not needed")
        bundle.writestr("../escape.dll", b"zip slip")
    return data.getvalue()


def test_download_checks_the_pinned_checksum_before_unpacking(tmp_path, monkeypatch):
    archive = _release_zip()
    target = tmp_path / "tool"
    with pytest.raises(dfr_setup.SetupError) as error:
        dfr_setup.download_tool(target, fetch=lambda url: archive)
    assert error.value.reason == dfr_setup.BAD_DOWNLOAD and not target.exists()

    monkeypatch.setattr(dfr_setup, "RELEASE_SHA256", hashlib.sha256(archive).hexdigest())
    assert dfr_setup.download_tool(target, fetch=lambda url: archive) == target
    assert sorted(p.name for p in target.iterdir()) == sorted(dfr.TOOL_FILES)  # only what DFR needs
    assert dfr.tool_missing_files(str(target)) == [] and not (tmp_path / "escape.dll").exists()

    def offline(url):
        raise OSError("no network")

    with pytest.raises(dfr_setup.SetupError) as error:
        dfr_setup.download_tool(target, fetch=offline)
    assert error.value.reason == dfr_setup.DOWNLOAD_FAILED


def test_archive_without_the_tool_is_rejected(tmp_path):
    with pytest.raises(dfr_setup.SetupError) as error:
        dfr_setup.extract_tool(_release_zip(names=dfr.TOOL_FILES[:2]), tmp_path / "tool")
    assert error.value.reason == dfr_setup.BAD_DOWNLOAD and not (tmp_path / "tool").exists()
    with pytest.raises(dfr_setup.SetupError):
        dfr_setup.extract_tool(b"not a zip", tmp_path / "tool")


def test_setup_runs_only_the_steps_that_are_missing(tool, tmp_path):
    steps = []
    state = {"installed": False}

    def install(tool_dir):
        state["installed"] = True
        return True

    def run(c, *, present=False, steamvr=False, download=None):
        return dfr_setup.run(
            c,
            steps.append,
            download=download or (lambda: pytest.fail("must not download")),
            install=install,
            installed=lambda d: state["installed"],
            present=lambda: present,
            steamvr_running=lambda: steamvr,
        )

    c, _ = make(tmp_path / "missing", system_ok=False)
    assert run(c, download=lambda: tool) == str(tool) and steps == ["download", "system_files"]
    dfr_setup.finish(c, str(tool))
    assert c.config.settings.gui_dfr_tool_dir == ""  # the incomplete chosen folder no longer hides it

    steps.clear()
    c, _ = make(tool)
    assert run(c) == str(tool) and steps == []  # already set up: nothing to do

    state["installed"] = False
    assert run(c, steamvr=True) == str(tool)  # first install: nothing can have the DLLs loaded
    state["installed"] = False
    with pytest.raises(dfr_setup.SetupError) as error:
        run(c, present=True, steamvr=True)  # replacing copies a running game may hold
    assert error.value.reason == dfr_setup.STEAMVR_RUNNING


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
    client.sendall((json.dumps({"type": "scene", "pid": 77, "key": GAME, "name": "HL:A", "exe": ""}) + "\n").encode())
    deadline = time.monotonic() + 3
    while c.status().game_key != GAME and time.monotonic() < deadline:
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


# ------------------------------------------------------------------ panel


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
        dfr.GAZE_OFF,
        dfr.ATTACHING,
        dfr.ATTACHED,
        dfr.IDLE,
        dfr.ATTACH_FAILED,
        dfr.NATIVE,
        dfr.OPENXR,
        dfr.RENDERER,
        dfr.DISABLED,
    ],
)
def test_panel_shows_every_state(state, monkeypatch):
    tk = pytest.importorskip("tkinter")
    from settings import dfr_panel

    # The real strings: a state without one raises KeyError instead of showing its key.
    with open(LANG_EN, "rb") as file:
        strings = tomllib.load(file)["dfr"]
    monkeypatch.setattr(dfr_panel, "tr", lambda key, **fmt: strings[key.split(".")[1]].format(**fmt))
    for reason in ("DOWNLOAD_FAILED", "BAD_DOWNLOAD", "WRITE_FAILED", "STEAMVR_RUNNING", "SYSTEM_FILES_FAILED"):
        assert "setup_" + getattr(dfr_setup, reason) in strings

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
        expected = "disabled" if state in dfr.NO_SWITCH_STATES else "normal"
        assert str(panel.enabled_cb.cget("state")) == expected
        in_setup = state in dfr.SETUP_STATES
        assert (panel.switch_row.winfo_manager() == "pack") is not in_setup
        can_set_up = state in (dfr.TOOL_MISSING, dfr.NEEDS_SYSTEM_FILES)
        assert (panel.setup_btn.winfo_manager() == "pack") is can_set_up
        assert (panel.retry_btn.winfo_manager() == "pack") is (state == dfr.ATTACH_FAILED)
        assert (panel.gaze_btn.winfo_manager() == "pack") is (state == dfr.GAZE_OFF)
        for tracking in (dfr.TRACKING_NONE, "VRChat OSC (EyeTrackVR)"):
            status.tracking = tracking
            panel._refresh()
            assert panel.status_label.cget("text").strip()
    finally:
        root.destroy()
