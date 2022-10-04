# Random environment variable to speed up webcam opening on the MSMF backend.
# https://github.com/opencv/opencv/issues/17687
import os

os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
from osc import VRChatOSC, EyeId
from config import EyeTrackConfig
from camera_widget import CameraWidget
from settings_widget import SettingsWidget
import queue
import threading
import PySimpleGUI as sg

WINDOW_NAME = "EyeTrackApp"
RIGHT_EYE_NAME = "-RIGHTEYEWIDGET-"
LEFT_EYE_NAME = "-LEFTEYEWIDGET-"
SETTINGS_NAME = "-SETTINGSWIDGET-"

LEFT_EYE_RADIO_NAME = "-LEFTEYERADIO-"
RIGHT_EYE_RADIO_NAME = "-RIGHTEYERADIO-"
BOTH_EYE_RADIO_NAME = "-BOTHEYERADIO-"
SETTINGS_RADIO_NAME = '-SETTINGSRADIO-'

def main():
    # Get Configuration
    config: EyeTrackConfig = EyeTrackConfig.load()
    config.save()

    cancellation_event = threading.Event()

    # Check to see if we can connect to our video source first. If not, bring up camera finding
    # dialog.

    # Check to see if we have an ROI. If not, bring up ROI finder GUI.

    # Spawn worker threads
    osc_queue: "queue.Queue[tuple[bool, int, int]]" = queue.Queue()
    osc = VRChatOSC(cancellation_event, osc_queue, config)
    osc_thread = threading.Thread(target=osc.run)
    osc_thread.start()

    #  t2s_queue: "queue.Queue[str | None]" = queue.Queue()
    #  t2s_engine = SpeechEngine(t2s_queue)
    #  t2s_thread = threading.Thread(target=t2s_engine.run)
    #  t2s_thread.start()
    #  t2s_queue.put("App Starting")

    eyes = [
        CameraWidget(EyeId.RIGHT, config, osc_queue),
        CameraWidget(EyeId.LEFT, config, osc_queue),
       # CameraWidget(EyeId.SETTINGS, config, osc_queue),

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
                eyes[0].widget_layout,
                vertical_alignment="top",
                key=RIGHT_EYE_NAME,
                visible=(config.eye_display_id in [EyeId.RIGHT, EyeId.BOTH]),
                background_color='#424042',
            ),
            sg.Column(
                eyes[1].widget_layout,
                vertical_alignment="top",
                key=LEFT_EYE_NAME,
                visible=(config.eye_display_id in [EyeId.LEFT, EyeId.BOTH]),
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

    if config.eye_display_id in [EyeId.RIGHT, EyeId.BOTH]:
        eyes[0].start()
    if config.eye_display_id in [EyeId.LEFT, EyeId.BOTH]:
        eyes[1].start()
    if config.eye_display_id in [EyeId.SETTINGS, EyeId.BOTH]:
        settings[0].start()

    # Create the window
    window = sg.Window("EyeTrackVR v0.1.6", layout, icon='Images/logo.ico', background_color='#292929')

    # GUI Render loop
    while True:
        # First off, check for any events from the GUI
        event, values = window.read(timeout=1)

        # If we're in either mode and someone hits q, quit immediately
        if event == "Exit" or event == sg.WIN_CLOSED:
           # eyes[2].stop()
            for eye in eyes:
                eye.stop()
            cancellation_event.set()
            osc_thread.join()
            #      t2s_engine.force_stop()
            #      t2s_queue.put(None)
            #      t2s_thread.join()
            print("Exiting EyeTrackApp")
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
            eyes[1].start()
            eyes[0].start()
            window[RIGHT_EYE_NAME].update(visible=True)
            window[LEFT_EYE_NAME].update(visible=True)
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
