"""Locating and launching the in-VR calibration overlay (EyeTrackVR-Overlay).

Every launch goes through ``overlay_command`` so the overlay always shows its
instruction text in the app's active UI language (``--lang=<code>``). The
overlay has built-in text for every language in ``lang/``; an unknown code
(e.g. a newly dropped-in language) falls back to English there, while the text
the app itself sends during data collection still comes from ``lang/``.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Self

from utils.misc_utils import resource_path

logger = logging.getLogger(__name__)

# The overlay/ submodule ships prebuilt runtimes in dist/<platform>/.
OVERLAY_DIST = Path(__file__).resolve().parents[2] / "overlay" / "dist"


def overlay_dist_folder() -> str:
    """The overlay/dist/ folder holding this platform's runtime."""
    if sys.platform == "win32":
        return "windows"
    return "linux-arm64" if platform.machine().lower() in ("aarch64", "arm64") else "linux"


def overlay_executable() -> str:
    """Resolve the overlay binary for this platform.

    Bundled builds carry it as ``tools/EyeTrackVR-Overlay.exe`` (Windows) or
    ``tools/linux/EyeTrackVR-Overlay`` with its loaders (Linux); source runs
    use ``overlay/dist/<platform>/`` from the submodule. Raises
    FileNotFoundError when unavailable so callers can fall back gracefully.
    """
    name = "EyeTrackVR-Overlay.exe" if sys.platform == "win32" else "EyeTrackVR-Overlay"
    if getattr(sys, "frozen", False):
        path = resource_path(f"{'tools/linux' if sys.platform == 'linux' else 'tools'}/{name}")
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


# The overlay sends its calibration signals here as big-endian int32s.
OVERLAY_SIGNAL_PORT = 2112


class OverlayExited(OSError):
    """The overlay process ended before the calibration finished."""


class OverlaySession:
    """One calibration overlay run, from launch until the overlay has stopped.

    Binds the signal socket before launching, so the overlay's first signal
    can't be lost. ``recv`` raises ``TimeoutError`` (``socket.timeout``) when the overlay has sent
    nothing for ``timeout`` seconds, and ``OverlayExited`` when it quits
    early (for example when no VR runtime is running). The overlay's output
    goes to ``calibration-overlay.log`` in the log folder.

    On leaving the ``with`` block the overlay is stopped. After ``finish()``
    it first gets a few seconds to show its completion card and exit by itself.
    """

    POLL_S = 0.25
    FINISH_GRACE_S = 5.0
    TERMINATE_GRACE_S = 2.0

    def __init__(self, *args: str, timeout: float = 120.0):
        self.args = args
        self.timeout = timeout
        self.process: subprocess.Popen | None = None
        self.sock: socket.socket | None = None
        self._log = None
        self._finished = False
        self._deadline = 0.0

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.close()

    def start(self) -> Self:
        """Bind the signal socket and launch the overlay. ``with`` calls this and
        ``close``; call them directly when a run doesn't fit one block."""
        try:
            command = overlay_command(*self.args)
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(self.POLL_S)
            self.sock.bind(("127.0.0.1", OVERLAY_SIGNAL_PORT))
            self._log = _open_overlay_log()
            self.process = subprocess.Popen(
                command,
                cwd=os.path.dirname(command[0]),
                stdout=self._log if self._log is not None else subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._deadline = time.monotonic() + self.timeout
            return self
        except BaseException:
            self.close()
            raise

    def recv(self, bufsize: int = 4096) -> bytes:
        """The next datagram from the overlay."""
        while time.monotonic() < self._deadline:
            try:
                data, _ = self.sock.recvfrom(bufsize)
                self._deadline = time.monotonic() + self.timeout
                return data
            except TimeoutError:
                code = self.process.poll()
                if code is not None:
                    raise OverlayExited(f"calibration overlay exited with code {code}; see calibration-overlay.log")
        raise TimeoutError(f"calibration overlay sent nothing for {self.timeout:.0f} s")

    def finish(self) -> None:
        """The calibration completed; let the overlay close on its own."""
        self._finished = True

    def close(self) -> None:
        try:
            if self.process is not None and self.process.poll() is None:
                if self._finished:
                    try:
                        self.process.wait(timeout=self.FINISH_GRACE_S)
                    except subprocess.TimeoutExpired:
                        pass
                _stop(self.process, self.TERMINATE_GRACE_S)
        finally:
            for resource in (self.sock, self._log):
                if resource is not None:
                    try:
                        resource.close()
                    except OSError:
                        pass


def _stop(process: subprocess.Popen, grace: float) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except ProcessLookupError:
        pass


def _open_overlay_log():
    try:
        from utils.logging_utils import log_directory

        return open(log_directory() / "calibration-overlay.log", "w", encoding="utf-8")
    except OSError as e:
        logger.warning("Calibration overlay output not logged: %s", e)
        return None
