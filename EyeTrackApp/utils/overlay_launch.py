"""Locating and launching the in-VR calibration overlay (EyeTrackVR-Overlay).

Every launch goes through ``overlay_command`` so the overlay always shows its
instruction text in the app's active UI language (``--lang=<code>``). The
overlay has built-in text for every language in ``lang/``; an unknown code
(e.g. a newly dropped-in language) falls back to English there, while the text
the app itself sends during data collection still comes from ``lang/``.
"""

from __future__ import annotations

import os
import sys

from utils.misc_utils import resource_path


def overlay_executable() -> str:
    """Resolve the overlay binary for this platform.

    Windows builds ship ``Tools/EyeTrackVR-Overlay.exe``; Linux ships the native
    ``Tools/linux/EyeTrackVR-Overlay`` alongside its loaders. Raises
    FileNotFoundError when unavailable so callers can fall back gracefully.
    """
    name = "EyeTrackVR-Overlay.exe" if sys.platform == "win32" else "EyeTrackVR-Overlay"
    folder = "Tools/linux" if sys.platform == "linux" else "Tools"
    path = resource_path(f"{folder}/{name}")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"in-VR overlay binary not found at {path}; overlay calibration "
            "requires the platform's native executable and runtime files in "
            f"{folder}/"
        )
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
