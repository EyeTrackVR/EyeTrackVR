"""
SteamVR companion for the app, run as its own process (`--dfr-monitor <port>`).

It holds a background OpenVR session separate from the app's (ovr/openvr_service.py
only connects while "Start and stop with SteamVR" is on, and owns quit handling). Over
the app's localhost socket, one JSON line per message (the frozen GUI build has no
usable stdout), it:

- reports the current scene application, for per-game DFR (ovr/dfr.py):

    {"type": "scene", "pid": 1234, "key": "steam.app.546560", "name": "Half-Life: Alyx", "exe": "C:\\...\\hlvr.exe"}
    {"type": "scene", "pid": 0}                       no SteamVR game in front
    {"type": "quit"}                                  SteamVR is closing; the monitor exits

- shows EyeTrackVR's dashboard panel once the app sends a "state" message, and reports
  clicks on it as "action" messages (ovr/vr_dashboard.py has both formats).

It exits when SteamVR quits (acknowledging the quit, which is true) or when the app
closes the socket.
"""

import json
import queue
import socket
import sys
import threading
import time

POLL_S = 0.5  # scene application checks
TICK_S = 0.05  # dashboard clicks and messages from the app
MARKER_TICK_S = 1 / 90  # while the gaze marker shows: it should move with the eyes


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


def _watch_socket(sock: socket.socket, stop: threading.Event, inbox: queue.Queue) -> None:
    """Messages from the app, until it closes the socket (it exited, or stopped us)."""
    try:
        for line in sock.makefile("r", encoding="utf-8"):
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict):
                inbox.put(message)
    except (OSError, ValueError):
        pass
    stop.set()


def run(port: int) -> int:
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    except OSError:
        return 1  # the app stopped listening; raising would pop the windowed build's error dialog
    sock.settimeout(None)
    out = sock.makefile("w", encoding="utf-8", newline="\n")

    def emit(message: dict) -> None:
        out.write(json.dumps(message) + "\n")
        out.flush()

    stop = threading.Event()
    inbox: queue.Queue = queue.Queue()
    threading.Thread(target=_watch_socket, args=(sock, stop, inbox), daemon=True).start()
    try:
        return _monitor(emit, stop, inbox)
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


def _dashboard_icon() -> str:
    from pathlib import Path

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return str(base / "assets" / "images" / "logo.png")


def _scene_message(openvr, apps, pid: int) -> dict:
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
    return message


def _monitor(emit, stop: threading.Event, inbox: queue.Queue | None = None) -> int:
    import openvr

    try:
        openvr.init(openvr.VRApplication_Background)
    except Exception as e:
        emit({"type": "error", "message": f"SteamVR not available ({e.__class__.__name__})"})
        return 1
    dashboard = None
    dashboard_failed = False
    try:
        apps = openvr.VRApplications()
        system = openvr.VRSystem()
        event = openvr.VREvent_t()
        last = None
        next_scene_check = 0.0
        try:  # the headset's per-eye view, for the app's foveation gaze (osc/foveation_gaze_sender.py)
            emit(
                {
                    "type": "hmd",
                    "left": [float(v) for v in system.getProjectionRaw(openvr.Eye_Left)],
                    "right": [float(v) for v in system.getProjectionRaw(openvr.Eye_Right)],
                }
            )
        except OSError:
            raise
        except Exception:
            pass
        while not stop.is_set():
            while system.pollNextEvent(event):
                if event.eventType == openvr.VREvent_Quit:
                    try:
                        system.acknowledgeQuit_Exiting()
                    except Exception:
                        pass
                    emit({"type": "quit"})
                    return 0
            now = time.monotonic()
            if now >= next_scene_check:
                next_scene_check = now + POLL_S
                pid = int(apps.getCurrentSceneProcessId() or 0)
                if pid != last:
                    last = pid
                    emit(_scene_message(openvr, apps, pid))

            while inbox is not None and not inbox.empty():
                message = inbox.get_nowait()
                if message.get("type") != "state" or dashboard_failed:
                    continue
                if dashboard is None:
                    try:
                        from ovr.vr_dashboard import Dashboard

                        dashboard = Dashboard(openvr, emit, _dashboard_icon())
                    except Exception as e:  # the panel is optional: scene reporting goes on
                        dashboard_failed = True
                        emit({"type": "error", "message": f"dashboard unavailable ({e.__class__.__name__}: {e})"})
                        continue
                dashboard.set_state(message)
            if dashboard is not None:
                try:
                    dashboard.poll()
                except OSError:
                    raise  # the app's socket closed
                except Exception as e:
                    dashboard, dashboard_failed = None, True
                    emit({"type": "error", "message": f"dashboard stopped ({e.__class__.__name__}: {e})"})
            if dashboard is None:
                stop.wait(min(POLL_S, 0.2))
            else:
                stop.wait(MARKER_TICK_S if dashboard.marker_on else TICK_S)
        return 0
    finally:
        if dashboard is not None:
            dashboard.close()
        try:
            openvr.shutdown()
        except Exception:
            pass
