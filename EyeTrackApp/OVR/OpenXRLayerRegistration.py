"""
Install EyeTrackVR's OpenXR API layer (openxr_layer/) as an implicit layer, or remove it.

The layer gives OpenXR runtimes without eye tracking (Monado, WiVRn, VDXR, WMR, ...)
XR_EXT_eye_gaze_interaction, fed by EyeTrackVR's gaze shared memory. It steps aside on
runtimes that already offer the extension (SteamVR with EyeTrackVR's driver), so it is safe
to have installed. It is installed only while "Foveated rendering gaze" is on; games pick it
up the next time they start.

Per user, no admin rights:
  Windows: HKCU\\SOFTWARE\\Khronos\\OpenXR\\1\\ApiLayers\\Implicit, value = manifest path, 0 = enabled.
           (The loader ignores HKCU for elevated processes; games normally aren't.)
  Linux:   $XDG_DATA_HOME/openxr/1/api_layers/implicit.d/<manifest>, with an absolute library path.
"""

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

LAYER_NAME = "XR_APILAYER_EYETRACKVR_eye_gaze"
MANIFEST = LAYER_NAME + ".json"
REGISTRY_KEY = r"SOFTWARE\Khronos\OpenXR\1\ApiLayers\Implicit"

INSTALLED = "installed"
ALREADY_INSTALLED = "already installed"
REMOVED = "removed"
NOT_INSTALLED = "not installed"
NO_LAYER = "layer not bundled"


def _library_name() -> str:
    return f"{LAYER_NAME}.dll" if sys.platform == "win32" else f"lib{LAYER_NAME}.so"


def bundled_layer_dir() -> Path | None:
    """The layer folder shipped with this install (or built from source), if complete."""
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent / "openxr_layer"
    else:
        # From source: openxr_layer/CMakeLists.txt built into <repo>/build/openxr_layer.
        candidate = Path(__file__).resolve().parents[2] / "build" / "openxr_layer" / "eyetrackvr_openxr_layer"
    if (candidate / MANIFEST).is_file() and (candidate / _library_name()).is_file():
        return candidate
    return None


def _xdg_implicit_layer_dir() -> Path:
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return data / "openxr" / "1" / "api_layers" / "implicit.d"


def implicit_layer_dir() -> Path:
    """Linux: where the loader looks for per-user implicit layers."""
    return _xdg_implicit_layer_dir()


class WindowsRegistry:
    """The few winreg operations the Windows registration needs, so tests can swap it out."""

    def values(self) -> dict[str, int]:
        import winreg

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
        except FileNotFoundError:
            return {}
        out = {}
        with key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    return out
                out[name] = value
                i += 1

    def set(self, name: str, value: int) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)

    def delete(self, name: str) -> None:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)


_WinregRegistry = WindowsRegistry  # tests replace WindowsRegistry; this keeps the real one reachable


def _is_ours(manifest_path: str) -> bool:
    return Path(manifest_path).name.lower() == MANIFEST.lower()


def _sync_windows(enabled: bool, layer_dir: Path | None, registry) -> str:
    values = registry.values()
    ours = [name for name in values if _is_ours(name)]
    wanted = str(layer_dir / MANIFEST) if enabled else None
    changed = False
    for name in ours:
        if wanted is None or os.path.normcase(name) != os.path.normcase(wanted):
            registry.delete(name)  # removed, or another / old install's copy
            changed = True
    if wanted is not None and values.get(wanted) != 0:
        registry.set(wanted, 0)
        changed = True
    if enabled:
        return INSTALLED if changed else ALREADY_INSTALLED
    return REMOVED if changed else NOT_INSTALLED


def _manifest_for(layer_dir: Path) -> str:
    """The bundled manifest with an absolute library path, for an install outside the layer folder."""
    data = json.loads((layer_dir / MANIFEST).read_text(encoding="utf-8"))
    data["api_layer"]["library_path"] = str(layer_dir / _library_name())
    return json.dumps(data, indent=4) + "\n"


def _sync_linux(enabled: bool, layer_dir: Path | None, implicit_dir: Path) -> str:
    target = implicit_dir / MANIFEST
    if not enabled:
        if target.is_file():
            target.unlink()
            return REMOVED
        return NOT_INSTALLED
    content = _manifest_for(layer_dir)
    try:
        if target.read_text(encoding="utf-8") == content:
            return ALREADY_INSTALLED
    except OSError:
        pass
    implicit_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".etvr-layer.", dir=implicit_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return INSTALLED


def sync(enabled: bool, layer_dir: Path | None = None, *, registry=None, implicit_dir: Path | None = None) -> str:
    """Install (enabled) or remove the implicit layer; returns one of the status strings."""
    if enabled:
        layer_dir = layer_dir or bundled_layer_dir()
        if layer_dir is None:
            return NO_LAYER
    if sys.platform == "win32" or registry is not None:
        status = _sync_windows(enabled, layer_dir, registry or WindowsRegistry())
    else:
        status = _sync_linux(enabled, layer_dir, implicit_dir or implicit_layer_dir())
    if status in (INSTALLED, REMOVED):
        logger.info("OpenXR eye gaze layer %s (%s); restart games to apply", status, layer_dir or "")
    return status


def sync_quietly(enabled: bool) -> str | None:
    """sync() for app code paths: never raises."""
    try:
        status = sync(enabled)
    except Exception:  # noqa: an OpenXR config problem must never break the app
        logger.exception("OpenXR layer registration failed")
        return None
    if enabled and status == NO_LAYER:
        logger.warning(
            "OpenXR eye gaze layer not installed: no built layer found%s",
            "" if getattr(sys, "frozen", False)
            else " (running from source: build it with `cmake -S openxr_layer -B build/openxr_layer"
                 " && cmake --build build/openxr_layer --config Release`)",
        )
    return status
