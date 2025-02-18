"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2025 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import os
import PySimpleGUI as sg
import queue
import requests
import threading
from camera_widget import CameraWidget
from config import EyeTrackConfig
from eye import EyeId
from settings.VRCFTModuleSettings import VRCFTSettingsWidget
from settings.general_settings_widget import SettingsWidget
from settings.algo_settings_widget import AlgoSettingsWidget
from osc.osc import OSCManager
from osc.OSCMessage import OSCMessage
from utils.misc_utils import is_nt, resource_path
import cv2
import numpy as np
import uuid

winmm = None

if is_nt:
    from winotify import Notification
    from ctypes import windll, c_int
    try:
        winmm = windll.winmm
    except OSError:
        print("\033[91m[WARN] Failed to load winmm.dll\033[0m")
os.system("color")  # init ANSI color


# Random environment variable to speed up webcam opening on the MSMF backend.
# https://github.com/opencv/opencv/issues/17687
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
WINDOW_NAME = "EyeTrackApp"



page_url = "https://github.com/RedHawk989/EyeTrackVR/releases/latest"
appversion = "EyeTrackApp 0.2.0 BETA 14"


class KeyManager:
    def __init__(self):
        self.update_keys()

    def update_keys(self):
        unique_id = str(uuid.uuid4())
        self.RIGHT_EYE_NAME = f"-RIGHTEYEWIDGET{unique_id}-"
        self.LEFT_EYE_NAME = f"-LEFTEYEWIDGET{unique_id}-"
        self.SETTINGS_NAME = f"-SETTINGSWIDGET{unique_id}-"
        self.ALGO_SETTINGS_NAME = f"-ALGOSETTINGSWIDGET{unique_id}-"
        self.VRCFT_MODULE_SETTINGS_NAME = f"-VRCFTSETTINGSWIDGET{unique_id}-"
        self.LEFT_EYE_RADIO_NAME = f"-LEFTEYERADIO{unique_id}-"
        self.RIGHT_EYE_RADIO_NAME = f"-RIGHTEYERADIO{unique_id}-"
        self.BOTH_EYE_RADIO_NAME = f"-BOTHEYERADIO{unique_id}-"
        self.SETTINGS_RADIO_NAME = f"-SETTINGSRADIO{unique_id}-"
        self.ALGO_SETTINGS_RADIO_NAME = f"-ALGOSETTINGSRADIO{unique_id}-"
        self.VRCFT_MODULE_SETTINGS_RADIO_NAME = f"-VRCFTSETTINGSRADIO{unique_id}-"
        self.GUIOFF_RADIO_NAME = f"-GUIOFF{unique_id}-"

# Create an instance of the KeyManager
key_manager = KeyManager()

def create_window(config, settings, eyes):

    key_manager.update_keys()

    for eye in eyes:
        eye.update_layouts()

    layout = [
        [
            sg.Radio(
                "Left Eye",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.LEFT),
                key=key_manager.LEFT_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Right Eye",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.RIGHT),
                key=key_manager.RIGHT_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Both Eyes",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.BOTH),
                key=key_manager.BOTH_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Settings",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.SETTINGS),
                key=key_manager.SETTINGS_RADIO_NAME,
            ),
            sg.Radio(
                "Algo Settings",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.ALGOSETTINGS),
                key=key_manager.ALGO_SETTINGS_RADIO_NAME,
            ),

        ],
        [
            sg.Radio(
                "VRCFT Module Settings",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.VRCFTMODULESETTINGS),
                key=key_manager.VRCFT_MODULE_SETTINGS_RADIO_NAME,
            ),
        ],
        [
            sg.Column(
                eyes[1].widget_layout,
                vertical_alignment="top",
                key=key_manager.LEFT_EYE_NAME,
                visible=(config.eye_display_id in [EyeId.LEFT, EyeId.BOTH]),
                background_color="#424042",
            ),
            sg.Column(
                eyes[0].widget_layout,
                vertical_alignment="top",
                key=key_manager.RIGHT_EYE_NAME,
                visible=(config.eye_display_id in [EyeId.RIGHT, EyeId.BOTH]),
                background_color="#424042",
            ),
            sg.Column(
                settings[0].get_layout(),
                vertical_alignment="top",
                key=key_manager.SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.SETTINGS]),
                background_color="#424042",
            ),
            sg.Column(
                settings[1].get_layout(),
                vertical_alignment="top",
                key=key_manager.ALGO_SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.ALGOSETTINGS]),
                background_color="#424042",
            ),
            sg.Column(
                settings[2].get_layout(),
                vertical_alignment="top",
                key=key_manager.VRCFT_MODULE_SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.VRCFTMODULESETTINGS]),
                background_color="#424042",
            ),
        ],
        [
            sg.Button(
                "GUI OFF",
                key=key_manager.GUIOFF_RADIO_NAME,
                button_color="#6f4ca1",
            ),
        ],
        # Keep at bottom!
        [sg.Text("- - -  Interface Paused  - - -", key="-WINFOCUS-", background_color="#292929", text_color="#F0F0F0", justification="center", expand_x=True, visible=False)],
    ]


    if config.eye_display_id in [EyeId.LEFT, EyeId.BOTH]:
        eyes[1].start()
    if config.eye_display_id in [EyeId.RIGHT, EyeId.BOTH]:
        eyes[0].start()
    if config.eye_display_id in [EyeId.SETTINGS]:
        settings[0].start()
    if config.eye_display_id in [EyeId.ALGOSETTINGS]:
        settings[1].start()
    if config.eye_display_id in [EyeId.VRCFTMODULESETTINGS]:
        settings[2].start()

    # the eye's needs to be running before it is passed to the OSC
    # Create the window
    return sg.Window(
        f"{appversion}",
        layout,
        icon=resource_path("Images/logo.ico"),
        background_color="#292929")

def timerResolution(toggle):
    if winmm != None:
        if toggle:
            rc = c_int(winmm.timeBeginPeriod(1))
            if rc.value != 0:
                # TIMEERR_NOCANDO = 97
                print(f"\033[93m[WARN] Failed to set timer resolution: {rc.value}\033[0m")
        else:
            winmm.timeEndPeriod(1)

def main():
    # Get Configuration
    config: EyeTrackConfig = EyeTrackConfig.load()
    config.save()

    cancellation_event = threading.Event()
    # Check to see if we can connect to our video source first. If not, bring up camera finding
    # dialog.
    try:
        if config.settings.gui_update_check:
            response = requests.get("https://api.github.com/repos/EyeTrackVR/EyeTrackVR/releases/latest")
            latestversion = response.json()["name"]
            if (
                appversion == latestversion
            ):  # If what we scraped and hardcoded versions are same, assume we are up to date.
                print(f"\033[92m[INFO] App is the latest version! [{latestversion}]\033[0m")
            else:
                print(
                    f"\033[93m[INFO] You have app version [{appversion}] installed. Please update to [{latestversion}] for the newest features.\033[0m"
                )
                try:
                    if is_nt:
                        cwd = os.getcwd()
                        # icon = cwd + "\Images\logo.ico"
                        icon = resource_path("Images/logo.ico")
                        toast = Notification(
                            app_id="EyeTrackApp",
                            title="New Update Available!",
                            msg=f"Please update to {latestversion}",
                            icon=r"{}".format(icon),
                        )
                        toast.add_actions(
                            label="Download Page",
                            launch="https://github.com/RedHawk989/EyeTrackVR/releases/latest",
                        )
                        toast.show()
                except Exception as e:
                    print("[INFO] Toast notifications not supported")
    except:
        print("\033[91m[INFO] Could not check for updates. Please try again later.\033[0m")

    timerResolution(True)

    osc_queue: queue.Queue[OSCMessage] = queue.Queue(maxsize=10)

    eyes = [
        CameraWidget(EyeId.RIGHT, config, osc_queue),
        CameraWidget(EyeId.LEFT, config, osc_queue),
    ]

    settings = [
        SettingsWidget(EyeId.SETTINGS, config),
        AlgoSettingsWidget(EyeId.ALGOSETTINGS, config),
        VRCFTSettingsWidget(EyeId.VRCFTMODULESETTINGS, config, osc_queue),
    ]

    osc_manager = OSCManager(
        osc_message_in_queue=osc_queue,
        config=config,
    )
    config.register_listener_callback(osc_manager.update)
    config.register_listener_callback(eyes[0].on_config_update)
    config.register_listener_callback(eyes[1].on_config_update)

    osc_manager.register_listeners(
        config.settings.gui_osc_recenter_address,
        [
            eyes[0].recenter_eyes,
            eyes[1].recenter_eyes,
        ],
    )
    osc_manager.register_listeners(
        config.settings.gui_osc_recalibrate_address,
        [
            eyes[0].recalibrate_eyes,
            eyes[1].recalibrate_eyes,
        ],
    )

    osc_manager.start()

    while True:
        tint = 33
        fs = False
        if config.settings.gui_disable_gui:
            layoutg = [
                [sg.Text("GUI Disabled!", background_color="#242224")],
                [sg.Button('Enable GUI', button_color="#6f4ca1")]
            ]

            # Create the window
            windowg = sg.Window('ETVR', layoutg, background_color="#242224", size=(200, 80)) #icon=resource_path("Images/logo.ico") adds cpu usage.....

            # Event loop
            while True:
                eventg, valuesg = windowg.read(timeout=tint)

                if eventg == sg.WINDOW_CLOSED:
                    config.settings.gui_disable_gui = False
                    config.save()
                    break
                elif eventg == 'Enable GUI':
                    config.settings.gui_disable_gui = False
                    config.save()
                    print('GUI Enabled')
                    break

            windowg.close()


        # First off, check for any events from the GUI
        window = create_window(config, settings, eyes)
        

        while True:
            event, values = window.read(timeout=tint) # this higher timeout saves some cpu usage

            # If we're in either mode and someone hits q, quit immediately
            if event in ("Exit", sg.WIN_CLOSED) and not config.settings.gui_disable_gui:
                for eye in eyes:
                    eye.stop()
                cancellation_event.set()
                osc_manager.shutdown()
                timerResolution(False)
                print("\033[94m[INFO] Exiting EyeTrackApp\033[0m")
                window.close()
                os._exit(0)  # I do not like this, but for now this fixes app hang on close
                return

            try:
                # If window isn't in focus increase timeout and stop loop early
                if window.TKroot.focus_get():
                    if fs:
                        fs = False
                        tint = 33
                        window["-WINFOCUS-"].update(visible=False)
                        window["-WINFOCUS-"].hide_row()
                        window.refresh()
                else:
                    if not fs:
                        fs = True
                        tint = 100
                        window["-WINFOCUS-"].update(visible=True)
                        window["-WINFOCUS-"].unhide_row()
                    continue
            except KeyError:
                pass

            if values[key_manager.RIGHT_EYE_RADIO_NAME] and config.eye_display_id != EyeId.RIGHT:
                config.settings.gui_disable_gui = False
                eyes[0].start()
                eyes[1].stop()
                settings[0].stop()
                settings[1].stop()
                settings[2].stop()
                window[key_manager.RIGHT_EYE_NAME].update(visible=True)
                window[key_manager.LEFT_EYE_NAME].update(visible=False)
                window[key_manager.SETTINGS_NAME].update(visible=False)
                window[key_manager.VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
                window[key_manager.ALGO_SETTINGS_NAME].update(visible=False)
                config.eye_display_id = EyeId.RIGHT
                config.settings.tracker_single_eye = 2
                config.save()

            elif values[key_manager.LEFT_EYE_RADIO_NAME] and config.eye_display_id != EyeId.LEFT:
                config.settings.gui_disable_gui = False
                settings[0].stop()
                settings[1].stop()
                settings[2].stop()
                eyes[0].stop()
                eyes[1].start()
                window[key_manager.RIGHT_EYE_NAME].update(visible=False)
                window[key_manager.LEFT_EYE_NAME].update(visible=True)
                window[key_manager.SETTINGS_NAME].update(visible=False)
                window[key_manager.VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
                window[key_manager.ALGO_SETTINGS_NAME].update(visible=False)
                config.eye_display_id = EyeId.LEFT
                config.settings.tracker_single_eye = 1
                config.save()

            elif values[key_manager.BOTH_EYE_RADIO_NAME] and config.eye_display_id != EyeId.BOTH:
                config.settings.gui_disable_gui = False
                settings[0].stop()
                settings[1].stop()
                settings[2].stop()
                eyes[1].start()
                eyes[0].start()
                window[key_manager.LEFT_EYE_NAME].update(visible=True)
                window[key_manager.RIGHT_EYE_NAME].update(visible=True)
                window[key_manager.SETTINGS_NAME].update(visible=False)
                window[key_manager.VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
                window[key_manager.ALGO_SETTINGS_NAME].update(visible=False)
                config.eye_display_id = EyeId.BOTH
                config.settings.tracker_single_eye = 0
                config.save()

            elif values[key_manager.SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.SETTINGS:
                config.settings.gui_disable_gui = False
                eyes[0].stop()
                eyes[1].stop()
                settings[1].stop()
                settings[0].start()
                settings[2].stop()
                window[key_manager.RIGHT_EYE_NAME].update(visible=False)
                window[key_manager.LEFT_EYE_NAME].update(visible=False)
                window[key_manager.SETTINGS_NAME].update(visible=True)
                window[key_manager.VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
                window[key_manager.ALGO_SETTINGS_NAME].update(visible=False)
                config.eye_display_id = EyeId.SETTINGS
                config.save()

            elif values[key_manager.ALGO_SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.ALGOSETTINGS:
                config.settings.gui_disable_gui = False
                eyes[0].stop()
                eyes[1].stop()
                settings[0].stop()
                settings[1].start()
                settings[2].stop()
                window[key_manager.RIGHT_EYE_NAME].update(visible=False)
                window[key_manager.LEFT_EYE_NAME].update(visible=False)
                window[key_manager.SETTINGS_NAME].update(visible=False)
                window[key_manager.VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
                window[key_manager.ALGO_SETTINGS_NAME].update(visible=True)
                config.eye_display_id = EyeId.ALGOSETTINGS
                config.save()

            elif values[key_manager.VRCFT_MODULE_SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.VRCFTMODULESETTINGS:
                config.settings.gui_disable_gui = False
                eyes[0].stop()
                eyes[1].stop()
                settings[0].stop()
                settings[1].stop()
                settings[2].start()
                window[key_manager.RIGHT_EYE_NAME].update(visible=False)
                window[key_manager.LEFT_EYE_NAME].update(visible=False)
                window[key_manager.SETTINGS_NAME].update(visible=False)
                window[key_manager.VRCFT_MODULE_SETTINGS_NAME].update(visible=True)
                window[key_manager.ALGO_SETTINGS_NAME].update(visible=False)
                config.eye_display_id = EyeId.VRCFTMODULESETTINGS
                config.save()
            else:

                # Otherwise, render all
                for eye in eyes:
                    if eye.started():
                        eye.render(window, event, values)
                for setting in settings:
                    if setting.started():
                        setting.render(window, event, values)

            if event == key_manager.GUIOFF_RADIO_NAME:
                config.settings.gui_disable_gui = True
                #  eyes[0].stop()
                # eyes[1].stop()
                settings[0].stop()
                settings[1].stop()
                settings[2].stop()
                window[key_manager.RIGHT_EYE_NAME].update(visible=False)
                window[key_manager.LEFT_EYE_NAME].update(visible=False)
                window[key_manager.SETTINGS_NAME].update(visible=False)
                window[key_manager.VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
                window[key_manager.ALGO_SETTINGS_NAME].update(visible=False)
                #config.eye_display_id = EyeId.GUIOFF
                config.save()
                window.close()
                break

if __name__ == "__main__":
    main()