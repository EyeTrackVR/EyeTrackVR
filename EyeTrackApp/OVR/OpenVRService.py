import openvr
import os
import sys
import json
from logging import getLogger, ERROR, WARN
from config import EyeTrackConfig
from eye import EyeId
from colorama import Fore
import PySimpleGUI as sg

class OpenVRException(Exception):
    pass

class OpenVRService:
    appKey: str = "etvr.etvrapp"
    manifest = {
        "source": "builtin",
        "applications": [
            {
                "app_key": appKey,
                "launch_type": "binary",
                "binary_path_windows": sys.executable,
                "is_dashboard_overlay": True,

                "strings": {
                    "en_us": {
                        "name": "EyeTrackVR",
                        "description": "EyeTrackVR allow translating a camera feed into face tracking datas."
                    }
                }
            }
        ]
    }

    manifestPath: str = os.path.abspath("app.vrmanifest")

    # Write openvr manifest file
    def write_manifest() -> None:
        with open(OpenVRService.manifestPath, 'w') as f:
            json.dump(OpenVRService.manifest, f)

    def __init__(self) -> None:
        self.is_initialized: bool = False
        self.logger = getLogger(__name__)

    # Initialize the openvr connection if it wasn't already
    def initialize(self):
        if self.is_initialized:
            return 

        try:
            openvr.init(openvr.VRApplication_Background)
        except openvr.error_code.InitError_Init_NoServerForBackgroundApp:
            raise OpenVRException("SteamVR is not running")
        except (openvr.error_code.InitError_Init_HmdNotFound,
                openvr.error_code.InitError_Init_HmdNotFoundPresenceFailed):
            raise OpenVRException("No headset connected")
        except openvr.error_code.InitError_Init_PathRegistryNotFound:
            raise OpenVRException("SteamVR might not be installed")
        except Exception as e:
            raise OpenVRException(f"Unknown SteamVR initialization error ({e.__class__.__name__})")

    def set_autostart(self, enabled: bool):
        if enabled:
            self.initialize()

            self.app = openvr.IVRApplications()
            # Write the manifest dynamically depending on current executable path
            OpenVRService.write_manifest()
            try:
                self.app.addApplicationManifest(OpenVRService.manifestPath)
                self.app.setApplicationAutoLaunch(OpenVRService.appKey, True)
            except openvr.error_code.ApplicationError_UnknownApplication:
                self.logger.log(ERROR, f"{Fore.RED}[ERROR] Could not register app in SteamVR")
                raise OpenVRException("Could not register SteamVR app")
            except Exception as e:
                raise OpenVRException(f"Unknown error enabling auto launch: {e.__class__.__name__}")
        else:
            if os.path.exists(OpenVRService.manifestPath):
                if self.initialize():
                    try:
                        self.app.removeApplicationManifest(OpenVRService.manifestPath)
                    except openvr.error_code.ApplicationError_UnknownApplication:
                        pass
                # App won't autostart if the manifest doesn't exit anymore when SteamVR starts.
                os.remove(OpenVRService.manifestPath)


    # Called when general settings get updated in case autostart option is modified
    def on_config_update(self, data):
        if "gui_openvr_autostart" in data:
            try:
                self.set_autostart(data["gui_openvr_autostart"])
            except OpenVRException as e:
                # Uncheck the autostart option if we failed to toggle it on
                self.window[f"-OPENVRAUTOSTART{EyeId.SETTINGS}-"].update(False)
                self.logger.log(WARN, f"{Fore.YELLOW}[WARN] Cannot enable steamvr autostart: {e.args[0]}")
                sg.popup_ok(
                    f"Cannot enable steamvr autostart: {e.args[0]}",
                    title="Warning",
                    text_color="#ffae42",
                    background_color="#292929"
                )


openvr_service = OpenVRService()
