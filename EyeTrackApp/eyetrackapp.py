import os
import os
import PySimpleGUI as sg
import queue
import requests
import threading

from camera_widget import CameraWidget
from config import EyeTrackConfig
from eye import EyeId
from osc import VRChatOSCReceiver, VRChatOSC
from general_settings_widget import SettingsWidget
from algo_settings_widget import AlgoSettingsWidget

from utils.misc_utils import is_nt

if is_nt:
    from winotify import Notification
os.system('color')  # init ANSI color

# Random environment variable to speed up webcam opening on the MSMF backend.
# https://github.com/opencv/opencv/issues/17687
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"

WINDOW_NAME = "EyeTrackApp"
RIGHT_EYE_NAME = "-RIGHTEYEWIDGET-"
LEFT_EYE_NAME = "-LEFTEYEWIDGET-"
SETTINGS_NAME = "-SETTINGSWIDGET-"
ALGO_SETTINGS_NAME = "-ALGOSETTINGSWIDGET-"

LEFT_EYE_RADIO_NAME = "-LEFTEYERADIO-"
RIGHT_EYE_RADIO_NAME = "-RIGHTEYERADIO-"
BOTH_EYE_RADIO_NAME = "-BOTHEYERADIO-"
SETTINGS_RADIO_NAME = "-SETTINGSRADIO-"
ALGO_SETTINGS_RADIO_NAME = "-ALGOSETTINGSRADIO-"

page_url = "https://github.com/RedHawk989/EyeTrackVR/releases/latest"
appversion = "EyeTrackApp 0.2.0 BETA 5"


def main():
    # Get Configuration
    config: EyeTrackConfig = EyeTrackConfig.load()
    config.save()

    cancellation_event = threading.Event()
    ROSC = False
    # Check to see if we can connect to our video source first. If not, bring up camera finding
    # dialog.

    if config.settings.gui_update_check:
        response = requests.get(
            "https://api.github.com/repos/RedHawk989/EyeTrackVR/releases/latest"
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
                    icon = cwd + "\Images\logo.ico"
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

    # Check to see if we have an ROI. If not, bring up ROI finder GUI.

    # Spawn worker threads
    osc_queue: queue.Queue[tuple[bool, int, int]] = queue.Queue()
    osc = VRChatOSC(cancellation_event, osc_queue, config)
    osc_thread = threading.Thread(target=osc.run)
    # start worker threads
    osc_thread.start()

    eyes = [
        CameraWidget(EyeId.RIGHT, config, osc_queue),
        CameraWidget(EyeId.LEFT, config, osc_queue),
    ]

    settings = [
        SettingsWidget(EyeId.SETTINGS, config, osc_queue),
        AlgoSettingsWidget(EyeId.ALGOSETTINGS, config, osc_queue),
    ]

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
                settings[0].widget_layout,
                vertical_alignment="top",
                key=SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.SETTINGS]),
                background_color="#424042",
            ),
            sg.Column(
                settings[1].widget_layout,
                vertical_alignment="top",
                key=ALGO_SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.ALGOSETTINGS]),
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
        # self.main_config.eye_display_id

    # the eye's needs to be running before it is passed to the OSC
    if config.settings.gui_ROSC:
        osc_receiver = VRChatOSCReceiver(cancellation_event, config, eyes)
        osc_receiver_thread = threading.Thread(target=osc_receiver.run)
        osc_receiver_thread.start()
        ROSC = True

    # Create the window
    window = sg.Window(
        f"{appversion}", layout, icon="Images/logo.ico", background_color="#292929"
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
            # shut down worker threads
            osc_thread.join()
            # TODO: find a way to have this function run on join maybe??
            # threading.Event() wont work because pythonosc spawns its own thread.
            # only way i can see to get around this is an ugly while loop that only checks if a threading event is triggered
            # and then call the pythonosc shutdown function
            if ROSC:
                osc_receiver.shutdown()
                osc_receiver_thread.join()
            print("\033[94m[INFO] Exiting EyeTrackApp\033[0m")
            return

        if values[RIGHT_EYE_RADIO_NAME] and config.eye_display_id != EyeId.RIGHT:
            eyes[0].start()
            eyes[1].stop()
            settings[0].stop()
            settings[1].stop()
            window[RIGHT_EYE_NAME].update(visible=True)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.RIGHT
            config.settings.tracker_single_eye = 2
            config.save()

        elif values[LEFT_EYE_RADIO_NAME] and config.eye_display_id != EyeId.LEFT:
            settings[0].stop()
            settings[1].stop()
            eyes[0].stop()
            eyes[1].start()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=True)
            window[SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.LEFT
            config.settings.tracker_single_eye = 1
            config.save()

        elif values[BOTH_EYE_RADIO_NAME] and config.eye_display_id != EyeId.BOTH:
            settings[0].stop()
            settings[1].stop()
            eyes[0].stop()
            eyes[1].start()
            eyes[0].start()
            window[LEFT_EYE_NAME].update(visible=True)
            window[RIGHT_EYE_NAME].update(visible=True)
            window[SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.BOTH
            config.settings.tracker_single_eye = 0
            config.save()

        elif values[SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.SETTINGS:
            eyes[0].stop()
            eyes[1].stop()
            settings[1].stop()
            settings[0].start()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=True)
            window[ALGO_SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.SETTINGS
            config.save()
            print("EE")


        elif values[ALGO_SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.ALGOSETTINGS:
            eyes[0].stop()
            eyes[1].stop()
            settings[0].stop()
            settings[1].start()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=False)
            window[ALGO_SETTINGS_NAME].update(visible=True)
            config.eye_display_id = EyeId.ALGOSETTINGS
            config.save()
            print("Easljghk")

        # Otherwise, render all
        for eye in eyes:
            if eye.started():
                eye.render(window, event, values)
        for setting in settings:
            if setting.started():
                setting.render(window, event, values)
    #    settings[0].render(window, event, values)
      #  settings[1].render(window, event, values)


if __name__ == "__main__":
    main()
