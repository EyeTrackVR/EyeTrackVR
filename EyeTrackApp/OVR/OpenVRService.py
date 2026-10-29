import openvr
import os
import shlex
import subprocess
import sys
import json
import threading
import time
from logging import getLogger, WARN, INFO
import tkinter as tk
from tkinter import messagebox
from colorama import Fore

from config import _USER_DATA_DIR
from localization import tr


class OpenVRException(Exception):
    pass


class SteamVRNotRunning(OpenVRException):
    """SteamVR is closed: a soft condition, applied later when it starts."""


# How often to retry connecting while SteamVR is closed, and to check that a
# connected SteamVR is still alive (a crashed vrserver sends no quit event).
_RECONNECT_S = 5.0
_LIVENESS_S = 5.0


def _is_frozen() -> bool:
    """True when running from a PyInstaller/py2exe bundle."""
    return bool(getattr(sys, "frozen", False))


def _app_dir() -> str:
    """Stable, absolute directory to anchor the vrmanifest in.

    Frozen build : folder containing the executable.
    From source  : folder containing the launched entry script.

    The previous implementation used ``os.path.abspath("app.vrmanifest")``,
    which resolves against the *current working directory*. That directory is
    not stable between launches (Start-menu shortcut vs. running from the
    folder vs. being relaunched by SteamVR itself), so SteamVR ended up storing
    a manifest path that often pointed at a file that no longer existed. We
    anchor to the executable/script location instead so the path is identical
    on every run.
    """
    if _is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    entry = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if entry and os.path.isfile(entry):
        return os.path.dirname(entry)
    return os.path.abspath(os.getcwd())


def _launch_target():
    """Return ``(binary_path, arguments)`` describing how SteamVR relaunches us.

    Frozen build : launch the executable directly, no arguments.
    From source  : launch the Python interpreter with the entry script as its
                   (quoted) argument, so ``python eyetrackapp.py`` is
                   reproduced. On Windows the windowless pythonw.exe is used
                   when present so no console window opens with SteamVR.
    """
    binary = os.path.abspath(sys.executable)
    if _is_frozen():
        return binary, ""
    if sys.platform == "win32":
        windowless = os.path.join(os.path.dirname(binary), "pythonw.exe")
        if os.path.isfile(windowless):
            binary = windowless
    entry = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if not entry:
        return binary, ""
    # SteamVR splits the arguments string itself; double quotes keep a path with spaces whole.
    return binary, subprocess.list2cmdline([entry])


def _unquote(arguments: str) -> str:
    try:
        parts = shlex.split(arguments, posix=sys.platform != "win32")
    except ValueError:
        return arguments
    return parts[0].strip('"') if parts else ""


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _vrserver_running() -> bool:
    """Whether SteamVR's server process exists. Unknown platforms report True
    so the check can only ever drop a dead connection, never a live one."""
    try:
        if sys.platform.startswith("linux"):
            for pid in os.listdir("/proc"):
                if pid.isdigit():
                    try:
                        with open(f"/proc/{pid}/comm", "rb") as comm:
                            if comm.read().strip() == b"vrserver":
                                return True
                    except OSError:
                        continue
            return False
        if sys.platform == "win32":
            return _windows_process_running("vrserver.exe")
    except Exception:
        pass
    return True


def _windows_process_running(name: str) -> bool:
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        return True
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == name:
                return True
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return False
    finally:
        kernel32.CloseHandle(snapshot)


class OpenVRService:
    appKey: str = "etvr.etvrapp"

    def __init__(self) -> None:
        self.is_initialized: bool = False
        self.app = None
        self.window = None
        # Tracks the user's desired state so poll/reconnect only run when the
        # "Start and Stop With SteamVR" option is actually enabled.
        self.autostart_enabled: bool = False
        # Registration succeeded against the SteamVR we are connected to.
        self._registered: bool = False
        # openvr.init can take ~100 ms while SteamVR is closed, so reconnects
        # run on a worker thread; the lock serializes every OpenVR session change.
        self._lock = threading.RLock()
        self._connecting = False
        self._next_reconnect = 0.0
        self._next_liveness = 0.0
        self._liveness_running = False
        self._server_gone = False
        self.logger = getLogger(__name__)

    @property
    def manifestPath(self) -> str:
        # Keep the manifest with the settings file. On Windows and in source
        # checkouts that is the app folder, elsewhere the user config folder.
        return os.path.join(_USER_DATA_DIR or _app_dir(), "app.vrmanifest")

    def _old_manifest_path(self):
        """The manifest older versions wrote next to the app, if it is still there."""
        old = os.path.join(_app_dir(), "app.vrmanifest")
        if os.path.isfile(old) and not _same_path(old, self.manifestPath):
            return old
        return None

    def _build_manifest(self) -> dict:
        binary, arguments = _launch_target()
        application = {
            "app_key": self.appKey,
            "launch_type": "binary",
            "is_dashboard_overlay": True,
            # The config and logs resolve relative to the app; never inherit
            # whatever directory SteamVR happens to launch from.
            "working_directory": _app_dir(),
            "strings": {
                "en_us": {
                    "name": "EyeTrackVR",
                    "description": "EyeTrackVR translates a camera feed into eye/face tracking data.",
                }
            },
        }
        # Only emit the key for the platform we're actually running on: that's
        # the machine that will launch us. Adding binary_path_linux here is what
        # makes auto-launch work on Linux.
        if sys.platform.startswith("linux"):
            application["binary_path_linux"] = binary
        elif sys.platform == "darwin":
            application["binary_path_osx"] = binary
        else:
            application["binary_path_windows"] = binary
        if arguments:
            application["arguments"] = arguments
        return {"source": "builtin", "applications": [application]}

    def write_manifest(self) -> None:
        with open(self.manifestPath, "w", encoding="utf-8") as f:
            json.dump(self._build_manifest(), f, indent=2)

    def _connect(self) -> None:
        try:
            openvr.init(openvr.VRApplication_Background)
            self.app = openvr.IVRApplications()
        except openvr.error_code.InitError_Init_NoServerForBackgroundApp:
            raise SteamVRNotRunning("SteamVR is not running")
        except (
            openvr.error_code.InitError_Init_HmdNotFound,
            openvr.error_code.InitError_Init_HmdNotFoundPresenceFailed,
        ):
            raise OpenVRException("No headset connected")
        except openvr.error_code.InitError_Init_PathRegistryNotFound:
            raise OpenVRException("SteamVR might not be installed")
        except Exception as e:
            raise OpenVRException(
                f"Unknown SteamVR initialization error ({e.__class__.__name__})"
            )
        # Tell SteamVR this process is the auto-launch app, so it doesn't start
        # a second copy of a manually opened EyeTrackVR.
        try:
            self.app.identifyApplication(os.getpid(), self.appKey)
        except Exception:
            pass

    def initialize(self) -> bool:
        with self._lock:
            if self.is_initialized:
                return True
            self._connect()
            self.is_initialized = True
            self._server_gone = False
            return True

    def _shutdown(self) -> None:
        with self._lock:
            if self.is_initialized:
                try:
                    openvr.shutdown()
                except Exception:
                    pass
            self.is_initialized = False
            self._registered = False
            self.app = None

    def _call_app_api(self, action: str, callback) -> None:
        """Call an IVRApplications method and normalize binding errors.

        pyopenvr checks the native EVRApplicationError itself: it raises an
        ApplicationError subclass on failure and returns ``None`` on success.
        Treating that successful ``None`` as an error caused Beta 8 to reject
        every manifest on Windows before it could enable auto-launch.
        """
        try:
            callback()
        except Exception as e:
            detail = str(e).strip() or e.__class__.__name__
            raise OpenVRException(f"{action} failed: {detail}") from e

    def _remove_stale_registration(self) -> None:
        """Drop a registration for this app key that points at another install.

        Linux tarballs unpack to a versioned folder, and a reinstall or a moved
        checkout changes the path too. SteamVR refuses a second manifest with the
        same key, so auto-launch would keep starting the old (or missing) binary."""
        try:
            if not self.app.isApplicationInstalled(self.appKey):
                return
            old_binary = self.app.getApplicationPropertyString(
                self.appKey, openvr.VRApplicationProperty_BinaryPath_String)
            old_arguments = self.app.getApplicationPropertyString(
                self.appKey, openvr.VRApplicationProperty_Arguments_String)
        except Exception:
            return
        binary, arguments = _launch_target()
        same_install = (old_binary and _same_path(old_binary, binary)
                        and _unquote(old_arguments or "") == _unquote(arguments))
        candidates = []
        if old_binary and not same_install:
            candidates.append(os.path.join(os.path.dirname(old_binary), "app.vrmanifest"))
        script = _unquote(old_arguments or "")
        if script and not same_install:
            candidates.append(os.path.join(os.path.dirname(script), "app.vrmanifest"))
        old_manifest = self._old_manifest_path()
        if old_manifest:
            candidates.append(old_manifest)
        for path in candidates:
            if _same_path(path, self.manifestPath):
                continue
            try:
                self.app.removeApplicationManifest(path)
                self.logger.log(INFO, f"[INFO] Removed stale SteamVR registration {path}")
            except Exception:
                pass
        if old_manifest:
            try:
                os.remove(old_manifest)
            except OSError:
                pass

    def _register_connected(self) -> None:
        """Write the manifest and register it for auto-launch (session must be open)."""
        self.write_manifest()
        self._remove_stale_registration()
        try:
            self._call_app_api(
                "Register manifest",
                lambda: self.app.addApplicationManifest(self.manifestPath),
            )
        except OpenVRException as e:
            key_taken = getattr(openvr.error_code, "ApplicationError_AppKeyAlreadyExists", ())
            if not isinstance(e.__cause__, key_taken):
                raise
            # A registration we could not identify still holds the key: replace it.
            self._call_app_api(
                "Register manifest",
                lambda: self.app.removeApplicationManifest(self.manifestPath),
            )
            self._call_app_api(
                "Register manifest",
                lambda: self.app.addApplicationManifest(self.manifestPath),
            )
        self._call_app_api(
            "Enable auto-launch",
            lambda: self.app.setApplicationAutoLaunch(self.appKey, True),
        )
        self._registered = True
        self.logger.log(
            INFO,
            f"{Fore.GREEN}[INFO] Registered EyeTrackVR for SteamVR auto-launch",
        )

    def _register(self) -> None:
        """(Re)write the manifest and register it for auto-launch.

        Requires a running SteamVR: raises SteamVRNotRunning otherwise.
        """
        with self._lock:
            self.initialize()
            self._register_connected()

    def _unregister(self) -> None:
        """Best-effort removal of the auto-launch registration and manifest."""
        with self._lock:
            paths = [self.manifestPath]
            old_manifest = self._old_manifest_path()
            if old_manifest:
                paths.append(old_manifest)
            try:
                self.initialize()
                if self.app is not None:
                    try:
                        self.app.setApplicationAutoLaunch(self.appKey, False)
                    except Exception:
                        pass
                    for path in paths:
                        try:
                            self.app.removeApplicationManifest(path)
                        except Exception:
                            pass
            except OpenVRException:
                # SteamVR isn't running; deleting the manifest file is enough,
                # since SteamVR won't auto-launch an app whose manifest no longer exists.
                pass
            self._registered = False
            for path in paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass

    def ensure_registered(self) -> None:
        """Re-assert auto-launch registration at startup.

        Self-heals the common case where the user enabled the option while
        SteamVR was closed: the manifest couldn't be registered then, but the
        next time the app starts with SteamVR open we register it here.
        """
        if not self.autostart_enabled:
            return
        try:
            self._register()
        except OpenVRException as e:
            # Quiet at startup: this will self-heal on a later run.
            self.logger.log(
                INFO,
                f"{Fore.CYAN}[INFO] SteamVR auto-launch not registered yet ({e.args[0]})",
            )
        except OSError as e:
            # e.g. unwritable app dir for the manifest; never fatal at startup.
            self.logger.log(
                WARN,
                f"{Fore.YELLOW}[WARN] SteamVR auto-launch manifest could not be written ({e})",
            )

    def _connect_in_background(self) -> None:
        """Worker: connect to a SteamVR that started after us, then register."""
        try:
            with self._lock:
                if self.is_initialized or not self.autostart_enabled:
                    return
                self._connect()
                # Registering here covers enabling the option while SteamVR was
                # closed: otherwise SteamVR would only learn of us on the next run.
                if not self._registered:
                    try:
                        self._register_connected()
                    except (OpenVRException, OSError) as e:
                        self.logger.log(WARN, f"[WARN] SteamVR auto-launch registration failed ({e})")
                self.is_initialized = True
                self._server_gone = False
                self.logger.log(INFO, "[INFO] Connected to SteamVR")
        except OpenVRException:
            pass
        except Exception:
            self.logger.exception("SteamVR connection attempt failed")
        finally:
            self._connecting = False

    def _check_liveness(self) -> None:
        try:
            self._server_gone = not _vrserver_running()
        finally:
            self._liveness_running = False

    def poll_quit_event(self) -> bool:
        """Drain the OpenVR event queue. Returns True if SteamVR sent a quit event.

        Called on the Tk thread every tick; never blocks on SteamVR."""
        if not self.autostart_enabled:
            return False
        now = time.monotonic()

        if not self.is_initialized:
            # Lazily (re)connect so we can still detect SteamVR shutting down
            # even when SteamVR started *after* this app.
            if not self._connecting and now >= self._next_reconnect:
                self._next_reconnect = now + _RECONNECT_S
                self._connecting = True
                threading.Thread(target=self._connect_in_background, daemon=True,
                                 name="SteamVRConnect").start()
            return False

        if self._server_gone:
            # SteamVR crashed or was killed: no quit event will ever come.
            self.logger.log(INFO, "[INFO] SteamVR is gone; waiting for it to start again")
            self._shutdown()
            self._server_gone = False
            self._next_reconnect = now + _RECONNECT_S
            return False
        if not self._liveness_running and now >= self._next_liveness:
            self._next_liveness = now + _LIVENESS_S
            self._liveness_running = True
            threading.Thread(target=self._check_liveness, daemon=True, name="SteamVRLiveness").start()

        if not self._lock.acquire(blocking=False):
            return False  # a registration is in progress; poll next tick
        try:
            system = openvr.VRSystem()
            event = openvr.VREvent_t()
            while system.pollNextEvent(event):
                if event.eventType == openvr.VREvent_Quit:
                    # Tell SteamVR we are exiting so it doesn't wait on us.
                    try:
                        system.acknowledgeQuit_Exiting()
                    except Exception:
                        pass
                    self._shutdown()
                    return True
        except Exception:
            # Lost the connection (e.g. SteamVR closed without a clean quit
            # event). Drop it and let the reconnect above retry; don't
            # force-quit the whole app on a transient polling error.
            self._shutdown()
        finally:
            self._lock.release()
        return False

    def set_autostart(self, enabled: bool):
        self.autostart_enabled = enabled
        if enabled:
            try:
                self._register()
            except SteamVRNotRunning:
                # SteamVR not running yet: keep the user's choice. The background
                # reconnect registers as soon as SteamVR starts. Any other error
                # propagates so the UI can surface it and revert the checkbox.
                self.logger.log(
                    INFO,
                    f"{Fore.CYAN}[INFO] SteamVR not running; auto-launch will be "
                    f"registered as soon as SteamVR starts.",
                )
                # Still drop a manifest so a manual SteamVR scan can find it.
                try:
                    self.write_manifest()
                except OSError:
                    pass
                self._next_reconnect = 0.0
        else:
            self._unregister()
            # Stop listening for SteamVR quit events once the option is off.
            self._shutdown()

    # Called when general settings get updated in case autostart option is modified
    def on_config_update(self, data):
        if "gui_openvr_autostart" in data:
            try:
                self.set_autostart(data["gui_openvr_autostart"])
            except (OpenVRException, OSError) as e:
                self.autostart_enabled = False
                if self.window is not None and hasattr(self.window, "set_openvr_autostart"):
                    self.window.set_openvr_autostart(False)
                error = e.args[0] if isinstance(e, OpenVRException) else str(e)
                self.logger.log(
                    WARN,
                    f"{Fore.YELLOW}[WARN] Cannot enable steamvr autostart: {error}",
                )
                _show_warning(
                    tr("openvr.warning_title"),
                    tr("openvr.autostart_failed", error=error),
                )


def _show_warning(title: str, message: str) -> None:
    # A second tk.Tk() alongside the app root breaks Tk variables/images, so
    # parent the dialog to the existing root and only create one if none exists.
    root = getattr(tk, "_default_root", None)
    if root is not None:
        messagebox.showwarning(title, message, parent=root)
        return
    popup_root = tk.Tk()
    popup_root.withdraw()
    try:
        messagebox.showwarning(title, message, parent=popup_root)
    finally:
        popup_root.destroy()

openvr_service = OpenVRService()
