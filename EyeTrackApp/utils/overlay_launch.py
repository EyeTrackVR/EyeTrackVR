"""Locating and launching the in-VR calibration overlay (EyeTrackVR-Overlay).

Every launch goes through ``overlay_command`` so the overlay always shows its
instruction text in the app's active UI language (``--lang=<code>``). The
overlay has built-in text for every language in ``lang/``; an unknown code
(e.g. a newly dropped-in language) falls back to English there, while the text
the app itself sends during data collection still comes from ``lang/``.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from utils.misc_utils import resource_path

# The overlay/ submodule ships prebuilt runtimes in dist/<platform>/.
OVERLAY_DIST = Path(__file__).resolve().parents[2] / "overlay" / "dist"


def overlay_dist_folder() -> str:
    """The overlay/dist/ folder holding this platform's runtime."""
    if sys.platform == "win32":
        return "windows"
    return "linux-arm64" if platform.machine().lower() in ("aarch64", "arm64") else "linux"


def overlay_executable() -> str:
    """Resolve the overlay binary for this platform.

    Bundled builds carry it as ``Tools/EyeTrackVR-Overlay.exe`` (Windows) or
    ``Tools/linux/EyeTrackVR-Overlay`` with its loaders (Linux); source runs
    use ``overlay/dist/<platform>/`` from the submodule. Raises
    FileNotFoundError when unavailable so callers can fall back gracefully.
    """
    name = "EyeTrackVR-Overlay.exe" if sys.platform == "win32" else "EyeTrackVR-Overlay"
    if getattr(sys, "frozen", False):
        path = resource_path(f"{'Tools/linux' if sys.platform == 'linux' else 'Tools'}/{name}")
        hint = "the app bundle is missing it"
    else:
        path = str(OVERLAY_DIST / overlay_dist_folder() / name)
        hint = "run: git submodule update --init overlay"
    if not os.path.isfile(path):
        raise FileNotFoundError(f"in-VR overlay binary not found at {path}; {hint}")
    return path


def overlay_language_arg() -> str:
    """``--lang=<code>`` for the app's active UI language."""
    try:
        from localization import get_active_language

        code = get_active_language() or "en"
    except Exception:
        code = "en"
    return f"--lang={code}"


def overlay_command(*args: str, executable: str | None = None) -> list[str]:
    """argv for launching the overlay with ``args`` (mode name, range flags)."""
    return [executable or overlay_executable(), *args, overlay_language_arg()]
