import os
from utils.misc_utils import is_nt
from osc import VRChatOSCReceiver, VRChatOSC, EyeId
from config import EyeTrackConfig
from camera_widget import CameraWidget
from settings_widget import SettingsWidget

import queue
import threading
import PySimpleGUI as sg
import sys
import urllib.request

import webbrowser

os.system('color') # init ANSI color

# Random environment variable to speed up webcam opening on the MSMF backend.
# https://github.com/opencv/opencv/issues/17687
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"

WINDOW_NAME = "EyeTrackApp"
RIGHT_EYE_NAME = "-RIGHTEYEWIDGET-"
LEFT_EYE_NAME = "-LEFTEYEWIDGET-"
SETTINGS_NAME = "-SETTINGSWIDGET-"

LEFT_EYE_RADIO_NAME = "-LEFTEYERADIO-"
RIGHT_EYE_RADIO_NAME = "-RIGHTEYERADIO-"
BOTH_EYE_RADIO_NAME = "-BOTHEYERADIO-"
SETTINGS_RADIO_NAME = '-SETTINGSRADIO-'


page_url = 'https://github.com/RedHawk989/EyeTrackVR/releases/latest'
appversion = "0.2.0 BETA 1"

def open_url():
    try: 
        webbrowser.open_new(page_url)
        print('Opening URL...')  
    except: 
        print('Failed to open URL. Unsupported variable type.')


def main():
    # Get Configuration
    config: EyeTrackConfig = EyeTrackConfig.load()
    config.save()

    cancellation_event = threading.Event()

    # Check to see if we can connect to our video source first. If not, bring up camera finding
    # dialog.
    if config.settings.gui_update_check:
        print("\033[95m[INFO] Checking for updates...\033[0m")
        url = "https://raw.githubusercontent.com/RedHawk989/EyeTrackVR-Installer/master/Version-Data/Version_Num.txt"
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                latestversion = res.read().decode("utf-8").strip()
        except urllib.error.HTTPError as err:
            print("Failed to check latest version.")
            print("{} : {}".format(err.code,err.reason))
        except urllib.error.URLError as err:
            print("Failed to check latest version.")
            print(err.reason)
        else:
            if appversion == latestversion:  # If what we scraped and hardcoded versions are same, assume we are up to date.
                print(f"\033[92m[INFO] App is up to date! [{latestversion}]\033[0m")
            else:
                print(
                    f"\033[93m[INFO] You have app version [{appversion}] installed. Please update to [{latestversion}] for the newest features.\033[0m")
                if is_nt:
                    from win10toast_click import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast(  # show windows toast
                        "EyeTrackVR has an update.",
                        "Click to go to the latest version.",
                        icon_path="Images/logo.ico",
                        duration=5,
                        threaded=True,
                        callback_on_click=open_url
                    )
                    
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
    ]

    layout = [
        [
            sg.Radio(
                "Right Eye",
                "EYESELECTRADIO",
                background_color='#292929',
                default=(config.eye_display_id == EyeId.RIGHT),
                key=RIGHT_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Left Eye",
                "EYESELECTRADIO",
                background_color='#292929',
                default=(config.eye_display_id == EyeId.LEFT),
                key=LEFT_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Both Eyes",
                "EYESELECTRADIO",
                background_color='#292929',
                default=(config.eye_display_id == EyeId.BOTH),
                key=BOTH_EYE_RADIO_NAME,
            ),
            sg.Radio(
                "Settings",
                "EYESELECTRADIO",
                background_color='#292929',
                default=(config.eye_display_id == EyeId.SETTINGS),
                key=SETTINGS_RADIO_NAME,
            ),
        ],
        [
            sg.Column(
                eyes[1].widget_layout,
                vertical_alignment="top",
                key=LEFT_EYE_NAME,
                visible=(config.eye_display_id in [EyeId.LEFT, EyeId.BOTH]),
                background_color='#424042',
            ),
            sg.Column(
                eyes[0].widget_layout,
                vertical_alignment="top",
                key=RIGHT_EYE_NAME,
                visible=(config.eye_display_id in [EyeId.RIGHT, EyeId.BOTH]),
                background_color='#424042',
            ),
            sg.Column(
                settings[0].widget_layout,
                vertical_alignment="top",
                key=SETTINGS_NAME,
                visible=(config.eye_display_id in [EyeId.SETTINGS]),
                background_color='#424042',
            ),
        ],
    ]

    if config.eye_display_id in [EyeId.LEFT, EyeId.BOTH]:
        eyes[1].start()
    if config.eye_display_id in [EyeId.RIGHT, EyeId.BOTH]:
        eyes[0].start()

    if config.eye_display_id in [EyeId.SETTINGS, EyeId.BOTH]:
        settings[0].start()

    # the eye's needs to be running before it is passed to the OSC
    osc_receiver = VRChatOSCReceiver(cancellation_event, config, eyes)
    osc_receiver_thread = threading.Thread(target=osc_receiver.run)
    osc_receiver_thread.start()

    # Create the window
    window = sg.Window(f"EyeTrackVR {appversion}" , layout, icon='Images/logo.ico', background_color='#292929')

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
            osc_receiver.shutdown()
            osc_receiver_thread.join()
            print("\033[94m[INFO] Exiting EyeTrackApp\033[0m")
            return

        if values[RIGHT_EYE_RADIO_NAME] and config.eye_display_id != EyeId.RIGHT:
            eyes[0].start()
            eyes[1].stop()
            settings[0].stop()
            window[RIGHT_EYE_NAME].update(visible=True)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.RIGHT
            config.settings.tracker_single_eye = 2
            config.save()
        elif values[LEFT_EYE_RADIO_NAME] and config.eye_display_id != EyeId.LEFT:
            settings[0].stop()
            eyes[0].stop()
            eyes[1].start()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=True)
            window[SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.LEFT
            config.settings.tracker_single_eye = 1
            config.save()
        elif values[BOTH_EYE_RADIO_NAME] and config.eye_display_id != EyeId.BOTH:
            settings[0].stop()
            eyes[0].stop()
            eyes[1].start()
            eyes[0].start()

            window[LEFT_EYE_NAME].update(visible=True)
            window[RIGHT_EYE_NAME].update(visible=True)
            window[SETTINGS_NAME].update(visible=False)
            config.eye_display_id = EyeId.BOTH
            config.settings.tracker_single_eye = 0
            config.save()

        elif values[SETTINGS_RADIO_NAME] and config.eye_display_id != EyeId.SETTINGS:
            eyes[0].stop()
            eyes[1].stop()
            settings[0].start()
            window[RIGHT_EYE_NAME].update(visible=False)
            window[LEFT_EYE_NAME].update(visible=False)
            window[SETTINGS_NAME].update(visible=True)
            config.eye_display_id = EyeId.SETTINGS
            config.save()

        # Otherwise, render all of our cameras
        for eye in eyes:
            if eye.started():
                eye.render(window, event, values)
        settings[0].render(window, event, values)


if __name__ == "__main__":
    main()
    