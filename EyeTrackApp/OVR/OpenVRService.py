import openvr
import os
import sys
import json
from logging import getLogger, WARN, INFO
import tkinter as tk
from tkinter import messagebox
from colorama import Fore

from localization import tr


class OpenVRException(Exception):
    pass


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
                   argument, so ``python eyetrackapp.py`` is reproduced. The
                   old code always used ``sys.executable`` with no arguments,
                   which meant a from-source install registered ``python.exe``
                   with no script and SteamVR launched a do-nothing interpreter.
    """
    binary = os.path.abspath(sys.executable)
    if _is_frozen():
        return binary, ""
    entry = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    return binary, entry


class OpenVRService:
    appKey: str = "etvr.etvrapp"

    def __init__(self) -> None:
        self.is_initialized: bool = False
        self.app = None
        self.window = None
        # Tracks the user's desired state so poll/reconnect only run when the
        # "Start and Stop With SteamVR" option is actually enabled.
        self.autostart_enabled: bool = False
        self._reconnect_ticks: int = 0
        self.logger = getLogger(__name__)

    @property
    def manifestPath(self) -> str:
        return os.path.join(_app_dir(), "app.vrmanifest")

    def _build_manifest(self) -> dict:
        binary, arguments = _launch_target()
        application = {
            "app_key": self.appKey,
            "launch_type": "binary",
            "is_dashboard_overlay": True,
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

    def initialize(self) -> bool:
        if self.is_initialized:
            return True

        try:
            openvr.init(openvr.VRApplication_Background)
            self.app = openvr.IVRApplications()
            self.is_initialized = True
        except openvr.error_code.InitError_Init_NoServerForBackgroundApp:
            raise OpenVRException("SteamVR is not running")
        except (
            openvr.error_code.InitError_Init_HmdNotFound,
            openvr.error_code.InitError_Init_HmdNotFoundPresenceFailed,
        ):
            raise OpenVRException("No headset connected")
        except openvr.error_code.InitError_Init_PathRegistryNotFound:
            raise OpenVRException("SteamVR might not be installed")
        except OpenVRException:
            raise
        except Exception as e:
            raise OpenVRException(
                f"Unknown SteamVR initialization error ({e.__class__.__name__})"
            )
        return True

    def _shutdown(self) -> None:
        if self.is_initialized:
            try:
                openvr.shutdown()
            except Exception:
                pass
        self.is_initialized = False
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

    def _register(self) -> None:
        """(Re)write the manifest and register it for auto-launch.

        Requires a running SteamVR: raises OpenVRException("SteamVR is not
        running") otherwise.
        """
        self.initialize()
        self.write_manifest()
        self._call_app_api(
            "Register manifest",
            lambda: self.app.addApplicationManifest(self.manifestPath),
        )
        self._call_app_api(
            "Enable auto-launch",
            lambda: self.app.setApplicationAutoLaunch(self.appKey, True),
        )
        self.logger.log(
            INFO,
            f"{Fore.GREEN}[INFO] Registered EyeTrackVR for SteamVR auto-launch",
        )

    def _unregister(self) -> None:
        """Best-effort removal of the auto-launch registration and manifest."""
        try:
            self.initialize()
            if self.app is not None:
                try:
                    self.app.setApplicationAutoLaunch(self.appKey, False)
                except Exception:
                    pass
                try:
                    self.app.removeApplicationManifest(self.manifestPath)
                except Exception:
                    pass
        except OpenVRException:
            # SteamVR isn't running; deleting the manifest file is enough,
            # since SteamVR won't auto-launch an app whose manifest no longer exists.
            pass
        try:
            if os.path.exists(self.manifestPath):
                os.remove(self.manifestPath)
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

    def poll_quit_event(self) -> bool:
        """Drain the OpenVR event queue. Returns True if SteamVR sent a quit event."""
        if not self.autostart_enabled:
            return False

        if not self.is_initialized:
            # Lazily (re)connect so we can still detect SteamVR shutting down
            # even when SteamVR started *after* this app. Throttled so we don't
            # call openvr.init() on every ~33 ms tick while SteamVR is closed.
            self._reconnect_ticks += 1
            if self._reconnect_ticks < 150:
                return False
            self._reconnect_ticks = 0
            try:
                self.initialize()
            except OpenVRException:
                return False

        try:
            system = openvr.VRSystem()
            event = openvr.VREvent_t()
            while system.pollNextEvent(event):
                if event.eventType == openvr.VREvent_Quit:
                    self._shutdown()
                    return True
        except Exception:
            # Lost the connection (e.g. SteamVR closed without a clean quit
            # event). Drop it and let the throttled reconnect above retry;
            # don't force-quit the whole app on a transient polling error.
            self._shutdown()
        return False

    def set_autostart(self, enabled: bool):
        self.autostart_enabled = enabled
        if enabled:
            try:
                self._register()
            except OpenVRException as e:
                # SteamVR not running yet: keep the user's choice and apply it
                # the next time the app starts with SteamVR open (ensure_registered).
                # Only "not running" is soft; any other error propagates so the
                # UI can surface it and revert the checkbox.
                if "not running" in str(e).lower():
                    self.logger.log(
                        INFO,
                        f"{Fore.CYAN}[INFO] SteamVR not running; auto-launch will be "
                        f"registered the next time EyeTrackVR starts with SteamVR open.",
                    )
                    # Still drop a manifest so a manual SteamVR scan can find it.
                    try:
                        self.write_manifest()
                    except OSError:
                        pass
                    return
                raise
        else:
            self._unregister()
            # Stop listening for SteamVR quit events once the option is off.
            self._shutdown()

    # Called when general settings get updated in case autostart option is modified
    def on_config_update(self, data):
        if "gui_openvr_autostart" in data:
            try:
                self.set_autostart(data["gui_openvr_autostart"])
            except OpenVRException as e:
                self.autostart_enabled = False
                if self.window is not None and hasattr(self.window, "set_openvr_autostart"):
                    self.window.set_openvr_autostart(False)
                self.logger.log(
                    WARN,
                    f"{Fore.YELLOW}[WARN] Cannot enable steamvr autostart: {e.args[0]}",
                )
                popup_root = tk.Tk()
                popup_root.withdraw()
                messagebox.showwarning(
                    tr("openvr.warning_title"),
                    tr("openvr.autostart_failed", error=e.args[0]),
                )
                popup_root.destroy()


openvr_service = OpenVRService()
