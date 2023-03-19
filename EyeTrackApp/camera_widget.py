import PySimpleGUI as sg
from config import EyeTrackConfig
from config import EyeTrackSettingsConfig
from threading import Event, Thread
from eye_processor import EyeProcessor, InformationOrigin
from enum import Enum
from queue import Queue, Empty
from camera import Camera, CameraState
from osc import EyeId
import cv2
import sys
from utils.misc_utils import PlaySound,SND_FILENAME,SND_ASYNC
import traceback
import numpy as np

class CameraWidget:
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig, osc_queue: Queue):
        self.gui_camera_addr = f"-CAMERAADDR{widget_id}-"
        self.gui_rotation_slider = f"-ROTATIONSLIDER{widget_id}-"
        self.gui_roi_button = f"-ROIMODE{widget_id}-"
        self.gui_roi_layout = f"-ROILAYOUT{widget_id}-"
        self.gui_roi_selection = f"-GRAPH{widget_id}-"
        self.gui_tracking_button = f"-TRACKINGMODE{widget_id}-"
        self.gui_save_tracking_button = f"-SAVETRACKINGBUTTON{widget_id}-"
        self.gui_tracking_layout = f"-TRACKINGLAYOUT{widget_id}-"
        self.gui_tracking_image = f"-IMAGE{widget_id}-"
        self.gui_output_graph = f"-OUTPUTGRAPH{widget_id}-"
        self.gui_restart_calibration = f"-RESTARTCALIBRATION{widget_id}-"
        self.gui_recenter_eyes = f"-RECENTEREYES{widget_id}-"
        self.gui_mode_readout = f"-APPMODE{widget_id}-"
        self.gui_circular_crop = f"-CIRCLECROP{widget_id}-"
        self.gui_roi_message = f"-ROIMESSAGE{widget_id}-"

        self.osc_queue = osc_queue
        self.main_config = main_config
        self.eye_id = widget_id
        self.settings_config = main_config.settings
        self.configl = main_config.left_eye
        self.configr = main_config.right_eye
        self.settings = main_config.settings
        if self.eye_id == EyeId.RIGHT:
            self.config = main_config.right_eye
        elif self.eye_id == EyeId.LEFT:
            self.config = main_config.left_eye
        else:
            raise RuntimeError("\033[91m[WARN] Cannot have a camera widget represent both eyes!\033[0m")

        self.roi_layout = [
            [
                sg.Graph( 
                    (640, 480),
                    (0, 480),
                    (640, 0),
                    key=self.gui_roi_selection,
                    drag_submits=True,
                    enable_events=True,
                    background_color='#424042',
                )
            ]
        ]

        # Define the window's contents
        self.tracking_layout = [
            [
                sg.Text("Rotation", background_color='#424042'),
                sg.Slider(
                    range=(0, 360),
                    default_value=self.config.rotation_angle,
                    orientation="h",
                    key=self.gui_rotation_slider,
                    background_color='#424042',
                    tooltip = "Adjust the rotation of your cameras, make them level.",
                ),
            ],
            [
                sg.Button("Restart Calibration", key=self.gui_restart_calibration, button_color='#6f4ca1', tooltip = "Start eye calibration. Look all arround to all extreams without blinking until sound is heard.",),
                sg.Button("Recenter Eyes", key=self.gui_recenter_eyes, button_color='#6f4ca1', tooltip = "Make your eyes center again.",),

            ],
            [
                sg.Text("Mode:", background_color='#424042'),
                sg.Text("Calibrating", key=self.gui_mode_readout, background_color='#424042'),
            #    sg.Checkbox(
            #        "Circle crop:",
            #        default=self.config.gui_circular_crop,
            #        key=self.gui_circular_crop,
            #        background_color='#424042',
            #        tooltip = "Circle crop only applies to RANSAC3D and Blob.",
            #    ),
            ],
            [sg.Image(filename="", key=self.gui_tracking_image)],
            [
                sg.Graph(
                    (200, 200),
                    (-100, 100),
                    (100, -100),
                    background_color="white",
                    key=self.gui_output_graph,
                    drag_submits=True,
                    enable_events=True,
                ),
                sg.Text("Please set an Eye Cropping.", key=self.gui_roi_message, background_color='#424042', visible=False),
            ],
        ]

        self.widget_layout = [
            [
                sg.Text("Camera Address", background_color='#424042'),
                sg.InputText(self.config.capture_source, key=self.gui_camera_addr, tooltip = "Enter the IP address or UVC port of your camera. (Include the 'http://')",),
            ],
            [
                sg.Button("Save and Restart Tracking", key=self.gui_save_tracking_button, button_color='#6f4ca1'),
            ],
            [
                sg.Button("Tracking Mode", key=self.gui_tracking_button, button_color='#6f4ca1', tooltip = "Go here to track your eye.",),
                sg.Button("Cropping Mode", key=self.gui_roi_button, button_color='#6f4ca1', tooltip = "Go here to crop out your eye.",),
            ],
            [
                sg.Column(self.tracking_layout, key=self.gui_tracking_layout, background_color='#424042'),
                sg.Column(self.roi_layout, key=self.gui_roi_layout, background_color='#424042', visible=False),
            ],
        ]

        self.cancellation_event = Event()
        # Set the event until start is called, otherwise we can block if shutdown is called.
        self.cancellation_event.set()
        self.capture_event = Event()
        self.capture_queue = Queue()
        self.roi_queue = Queue()

        self.image_queue = Queue()

        self.ransac = EyeProcessor(
            self.config,
            self.settings_config,
            self.cancellation_event,
            self.capture_event,
            self.capture_queue,
            self.image_queue,
            self.eye_id,
        )

        self.camera_status_queue = Queue()
        self.camera = Camera(
            self.config,
            0,
            self.cancellation_event,
            self.capture_event,
            self.camera_status_queue,
            self.capture_queue,
        )

        self.x0, self.y0 = None, None
        self.x1, self.y1 = None, None
        self.figure = None
        self.is_mouse_up = True
        self.in_roi_mode = False

    def started(self):
        return not self.cancellation_event.is_set()

    def start(self):
        # If we're already running, bail
        if not self.cancellation_event.is_set():
            return
        self.cancellation_event.clear()
        self.ransac_thread = Thread(target=self.ransac.run)
        self.ransac_thread.start()
        self.camera_thread = Thread(target=self.camera.run)
        self.camera_thread.start()

    def stop(self):
        # If we're not running yet, bail
        if self.cancellation_event.is_set():
            return
        self.cancellation_event.set()
        self.ransac_thread.join()
        self.camera_thread.join()

    def render(self, window, event, values):
        changed = False
        # If anything has changed in our configuration settings, change/update those.
        if (
            event == self.gui_save_tracking_button
            and values[self.gui_camera_addr] != self.config.capture_source
        ):
            print("\033[94m[INFO] New value: {}\033[0m".format(values[self.gui_camera_addr]))
            try:
                # Try storing ints as ints, for those using wired cameras.
                self.config.capture_source = int(values[self.gui_camera_addr])
            except ValueError:
                if values[self.gui_camera_addr] == "":
                    self.config.capture_source = None
                else:
                    if len(values[self.gui_camera_addr]) > 5 and "http" not in values[self.gui_camera_addr] and ".mp4" not in values[self.gui_camera_addr]: # If http is not in camera address, add it.
                        self.config.capture_source = f"http://{values[self.gui_camera_addr]}/"   
                    else:
                        self.config.capture_source = values[self.gui_camera_addr]
            changed = True



        if self.config.rotation_angle != values[self.gui_rotation_slider]:
            self.config.rotation_angle = int(values[self.gui_rotation_slider])
            changed = True

      # if self.config.gui_circular_crop != values[self.gui_circular_crop]:
       #     self.config.gui_circular_crop = values[self.gui_circular_crop]
        #    changed = True

        if changed:
            self.main_config.save()

        if event == self.gui_tracking_button:
            print("\033[94m[INFO] Moving to tracking mode\033[0m")
            self.in_roi_mode = False
            self.camera.set_output_queue(self.capture_queue)
            window[self.gui_roi_layout].update(visible=False)
            window[self.gui_tracking_layout].update(visible=True)

        if event == self.gui_roi_button:
            print("\033[94m[INFO] Move to roi mode\033[0m")
            self.in_roi_mode = True
            self.camera.set_output_queue(self.roi_queue)
            window[self.gui_roi_layout].update(visible=True)
            window[self.gui_tracking_layout].update(visible=False)

        if event == "{}+UP".format(self.gui_roi_selection):
            # Event for mouse button up in ROI mode
            self.is_mouse_up = True
            if self.x1 < 0:
                    self.x1 = 0
            if self.y1 < 0:
                    self.y1 = 0 
            if abs(self.x0 - self.x1) != 0 and abs(self.y0 - self.y1) != 0:
                self.config.roi_window_x = min([self.x0, self.x1])
                self.config.roi_window_y = min([self.y0, self.y1])
                self.config.roi_window_w = abs(self.x0 - self.x1)
                self.config.roi_window_h = abs(self.y0 - self.y1)
                self.main_config.save()
                

        if event == self.gui_roi_selection:
            # Event for mouse button down or mouse drag in ROI mode
            if self.is_mouse_up:
                self.is_mouse_up = False
                self.x0, self.y0 = values[self.gui_roi_selection]
            self.x1, self.y1 = values[self.gui_roi_selection]

        if event == self.gui_restart_calibration:
            self.ransac.calibration_frame_counter = 300
            PlaySound('Audio/start.wav', SND_FILENAME | SND_ASYNC)

        if event == self.gui_recenter_eyes:
            self.settings.gui_recenter_eyes = True

        needs_roi_set = self.config.roi_window_h <= 0 or self.config.roi_window_w <= 0

        if self.config.capture_source is None or self.config.capture_source == "":
            window[self.gui_mode_readout].update("Waiting for camera address")
            window[self.gui_roi_message].update(visible=False)
            window[self.gui_output_graph].update(visible=False)
        elif self.camera.camera_status == CameraState.CONNECTING:
            window[self.gui_mode_readout].update("Camera Connecting")
        elif self.camera.camera_status == CameraState.DISCONNECTED:
            window[self.gui_mode_readout].update("CAMERA DISCONNECTED")
        elif needs_roi_set:
            window[self.gui_mode_readout].update("Awaiting Eye Crop")
        elif self.ransac.calibration_frame_counter != None:
            window[self.gui_mode_readout].update("Calibration")
        else:
            window[self.gui_mode_readout].update("Tracking")

        if self.in_roi_mode:
            try:
                if self.roi_queue.empty():
                    self.capture_event.set()
                maybe_image = self.roi_queue.get(block=False)
                imgbytes = cv2.imencode(".ppm", maybe_image[0])[1].tobytes()
                graph = window[self.gui_roi_selection]
                if self.figure:
                    graph.delete_figure(self.figure)
                # INCREDIBLY IMPORTANT ERASE. Drawing images does NOT overwrite the buffer, the fucking
                # graph keeps every image fed in until you call this. Therefore we have to make sure we
                # erase before we redraw, otherwise we'll leak memory *very* quickly.
                graph.erase()
                graph.draw_image(data=imgbytes, location=(0, 0))
                if None not in (self.x0, self.y0, self.x1, self.y1):
                    self.figure = graph.draw_rectangle(
                        (self.x0, self.y0), (self.x1, self.y1), line_color="#6f4ca1"
                    )
            except Empty:
                pass
        else:
            if needs_roi_set:
                window[self.gui_roi_message].update(visible=True)
                window[self.gui_output_graph].update(visible=False)
                return
            try:
                window[self.gui_roi_message].update(visible=False)
                window[self.gui_output_graph].update(visible=True)
                (maybe_image, eye_info) = self.image_queue.get(block=False)
                imgbytes = cv2.imencode(".ppm", maybe_image)[1].tobytes()
                window[self.gui_tracking_image].update(data=imgbytes)

                # Update the GUI
                graph = window[self.gui_output_graph]
                graph.erase()

                if eye_info.info_type != InformationOrigin.FAILURE: #and not eye_info.blink:
                    graph.update(background_color="white")
                    if not np.isnan(eye_info.x) and not np.isnan(eye_info.y):
                        
                        graph.draw_circle(
                            (eye_info.x * -100, eye_info.y * -100),
                            25,
                            fill_color="black",
                            line_color="white",
                        )
                    else:
                        graph.draw_circle(
                            (0.0 * -100, 0.0 * -100),
                            25,
                            fill_color="black",
                            line_color="white",
                        )

               # elif eye_info.blink:
                #    graph.update(background_color="#6f4ca1")
                elif eye_info.info_type == InformationOrigin.FAILURE:
                    graph.update(background_color="red")
                # Relay information to OSC
                if eye_info.info_type != InformationOrigin.FAILURE:
                    self.osc_queue.put((self.eye_id, eye_info))
            except Empty:
                pass
