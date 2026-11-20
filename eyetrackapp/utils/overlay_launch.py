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
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Self

from utils.misc_utils import resource_path

logger = logging.getLogger(__name__)

# packaging/fetch_overlay.py downloads the runtimes into overlay/<platform>/.
OVERLAY_DIST = Path(__file__).resolve().parents[2] / "overlay"


def overlay_dist_folder() -> str:
    """The overlay/ folder holding this platform's runtime."""
    if sys.platform == "win32":
        return "windows"
    return "linux-arm64" if platform.machine().lower() in ("aarch64", "arm64") else "linux"


def overlay_executable() -> str:
    """Resolve the overlay binary for this platform.

    Bundled builds carry it as ``tools/EyeTrackVR-Overlay.exe`` (Windows) or
    ``tools/linux/EyeTrackVR-Overlay`` with its loaders (Linux); source runs
    use ``overlay/<platform>/`` from packaging/fetch_overlay.py. Raises
    FileNotFoundError when unavailable so callers can fall back gracefully.
    """
    name = "EyeTrackVR-Overlay.exe" if sys.platform == "win32" else "EyeTrackVR-Overlay"
    if getattr(sys, "frozen", False):
        path = resource_path(f"{'tools/linux' if sys.platform == 'linux' else 'tools'}/{name}")
        hint = "the app bundle is missing it"
    else:
        path = str(OVERLAY_DIST / overlay_dist_folder() / name)
        hint = f"run: python packaging/fetch_overlay.py {overlay_dist_folder()}"
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
# The overlay's interactive and preview modes take commands here.
OVERLAY_CMD_PORT = 2113

# Interactive overlay protocol (the overlay's modes.cpp): the app places each
# dot. 110 starts a pass and is answered by 10 once it runs. 111 <x> <y> then
# glides a dot to (x, y), converges its ring and signals 20 as the dot becomes
# capture-ready, holds it 0.5 s and keeps it on screen until the next 111.
# Commands that arrive during that hold wait for it to end. 119 ends the pass
# with 19, 50 <utf-8> shows text, 98 hides it and 200 quits.
SIG_PASS_RUNNING = 10
SIG_PASS_ENDED = 19
SIG_DOT_HELD = 20
SIG_READY = 255
CMD_TEXT = 50
CMD_HIDE_TEXT = 98
CMD_START_PASS = 110
CMD_DOT = 111
CMD_END_PASS = 119
CMD_QUIT = 200


# The overlay shows at most this many bytes of text.
HEADSET_TEXT_BYTES = 400


def headset_text(lines: list) -> str:
    """``lines`` as overlay text, cut to whole lines that fit."""
    lines = list(lines)
    while len("\n".join(lines).encode("utf-8")) > HEADSET_TEXT_BYTES and len(lines) > 1:
        lines.pop()
    return "\n".join(lines).encode("utf-8")[:HEADSET_TEXT_BYTES].decode("utf-8", "ignore")


class OverlayExited(OSError):
    """The overlay process ended before the calibration finished."""


class OverlayStopped(Exception):
    """The app stopped waiting for the overlay."""


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
        self._cmd_sock: socket.socket | None = None
        self._log = None
        self._finished = False
        self._deadline = 0.0
        self._started_wall = 0.0

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
            self._started_wall = time.time()
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

    def wait_for(self, signal: int, keep_going=lambda: True) -> None:
        """Read signals until ``signal`` arrives. Raises OverlayStopped once
        ``keep_going()`` is false."""
        while True:
            if not keep_going():
                raise OverlayStopped
            data = self.recv(16)
            if len(data) >= 4 and struct.unpack(">i", data[:4])[0] == signal:
                return

    def pause(self, seconds: float, keep_going=lambda: True) -> None:
        """Wait ``seconds``. Raises OverlayStopped once ``keep_going()`` is
        false and OverlayExited when the overlay quits meanwhile."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if not keep_going():
                raise OverlayStopped
            code = self.process.poll()
            if code is not None:
                raise OverlayExited(f"calibration overlay exited with code {code}; see calibration-overlay.log")
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def send(self, code: int, *values: float) -> None:
        """Send a command and its float arguments to the overlay's command port."""
        self._send_command(struct.pack(f">i{len(values)}f", code, *values))

    def send_text(self, code: int, text: str) -> None:
        """Send a command followed by UTF-8 text."""
        self._send_command(struct.pack(">i", code) + text.encode("utf-8"))

    def _send_command(self, payload: bytes) -> None:
        if self._cmd_sock is None:
            self._cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._cmd_sock.sendto(payload, ("127.0.0.1", OVERLAY_CMD_PORT))

    def log_text(self) -> str:
        """What the overlay has logged in this run so far (its resolved gaze
        range among it). Its output file can lag while it runs, so this also
        reads the overlay's own per-line-flushed log, which is beside the
        binary or in the temp folder when that is read-only."""
        import tempfile

        paths = []
        if self._log is not None:
            paths.append(Path(self._log.name))
        if self.process is not None:
            name = "eyetrackvr_overlay.log"
            paths += [Path(self.process.args[0]).parent / name, Path(tempfile.gettempdir()) / name]
        text = []
        for path in paths:
            try:
                if path.stat().st_mtime >= self._started_wall - 1.0:
                    text.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        return "\n".join(text)

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
            for resource in (self.sock, self._cmd_sock, self._log):
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
