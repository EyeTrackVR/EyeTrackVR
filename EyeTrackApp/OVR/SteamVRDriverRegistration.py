"""
Register EyeTrackVR's SteamVR driver (steamvr_driver/) with SteamVR, or remove it.

The driver feeds EyeTrackVR's gaze into SteamVR's eye tracking input on any headset, so
SteamVR's OpenXR runtime offers XR_EXT_eye_gaze_interaction. It is registered only while
"Foveated rendering gaze" is on, and SteamVR loads drivers at startup, so a change takes
effect the next time SteamVR starts.

Registration is an entry in openvrpaths.vrpath's "external_drivers" list, which is all
`vrpathreg adddriver` writes. Editing it directly works the same on Windows and Linux
without locating vrpathreg (which on Linux also needs SteamVR's library path).
"""

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

DRIVER_NAME = "eyetrackvr"
MANIFEST = "driver.vrdrivermanifest"

REGISTERED = "registered"
ALREADY_REGISTERED = "already registered"
UNREGISTERED = "unregistered"
NOT_REGISTERED = "not registered"
NO_STEAMVR = "SteamVR not installed"
NO_DRIVER = "driver not bundled"


def _binary_relpath() -> str:
    if sys.platform == "win32":
        return "bin/win64/driver_eyetrackvr.dll"
    import platform

    arm = platform.machine().lower() in ("aarch64", "arm64")
    return f"bin/{'linuxarm64' if arm else 'linux64'}/driver_eyetrackvr.so"


def openvrpaths_file() -> Path | None:
    """SteamVR's openvrpaths.vrpath for this user, or None if SteamVR has never run."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        candidates = [Path(base) / "openvr" / "openvrpaths.vrpath"] if base else []
    else:
        config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        candidates = [
            config / "openvr" / "openvrpaths.vrpath",
            # Flatpak Steam keeps its own config tree.
            Path.home() / ".var/app/com.valvesoftware.Steam/.config/openvr/openvrpaths.vrpath",
        ]
    return next((p for p in candidates if p.is_file()), None)


def bundled_driver_dir() -> Path | None:
    """The driver folder shipped with this install (or built from source), if complete."""
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent / "steamvr_driver" / DRIVER_NAME
    else:
        # From source: steamvr_driver/CMakeLists.txt built into <repo>/build/steamvr_driver.
        candidate = Path(__file__).resolve().parents[2] / "build" / "steamvr_driver" / DRIVER_NAME
    if (candidate / MANIFEST).is_file() and (candidate / _binary_relpath()).is_file():
        return candidate
    return None


def _manifest_name(driver_dir: Path) -> str | None:
    try:
        return json.loads((driver_dir / MANIFEST).read_text(encoding="utf-8-sig")).get("name")
    except (OSError, ValueError, AttributeError):
        return None


def _is_ours(entry: str) -> bool:
    """An EyeTrackVR driver entry: this install's, another install's, or a removed one's."""
    path = Path(entry)
    if path.is_dir():
        return _manifest_name(path) == DRIVER_NAME
    # Gone (uninstalled / moved install): only our own folder layout counts as ours.
    return path.name == DRIVER_NAME and path.parent.name == "steamvr_driver"


def _same(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def _write_atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".openvrpaths.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent="\t")
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sync(enabled: bool, paths_file: Path | None = None, driver_dir: Path | None = None) -> str:
    """Make SteamVR's driver list match ``enabled``; returns one of the status strings.

    Enabling keeps exactly one EyeTrackVR entry, this install's, replacing entries left by
    other or removed installs. Disabling removes every EyeTrackVR entry. Other drivers and
    keys are left alone, and nothing is written when nothing changes.
    """
    paths_file = paths_file or openvrpaths_file()
    if paths_file is None:
        return NO_STEAMVR
    if enabled:
        driver_dir = driver_dir or bundled_driver_dir()
        if driver_dir is None:
            return NO_DRIVER
    try:
        data = json.loads(paths_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        logger.warning("SteamVR driver: cannot read %s (%s); leaving it alone", paths_file, exc)
        return NOT_REGISTERED
    if not isinstance(data, dict):
        return NOT_REGISTERED
    entries = [e for e in (data.get("external_drivers") or []) if isinstance(e, str)]
    others = [e for e in entries if not _is_ours(e)]
    wanted = others + [str(driver_dir)] if enabled else others

    if len(wanted) == len(entries) and all(_same(a, b) for a, b in zip(wanted, entries)):
        return ALREADY_REGISTERED if enabled else NOT_REGISTERED
    data["external_drivers"] = wanted
    _write_atomic(paths_file, data)
    logger.info(
        "SteamVR driver %s (%s); restart SteamVR to apply",
        "registered" if enabled else "unregistered",
        driver_dir if enabled else paths_file,
    )
    return REGISTERED if enabled else UNREGISTERED


def sync_quietly(enabled: bool) -> str | None:
    """sync() for app code paths: never raises."""
    try:
        status = sync(enabled)
    except Exception:  # noqa: a SteamVR config problem must never break the app
        logger.exception("SteamVR driver registration failed")
        return None
    if enabled and status == NO_DRIVER:
        logger.warning(
            "SteamVR driver not registered: no built driver found%s",
            "" if getattr(sys, "frozen", False)
            else " (running from source: build it with `cmake -S steamvr_driver -B build/steamvr_driver"
                 " && cmake --build build/steamvr_driver --config Release`)",
        )
    elif enabled and status == NO_STEAMVR:
        logger.info("SteamVR driver not registered: %s", status)
    return status
