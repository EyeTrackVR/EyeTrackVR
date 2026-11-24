"""
Per-game dynamic foveated rendering for SteamVR games (Windows), driving PimaxMagic4All.

PimaxMagic4All injects Pimax's foveated rendering into D3D11 OpenVR games. Its DFR-UI
attaches to every game; this controller replaces it with a per-game switch:

- a monitor process (ovr/dfr_monitor.py) reports the SteamVR game in front;
- each game is off until the user turns it on, then remembered (settings.gui_dfr_games);
- an enabled game gets `MagicAttach_x64.exe /pid <pid>`, and its quality is written to
  HKCU\\SOFTWARE\\FR-Utility\\mode, which the injected code re-reads live, so on/off and
  quality changes apply instantly in the running game (code that is already injected
  can't be removed: "off" is mode 0 until the game restarts);
- games with Easy Anti-Cheat / BattlEye (and VRChat) are never attached.

What the game process really holds decides the state, not this app's memory of it:
whether the foveation DLLs are loaded is read from the process's module list, and the
eye tracker they picked from PimaxMagic4All's own log. So an app restart, a reused
process id or a failed injection can't leave the panel saying something untrue.

The injected code picks its eye tracker once, when it loads. Nothing is attached until
EyeTrackVR's gaze output is up (the "Foveated rendering support" setting), or the game
would stay on fixed foveation until it restarts.

Pimax's binaries are not shipped with EyeTrackVR: ovr/dfr_setup.py downloads a
PimaxMagic4All release, or the user points the app at a copy. Its two system DLLs are
copied into System32 once (UAC).
"""

import json
import logging
import ntpath
import os
import re
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
DEBUG_MODE = "debug"  # shows the foveation rings; not offered in release builds


def user_modes() -> tuple[str, ...]:
    """The qualities the user can pick: release builds (packaging/build_release.bat)
    leave out the debug view."""
    from build_info import is_release_build

    return tuple(m for m in MODES if m != DEBUG_MODE or not is_release_build())


REGISTRY_KEY = r"SOFTWARE\FR-Utility"

TOOL_FILES = (
    "MagicAttach_x64.exe",
    "LibMagicD3D1164.dll",
    "libPVRClient64.dll",
    "VarjoLib.dll",
)
SYSTEM_FILES = ("libPVRClient64.dll", "VarjoLib.dll")
# In a game's module list once the injection worked.
INJECTED_MODULES = ("libmagicd3d1164.dll", "libpvrclient64.dll")
# Loaded by the injected code once the game's rendering really goes through it.
ACTIVE_MODULES = ("libpvrclient64.dll",)

# Games whose anti-cheat bans injected code, by SteamVR app key. Folders are checked too.
BLOCKED_KEYS = {"steam.app.438100": "VRChat (Easy Anti-Cheat)"}
ANTI_CHEAT_MARKERS = ("easyanticheat", "battleye", "beservice", "eac_launcher")

# How a game gets foveated rendering. The per-game switch only exists for INJECT; the
# others get EyeTrackVR's gaze through the "Foveated rendering support" outputs on their own.
METHOD_AUTO = "auto"  # setting only: work it out (detect_method)
METHOD_INJECT = "inject"  # PimaxMagic4All, added to the game by this app
METHOD_NATIVE = "native"  # the game foveates itself from SteamVR's eye tracking
METHOD_OPENXR = "openxr"  # OpenXR game: quad views (Quad-Views-Foveated) or its own OpenXR path
METHOD_NONE = "none"  # nothing can, or the user said so
METHODS = (METHOD_AUTO, METHOD_INJECT, METHOD_NATIVE, METHOD_OPENXR, METHOD_NONE)

# Known games, by SteamVR app key. Everything else is detected from what the game loads.
NATIVE_KEYS = {"steam.app.546560"}  # Half-Life: Alyx (its October 2026 foveated rendering update)
QUAD_VIEWS_KEYS = {"steam.app.223750", "steam.app.555160"}  # DCS World, Pavlov VR
QUAD_VIEWS_EXES = {"dcs.exe"}  # DCS World installed outside Steam
# Renderers PimaxMagic4All can't hook, when the game has no Direct3D 11 loaded.
OTHER_RENDERERS = (("vulkan-1.dll", "Vulkan"), ("d3d12.dll", "Direct3D 12"))

# Scene apps that are SteamVR itself, not games.
IGNORED_KEY_PREFIXES = ("system.", "openvr.tool.", "openvr.component.")

UNSUPPORTED = "unsupported"  # not Windows
STEAMVR_OFF = "steamvr_off"
NO_GAME = "no_game"
TOOL_MISSING = "tool_missing"  # no complete PimaxMagic4All copy
NEEDS_SYSTEM_FILES = "needs_system_files"
NEEDS_QUAD_VIEWS = "needs_quad_views"  # OpenXR game, Quad-Views-Foveated not installed (Set up adds it)
DFR_UI_RUNNING = "dfr_ui_running"  # PimaxMagic4All's own UI would fight us
BLOCKED = "blocked"
OFF = "off"  # game known, DFR off for it
GAZE_OFF = "gaze_off"  # DFR on for the game, waiting for EyeTrackVR's gaze output
ATTACHING = "attaching"  # MagicAttach started, the game has not loaded the DLLs yet
ATTACHED = "attached"  # DFR on and in use in this process
IDLE = "idle"  # injected, but the game never started using it (attached too late, or it foveates itself)
ATTACH_FAILED = "attach_failed"  # MagicAttach did not start, or the game never loaded the DLLs

NATIVE = "native"  # the game has its own eye-tracked foveated rendering
OPENXR = "openxr"  # OpenXR game: quad views, not injection
RENDERER = "renderer"  # not Direct3D 11: PimaxMagic4All can't work (detail: the renderer)
DISABLED = "disabled"  # the user set this game's method to none

SETUP_STATES = (UNSUPPORTED, TOOL_MISSING, NEEDS_SYSTEM_FILES)
# The game is handled another way, or not at all: there is no switch to use.
NO_SWITCH_STATES = (BLOCKED, NATIVE, OPENXR, NEEDS_QUAD_VIEWS, RENDERER, DISABLED)
# Set up can be pressed: it installs whatever is missing (ovr/dfr_setup.py).
SET_UP_STATES = (TOOL_MISSING, NEEDS_SYSTEM_FILES, NEEDS_QUAD_VIEWS)
# A game is in front and its switch can be used.
SWITCHABLE_STATES = (OFF, GAZE_OFF, ATTACHING, ATTACHED, IDLE, ATTACH_FAILED, DFR_UI_RUNNING)

# Status.tracking, from PimaxMagic4All's log.
TRACKING_UNKNOWN = ""
TRACKING_NONE = "none"  # no eye tracker found: fixed foveation


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
    invert_y: bool = False
    tracking: str = TRACKING_UNKNOWN  # eye tracker the game uses, TRACKING_NONE, or unknown
    method: str = METHOD_INJECT  # how this game gets foveated rendering
    method_choice: str = METHOD_AUTO  # the saved per-game setting
    quad_views: bool = True  # Quad-Views-Foveated installed (False: Set up still has it to add)


def status_text(status: Status) -> str:
    """The one-line explanation of a status, in the user's language."""
    from localization import tr

    if status.state == ATTACHED:
        if status.tracking == TRACKING_NONE:
            return tr("dfr.state_attached_fixed")
        if status.tracking:
            return tr("dfr.state_attached_tracking", tracker=status.tracking)
    return tr(f"dfr.state_{status.state}", reason=status.detail)


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


def system_files_present(system32: Path | None = None) -> bool:
    """Some copy is already in System32. Replacing it needs SteamVR closed: a running
    game may have it loaded."""
    system32 = system32 or _system32()
    return any((system32 / name).exists() for name in SYSTEM_FILES)


def system_files_copy(tool_dir: str, system32: Path | None = None) -> str:
    """The cmd.exe command that copies the system DLLs into System32. Raises ValueError
    for a path cmd could misread."""
    system32 = system32 or _system32()
    copies = []
    for name in SYSTEM_FILES:
        source, target = str(Path(tool_dir) / name), str(system32 / name)
        if any(c in source + target for c in '"%^&|<>'):
            raise ValueError(f"unsupported character in {source!r}")
        copies.append(f'copy /y /b "{source}" "{target}" >nul')
    return " && ".join(copies)


def cmd_arguments(*commands: str) -> str:
    """cmd.exe arguments that run each command in turn, whether or not the one before failed."""
    return f'/d /s /c "{" & ".join(f"({c})" for c in commands)}"'


def system_files_command(tool_dir: str, system32: Path | None = None) -> str:
    """cmd.exe arguments that copy the system DLLs into System32."""
    return cmd_arguments(system_files_copy(tool_dir, system32))


def install_system_files(tool_dir: str) -> bool:
    """Copy PimaxMagic4All's two DLLs into System32, elevated (one UAC prompt), and wait.
    Returns True once System32 holds this copy's files."""
    try:
        parameters = system_files_command(tool_dir)
    except ValueError as e:
        logger.warning("DFR: cannot install the system files (%s)", e)
        return False
    run_elevated(parameters)
    return system_files_installed(tool_dir)


def run_elevated(parameters: str, timeout_ms: int = 60_000) -> bool:
    """Run cmd.exe with these arguments elevated (one UAC prompt), hidden, and wait.
    Returns False when the prompt was declined or cmd could not start."""
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
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = "cmd.exe"
    info.lpParameters = parameters
    info.nShow = 0  # SW_HIDE
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)) or not info.hProcess:
        return False  # declined at the UAC prompt, or could not start
    kernel32 = ctypes.windll.kernel32
    kernel32.WaitForSingleObject(info.hProcess, timeout_ms)
    kernel32.CloseHandle(info.hProcess)
    return True


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


def detect_method(key: str, exe: str, loaded) -> tuple[str, str]:
    """How this game gets foveated rendering, and for METHOD_NONE the renderer that rules
    injection out. ``loaded(dll)`` says whether the game process has a DLL loaded (None
    when the process can't be inspected, which leaves the default: inject)."""
    if key in NATIVE_KEYS:
        return METHOD_NATIVE, ""
    # exe is a Windows path; ntpath splits it on any OS.
    if key in QUAD_VIEWS_KEYS or ntpath.basename(exe).lower() in QUAD_VIEWS_EXES:
        return METHOD_OPENXR, ""
    # PimaxMagic4All hooks OpenVR's frame submission: an OpenXR game never calls it.
    if loaded("openxr_loader.dll") and loaded("openvr_api.dll") is False:
        return METHOD_OPENXR, ""
    if loaded("d3d11.dll") is False:
        for dll, renderer in OTHER_RENDERERS:
            if loaded(dll):
                return METHOD_NONE, renderer
    return METHOD_INJECT, ""


def is_game_key(key: str) -> bool:
    return bool(key) and not key.startswith(IGNORED_KEY_PREFIXES) and key != "etvr.etvrapp"


def _process_running(image: str) -> bool:
    from ovr.openvr_service import _windows_process_running

    return _windows_process_running(image)


def _quad_views_installed() -> bool:
    from ovr import quad_views

    return quad_views.installed()


def _vrserver_running() -> bool:
    if sys.platform not in ("win32", "linux"):
        return False  # no SteamVR (and no openvr package) on macOS
    from ovr.openvr_service import _vrserver_running as running

    return running()


def gaze_output_ready() -> bool:
    """EyeTrackVR's foveation gaze sender is up: it holds the mutex PimaxMagic4All looks
    for when it picks its eye tracker."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    from osc.foveation_gaze_sender import FOVEATION_MUTEX

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    kernel32.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenMutexW(0x00100000, False, FOVEATION_MUTEX)  # SYNCHRONIZE
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def process_has_module(pid: int, names=INJECTED_MODULES) -> bool | None:
    """Whether a process has one of these DLLs loaded. None when its module list can't
    be read (elevated or protected process, or it just exited)."""
    if sys.platform != "win32" or pid <= 0:
        return None
    import ctypes
    from ctypes import wintypes

    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("th32ModuleID", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("GlblcntUsage", wintypes.DWORD),
            ("ProccntUsage", wintypes.DWORD),
            ("modBaseAddr", ctypes.c_void_p),
            ("modBaseSize", wintypes.DWORD),
            ("hModule", wintypes.HMODULE),
            ("szModule", ctypes.c_wchar * 256),
            ("szExePath", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Module32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W))
    kernel32.Module32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    invalid = wintypes.HANDLE(-1).value
    snapshot = invalid
    for _ in range(5):  # ERROR_BAD_LENGTH: the module list changed under us, ask again
        snapshot = kernel32.CreateToolhelp32Snapshot(0x8 | 0x10, pid)  # SNAPMODULE | SNAPMODULE32
        if snapshot not in (None, invalid) or ctypes.get_last_error() != 24:
            break
    if snapshot in (None, invalid):
        return None
    try:
        wanted = {name.lower() for name in names}
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
        ok = kernel32.Module32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szModule.lower() in wanted:
                return True
            ok = kernel32.Module32NextW(snapshot, ctypes.byref(entry))
        return False
    finally:
        kernel32.CloseHandle(snapshot)


def tool_log_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "PvrEmu" / "PvrEmu.log"


_LOG_HELLO = re.compile(r"Hello World from '([^']*)'")
_LOG_TRACKER = re.compile(r"Using eye tracking: (.+)|(No supported eye tracking)")


def tracking_from_log(exe: str, path: Path | None = None) -> str:
    """Eye tracker the injected code chose in this game, from PimaxMagic4All's log (it
    restarts the log in each game it loads into). TRACKING_NONE when it found none,
    TRACKING_UNKNOWN while it has not said, or when the log is about another game."""
    try:
        with open(path or tool_log_path(), "r", encoding="utf-8", errors="replace") as file:
            text = file.read(65536)
    except OSError:
        return TRACKING_UNKNOWN
    hello = None
    for hello in _LOG_HELLO.finditer(text):
        pass
    if hello is None or (exe and os.path.normcase(hello.group(1)) != os.path.normcase(exe)):
        return TRACKING_UNKNOWN
    choice = None
    for choice in _LOG_TRACKER.finditer(text, hello.end()):
        pass
    if choice is None:
        return TRACKING_UNKNOWN
    return choice.group(1).strip() if choice.group(1) else TRACKING_NONE


class Registry:
    """HKCU\\SOFTWARE\\FR-Utility, which the injected PimaxMagic4All code watches."""

    def get(self, name: str) -> int | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
                return int(winreg.QueryValueEx(key, name)[0])
        except (OSError, TypeError, ValueError):
            return None

    def set(self, name: str, value: int) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))


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


@dataclass
class _Process:
    """What is known about the game process in front."""

    pid: int = 0
    exe: str = ""
    blocked: str | None = None  # anti-cheat reason, once looked up
    first_seen: float = 0.0
    method: str = ""  # detected method; settles once the game has loaded its renderer
    method_reason: str = ""
    injected: bool = False  # the DLLs were seen in its module list
    injected_at: float | None = None  # when that was first seen
    active: bool = False  # the game's rendering goes through them
    launched_at: float | None = None  # when MagicAttach was started for it
    launch_failed: bool = False
    off_checked: bool = False  # a mode left on by an earlier run was cleared
    tracking: str = TRACKING_UNKNOWN
    next_log_read: float = 0.0


class DfrController:
    TICK_S = 0.5
    MONITOR_RETRY_S = 5.0
    PROCESS_CHECK_S = 2.0
    TOOL_CHECK_S = 2.0
    SYSTEM_CHECK_S = 5.0
    ATTACH_CONFIRM_S = 15.0  # MagicAttach to the DLLs showing up in the game
    LOG_READ_S = 1.0

    def __init__(
        self,
        config=None,
        registry=None,
        attach=None,
        monitor_command=None,
        steamvr_running=None,
        dfr_ui_running=None,
        system_files_ok=None,
        gaze_ready=None,
        has_module=None,
        tracking=None,
        is_active=None,
        module_loaded=None,
        quad_views_ok=None,
    ):
        self.config = config  # EyeTrackConfig
        self.registry = registry if registry is not None else (Registry() if sys.platform == "win32" else None)
        self._attach = attach or self._magic_attach
        self._monitor_command = monitor_command or _monitor_command
        self._steamvr_running = steamvr_running or _vrserver_running
        self._dfr_ui_running = dfr_ui_running or (lambda: _process_running("dfr-ui.exe"))
        self._system_files_ok = system_files_ok or system_files_installed
        self._quad_views_ok = quad_views_ok or _quad_views_installed
        self._gaze_ready = gaze_ready or gaze_output_ready
        self._has_module = has_module or process_has_module
        self._is_active = is_active or (lambda pid: process_has_module(pid, ACTIVE_MODULES))
        self._module_loaded = module_loaded or (lambda pid, dll: process_has_module(pid, (dll,)))
        self._tracking = tracking or tracking_from_log
        self._lock = threading.RLock()
        self._scene = _Scene()
        self._process = _Process()
        # Processes MagicAttach was started for, for games whose module list can't be read.
        self._launched: dict[int, str] = {}
        self._monitor: subprocess.Popen | None = None
        self._monitor_socket: socket.socket | None = None
        self._written: dict[str, int] = {}  # registry values this run wrote
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = Status(UNSUPPORTED if sys.platform != "win32" else STEAMVR_OFF)
        self._next_monitor_start = 0.0
        self._cache: dict[str, tuple[float, object]] = {}
        # Dashboard panel (ovr/vr_dashboard.py). ``actions`` are the app's handlers for
        # its buttons ("recenter", "recalibrate"); ``run_on_ui`` runs a callable on the
        # app's UI thread. Both are set by the app once its window exists.
        self.actions: dict = {}
        self.run_on_ui = None
        self._sent_state: dict | None = None

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

    def _tool_state(self) -> tuple[str, bool]:
        tool_dir = self.tool_dir()
        return tool_dir, bool(tool_missing_files(tool_dir))

    def _games(self) -> dict:
        return dict(getattr(self.settings, "gui_dfr_games", None) or {})

    def game_settings(self, key: str) -> dict:
        entry = self._games().get(key) or {}
        mode = entry.get("mode", DEFAULT_MODE)
        method = entry.get("method", METHOD_AUTO)
        return {
            "enabled": bool(entry.get("enabled", False)),
            "mode": mode if mode in user_modes() else DEFAULT_MODE,
            "invert_y": bool(entry.get("invert_y", False)),
            "method": method if method in METHODS else METHOD_AUTO,
            "name": entry.get("name", ""),
        }

    def set_game(
        self,
        key: str,
        *,
        enabled: bool | None = None,
        mode: str | None = None,
        invert_y: bool | None = None,
        method: str | None = None,
    ) -> None:
        """Remember this game's DFR choice and apply it now."""
        if not is_game_key(key):
            return
        games = self._games()
        entry = dict(games.get(key) or {})
        if enabled is not None:
            entry["enabled"] = bool(enabled)
        if mode is not None and mode in user_modes():
            entry["mode"] = mode
        if invert_y is not None:
            entry["invert_y"] = bool(invert_y)
        if method in METHODS:
            if method == METHOD_AUTO:
                entry.pop("method", None)
            else:
                entry["method"] = method
        with self._lock:
            if key == self._scene.key and self._scene.name:
                entry["name"] = self._scene.name
        entry.setdefault("mode", DEFAULT_MODE)
        games[key] = entry
        self.config.update({"gui_dfr_games": games}, save=True)
        self.tick()

    def set_tool_dir(self, path: str) -> None:
        self.config.update({"gui_dfr_tool_dir": str(path or "")}, save=True)
        self.recheck_setup()

    def recheck_setup(self) -> None:
        """The tool folder or System32 changed: look again now."""
        with self._lock:
            self._cache.pop("tool", None)
            self._cache.pop("system", None)
            self._cache.pop("quad_views", None)
        self.tick()

    def retry_attach(self) -> None:
        """Run MagicAttach again for the game in front (DFR-UI's "Try Re-Attach")."""
        with self._lock:
            self._launched.pop(self._process.pid, None)
            self._process.launched_at = None
            self._process.launch_failed = False
        self.tick()

    # --------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="DfrController", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """App exit: turn DFR off in a running game (the user's switch lives in this app)."""
        self._stop.set()
        with self._lock:
            # Closing the socket is enough: the monitor shuts its own OpenVR session
            # down and exits. Waiting on that stalled app exit, then killed it anyway.
            self._stop_monitor(wait=False)
            if self._written.get("mode", MODE_OFF) != MODE_OFF:
                self._write("mode", MODE_OFF)

    def _run(self) -> None:
        while not self._stop.wait(self.TICK_S):
            try:
                self.tick()
            except Exception:
                logger.exception("DFR controller tick failed")

    def status(self) -> Status:
        return self._status  # replaced whole by tick(); no lock, so the UI never waits on one

    # --------------------------------------------------------- monitor

    def _cached(self, name: str, ttl: float, check):
        """A file system or process list check, at most every ``ttl`` seconds."""
        now = time.monotonic()
        at, value = self._cache.get(name, (-1e9, None))
        if now - at >= ttl:
            value = check()
            self._cache[name] = (now, value)
        return value

    def _ensure_monitor(self, wanted: bool) -> None:
        alive = self._monitor is not None and self._monitor.poll() is None
        if wanted and not alive:
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
        elif not wanted and (alive or self._monitor is not None):
            self._stop_monitor()

    def _stop_monitor(self, wait: bool = True) -> None:
        monitor, self._monitor = self._monitor, None
        connection, self._monitor_socket = self._monitor_socket, None
        self._sent_state = None
        self._scene = _Scene()
        if connection is not None:
            try:
                connection.close()  # the monitor exits when the socket closes
            except OSError:
                pass
        if monitor is None or not wait:
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
                self._sent_state = None
            else:  # stopped meanwhile
                connection.close()
                return
        try:
            for line in connection.makefile("r", encoding="utf-8"):
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if isinstance(message, dict):
                    self.on_monitor_message(message)
        except OSError:
            pass
        with self._lock:
            current = self._monitor is monitor
        if current:  # a monitor that was replaced must not clear its successor's game
            self.on_monitor_message({"type": "scene", "pid": 0})

    def on_monitor_message(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "scene":
            try:
                pid = int(message.get("pid") or 0)
            except (TypeError, ValueError):
                pid = 0
            with self._lock:
                self._scene = (
                    _Scene(
                        pid,
                        str(message.get("key") or ""),
                        str(message.get("name") or ""),
                        str(message.get("exe") or ""),
                    )
                    if pid > 0
                    else _Scene()
                )
            self.tick()
        elif kind == "quit":
            with self._lock:
                self._scene = _Scene()
        elif kind == "action":
            self._on_dashboard_action(message)
        elif kind == "hmd":
            try:
                from osc.foveation_gaze_sender import set_headset_projection

                set_headset_projection(message.get("left"), message.get("right"))
            except Exception:
                logger.exception("Could not use the headset's projection")
        elif kind == "error":
            logger.info("SteamVR companion: %s", message.get("message"))

    # --------------------------------------------------------- dashboard

    def _dashboard_wanted(self) -> bool:
        return self.config is not None and bool(getattr(self.settings, "gui_vr_dashboard", False))

    def dashboard_state(self, status: Status) -> dict:
        """What the dashboard panel shows, labels in the user's language."""
        from localization import tr

        if status.game_key:
            game = tr("dfr.current_game", name=status.game_name)
        else:
            game = tr("dfr.no_game") if status.steamvr else tr("dfr.steamvr_off")
        labels = {
            "recenter": tr("dashboard.recenter"),
            "calibrate": tr("dashboard.calibrate"),
            "dfr_title": tr("dashboard.dfr_title"),
            "dfr_on": tr("dashboard.dfr_on"),
            "dfr_off": tr("dashboard.dfr_off"),
            "gaze_marker": tr("dashboard.gaze_marker"),
        }
        labels.update({f"quality_{mode}": tr(f"dfr.quality_{mode}") for mode in user_modes()})
        return {
            "type": "state",
            "labels": labels,
            "game": game,
            # Injection is Windows-only: elsewhere the panel has no foveated rendering part.
            "dfr_supported": status.state != UNSUPPORTED,
            "qualities": list(user_modes()),
            "note": {
                NATIVE: tr("dfr.note_native"),
                OPENXR: tr("dfr.note_openxr"),
                NEEDS_QUAD_VIEWS: tr("dfr.note_needs_quad_views"),
                BLOCKED: tr("dfr.note_none"),
                RENDERER: tr("dfr.note_none"),
                DISABLED: tr("dfr.note_none"),
            }.get(status.state, ""),
            "dfr": {
                "available": status.state in SWITCHABLE_STATES,
                "enabled": status.enabled,
                "mode": status.mode,
                "key": status.game_key,
            },
        }

    def _send_dashboard_state(self, status: Status) -> None:
        connection = self._monitor_socket
        if connection is None or not self._dashboard_wanted():
            return
        try:
            state = self.dashboard_state(status)
            if state == self._sent_state:
                return
            connection.sendall((json.dumps(state) + "\n").encode("utf-8"))
            self._sent_state = state
        except OSError:
            pass  # the companion is going away; the reader thread notices
        except Exception:
            logger.exception("Could not build the dashboard panel")

    def _ui(self, action) -> None:
        def run():
            try:
                action()
            except Exception:
                logger.exception("Dashboard action failed")

        if self.run_on_ui is not None:
            self.run_on_ui(run)
        else:
            run()

    def _on_dashboard_action(self, message: dict) -> None:
        name, value = message.get("name"), message.get("value")
        if name in ("recenter", "recalibrate"):
            handler = self.actions.get(name)
            if handler is not None:
                self._ui(handler)
            return
        key = str(message.get("key") or "")
        with self._lock:
            current = self._scene.key
        if not key or key != current:
            return  # the click was for a game that is no longer in front
        if name == "dfr_enabled":

            def switch():
                if value and not getattr(self.settings, "gui_foveation_gaze", False):
                    # The game needs the gaze output before it is attached.
                    self.config.update({"gui_foveation_gaze": True}, save=True)
                self.set_game(key, enabled=bool(value))

            self._ui(switch)
        elif name == "dfr_mode" and value in MODES:
            self._ui(lambda: self.set_game(key, mode=value))

    # --------------------------------------------------------- decisions

    def _write(self, name: str, value: int) -> None:
        if self.registry is None:
            return
        try:
            self.registry.set(name, value)
            self._written[name] = value
        except OSError as e:
            logger.warning("DFR: could not write the foveation setting %s (%s)", name, e)

    def _ensure(self, name: str, value: int) -> None:
        """Make the registry hold this value, also after something else changed it."""
        if self.registry is not None and self.registry.get(name) != value:
            self._write(name, value)

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

    def _process_for(self, scene: _Scene) -> _Process:
        if self._process.pid != scene.pid or self._process.exe != scene.exe:
            self._process = _Process(scene.pid, scene.exe, first_seen=time.monotonic())
            if self._launched.get(scene.pid, scene.exe) != scene.exe:
                del self._launched[scene.pid]  # the process id was reused by another game
        return self._process

    METHOD_SETTLE_S = 10.0  # a game loads its renderer and VR runtime within this

    def _method(self, process: _Process, scene: _Scene, game: dict) -> tuple[str, str]:
        """The game's method: the user's choice, else detected. Detection is repeated
        while the game is still starting, then kept."""
        if game["method"] != METHOD_AUTO:
            return game["method"], ""
        if not process.method or time.monotonic() - process.first_seen < self.METHOD_SETTLE_S:
            process.method, process.method_reason = detect_method(
                scene.key, scene.exe, lambda dll: self._module_loaded(process.pid, dll)
            )
        return process.method, process.method_reason

    def _attach_state(self, process: _Process, tool_dir: str, game: dict, name: str) -> str:
        """Bring an enabled game to "DLLs loaded", one step per tick."""
        now = time.monotonic()
        loaded = None
        if not process.injected:
            loaded = self._has_module(process.pid)
            process.injected = bool(loaded)
        if process.injected:
            if not process.active:
                # Injected is not yet in use: the game has to start rendering through it.
                in_use = self._is_active(process.pid)
                process.active = in_use is None or bool(in_use)  # can't look: trust it
            if process.active:
                return ATTACHED
            if process.injected_at is None:
                process.injected_at = now
            return ATTACHING if now - process.injected_at < self.ATTACH_CONFIRM_S else IDLE
        if process.launch_failed:
            return ATTACH_FAILED
        launched = process.launched_at is not None or process.pid in self._launched
        if not launched:
            if not self._gaze_ready():
                return GAZE_OFF
            # Settings first: the injected code reads them as it loads.
            self._apply_settings(game)
            if not self._attach(tool_dir, process.pid):
                process.launch_failed = True
                return ATTACH_FAILED
            process.launched_at = now
            self._launched[process.pid] = process.exe
            logger.info("DFR: attaching to %s (pid %s)", name, process.pid)
            return ATTACHING
        if loaded is None:
            return ATTACHED  # can't look inside this process: MagicAttach ran, trust it
        if process.launched_at is not None and now - process.launched_at < self.ATTACH_CONFIRM_S:
            return ATTACHING
        return ATTACH_FAILED

    def _apply_settings(self, game: dict) -> None:
        self._ensure("ignore_eye_tracking", 0)  # DFR-UI's "force fixed" would silently win
        self._ensure("invert_y_axis", int(game["invert_y"]))
        self._ensure("mode", MODES[game["mode"]])

    def _apply_off(self, process: _Process | None) -> None:
        """Mode 0, but never touch the key for someone who never turned DFR on here."""
        if self._written.get("mode", MODE_OFF) != MODE_OFF:
            self._write("mode", MODE_OFF)
        elif process is not None and not process.off_checked:
            # An earlier run of this app (or DFR-UI) may have left this game foveated.
            process.off_checked = True
            if self.registry is not None and self._has_module(process.pid):
                if self.registry.get("mode") not in (None, MODE_OFF):
                    self._write("mode", MODE_OFF)

    def tick(self) -> Status:
        """Re-evaluate the current game, apply its DFR choice and refresh the dashboard
        panel. Thread-safe."""
        with self._lock:
            status = self._evaluate()
            self._send_dashboard_state(status)
            return self._set_status(status)

    def _companion_for_dashboard(self) -> bool:
        """With DFR not usable (not set up, or not Windows) the companion process still
        runs for the dashboard panel, if that is on. Returns whether SteamVR runs."""
        steamvr = self._dashboard_wanted() and bool(
            self._cached("steamvr", self.PROCESS_CHECK_S, self._steamvr_running)
        )
        self._ensure_monitor(steamvr)
        return steamvr

    def _evaluate(self) -> Status:
        if sys.platform != "win32" and self.registry is None:
            return Status(UNSUPPORTED, steamvr=self._companion_for_dashboard())
        tool_dir, missing = self._cached("tool", self.TOOL_CHECK_S, self._tool_state)
        # One-time setup first. Until it is done nothing else runs: no SteamVR
        # polling and no monitor process for someone who doesn't use this.
        setup = None
        if missing:
            setup = TOOL_MISSING
        elif not self._cached("system", self.SYSTEM_CHECK_S, lambda: bool(self._system_files_ok(tool_dir))):
            setup = NEEDS_SYSTEM_FILES
        if setup:
            steamvr = self._companion_for_dashboard()
            self._apply_off(None)
            return Status(setup, tool_dir=tool_dir, steamvr=steamvr)

        # Checked with or without a game, so Set up can add it before the first OpenXR game.
        quad_views = bool(self._cached("quad_views", self.SYSTEM_CHECK_S, self._quad_views_ok))
        steamvr = bool(self._cached("steamvr", self.PROCESS_CHECK_S, self._steamvr_running))
        self._ensure_monitor(steamvr)
        scene = self._scene if steamvr else _Scene()
        if not (steamvr and is_game_key(scene.key)):
            self._apply_off(None)
            return Status(
                NO_GAME if steamvr else STEAMVR_OFF, tool_dir=tool_dir, steamvr=steamvr, quad_views=quad_views
            )

        game = self.game_settings(scene.key)
        process = self._process_for(scene)
        status = Status(
            OFF,
            scene.key,
            scene.name or game["name"] or scene.key,
            game["enabled"],
            game["mode"],
            tool_dir=tool_dir,
            steamvr=True,
            invert_y=game["invert_y"],
            quad_views=quad_views,
        )
        if process.blocked is None:
            process.blocked = anti_cheat_reason(scene.key, scene.exe)
        active = False
        status.method_choice = game["method"]
        status.method, reason = (METHOD_NONE, "") if process.blocked else self._method(process, scene, game)
        if process.blocked:
            status.state, status.detail = BLOCKED, process.blocked
        elif status.method == METHOD_NATIVE:
            status.state = NATIVE
        elif status.method == METHOD_OPENXR:
            status.state = OPENXR if quad_views else NEEDS_QUAD_VIEWS
        elif status.method == METHOD_NONE:
            status.state, status.detail = (RENDERER, reason) if reason else (DISABLED, "")
        elif self._cached("dfr_ui", self.PROCESS_CHECK_S, self._dfr_ui_running):
            status.state = DFR_UI_RUNNING
        elif game["enabled"]:
            status.state = self._attach_state(process, tool_dir, game, status.game_name)
            # Keep the settings applied unless MagicAttach itself could not start: if
            # the DLLs load late, the game still comes up as the user asked.
            active = status.state in (ATTACHED, ATTACHING, IDLE) or (
                status.state == ATTACH_FAILED and not process.launch_failed
            )
        if active:
            self._apply_settings(game)
            if status.state == ATTACHED:
                status.tracking = self._read_tracking(process)
        else:
            self._apply_off(process)
        return status

    def _read_tracking(self, process: _Process) -> str:
        now = time.monotonic()
        if process.tracking == TRACKING_UNKNOWN and now >= process.next_log_read:
            process.next_log_read = now + self.LOG_READ_S
            process.tracking = self._tracking(process.exe)
        return process.tracking

    def _set_status(self, status: Status) -> Status:
        with self._lock:
            self._status = status
        return status


dfr_controller = DfrController()
