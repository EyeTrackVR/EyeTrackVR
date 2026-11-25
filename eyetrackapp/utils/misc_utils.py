import os
import sys
from pathlib import Path
from typing import Union

is_nt = os.name == "nt"
# os.name is "posix" on both macOS and Linux, so the platform has to be read
# from sys.platform; the old `os.name == "Darwin"` check was never true.
is_macos = sys.platform == "darwin"
is_linux = sys.platform.startswith("linux")


SND_FILENAME = SND_ASYNC = 1

if is_nt:
    import winsound

    PlaySound = winsound.PlaySound
    SND_FILENAME = winsound.SND_FILENAME
    SND_ASYNC = winsound.SND_ASYNC
else:
    import shutil
    import subprocess

    # First available CLI player wins. paplay covers PulseAudio/PipeWire
    # (virtually every desktop distro), aplay is the ALSA fallback, afplay
    # is macOS. Resolved once at import so PlaySound stays cheap.
    _PLAYER = next((p for p in ("paplay", "aplay", "afplay") if shutil.which(p)), None)

    def PlaySound(sound, flags=0):
        """winsound.PlaySound-compatible shim. Only the (filename, ASYNC)
        call shape the app uses is supported; anything else is ignored."""
        if not sound or _PLAYER is None:
            return
        try:
            subprocess.Popen(
                [_PLAYER, str(sound)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass  # No audio stack (headless session); sounds are best-effort.


def clamp(x, low, high):
    return max(low, min(x, high))


def resource_path(relative_path: Union[str, Path]) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # In development, use the directory where this file is located (eyetrackapp/)
        base_path = Path(__file__).parent.parent

    return str(base_path / relative_path)
