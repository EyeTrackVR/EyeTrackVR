"""
"Check VR eye gaze": a self-test of the foveated rendering gaze chain, link by link.

    setting -> gaze shared memory (+ named mutex) -> SteamVR driver registered
    -> (OpenXR layer) -> SteamVR running -> driver attached (vrserver.txt) -> what OpenVR apps see

Run `eyetrackapp.py --gaze-selftest` while EyeTrackVR is open and tracking. It prints one line per
check, then what to do about the first failure, and writes the same text to gaze_selftest.txt in
the logs folder (the frozen Windows build has no console). Everything here only reads state.

run_checks() is Tk-free and takes every probe as a function (Probes), so tests can fake each one.
The OpenVR probe runs in a short-lived child (`eyetrackapp.py --gaze-selftest-probe <out.json>`):
openvr.init is per process, and the app may already hold a session.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from osc import gaze_shared_memory as gsm

PASS, FAIL, WARN, SKIP = "pass", "fail", "warn", "skipped"
_LABEL = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN", SKIP: "SKIP"}

FRESH_S = 1.0  # a publisher that is tracking updates far more often than this
REPORT_NAME = "gaze_selftest.txt"
DRIVER_LOG_NAME = "eyetrackvr"  # SteamVR prefixes driver log lines with the driver name
MUTEX_NAME = "Local\\eyetrackvr-osc-gaze"  # osc/foveation_gaze_sender.py FOVEATION_MUTEX
PROBE_TIMEOUT_S = 20.0
LOG_TAIL_BYTES = 2 * 1024 * 1024


@dataclass
class Check:
    id: str
    title: str
    status: str
    message: str
    detail: str = ""
    hint: str = ""  # what to do next when this is the first failure (or warning)


# ------------------------------------------------------------------ probe results


@dataclass
class GazeBlock:
    exists: bool
    sample: dict | None = None  # gaze_shared_memory.read() of the block
    where: str = ""


@dataclass
class DriverState:
    expected_dir: Path
    binary_relpath: str
    has_manifest: bool
    has_binary: bool
    paths_file: Path | None  # openvrpaths.vrpath
    registered: list[str] | None  # EyeTrackVR entries in external_drivers; None = file unreadable
    steamvr_setting: str | None = None  # "disabled" / "blocked_by_safe_mode" in steamvr.vrsettings


@dataclass
class LayerState:
    expected_dir: Path
    bundled: bool
    installed: bool  # as openxr_layer_registration.is_installed() sees it
    entries: list[str] = field(default_factory=list)


@dataclass
class LogTail:
    path: Path | None
    text: str = ""
    searched: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ real probes


def _read_consistent(buffer, tries: int = 50) -> dict | None:
    for _ in range(tries):  # the writer may be mid-update (odd seq / CRC mismatch)
        sample = gsm.read(buffer)
        if sample is not None:
            return sample
        time.sleep(0.002)
    return None


def read_gaze_block() -> GazeBlock:
    """The gaze shared memory as a reader sees it, opened read-only: never creates it."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenFileMappingW.restype = wintypes.HANDLE
        k32.OpenFileMappingW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        k32.MapViewOfFile.restype = ctypes.c_void_p
        k32.MapViewOfFile.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t)
        k32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        FILE_MAP_READ = 0x0004
        handle = k32.OpenFileMappingW(FILE_MAP_READ, False, gsm.WIN32_NAME)
        if not handle:
            return GazeBlock(False, where=gsm.WIN32_NAME)
        try:
            address = k32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, gsm.SIZE)
            if not address:
                return GazeBlock(True, where=gsm.WIN32_NAME)
            try:
                view = memoryview((ctypes.c_char * gsm.SIZE).from_address(address)).cast("B")
                sample = _read_consistent(view)
                view.release()
            finally:
                k32.UnmapViewOfFile(address)
        finally:
            k32.CloseHandle(handle)
        return GazeBlock(True, sample, gsm.WIN32_NAME)
    if sys.platform.startswith("linux"):
        import mmap

        if not os.path.exists(gsm.POSIX_PATH):
            return GazeBlock(False, where=gsm.POSIX_PATH)
        fd = os.open(gsm.POSIX_PATH, os.O_RDONLY)
        try:
            with mmap.mmap(fd, gsm.SIZE, access=mmap.ACCESS_READ) as m:
                return GazeBlock(True, _read_consistent(m), gsm.POSIX_PATH)
        except (OSError, ValueError):
            return GazeBlock(True, None, gsm.POSIX_PATH)
        finally:
            os.close(fd)
    return GazeBlock(False, where=f"not supported on {sys.platform}")


def foveation_mutex_exists() -> bool | None:
    """Whether the publisher's named mutex exists (opened, never created); None off Windows."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenMutexW.restype = wintypes.HANDLE
    k32.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    SYNCHRONIZE = 0x00100000
    handle = k32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    if not handle:
        return False
    k32.CloseHandle(handle)
    return True


def _openvr_dirs(key: str) -> list[Path]:
    """Folders listed under ``key`` ("log", "config") in openvrpaths.vrpath."""
    from ovr import steamvr_driver_registration as reg

    paths_file = reg.openvrpaths_file()
    data = reg.read_openvrpaths(paths_file) if paths_file else None
    return [Path(p) for p in ((data or {}).get(key) or []) if isinstance(p, str)]


def _steamvr_driver_setting(config_dirs: list[Path]) -> str | None:
    """SteamVR's own on/off for this driver (Manage Add-ons, safe mode), from steamvr.vrsettings."""
    for folder in config_dirs:
        try:
            data = json.loads((folder / "steamvr.vrsettings").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        section = data.get(f"driver_{DRIVER_LOG_NAME}") if isinstance(data, dict) else None
        if not isinstance(section, dict):
            return None
        if section.get("blocked_by_safe_mode") is True:
            return "blocked_by_safe_mode"
        if section.get("enable") is False:
            return "disabled"
        return None
    return None


def driver_state() -> DriverState:
    from ovr import steamvr_driver_registration as reg

    expected = reg.expected_driver_dir()
    paths_file = reg.openvrpaths_file()
    return DriverState(
        expected_dir=expected,
        binary_relpath=reg._binary_relpath(),
        has_manifest=(expected / reg.MANIFEST).is_file(),
        has_binary=(expected / reg._binary_relpath()).is_file(),
        paths_file=paths_file,
        registered=reg.registered_entries(paths_file) if paths_file else None,
        steamvr_setting=_steamvr_driver_setting(_openvr_dirs("config")) if paths_file else None,
    )


def layer_state() -> LayerState:
    from ovr import openxr_layer_registration as xr

    bundled = xr.bundled_layer_dir()
    return LayerState(
        expected_dir=xr.expected_layer_dir(),
        bundled=bundled is not None,
        installed=bundled is not None and xr.is_installed(bundled),
        entries=xr.installed_entries(),
    )


def steamvr_running() -> bool:
    if sys.platform not in ("win32", "linux"):
        return False  # no SteamVR (and no openvr package) on macOS
    from ovr.openvr_service import _vrserver_running

    return _vrserver_running()


def _steam_dirs() -> list[Path]:
    """Steam install folders when openvrpaths.vrpath doesn't name the log folder."""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                return [Path(winreg.QueryValueEx(key, "SteamPath")[0])]
        except OSError:
            return []
    home = Path.home()
    return [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    ]


def read_tail(path: Path, max_bytes: int = LOG_TAIL_BYTES) -> str:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - max_bytes))
        data = f.read()
    text = data.decode("utf-8", "replace")
    if size > max_bytes:
        text = text.split("\n", 1)[-1]  # drop the partial first line
    return text


def find_vrserver_log() -> LogTail:
    """The tail of SteamVR's vrserver.txt (Steam/logs), found via openvrpaths.vrpath."""
    folders = _openvr_dirs("log") + [p.parent / "logs" for p in _openvr_dirs("config")]
    folders += [p / "logs" for p in _steam_dirs()]
    searched: list[str] = []
    for folder in folders:
        path = folder / "vrserver.txt"
        if str(path) in searched:
            continue
        searched.append(str(path))
        if path.is_file():
            try:
                return LogTail(path, read_tail(path), searched)
            except OSError:
                continue
    return LogTail(None, "", searched)


def probe_command(out_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--gaze-selftest-probe", str(out_path)]
    script = Path(__file__).resolve().parents[1] / "eyetrackapp.py"
    return [sys.executable, str(script), "--gaze-selftest-probe", str(out_path)]


def run_openvr_probe(timeout: float = PROBE_TIMEOUT_S) -> dict:
    """Run the OpenVR probe in a child process and return its JSON result."""
    with tempfile.TemporaryDirectory(prefix="etvr-gaze-probe-") as tmp:
        out = Path(tmp) / "probe.json"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(
                probe_command(out), capture_output=True, text=True, timeout=timeout, creationflags=flags
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"the OpenVR probe did not finish within {timeout:.0f} s"}
        except OSError as exc:
            return {"ok": False, "error": f"could not start the OpenVR probe ({exc})"}
        text = out.read_text(encoding="utf-8") if out.is_file() else (proc.stdout or "").strip()
        try:
            return json.loads(text.splitlines()[-1])
        except (ValueError, IndexError):
            tail = " ".join((proc.stderr or "").strip().splitlines()[-3:])
            return {"ok": False, "error": f"the OpenVR probe exited with code {proc.returncode} and no result. {tail}"}


# ------------------------------------------------------------------ OpenVR probe (child process)


def _jsonable(value):
    import ctypes

    if isinstance(value, (bool, int, str)) or value is None:
        return value
    if isinstance(value, float):
        return round(value, 5)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, ctypes.Structure):
        return {name: _jsonable(getattr(value, name)) for name, *_ in value._fields_}
    if isinstance(value, (ctypes.Array, list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, ctypes._SimpleCData):
        return _jsonable(value.value)
    return repr(value)


def _foveation_query(openvr, system):
    """(call, where) for IVRSystem::GetEyeTrackedFoveationCenter, or (None, why not)."""
    name = "getEyeTrackedFoveationCenter"
    method = getattr(system, name, None)
    if callable(method):
        return (lambda: _jsonable(method())), "pyopenvr IVRSystem wrapper"
    entry = getattr(system.function_table, name, None)
    if entry is not None:
        import ctypes

        argtypes = list(getattr(type(entry), "_argtypes_", None) or [])
        if not all(hasattr(t, "_type_") and issubclass(t, ctypes._Pointer) for t in argtypes):
            return None, f"function table entry has arguments this probe can't fill: {argtypes}"

        def call():
            outs = [t._type_() for t in argtypes]
            result = entry(*[ctypes.byref(o) for o in outs])
            return _jsonable({"result": result, "out": outs})

        return call, "IVRSystem function table (ctypes)"
    try:
        from openvr.version import __version__ as version
    except ImportError:
        version = "?"
    return None, (
        f"not available in this OpenVR binding (pyopenvr {version}, {openvr.IVRSystem_Version}: "
        f"neither IVRSystem.{name} nor a function table entry)"
    )


def openvr_probe_payload(duration_s: float = 1.0, samples: int = 10) -> dict:
    """Open a background OpenVR session and read what an OpenVR app sees on the HMD."""
    import ctypes

    import openvr

    out: dict = {"ok": False, "interface": getattr(openvr, "IVRSystem_Version", "?")}
    try:
        system = openvr.init(openvr.VRApplication_Background)  # never starts SteamVR
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    try:
        out["ok"] = True
        hmd = openvr.k_unTrackedDeviceIndex_Hmd
        out["hmd_connected"] = bool(system.isTrackedDeviceConnected(hmd))
        for key, prop in (
            ("tracking_system", openvr.Prop_TrackingSystemName_String),
            ("model", openvr.Prop_ModelNumber_String),
            ("manufacturer", openvr.Prop_ManufacturerName_String),
        ):
            try:
                out[key] = system.getStringTrackedDeviceProperty(hmd, prop)
            except Exception as exc:
                out[key] = None
                out[f"{key}_error"] = str(exc)
        try:
            out["runtime_version"] = system.getRuntimeVersion()
        except Exception:
            out["runtime_version"] = None
        # The function table directly: the wrapper raises instead of returning the error code.
        error = openvr.ETrackedPropertyError()
        value = system.function_table.getBoolTrackedDeviceProperty(
            hmd, openvr.Prop_SupportsXrEyeGazeInteraction_Bool, ctypes.byref(error)
        )
        try:
            error_name = system.getPropErrorNameFromEnum(error.value)
            error_name = error_name.decode() if isinstance(error_name, bytes) else str(error_name)
        except Exception:
            error_name = str(error.value)
        out["prop"] = {"value": bool(value), "code": int(error.value), "error": error_name}

        call, where = _foveation_query(openvr, system)
        fov: dict = {"available": call is not None, "where": where, "samples": [], "errors": []}
        if call is not None:
            for _ in range(samples):
                try:
                    fov["samples"].append(call())
                except Exception as exc:
                    fov["errors"].append(f"{type(exc).__name__}: {exc}")
                time.sleep(duration_s / samples)
        out["foveation"] = fov
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            openvr.shutdown()
        except Exception:
            pass
    return out


def probe_main(out_path: str | None = None) -> int:
    """`--gaze-selftest-probe [out.json]`: one JSON line to stdout and, if given, the file."""
    try:
        payload = openvr_probe_payload()
    except Exception as exc:
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    line = json.dumps(payload)
    if out_path:
        Path(out_path).write_text(line + "\n", encoding="utf-8")
    if sys.stdout is not None:
        print(line, flush=True)
    return 0


# ------------------------------------------------------------------ vrserver.txt


_SESSION_START = re.compile(r"vrserver \S+ startup with PID=")
_DRIVER_LINE = re.compile(rf"(?:^|\s-\s){DRIVER_LOG_NAME}: (?P<msg>.*?)\s*$")
_STEAMVR_ABOUT_US = re.compile(rf"\bdriver {DRIVER_LOG_NAME}\b", re.IGNORECASE)
_ATTACH = re.compile(
    r"Attach via (?P<route>\w+) to device (?P<device>\d+): CreateEyeTrackingComponent -> (?P<name>\w+) \((?P<code>-?\d+)\)"
)
_UPDATE = re.compile(r"UpdateEyeTrackingComponent -> (?P<name>\w+) \((?P<code>-?\d+)\)")
_PROP = re.compile(r"Prop_SupportsXrEyeGazeInteraction_Bool = (?P<value>-?\d+) -> (?P<code>-?\d+)")
_WRAP = re.compile(r"Wrapping HMD '(?P<serial>.*)' to attach eye tracking")


@dataclass
class LogFindings:
    session_found: bool = False  # a "vrserver ... startup" line was in the tail
    loaded: bool = False  # SteamVR's "Loaded server driver eyetrackvr" or the driver's own start line
    driver_started: bool = False
    disabled: bool = False  # "Not loading driver eyetrackvr because it is disabled in settings"
    shim: bool | None = None
    shim_patch_failed: bool = False
    wrapped_serial: str | None = None
    attach_route: str | None = None
    attach_device: int | None = None
    attach_error: str | None = None
    attach_code: int | None = None
    update_error: str | None = None
    prop_value: int | None = None
    prop_code: int | None = None
    driver_lines: list[str] = field(default_factory=list)
    steamvr_lines: list[str] = field(default_factory=list)


def current_session(text: str) -> list[str]:
    """Lines of the last SteamVR session in a vrserver.txt tail."""
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if _SESSION_START.search(lines[i]):
            return lines[i:]
    return lines


def parse_vrserver_log(text: str) -> LogFindings:
    lines = current_session(text)
    found = LogFindings(session_found=bool(lines) and bool(_SESSION_START.search(lines[0])))
    for line in lines:
        m = _DRIVER_LINE.search(line)
        if m is None:
            if _STEAMVR_ABOUT_US.search(line):
                found.steamvr_lines.append(line.strip())
                if "Loaded server driver" in line:
                    found.loaded = True
                elif "disabled in settings" in line:
                    found.disabled = True
            continue
        msg = m.group("msg")
        found.driver_lines.append(msg)
        if msg.startswith("EyeTrackVR gaze driver starting"):
            found.driver_started = found.loaded = True
        elif msg.startswith("Watching for the HMD"):
            found.shim = True
        elif msg.startswith("HMD shim unavailable"):
            found.shim = False
        elif msg.startswith("Could not patch IVRServerDriverHost::TrackedDeviceAdded"):
            found.shim_patch_failed = True
        elif (w := _WRAP.search(msg)) is not None:
            found.wrapped_serial = w.group("serial")
        elif (a := _ATTACH.search(msg)) is not None:
            found.attach_route, found.attach_device = a.group("route"), int(a.group("device"))
            found.attach_error, found.attach_code = a.group("name"), int(a.group("code"))
        elif (u := _UPDATE.search(msg)) is not None:
            found.update_error = f"{u.group('name')} ({u.group('code')})"
        elif (p := _PROP.search(msg)) is not None:
            found.prop_value, found.prop_code = int(p.group("value")), int(p.group("code"))
    return found


# ------------------------------------------------------------------ checks


def _default_probe(name: str):
    return lambda: globals()[name]()  # resolved at call time so tests can also patch the module


@dataclass
class Probes:
    read_gaze: Callable[[], GazeBlock] = field(default_factory=lambda: _default_probe("read_gaze_block"))
    now_ns: Callable[[], int] = time.perf_counter_ns
    clock_id: Callable[[], int | None] = gsm.clock_id
    mutex_exists: Callable[[], bool | None] = field(default_factory=lambda: _default_probe("foveation_mutex_exists"))
    driver_state: Callable[[], DriverState] = field(default_factory=lambda: _default_probe("driver_state"))
    layer_state: Callable[[], LayerState] = field(default_factory=lambda: _default_probe("layer_state"))
    steamvr_running: Callable[[], bool] = field(default_factory=lambda: _default_probe("steamvr_running"))
    vrserver_log: Callable[[], LogTail] = field(default_factory=lambda: _default_probe("find_vrserver_log"))
    openvr_probe: Callable[[], dict] = field(default_factory=lambda: _default_probe("run_openvr_probe"))
    frozen: bool = field(default_factory=lambda: bool(getattr(sys, "frozen", False)))


def _flags(flags: int) -> str:
    names = [n for bit, n in ((gsm.FLAG_GAZE_VALID, "gaze"), (gsm.FLAG_OPENNESS_VALID, "openness")) if flags & bit]
    return "+".join(names) or "none"


def check_setting(config) -> Check:
    settings = getattr(config, "settings", config)
    if bool(getattr(settings, "gui_foveation_gaze", False)):
        return Check("setting", "Setting", PASS, '"Foveated rendering support" is on')
    return Check(
        "setting",
        "Setting",
        FAIL,
        '"Foveated rendering support" is off, so EyeTrackVR publishes no gaze for VR',
        hint='Turn on "Foveated rendering support" in EyeTrackVR\'s settings. That also registers the SteamVR '
        "driver and the OpenXR layer. Then restart SteamVR (it loads drivers only at startup) and run this "
        "check again while EyeTrackVR is tracking.",
    )


def check_publisher(p: Probes) -> Check:
    title = "Publisher"
    block = p.read_gaze()
    if not block.exists:
        return Check(
            "publisher",
            title,
            FAIL,
            f"no gaze shared memory ({block.where}): EyeTrackVR is not running or has not started publishing",
            hint="Start EyeTrackVR with both cameras streaming and keep it open: the gaze block exists only "
            "while EyeTrackVR runs with the setting on. Run this check from a second window while it tracks.",
        )
    sample = block.sample
    if sample is None:
        return Check(
            "publisher",
            title,
            FAIL,
            f"gaze shared memory exists ({block.where}) but holds no valid sample (wrong version or corrupt)",
            hint="Close every EyeTrackVR copy and any tool that reads the gaze block, start EyeTrackVR again "
            "and rerun this check.",
        )
    eyes = sample["eyes"]
    detail = "\n".join(
        f"{name}: flags={_flags(e.flags)} openness={e.openness:.2f} confidence={e.confidence:.2f} "
        f"direction=({e.direction[0]:+.3f}, {e.direction[1]:+.3f}, {e.direction[2]:+.3f})"
        for name, e in zip(("left", "right", "combined"), eyes)
    )
    detail = f"{block.where}: sample #{sample['sample_count']} from pid {sample['pid']}\n{detail}"
    if sample["clock"] != p.clock_id():
        return Check(
            "publisher",
            title,
            WARN,
            f"gaze shared memory uses clock {sample['clock']}, not this OS's; can't tell its age",
            detail,
        )
    if sample["sample_count"] == 0:
        return Check(
            "publisher",
            title,
            FAIL,
            "gaze shared memory exists but nothing was published yet (no tracked frames)",
            detail,
            hint="EyeTrackVR is running but not tracking: check both cameras show a picture and an eye "
            "tracking algorithm is on, then run this check again.",
        )
    age_s = (p.now_ns() - sample["publish_time_ns"]) / 1e9
    if age_s > FRESH_S or age_s < -FRESH_S:
        return Check(
            "publisher",
            title,
            FAIL,
            f"gaze is stale: last sample {age_s:.1f} s old (EyeTrackVR stopped tracking or was closed)",
            detail,
            hint="EyeTrackVR is not publishing fresh gaze: make sure it is open, both cameras stream and the "
            "eyes are tracked, then run this check again while it tracks.",
        )
    combined = eyes[gsm.EYE_COMBINED]
    if not combined.flags & gsm.FLAG_GAZE_VALID:
        return Check(
            "publisher",
            title,
            WARN,
            f"fresh ({age_s * 1000:.0f} ms old) but gaze is flagged invalid right now (eyes closed or lost)",
            detail,
            hint="Keep your eyes open and in view of the cameras while the check runs; if gaze stays invalid, "
            "recalibrate in EyeTrackVR.",
        )
    return Check("publisher", title, PASS, f"fresh ({age_s * 1000:.0f} ms old), combined gaze valid", detail)


def check_mutex(p: Probes) -> Check:
    exists = p.mutex_exists()
    if exists is None:
        return Check("mutex", "Publisher mutex", SKIP, "only used on Windows")
    if exists:
        return Check("mutex", "Publisher mutex", PASS, f"{MUTEX_NAME} is held")
    return Check(
        "mutex",
        "Publisher mutex",
        WARN,
        f"{MUTEX_NAME} does not exist; PimaxMagic4All won't open its UDP gaze port",
        hint="Restart EyeTrackVR. Only PimaxMagic4All's UDP gaze path needs this mutex; the SteamVR and "
        "OpenXR checks do not.",
    )


def check_driver(p: Probes) -> Check:
    title = "SteamVR driver"
    s = p.driver_state()
    if not (s.has_manifest and s.has_binary):
        missing = ", ".join(
            n for n, ok in (("driver.vrdrivermanifest", s.has_manifest), (s.binary_relpath, s.has_binary)) if not ok
        )
        build = (
            "Reinstall EyeTrackVR."
            if p.frozen
            else "Build it: cmake -S native/steamvr_driver -B build/steamvr_driver && "
            "cmake --build build/steamvr_driver --config Release, then restart EyeTrackVR."
        )
        return Check(
            "driver",
            title,
            FAIL,
            f"driver not found at {s.expected_dir} (missing {missing})",
            hint=f"The SteamVR driver is not on this PC. {build}",
        )
    if s.paths_file is None:
        return Check(
            "driver",
            title,
            FAIL,
            "SteamVR has never run for this user (no openvrpaths.vrpath)",
            hint="Install SteamVR and start it once, close it, restart EyeTrackVR (it registers the driver at "
            "startup while the setting is on), then start SteamVR again.",
        )
    if s.registered is None:
        return Check(
            "driver",
            title,
            FAIL,
            f"cannot read {s.paths_file}",
            hint="SteamVR's openvrpaths.vrpath is unreadable. Start SteamVR once so it rewrites it, then "
            "restart EyeTrackVR.",
        )
    from ovr import steamvr_driver_registration as reg

    if not any(reg._same(e, str(s.expected_dir)) for e in s.registered):
        where = f"another install's copy is registered: {', '.join(s.registered)}" if s.registered else "not listed"
        return Check(
            "driver",
            title,
            FAIL,
            f"not registered with SteamVR ({where} in {s.paths_file})",
            hint='EyeTrackVR registers its driver while "Foveated rendering support" is on: turn the setting off '
            "and on again (or restart EyeTrackVR), then restart SteamVR.",
        )
    if s.steamvr_setting is not None:
        why = "blocked by SteamVR safe mode" if s.steamvr_setting == "blocked_by_safe_mode" else "turned off"
        return Check(
            "driver",
            title,
            FAIL,
            f"registered, but {why} in SteamVR's settings (driver_{DRIVER_LOG_NAME} in steamvr.vrsettings)",
            str(s.expected_dir),
            hint="SteamVR is set not to load EyeTrackVR's driver. In SteamVR: Settings > Startup / Shutdown > "
            "Manage Add-ons, turn EyeTrackVR on, then restart SteamVR.",
        )
    return Check("driver", title, PASS, f"registered: {s.expected_dir}")


def check_layer(p: Probes) -> Check:
    title = "OpenXR layer"
    s = p.layer_state()
    only = "Only non-SteamVR OpenXR runtimes need it; it does not affect the SteamVR checks."
    if not s.bundled:
        build = (
            "Reinstall EyeTrackVR."
            if p.frozen
            else "Build it: cmake -S native/openxr_layer -B build/openxr_layer && "
            "cmake --build build/openxr_layer --config Release, then restart EyeTrackVR."
        )
        return Check("openxr_layer", title, WARN, f"layer not found at {s.expected_dir}", hint=f"{build} {only}")
    if s.installed:
        return Check("openxr_layer", title, PASS, "installed as an implicit layer", "\n".join(s.entries))
    other = f" (registered elsewhere: {', '.join(s.entries)})" if s.entries else ""
    return Check(
        "openxr_layer",
        title,
        WARN,
        f"not installed for this install{other}",
        hint=f'Turn "Foveated rendering support" off and on again, or restart EyeTrackVR. {only}',
    )


def check_steamvr_running(p: Probes) -> Check:
    if p.steamvr_running():
        return Check("steamvr", "SteamVR running", PASS, "vrserver is running")
    return Check(
        "steamvr",
        "SteamVR running",
        FAIL,
        "SteamVR is not running",
        hint="Start SteamVR with the headset connected and wait until the headset shows as ready, keep "
        "EyeTrackVR tracking, then run this check again. The remaining checks need a running SteamVR.",
    )


def check_vrserver_log(p: Probes, running: bool) -> Check:
    title = "SteamVR log"
    tail = p.vrserver_log()
    if tail.path is None:
        return Check(
            "vrserver_log",
            title,
            WARN,
            "could not find SteamVR's vrserver.txt",
            "looked in:\n" + "\n".join(tail.searched),
            hint="SteamVR's log folder was not found, so the driver's attach result is unknown. Look for "
            '"eyetrackvr:" lines in Steam\\logs\\vrserver.txt by hand.',
        )
    f = parse_vrserver_log(tail.text)
    when = "current SteamVR session" if running else "last SteamVR session; SteamVR is not running now"
    detail = [f"{tail.path} ({when})"]
    detail += [f"SteamVR: {line}" for line in f.steamvr_lines[-3:]]
    detail += [f"{DRIVER_LOG_NAME}: {line}" for line in f.driver_lines[-8:]]
    detail = "\n".join(detail)
    restart = "Restart SteamVR" if running else "Start SteamVR"
    if f.disabled and not f.loaded:
        return Check(
            "vrserver_log",
            title,
            FAIL,
            f"SteamVR skipped the driver: disabled in its settings ({when})",
            detail,
            hint="In SteamVR: Settings > Startup / Shutdown > Manage Add-ons, turn EyeTrackVR on, then restart "
            "SteamVR.",
        )
    if not f.loaded:
        return Check(
            "vrserver_log",
            title,
            FAIL,
            f"SteamVR did not load the driver ({when})",
            detail,
            hint=f"{restart}: SteamVR loads drivers only at startup, so a driver registered while it ran is "
            "picked up next time. If it still isn't loaded, look for EyeTrackVR under SteamVR Settings > "
            "Startup / Shutdown > Manage Add-ons.",
        )
    if f.attach_error is None:
        shim = " (and its HMD hook could not be installed)" if f.shim_patch_failed or f.shim is False else ""
        return Check(
            "vrserver_log",
            title,
            FAIL,
            f"driver loaded but never attached to a headset{shim} ({when})",
            detail,
            hint=f"No headset reached the driver. Connect and power the headset, {restart.lower()} and wait "
            "until it shows as ready, then run this check again.",
        )
    attach = f"Attach via {f.attach_route} to device {f.attach_device} -> {f.attach_error} ({f.attach_code})"
    if f.attach_error != "None":
        if f.attach_error == "PermissionDenied":
            message = f"{attach}: SteamVR refused a cross-driver component (the headset's driver does not let "
            message += "other drivers add an eye tracking component to its HMD)"
            hint = (
                "SteamVR refused to let EyeTrackVR's driver add eye tracking to this headset "
                "(PermissionDenied). Settings on this PC can't change that. Report the headset model and "
                "this output to EyeTrackVR."
            )
        else:
            message = f"{attach}: SteamVR rejected the eye tracking component"
            hint = f"SteamVR rejected the eye tracking component ({f.attach_error}). Report the headset model "
            hint += "and this output to EyeTrackVR."
        return Check("vrserver_log", title, FAIL, f"{message} ({when})", detail, hint=hint)
    if f.prop_value is None:
        return Check(
            "vrserver_log",
            title,
            WARN,
            f"{attach}; no Prop_SupportsXrEyeGazeInteraction_Bool line yet ({when})",
            detail,
            hint="The driver attached but hasn't set the support property yet. Wait a few seconds with "
            "EyeTrackVR tracking and run this check again.",
        )
    if f.prop_code != 0:
        return Check(
            "vrserver_log",
            title,
            FAIL,
            f"{attach}; setting Prop_SupportsXrEyeGazeInteraction_Bool failed (error {f.prop_code}) ({when})",
            detail,
            hint="SteamVR refused the eye gaze support property on this headset. Report the headset model and "
            "this output to EyeTrackVR.",
        )
    prop = f"Prop_SupportsXrEyeGazeInteraction_Bool = {f.prop_value}"
    if f.prop_value != 1:
        return Check(
            "vrserver_log",
            title,
            WARN,
            f"{attach}; {prop}: the driver saw no gaze published when it last checked ({when})",
            detail,
            hint="The driver attached, but EyeTrackVR wasn't publishing gaze when it last checked. Keep "
            "EyeTrackVR tracking with the setting on; the driver re-checks every second.",
        )
    if f.update_error:
        return Check(
            "vrserver_log",
            title,
            WARN,
            f"{attach}; {prop}; but UpdateEyeTrackingComponent -> {f.update_error} ({when})",
            detail,
            hint="SteamVR rejects the gaze updates themselves. Report the headset model and this output.",
        )
    return Check("vrserver_log", title, PASS, f"{attach}; {prop} ({when})", detail)


def check_openvr_hmd(result: dict) -> Check:
    title = "OpenVR HMD"
    if not result.get("ok"):
        return Check(
            "openvr_hmd",
            title,
            FAIL,
            f"could not open an OpenVR background session: {result.get('error')}",
            hint="SteamVR is running but refused a background OpenVR session. Wait until SteamVR has fully "
            "started (headset ready) and run this check again.",
        )
    hmd = " / ".join(str(result.get(k)) for k in ("tracking_system", "model") if result.get(k)) or "unknown"
    detail = "\n".join(
        f"{k}: {result.get(k)}" for k in ("tracking_system", "model", "manufacturer", "runtime_version", "interface")
    )
    if not result.get("hmd_connected"):
        return Check(
            "openvr_hmd",
            title,
            FAIL,
            "SteamVR has no headset connected",
            detail,
            hint="Connect and power the headset and wait until SteamVR shows it as ready, then run this check again.",
        )
    prop = result.get("prop") or {}
    if prop.get("code"):
        return Check(
            "openvr_hmd",
            title,
            FAIL,
            f"HMD ({hmd}) has no Prop_SupportsXrEyeGazeInteraction_Bool ({prop.get('error')})",
            detail,
            hint="Apps can't see eye gaze support on this HMD: the driver never set the property. See the "
            "SteamVR log check above for why.",
        )
    if not prop.get("value"):
        return Check(
            "openvr_hmd",
            title,
            FAIL,
            f"HMD ({hmd}) reports Prop_SupportsXrEyeGazeInteraction_Bool = false",
            detail,
            hint="OpenVR apps see no eye gaze support. The driver sets it only while EyeTrackVR publishes "
            "fresh gaze (checked once a second): fix the first failing check above, or keep EyeTrackVR "
            "tracking and run this again.",
        )
    return Check(
        "openvr_hmd", title, PASS, f"HMD ({hmd}) reports Prop_SupportsXrEyeGazeInteraction_Bool = true", detail
    )


def check_openvr_foveation(result: dict) -> Check:
    title = "Foveation centre"
    if not result.get("ok"):
        return Check("openvr_foveation", title, SKIP, "skipped: no OpenVR session")
    fov = result.get("foveation") or {}
    if not fov.get("available"):
        return Check(
            "openvr_foveation",
            title,
            WARN,
            f"GetEyeTrackedFoveationCenter: {fov.get('where') or 'not available'}",
            hint="This build's OpenVR binding can't ask SteamVR for the eye-tracked foveation centre, so "
            "that last link is untested here; the other checks still cover the chain.",
        )
    samples, errors = fov.get("samples") or [], fov.get("errors") or []
    detail = f"via {fov.get('where')}\n" + "\n".join(json.dumps(s) for s in samples[:10])
    if errors:
        detail += "\nerrors: " + "; ".join(errors[:3])
    if not samples:
        return Check("openvr_foveation", title, FAIL, "GetEyeTrackedFoveationCenter returned no values", detail)
    if len({json.dumps(s, sort_keys=True) for s in samples}) > 1:
        return Check(
            "openvr_foveation", title, PASS, f"returns values that change ({len(samples)} samples over ~1 s)", detail
        )
    return Check(
        "openvr_foveation",
        title,
        WARN,
        f"returns a value, but it did not change over {len(samples)} samples",
        detail,
        hint="Look around (move your eyes) while the check runs; if the value never changes, SteamVR is not "
        "using EyeTrackVR's gaze for it.",
    )


def run_checks(config, probes: Probes | None = None) -> list[Check]:
    """All checks in dependency order; a check whose prerequisite failed is skipped."""
    p = probes or Probes()
    done: dict[str, Check] = {}
    out: list[Check] = []

    def run(check_id: str, title: str, requires: tuple[str, ...], fn) -> None:
        for dep in requires:
            prior = done.get(dep)
            if prior is None or prior.status not in (PASS, WARN):
                state = "was skipped" if prior is not None and prior.status == SKIP else "failed"
                name = prior.title if prior is not None else dep
                check = Check(check_id, title, SKIP, f"skipped: {name} {state}")
                break
        else:
            try:
                check = fn()
            except Exception as exc:  # a diagnostic must always produce its report
                check = Check(check_id, title, FAIL, f"check crashed: {type(exc).__name__}: {exc}")
        done[check_id] = check
        out.append(check)

    run("setting", "Setting", (), lambda: check_setting(config))
    run("publisher", "Publisher", ("setting",), lambda: check_publisher(p))
    run("mutex", "Publisher mutex", ("setting",), lambda: check_mutex(p))
    run("driver", "SteamVR driver", ("setting",), lambda: check_driver(p))
    run("openxr_layer", "OpenXR layer", ("setting",), lambda: check_layer(p))
    run("steamvr", "SteamVR running", (), lambda: check_steamvr_running(p))
    running = done["steamvr"].status == PASS
    run("vrserver_log", "SteamVR log", ("driver",), lambda: check_vrserver_log(p, running))
    probe: dict = {}

    def openvr_result() -> dict:
        if not probe:
            probe.update(p.openvr_probe())
        return probe

    run("openvr_hmd", "OpenVR HMD", ("steamvr",), lambda: check_openvr_hmd(openvr_result()))
    run("openvr_foveation", "Foveation centre", ("steamvr",), lambda: check_openvr_foveation(openvr_result()))
    return out


# ------------------------------------------------------------------ report


def next_steps(checks: list[Check]) -> str:
    """One paragraph: what to do about the first failure (or warning)."""
    failed = next((c for c in checks if c.status == FAIL), None)
    if failed is not None:
        return f"First failure: {failed.title}. " + (failed.hint or failed.message)
    warned = [c for c in checks if c.status == WARN]
    if warned:
        first = warned[0]
        return f"Nothing failed. First warning: {first.title}. " + (first.hint or first.message)
    if any(c.status == SKIP for c in checks if c.id in ("openvr_hmd", "openvr_foveation")):
        return "Nothing failed, but the SteamVR checks were skipped. Run this again with SteamVR running."
    return (
        "Every link works: EyeTrackVR publishes fresh gaze, SteamVR loaded the driver and attached it to the "
        "headset, and OpenVR apps see eye gaze support."
    )


def format_report(checks: list[Check], when: datetime | None = None) -> str:
    when = when or datetime.now()
    width = max(len(c.title) for c in checks)
    lines = [f"EyeTrackVR VR eye gaze self-test, {when:%Y-%m-%d %H:%M:%S}", ""]
    lines += [f"{_LABEL[c.status]:4}  {c.title:<{width}}  {c.message}" for c in checks]
    details = [c for c in checks if c.detail]
    if details:
        lines += ["", "Details:"]
        for c in details:
            lines.append(f"  {c.title}:")
            lines += [f"    {line}" for line in c.detail.splitlines()]
    lines += ["", "What to do next: " + next_steps(checks)]
    return "\n".join(lines) + "\n"


def main() -> int:
    """`eyetrackapp.py --gaze-selftest`: print the report, save it next to the logs, exit 0 if nothing failed."""
    from config import EyeTrackConfig

    checks = run_checks(EyeTrackConfig.load())
    report = format_report(checks)
    saved = None
    try:
        from utils.logging_utils import log_directory

        saved = log_directory() / REPORT_NAME
        saved.write_text(report, encoding="utf-8")
    except OSError:
        saved = None
    if sys.stdout is not None:
        print(report, end="")
        print(f"Saved to {saved}" if saved else "Could not save the report next to the logs.", flush=True)
    return 1 if any(c.status == FAIL for c in checks) else 0
