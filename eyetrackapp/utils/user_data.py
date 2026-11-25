"""Where EyeTrackVR keeps the files it writes for the user (settings, calibration
statistics, recordings). One place decides the folder so nothing writes to the
working directory by accident."""

from __future__ import annotations

import glob
import logging
import os
import shutil
import sys
import tempfile

logger = logging.getLogger(__name__)

SETTINGS_NAME = "eyetrack_settings.json"
# Copied from an install folder on first start, settings file last (its
# presence in the new folder is what marks the migration done).
_MIGRATED_NAMES = ("eyetrack_settings.backup",)
_MIGRATED_PATTERNS = ("RANSAC_BLINK_*.cfg", "IBO_*.png", "EBPD_*.png")

# Resolution runs at import, before setup_logging() exists; it replays these.
_startup_messages: list[tuple[int, str]] = []


def _note(level: int, message: str) -> None:
    _startup_messages.append((level, message))


def log_startup_messages() -> None:
    """Log what resolving the folder did (called once logging is set up)."""
    while _startup_messages:
        level, message = _startup_messages.pop(0)
        logger.log(level, message)


def windows_data_home(localappdata: str | None = None) -> str:
    """%LOCALAPPDATA%\\EyeTrackVR, the folder contributions, updates and DFR tools
    already use (same fallback as contributions.client._data_home)."""
    if localappdata is None:
        localappdata = os.environ.get("LOCALAPPDATA")
    base = localappdata or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "EyeTrackVR")


def _inside(path: str, root: str | None) -> bool:
    if not root:
        return False
    path = os.path.normcase(os.path.abspath(path))
    root = os.path.normcase(os.path.abspath(root)).rstrip("\\/")
    return path.startswith(root + os.sep)


def is_installed_build(frozen: bool, exe_dir: str, environ=os.environ) -> bool:
    """A Windows build placed by the installer, whose folder users can't write.

    The release marker (build_info) only tells release from dev builds, and the
    same release build is also unzipped as a portable copy. Inno Setup leaves
    unins000.exe beside the exe; anything under Program Files counts too,
    because a copy there is not user-writable either way."""
    if not frozen:
        return False
    if glob.glob(os.path.join(glob.escape(exe_dir), "unins*.exe")):
        return True
    return any(_inside(exe_dir, environ.get(var)) for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"))


def _publish_new(src: str, dst: str) -> None:
    """Copy ``src`` to ``dst`` unless ``dst`` exists. The copy appears whole or
    not at all, and a second process doing the same never overwrites it."""
    if not os.path.isfile(src) or os.path.exists(dst):
        return
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(dst) + ".", suffix=".migrating", dir=os.path.dirname(dst))
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as source:
            shutil.copyfileobj(source, out)
            out.flush()
            os.fsync(out.fileno())
        try:
            # A hard link never replaces an existing name (NTFS and POSIX alike).
            os.link(tmp, dst)
        except FileExistsError:
            pass  # another instance migrated first
        except OSError:
            if os.name != "nt":
                raise
            try:
                os.rename(tmp, dst)  # no hard links here; Windows rename refuses to overwrite
            except FileExistsError:
                pass
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def migrate(new_dir: str, legacy_dirs) -> str:
    """Copy the user's files from where older versions kept them (the install
    folder) into ``new_dir``, once. Originals are never deleted and nothing in
    ``new_dir`` is overwritten. Returns the folder to use: ``new_dir``, or the
    old folder when copying failed, so the app still finds its settings."""
    if os.path.exists(os.path.join(new_dir, SETTINGS_NAME)):
        return new_dir
    source = next((d for d in legacy_dirs if os.path.isfile(os.path.join(d, SETTINGS_NAME))), None)
    if source is None:
        return new_dir
    names = list(_MIGRATED_NAMES)
    for pattern in _MIGRATED_PATTERNS:
        names += sorted(os.path.basename(p) for p in glob.glob(os.path.join(glob.escape(source), pattern)))
    try:
        for name in [*names, SETTINGS_NAME]:
            _publish_new(os.path.join(source, name), os.path.join(new_dir, name))
    except OSError as e:
        _note(logging.WARNING, f"Could not copy settings from {source} to {new_dir}, still using the old folder: {e!r}")
        return source
    _note(logging.INFO, f"Copied settings from {source} to {new_dir}; the originals were left in place")
    return new_dir


def _resolve_windows(frozen: bool, exe_dir: str, cwd: str, localappdata: str | None, environ=os.environ) -> str:
    installed = is_installed_build(frozen, exe_dir, environ)
    # Source checkouts and portable copies keep a settings file found in the
    # working directory; an installed build moves out of its install folder.
    if not installed and os.path.exists(os.path.join(cwd, SETTINGS_NAME)):
        return ""
    path = windows_data_home(localappdata)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        _note(logging.WARNING, f"Cannot create {path}, using the working directory: {e!r}")
        return ""
    if not installed:
        return path
    legacy = [exe_dir]
    if os.path.normcase(os.path.abspath(cwd)) != os.path.normcase(os.path.abspath(exe_dir)):
        legacy.append(cwd)
    return migrate(path, legacy)


def _resolve_user_data_dir() -> str:
    """Directory holding the settings file ("" means the working directory).

    Windows: %LOCALAPPDATA%\\EyeTrackVR (the install folder is not writable by
    the user), copying an installed build's old settings across once. Linux and
    macOS: the XDG config dir. A config file already present in the CWD wins for
    source checkouts and portable unpacked builds.
    """
    if os.name == "nt":
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        return _resolve_windows(bool(getattr(sys, "frozen", False)), exe_dir, os.getcwd(), None)
    if os.path.exists(SETTINGS_NAME):
        return ""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, "EyeTrackVR")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return ""
    return path


_USER_DATA_DIR = _resolve_user_data_dir()
_note(logging.INFO, f"User data folder: {os.path.abspath(_USER_DATA_DIR or os.curdir)}")


def user_data_dir() -> str:
    """The folder for user files; "" means the working directory."""
    return _USER_DATA_DIR


def user_data_path(name: str) -> str:
    """Path of a user file called ``name`` inside the user data folder."""
    return os.path.join(_USER_DATA_DIR, name)
