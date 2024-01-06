import PySimpleGUI as sg
from config import EyeTrackConfig
from config import EyeTrackSettingsConfig
from collections import deque
from threading import Event, Thread
from eye_processor import EyeProcessor, EyeInfoOrigin
from enum import Enum
from queue import Queue, Empty
from camera import Camera, CameraState
from osc import EyeId
import cv2
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC, resource_path
import numpy as np
import time

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
        self.gui_tracking_fps = f"-TRACKINGFPS{widget_id}-"
        self.gui_tracking_bps = f"-TRACKINGBPS{widget_id}-"
        self.gui_output_graph = f"-OUTPUTGRAPH{widget_id}-"
        self.gui_restart_calibration = f"-RESTARTCALIBRATION{widget_id}-"
        self.gui_stop_calibration = f"-STOPCALIBRATION{widget_id}-"
        self.gui_recenter_eyes = f"-RECENTEREYES{widget_id}-"
        self.gui_mode_readout = f"-APPMODE{widget_id}-"
        self.gui_roi_message = f"-ROIMESSAGE{widget_id}-"
        self.gui_mask_markup = f"-MARKUP{widget_id}-"
        self.gui_mask_lighten = f"-LIGHTEN{widget_id}-"
        self.gui_restart_3d_calibration = f"-RESTART3DCALIBRATION{widget_id}-"

        self.last_eye_info = None
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
            raise RuntimeError(
                "\033[91m[WARN] Cannot have a camera widget represent both eyes!\033[0m"
            )

        self.cancellation_event = Event()
        # Set the event until start is called, otherwise we can block if shutdown is called.
        self.cancellation_event.set()
        self.capture_event = Event()
        self.capture_queue = Queue(maxsize=2)
        self.roi_queue = Queue(maxsize=2)
        self.image_queue = Queue(maxsize=500)

        self.ransac = EyeProcessor(
            self.config,
            self.settings_config,
            main_config,
            self.cancellation_event,
            self.capture_event,
            self.capture_queue,
            self.image_queue,
            self.eye_id,
        )

        self.camera_status_queue = Queue(maxsize=2)
        self.camera = Camera(
            self.config,
            0,
            self.cancellation_event,
            self.capture_event,
            self.camera_status_queue,
            self.capture_queue,
        )

        self.roi_layout = [
            [
                sg.Button(
                    "Mark Out",
                    key=self.gui_mask_markup,
                    button_color="#6f4ca1",
                    tooltip="Mark out stuff that is not your eye.",
                ),
                sg.Button(
                    "Lighten",
                    key=self.gui_mask_lighten,
                    button_color="#6f4ca1",
                    tooltip="Lighten shadowed areas.",
                ),
            ],
            [
                sg.Graph(
                    (640, 480),
                    (0, 480),
                    (640, 0),
                    key=self.gui_roi_selection,
                    drag_submits=True,
                    enable_events=True,
                    background_color="#424042",
                ),
            ],
        ]

        # Define the window's contents
        self.tracking_layout = [
            [
                sg.Text("Rotation", background_color="#424042"),
                sg.Slider(
                    range=(0, 360),
                    default_value=self.config.rotation_angle,
                    orientation="h",
                    key=self.gui_rotation_slider,
                    background_color="#424042",
                    tooltip="Adjust the rotation of your cameras, make them level.",
                ),
            ],
            [
                sg.Button(
                    "2D Calibration",
                    key=self.gui_restart_calibration,
                    button_color="#6f4ca1",
                    tooltip="Start eye calibration. Look all arround to all extreams without blinking until sound is heard.",
                ),
                sg.Button(
                    "3D Calibration",
                    key=self.gui_restart_3d_calibration,
                    button_color="#6f4ca1",
                    tooltip="Start 3d eye calibration, must have steamvr open and eyes in hmd",
                ),
                sg.Button(
                    "Stop Calibration",
                    key=self.gui_stop_calibration,
                    button_color="#6f4ca1",
                    tooltip="Stop eye calibration manualy.",
                ),
                sg.Button(
                    "Recenter Eyes",
                    key=self.gui_recenter_eyes,
                    button_color="#6f4ca1",
                    tooltip="Make your eyes center again.",
                ),
            ],
            [
                sg.Text("Mode:", background_color="#424042"),
                sg.Text(
                    "Calibrating", key=self.gui_mode_readout, background_color="#424042"
                ),
                sg.Text("", key=self.gui_tracking_fps, background_color="#424042"),
                sg.Text("", key=self.gui_tracking_bps, background_color="#424042"),
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
                sg.Text(
                    "Please set an Eye Cropping.",
                    key=self.gui_roi_message,
                    background_color="#424042",
                    visible=False,
                ),
            ],
        ]

        self.widget_layout = [
            [
                sg.Text("Camera Address", background_color="#424042"),
                sg.InputText(
                    self.config.capture_source,
                    key=self.gui_camera_addr,
                    tooltip="Enter the IP address or UVC port of your camera. (Include the 'http://')",
                ),
            ],
            [
                sg.Button(
                    "Save and Restart Tracking",
                    key=self.gui_save_tracking_button,
                    button_color="#6f4ca1",
                ),
            ],
            [
                sg.Button(
                    "Tracking Mode",
                    key=self.gui_tracking_button,
                    button_color="#6f4ca1",
                    tooltip="Go here to track your eye.",
                ),
                sg.Button(
                    "Cropping Mode",
                    key=self.gui_roi_button,
                    button_color="#6f4ca1",
                    tooltip="Go here to crop out your eye.",
                ),
            ],
            [
                sg.Column(
                    self.tracking_layout,
                    key=self.gui_tracking_layout,
                    background_color="#424042",
                ),
                sg.Column(
                    self.roi_layout,
                    key=self.gui_roi_layout,
                    background_color="#424042",
                    visible=False,
                ),
            ],
        ]

        self.x0, self.y0 = None, None
        self.x1, self.y1 = None, None
        self.figure = None
        self.is_mouse_up = True
        self.in_roi_mode = False
        self.movavg_fps_queue = deque(maxlen=120)
        self.movavg_bps_queue = deque(maxlen=120)

    def _movavg_fps(self, next_fps):
        self.movavg_fps_queue.append(next_fps)
        fps = round(sum(self.movavg_fps_queue) / len(self.movavg_fps_queue))
        millisec = round((1 / fps if fps else 0) * 1000)
        return f"{fps} Fps {millisec} ms"

    def _movavg_bps(self, next_bps):
        self.movavg_bps_queue.append(next_bps)
        return f"{sum(self.movavg_bps_queue) / len(self.movavg_bps_queue) * 0.001 * 0.001 * 8:.3f} Mbps"

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
        with self.image_queue.mutex:
            self.image_queue.queue.clear()
        self.cancellation_event.set()
        self.ransac_thread.join()
        self.camera_thread.join()

    def render(self, window, event, values):
        if self.image_queue.qsize() > 2:
            with self.image_queue.mutex:
                self.image_queue.queue.clear()
        else:
            pass
        changed = False

        # If anything has changed in our configuration settings, change/update those.
        if (
            event == self.gui_save_tracking_button
            and values[self.gui_camera_addr] != self.config.capture_source
        ):
            print(
                "\033[94m[INFO] New value: {}\033[0m".format(
                    values[self.gui_camera_addr]
                )
            )
            try:
                # Try storing ints as ints, for those using wired cameras.
                self.config.capture_source = int(values[self.gui_camera_addr])
            except ValueError:
                if values[self.gui_camera_addr] == "":
                    self.config.capture_source = None
                else:
                    if (
                        len(values[self.gui_camera_addr]) > 5
                        and "http" not in values[self.gui_camera_addr]
                        and ".mp4" not in values[self.gui_camera_addr]
                    ):  # If http is not in camera address, add it.
                        self.config.capture_source = (
                            f"http://{values[self.gui_camera_addr]}/"
                        )
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

        if event == self.gui_restart_3d_calibration:
            self.ransac.calibration_3d_frame_counter = -621
            self.ransac.ibo.clear_filter()
            PlaySound(resource_path("Audio/start.wav"), SND_FILENAME | SND_ASYNC)

        if event == self.gui_restart_calibration:
            self.ransac.calibration_frame_counter = self.settings.calibration_samples
            self.ransac.ibo.clear_filter()
            PlaySound(resource_path("Audio/start.wav"), SND_FILENAME | SND_ASYNC)

        if event == self.gui_stop_calibration:
            self.ransac.calibration_frame_counter = 0

        if event == self.gui_recenter_eyes:
            self.settings.gui_recenter_eyes = True

        needs_roi_set = self.config.roi_window_h <= 0 or self.config.roi_window_w <= 0

        # TODO: Refactor if statements below...
        window[self.gui_tracking_fps].update("")
        window[self.gui_tracking_bps].update("")
        if self.config.capture_source is None or self.config.capture_source == "":
            window[self.gui_mode_readout].update("Waiting for camera address")
            window[self.gui_roi_message].update(visible=False)
            window[self.gui_output_graph].update(visible=False)
        elif self.camera.camera_status == CameraState.CONNECTING:
            window[self.gui_mode_readout].update("Camera Connecting")
        elif self.camera.camera_status == CameraState.DISCONNECTED:
            window[self.gui_mode_readout].update("Camera Reconnecting...")

        elif needs_roi_set:
            window[self.gui_mode_readout].update("Awaiting Eye Crop")
        elif self.ransac.calibration_frame_counter != None:
            window[self.gui_mode_readout].update("Calibration")
        else:
            window[self.gui_mode_readout].update("Tracking")
            window[self.gui_tracking_fps].update(self._movavg_fps(self.camera.fps))
            window[self.gui_tracking_bps].update(self._movavg_bps(self.camera.bps))

        if event == self.gui_mask_lighten:
            while True:
                try:
                    imgbytes = cv2.imencode(".ppm", maybe_image[0])[1].tobytes()
                    image = cv2.imdecode(
                        np.frombuffer(imgbytes, np.uint8), cv2.IMREAD_COLOR
                    )

                    cv2.imshow("Image", image)
                    cv2.waitKey(1)
                    #cv2.destroyAllWindows()
                    print("lighten")
                except Empty:
                    pass
        if event == self.gui_mask_markup:
            print("markup")

        if self.in_roi_mode:
            try:
                if self.roi_queue.empty():
                    self.capture_event.set()
                maybe_image = self.roi_queue.get(block=False, timeout=0.1) # this makes the ROI GUI page load slower when there isnt a cam, but fixes bad esp frame drop/lag/stutter
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

                if (
                    eye_info.info_type != EyeInfoOrigin.FAILURE
                ):  # and not eye_info.blink:
                    graph.update(background_color="white")
                    if not np.isnan(eye_info.x) and not np.isnan(eye_info.y):

                        graph.draw_circle(
                            (eye_info.x * -100, eye_info.y * -100),
                            eye_info.pupil_dilation * 25,
                            fill_color="black",
                            line_color="white",
                        )
                    else:
                        graph.draw_circle(
                            (0.0 * -100, 0.0 * -100),
                            20,
                            fill_color="black",
                            line_color="white",
                        )

                    if not np.isnan(eye_info.blink):

                        graph.draw_line(
                            (-100, abs(eye_info.blink) * 2 * 200),
                            (-100, 100),
                            color="#6f4ca1",
                            width=10,
                        )
                    else:
                        graph.draw_line(
                            (-100, 0.5 * 200), (-100, 100), color="#6f4ca1", width=10
                        )

                    if eye_info.blink <= 0.0:
                        graph.update(background_color="#6f4ca1")

                elif eye_info.info_type == EyeInfoOrigin.FAILURE:
                    graph.update(background_color="red")
                # Relay information to OSC
                if eye_info.info_type != EyeInfoOrigin.FAILURE:
                    self.osc_queue.put((self.eye_id, eye_info))
            except Empty:
                pass
