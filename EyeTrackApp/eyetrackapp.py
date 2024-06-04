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

Copyright (c) 2023 EyeTrackVR <3
LICENSE: GNU GPLv3 
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

if is_nt:
    from winotify import Notification
os.system("color")  # init ANSI color

# Random environment variable to speed up webcam opening on the MSMF backend.
# https://github.com/opencv/opencv/issues/17687
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
WINDOW_NAME = "EyeTrackApp"
RIGHT_EYE_NAME = "-RIGHTEYEWIDGET-"
LEFT_EYE_NAME = "-LEFTEYEWIDGET-"
SETTINGS_NAME = "-SETTINGSWIDGET-"
ALGO_SETTINGS_NAME = "-ALGOSETTINGSWIDGET-"
VRCFT_MODULE_SETTINGS_NAME = "-VRCFTSETTINGSWIDGET-"
LEFT_EYE_RADIO_NAME = "-LEFTEYERADIO-"
RIGHT_EYE_RADIO_NAME = "-RIGHTEYERADIO-"
BOTH_EYE_RADIO_NAME = "-BOTHEYERADIO-"
SETTINGS_RADIO_NAME = "-SETTINGSRADIO-"
ALGO_SETTINGS_RADIO_NAME = "-ALGOSETTINGSRADIO-"
VRCFT_MODULE_SETTINGS_RADIO_NAME = "-VRCFTSETTINGSRADIO-"

page_url = "https://github.com/RedHawk989/EyeTrackVR/releases/latest"
appversion = "EyeTrackApp 0.2.0 BETA 11"


def main():
    # Get Configuration
    config: EyeTrackConfig = EyeTrackConfig.load()
    config.save()

    cancellation_event = threading.Event()
    # Check to see if we can connect to our video source first. If not, bring up camera finding
    # dialog.

    try:
        if config.settings.gui_update_check:
            response = requests.get(
                "https://api.github.com/repos/EyeTrackVR/EyeTrackVR/releases/latest"
            )
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

    osc_queue: queue.Queue[OSCMessage] = queue.Queue()

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

    layout = [
        [
            sg.Radio(
                "Left Eye",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.LEFT),
                key=LEFT_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Right Eye",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.RIGHT),
                key=RIGHT_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Both Eyes",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.BOTH),
                key=BOTH_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Settings",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.SETTINGS),
                key=SETTINGS_RADIO_NAME,
            ),
            sg.Radio(
                "Algo Settings",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.ALGOSETTINGS),
                key=ALGO_SETTINGS_RADIO_NAME,
            ),
            sg.Radio(
                "VRCFT Module Settings",
                "EYESELECTRADIO",
                background_color="#292929",
                default=(config.eye_display_id == EyeId.VRCFTMODULESETTINGS),
                key=VRCFT_MODULE_SETTINGS_RADIO_NAME,
            ),
        ],
        [
            sg.Column(
                eyes[1].widget_layout,
                vertical_alignment="top",
                key=LEFT_EYE_NAME,
                visible=(config.eye_display_id in [EyeId.LEFT, EyeId.BOTH]),
                background_color="#424042",
            ),
            sg.Column(
                eyes[0].widget_layout,
                vertical_alignment="top",
                key=RIGHT_EYE_NAME,
                visible=(config.eye_display_id in [EyeId.RIGHT, EyeId.BOTH]),
                background_color="#424042",
            ),
            sg.Column(
                settings[0].get_layout(),
                vertical_alignment="top",
                key=SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.SETTINGS]),
                background_color="#424042",
            ),
            sg.Column(
                settings[1].get_layout(),
                vertical_alignment="top",
                key=ALGO_SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.ALGOSETTINGS]),
                background_color="#424042",
            ),
            sg.Column(
                settings[2].get_layout(),
                vertical_alignment="top",
                key=VRCFT_MODULE_SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.VRCFTMODULESETTINGS]),
                background_color="#424042",
            ),
        ],
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
    window = sg.Window(
        f"{appversion}",
        layout,
        icon=resource_path("Images/logo.ico"),
        background_color="#292929",
    )

    # GUI Render loop
    while True:
        # First off, check for any events from the GUI
        event, values = window.read(timeout=1)

        # If we're in either mode and someone hits q, quit immediately
        if event == "Exit" or event == sg.WIN_CLOSED:
            for eye in eyes:
                eye.stop()
            cancellation_event.set()
            osc_manager.shutdown()
            print("\033[94m[INFO] Exiting EyeTrackApp\033[0m")
            return

        if values[RIGHT_EYE_RADIO_NAME] and config.eye_display_id != EyeId.RIGHT:
            eyes[0].start()
            eyes[1].stop()
            settings[0].stop()
            settings[1].stop()
            settings[2].stop()
            window[RIGHT_EYE_NAME].update(visible=True)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=False)
            window[VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.RIGHT
            config.settings.tracker_single_eye = 2
            config.save()

        elif values[LEFT_EYE_RADIO_NAME] and config.eye_display_id != EyeId.LEFT:
            settings[0].stop()
            settings[1].stop()
            settings[2].stop()
            eyes[0].stop()
            eyes[1].start()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=True)
            window[SETTINGS_NAME].update(visible=False)
            window[VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.LEFT
            config.settings.tracker_single_eye = 1
            config.save()

        elif values[BOTH_EYE_RADIO_NAME] and config.eye_display_id != EyeId.BOTH:
            settings[0].stop()
            settings[1].stop()
            settings[2].stop()
            eyes[1].start()
            eyes[0].start()
            window[LEFT_EYE_NAME].update(visible=True)
            window[RIGHT_EYE_NAME].update(visible=True)
            window[SETTINGS_NAME].update(visible=False)
            window[VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.BOTH
            config.settings.tracker_single_eye = 0
            config.save()

        elif values[SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.SETTINGS:
            eyes[0].stop()
            eyes[1].stop()
            settings[1].stop()
            settings[0].start()
            settings[2].stop()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=True)
            window[VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.SETTINGS
            config.save()

        elif values[ALGO_SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.ALGOSETTINGS:
            eyes[0].stop()
            eyes[1].stop()
            settings[0].stop()
            settings[1].start()
            settings[2].stop()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=False)
            window[VRCFT_MODULE_SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=True)
            config.eye_display_id = EyeId.ALGOSETTINGS
            config.save()

        elif values[VRCFT_MODULE_SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.VRCFTMODULESETTINGS:
            eyes[0].stop()
            eyes[1].stop()
            settings[0].stop()
            settings[1].stop()
            settings[2].start()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=False)
            window[VRCFT_MODULE_SETTINGS_NAME].update(visible=True)
            window[ALGO_SETTINGS_NAME].update(visible=False)
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


if __name__ == "__main__":
    main()
