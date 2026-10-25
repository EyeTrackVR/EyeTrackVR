"""One EyeTrackVR per user: a second copy would fight the first over cameras and
OSC ports (e.g. opened by hand, then auto-launched again by SteamVR).

The lock is an OS file lock, so it is released automatically when the process
exits or crashes; a stale lock file never blocks the next start."""
import os
from pathlib import Path
import sys

_handle = None


def _lock_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("XDG_STATE_HOME")
                    or Path.home() / ".local/state")
    return base / "EyeTrackVR" / "eyetrackapp.lock"


def acquire(path=None) -> bool:
    """True if this process is the only running EyeTrackVR (keep the lock for life)."""
    global _handle
    if _handle is not None:
        return True
    path = Path(path) if path is not None else _lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+b")
    except OSError:
        return True  # cannot lock: never refuse to start because of it
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, 2) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _handle = handle
    return True


def release() -> None:
    global _handle
    if _handle is not None:
        try:
            _handle.close()
        finally:
            _handle = None
