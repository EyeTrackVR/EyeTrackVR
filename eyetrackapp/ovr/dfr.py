"""
Per-game dynamic foveated rendering for SteamVR games (Windows), driving PimaxMagic4All.

PimaxMagic4All injects Pimax's foveated rendering into D3D11 OpenVR games. Its DFR-UI
attaches to every game; this controller replaces it with a per-game switch:

- a monitor process (ovr/dfr_monitor.py) reports the SteamVR game in front;
- each game is off until the user turns it on, then remembered (settings.gui_dfr_games);
- an enabled game gets `MagicAttach_x64.exe /pid <pid>` once per process, and its
  quality is written to HKCU\\SOFTWARE\\FR-Utility\\mode, which the injected code
  re-reads live, so on/off and quality changes apply instantly in the running game
  (code that is already injected can't be removed: "off" is mode 0 until the game restarts);
- games with Easy Anti-Cheat / BattlEye (and VRChat) are never attached.

Pimax's binaries are not shipped with EyeTrackVR: the user points the app at a
PimaxMagic4All folder. Its first-run step copies two DLLs into System32 (UAC).
"""

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MODE_OFF = 0
MODES = {"maximum": 1, "balanced": 2, "minimum": 3, "debug": 4}  # FR-Utility "mode" values
DEFAULT_MODE = "balanced"
REGISTRY_KEY = r"SOFTWARE\FR-Utility"

TOOL_FILES = (
    "MagicAttach_x64.exe",
    "LibMagicD3D1164.dll",
    "libPVRClient64.dll",
    "VarjoLib.dll",
    "install_system_files.bat",
)
SYSTEM_FILES = ("libPVRClient64.dll", "VarjoLib.dll")

# Games whose anti-cheat bans injected code, by SteamVR app key. Folders are checked too.
BLOCKED_KEYS = {"steam.app.438100": "VRChat (Easy Anti-Cheat)"}
ANTI_CHEAT_MARKERS = ("easyanticheat", "battleye", "beservice", "eac_launcher")

# Scene apps that are SteamVR itself, not games.
IGNORED_KEY_PREFIXES = ("system.", "openvr.tool.", "openvr.component.")

UNSUPPORTED = "unsupported"  # not Windows
STEAMVR_OFF = "steamvr_off"
NO_GAME = "no_game"
TOOL_MISSING = "tool_missing"  # PimaxMagic4All folder not set / incomplete
NEEDS_SYSTEM_FILES = "needs_system_files"
DFR_UI_RUNNING = "dfr_ui_running"  # PimaxMagic4All's own UI would fight us
BLOCKED = "blocked"
OFF = "off"  # game known, DFR off for it
ATTACHED = "attached"  # DFR on and injected into this process
ATTACH_FAILED = "attach_failed"


@dataclass
class Status:
    state: str
    game_key: str = ""
    game_name: str = ""
    enabled: bool = False
    mode: str = DEFAULT_MODE
    detail: str = ""
    tool_dir: str = ""
    steamvr: bool = False


# ---------------------------------------------------------------- helpers


def default_tool_dirs() -> list[Path]:
    """Where a PimaxMagic4All copy is picked up without the user choosing a folder."""
    dirs = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "EyeTrackVR" / "PimaxMagic4All")
    if not getattr(sys, "frozen", False):
        # Source checkout next to a PimaxMagic4All checkout built with its EyeTrackVR-DFR folder.
        dirs.append(Path(__file__).resolve().parents[3] / "PimaxMagic4All" / "bin" / "EyeTrackVR-DFR")
    return dirs


def tool_missing_files(tool_dir: str) -> list[str]:
    if not tool_dir or not os.path.isdir(tool_dir):
        return list(TOOL_FILES)
    return [f for f in TOOL_FILES if not os.path.isfile(os.path.join(tool_dir, f))]


def _system32() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"


def _same_file(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def system_files_installed(tool_dir: str, system32: Path | None = None) -> bool:
    """The DLLs the injected code loads from System32 match this PimaxMagic4All copy
    (the same check DFR-UI makes)."""
    system32 = system32 or _system32()
    return all(_same_file(system32 / name, Path(tool_dir) / name) for name in SYSTEM_FILES)


def install_system_files(tool_dir: str) -> bool:
    """Run PimaxMagic4All's install_system_files.bat elevated (UAC prompt) and wait.
    SteamVR must be closed. Returns True on success."""
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    SEE_MASK_NOCLOSEPROCESS = 0x40
    bat = os.path.join(tool_dir, "install_system_files.bat")
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = "cmd.exe"
    info.lpParameters = f'/s /c ""{bat}" "{tool_dir}""'
    info.nShow = 0  # SW_HIDE
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)) or not info.hProcess:
        return False  # declined at the UAC prompt, or could not start
    kernel32 = ctypes.windll.kernel32
    kernel32.WaitForSingleObject(info.hProcess, 60_000)
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    kernel32.CloseHandle(info.hProcess)
    return code.value == 0 and system_files_installed(tool_dir)


def anti_cheat_reason(key: str, exe: str) -> str:
    """Why this game must never be attached, or ""."""
    if key in BLOCKED_KEYS:
        return BLOCKED_KEYS[key]
    if not exe:
        return ""
    folder = Path(exe).parent
    for directory in (folder, folder.parent, folder.parent.parent):
        try:
            names = [entry.lower() for entry in os.listdir(directory)]
        except OSError:
            continue
        for marker in ANTI_CHEAT_MARKERS:
            hit = next((n for n in names if n.startswith(marker)), None)
            if hit:
                return "BattlEye" if "battleye" in hit or "beservice" in hit else "Easy Anti-Cheat"
    return ""


def is_game_key(key: str) -> bool:
    return bool(key) and not key.startswith(IGNORED_KEY_PREFIXES) and key != "etvr.etvrapp"


def _process_running(image: str) -> bool:
    from ovr.openvr_service import _windows_process_running

    return _windows_process_running(image)


def _vrserver_running() -> bool:
    from ovr.openvr_service import _vrserver_running as running

    return running()


class Registry:
    """HKCU\\SOFTWARE\\FR-Utility, which the injected PimaxMagic4All code watches."""

    def get_mode(self) -> int | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
                return int(winreg.QueryValueEx(key, "mode")[0])
        except OSError:
            return None

    def set_mode(self, mode: int) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "mode", 0, winreg.REG_DWORD, int(mode))


def _monitor_command(port: int) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--dfr-monitor", str(port)]
    return [sys.executable, str(Path(__file__).resolve().parents[1] / "eyetrackapp.py"), "--dfr-monitor", str(port)]


# ---------------------------------------------------------------- controller


@dataclass
class _Scene:
    pid: int = 0
    key: str = ""
    name: str = ""
    exe: str = ""


class DfrController:
    TICK_S = 0.5

    def __init__(
        self,
        config=None,
        registry=None,
        attach=None,
        monitor_command=None,
        steamvr_running=None,
        dfr_ui_running=None,
        system_files_ok=None,
    ):
        self.config = config  # EyeTrackConfig
        self.registry = registry if registry is not None else (Registry() if sys.platform == "win32" else None)
        self._attach = attach or self._magic_attach
        self._monitor_command = monitor_command or _monitor_command
        self._steamvr_running = steamvr_running or _vrserver_running
        self._dfr_ui_running = dfr_ui_running or (lambda: _process_running("dfr-ui.exe"))
        self._system_files_ok = system_files_ok or system_files_installed
        self._lock = threading.RLock()
        self._scene = _Scene()
        self._monitor: subprocess.Popen | None = None
        self._monitor_socket: socket.socket | None = None
        self._attached: set[int] = set()
        self._attach_failed: set[int] = set()
        self._written_mode: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = Status(UNSUPPORTED if sys.platform != "win32" else STEAMVR_OFF)
        self._next_system_check = 0.0
        self._system_ok_cache = False
        self._next_monitor_start = 0.0
        self._process_cache: dict[str, tuple[float, bool]] = {}

    # --------------------------------------------------------- settings

    @property
    def settings(self):
        return self.config.settings

    def tool_dir(self) -> str:
        """The chosen PimaxMagic4All folder, or the first complete one in a default place."""
        chosen = str(getattr(self.settings, "gui_dfr_tool_dir", "") or "")
        if chosen:
            return chosen
        return next((str(c) for c in default_tool_dirs() if not tool_missing_files(str(c))), "")

    def _games(self) -> dict:
        return dict(getattr(self.settings, "gui_dfr_games", None) or {})

    def game_settings(self, key: str) -> dict:
        entry = self._games().get(key) or {}
        mode = entry.get("mode", DEFAULT_MODE)
        return {
            "enabled": bool(entry.get("enabled", False)),
            "mode": mode if mode in MODES else DEFAULT_MODE,
            "name": entry.get("name", ""),
        }

    def set_game(self, key: str, *, enabled: bool | None = None, mode: str | None = None) -> None:
        """Remember this game's DFR choice and apply it now."""
        if not is_game_key(key):
            return
        games = self._games()
        entry = dict(games.get(key) or {})
        if enabled is not None:
            entry["enabled"] = bool(enabled)
        if mode is not None and mode in MODES:
            entry["mode"] = mode
        with self._lock:
            if key == self._scene.key and self._scene.name:
                entry["name"] = self._scene.name
        entry.setdefault("mode", DEFAULT_MODE)
        games[key] = entry
        self.config.update({"gui_dfr_games": games}, save=True)
        self.tick()

    def set_tool_dir(self, path: str) -> None:
        self.config.update({"gui_dfr_tool_dir": str(path or "")}, save=True)
        self._next_system_check = 0.0
        self.tick()

    # --------------------------------------------------------- lifecycle

    def start(self) -> None:
        if sys.platform != "win32" or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="DfrController", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """App exit: turn DFR off in a running game (the user's switch lives in this app)."""
        self._stop.set()
        self._stop_monitor()
        with self._lock:
            if self._written_mode not in (None, MODE_OFF):
                self._write_mode(MODE_OFF)

    def _run(self) -> None:
        while not self._stop.wait(self.TICK_S):
            try:
                self.tick()
            except Exception:
                logger.exception("DFR controller tick failed")

    def status(self) -> Status:
        with self._lock:
            return self._status

    # --------------------------------------------------------- monitor

    MONITOR_RETRY_S = 5.0
    PROCESS_CHECK_S = 2.0

    def _cached(self, name: str, check) -> bool:
        """A process-list check, at most every PROCESS_CHECK_S."""
        now = time.monotonic()
        at, value = self._process_cache.get(name, (-1e9, False))
        if now - at >= self.PROCESS_CHECK_S:
            value = bool(check())
            self._process_cache[name] = (now, value)
        return value

    def _ensure_monitor(self, steamvr: bool) -> None:
        alive = self._monitor is not None and self._monitor.poll() is None
        if steamvr and not alive:
            self._monitor = None
            now = time.monotonic()
            if now < self._next_monitor_start:
                return  # it just exited (SteamVR starting or quitting): don't spin
            self._next_monitor_start = now + self.MONITOR_RETRY_S
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(10)
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self._monitor = subprocess.Popen(
                    self._monitor_command(listener.getsockname()[1]),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
                threading.Thread(
                    target=self._read_monitor, args=(self._monitor, listener), daemon=True, name="DfrMonitorReader"
                ).start()
            except OSError as e:
                listener.close()
                logger.warning("DFR: could not start the SteamVR game monitor (%s)", e)
        elif not steamvr and alive:
            self._stop_monitor()

    def _stop_monitor(self) -> None:
        monitor, self._monitor = self._monitor, None
        connection, self._monitor_socket = self._monitor_socket, None
        if connection is not None:
            try:
                connection.close()  # the monitor exits when the socket closes
            except OSError:
                pass
        if monitor is None:
            return
        try:
            monitor.wait(timeout=2)
        except Exception:
            try:
                monitor.kill()
            except Exception:
                pass

    def _read_monitor(self, monitor: subprocess.Popen, listener: socket.socket) -> None:
        try:
            connection, _ = listener.accept()
        except OSError:
            return  # the monitor never connected (it failed to start)
        finally:
            listener.close()
        with self._lock:
            if self._monitor is monitor:
                self._monitor_socket = connection
            else:  # stopped meanwhile
                connection.close()
                return
        try:
            for line in connection.makefile("r", encoding="utf-8"):
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                self.on_monitor_message(message)
        except OSError:
            pass
        self.on_monitor_message({"type": "scene", "pid": 0})

    def on_monitor_message(self, message: dict) -> None:
        if message.get("type") == "scene":
            with self._lock:
                pid = int(message.get("pid") or 0)
                self._scene = (
                    _Scene(pid, message.get("key", ""), message.get("name", ""), message.get("exe", ""))
                    if pid
                    else _Scene()
                )
            self.tick()
        elif message.get("type") == "quit":
            with self._lock:
                self._scene = _Scene()

    # --------------------------------------------------------- decisions

    def _write_mode(self, mode: int) -> None:
        if self.registry is None:
            return
        try:
            self.registry.set_mode(mode)
            self._written_mode = mode
        except OSError as e:
            logger.warning("DFR: could not write the foveation mode (%s)", e)

    def _magic_attach(self, tool_dir: str, pid: int) -> bool:
        exe = os.path.join(tool_dir, "MagicAttach_x64.exe")
        try:
            subprocess.Popen(
                [exe, "/pid", str(pid)], cwd=tool_dir, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            return True
        except OSError as e:
            logger.warning("DFR: attaching to process %s failed (%s)", pid, e)
            return False

    def _system_ready(self, tool_dir: str) -> bool:
        now = time.monotonic()
        if now >= self._next_system_check:
            self._next_system_check = now + 5.0
            self._system_ok_cache = self._system_files_ok(tool_dir)
        return self._system_ok_cache

    def tick(self) -> Status:
        """Re-evaluate the current game and apply its DFR choice. Thread-safe."""
        if sys.platform != "win32" and self.registry is None:
            return self._set_status(Status(UNSUPPORTED))
        steamvr = self._cached("steamvr", self._steamvr_running)
        with self._lock:
            self._ensure_monitor(steamvr)
            scene = self._scene if steamvr else _Scene()
            tool_dir = self.tool_dir()
            want_mode = MODE_OFF
            in_game = steamvr and is_game_key(scene.key)
            game = self.game_settings(scene.key) if in_game else None
            status = Status(STEAMVR_OFF, tool_dir=tool_dir, steamvr=steamvr)
            if game is not None:
                status = Status(
                    OFF,
                    scene.key,
                    scene.name or game["name"] or scene.key,
                    game["enabled"],
                    game["mode"],
                    tool_dir=tool_dir,
                    steamvr=True,
                )

            # One-time setup first, whether or not SteamVR runs: installing the system
            # files needs SteamVR closed, so that step must stay visible then.
            blocked = anti_cheat_reason(scene.key, scene.exe) if in_game else ""
            if blocked:
                status.state, status.detail = BLOCKED, blocked
            elif tool_missing_files(tool_dir):
                status.state = TOOL_MISSING
            elif not self._system_ready(tool_dir):
                status.state = NEEDS_SYSTEM_FILES
            elif not steamvr:
                status.state = STEAMVR_OFF
            elif game is None:
                status.state = NO_GAME
            elif self._cached("dfr_ui", self._dfr_ui_running):
                status.state = DFR_UI_RUNNING
            elif game["enabled"]:
                if scene.pid not in self._attached and scene.pid not in self._attach_failed:
                    if self._attach(tool_dir, scene.pid):
                        self._attached.add(scene.pid)
                        logger.info("DFR: attached to %s (pid %s)", status.game_name, scene.pid)
                    else:
                        self._attach_failed.add(scene.pid)
                status.state = ATTACHED if scene.pid in self._attached else ATTACH_FAILED
                want_mode = MODES[game["mode"]] if status.state == ATTACHED else MODE_OFF

            # The injected code reads this live. Only write once we have reason to:
            # never touch the key for someone who never turned DFR on.
            if want_mode != MODE_OFF or self._written_mode not in (None, MODE_OFF):
                if want_mode != self._written_mode:
                    self._write_mode(want_mode)
            return self._set_status(status)

    def _set_status(self, status: Status) -> Status:
        with self._lock:
            self._status = status
        return status


dfr_controller = DfrController()
