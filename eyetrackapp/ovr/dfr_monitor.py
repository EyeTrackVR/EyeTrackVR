"""
SteamVR game monitor for per-game DFR, run as its own process (`--dfr-monitor <port>`).

It holds a background OpenVR session separate from the app's (ovr/openvr_service.py
only connects while "Start and stop with SteamVR" is on, and owns quit handling),
and sends one JSON line per change of the current scene application to the app's
localhost socket (the frozen GUI build has no usable stdout):

  {"type": "scene", "pid": 1234, "key": "steam.app.546560", "name": "Half-Life: Alyx", "exe": "C:\\...\\hlvr.exe"}
  {"type": "scene", "pid": 0}                       no SteamVR game in front
  {"type": "quit"}                                  SteamVR is closing; the monitor exits

It exits when SteamVR quits (acknowledging the quit, which is true) or when the app
closes the socket.
"""

import json
import socket
import sys
import threading
import time

POLL_S = 0.5


def process_image_path(pid: int) -> str:
    """Full path of a process's executable, or "" (Windows)."""
    if sys.platform != "win32" or pid <= 0:
        return ""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def app_key_for_pid(openvr, apps, pid: int) -> str:
    """SteamVR app key of a process. Calls the function table with a full-size buffer:
    pyopenvr's wrapper sizes its buffer from the error code of a probe call."""
    import ctypes

    try:
        buffer = ctypes.create_string_buffer(int(getattr(openvr, "k_unMaxApplicationKeyLength", 128)))
        error = apps.function_table.getApplicationKeyByProcessId(pid, buffer, len(buffer))
        if error == 0 and buffer.value:
            return buffer.value.decode("utf-8", "replace")
    except Exception:
        pass
    try:
        return apps.getApplicationKeyByProcessId(pid) or ""
    except Exception:
        return ""


def _watch_socket(sock: socket.socket, stop: threading.Event) -> None:
    """The app closes the socket when it exits or stops us."""
    try:
        while sock.recv(64):
            pass
    except OSError:
        pass
    stop.set()


def run(port: int) -> int:
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    sock.settimeout(None)
    out = sock.makefile("w", encoding="utf-8", newline="\n")

    def emit(message: dict) -> None:
        out.write(json.dumps(message) + "\n")
        out.flush()

    stop = threading.Event()
    threading.Thread(target=_watch_socket, args=(sock, stop), daemon=True).start()
    try:
        return _monitor(emit, stop)
    except OSError:
        return 0  # the app went away mid-write
    finally:
        try:
            out.flush()
            # FIN after the last line. A bare close() while the watcher thread sits
            # in recv() makes Windows reset the connection, which can drop "quit".
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass


def _monitor(emit, stop: threading.Event) -> int:
    import openvr

    try:
        openvr.init(openvr.VRApplication_Background)
    except Exception as e:
        emit({"type": "error", "message": f"SteamVR not available ({e.__class__.__name__})"})
        return 1
    try:
        apps = openvr.VRApplications()
        system = openvr.VRSystem()
        event = openvr.VREvent_t()
        last = None
        while not stop.is_set():
            while system.pollNextEvent(event):
                if event.eventType == openvr.VREvent_Quit:
                    try:
                        system.acknowledgeQuit_Exiting()
                    except Exception:
                        pass
                    emit({"type": "quit"})
                    return 0
            pid = int(apps.getCurrentSceneProcessId() or 0)
            if pid != last:
                last = pid
                message = {"type": "scene", "pid": pid}
                if pid:
                    key = app_key_for_pid(openvr, apps, pid)
                    name = ""
                    if key:
                        try:
                            name = apps.getApplicationPropertyString(key, openvr.VRApplicationProperty_Name_String)
                        except Exception:
                            name = ""
                    exe = process_image_path(pid)
                    message.update(key=key or f"pid.{pid}", name=name or exe.rsplit("\\", 1)[-1] or key, exe=exe)
                emit(message)
            time.sleep(POLL_S)
        return 0
    finally:
        try:
            openvr.shutdown()
        except Exception:
            pass
