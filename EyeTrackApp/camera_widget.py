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

import PySimpleGUI as sg
from config import EyeTrackConfig
from collections import deque
from threading import Event, Thread
import math
from eye import EyeId
from eye_processor import EyeProcessor, EyeInfoOrigin
from queue import Queue, Empty
from camera import Camera, CameraState
import cv2
from osc.OSCMessage import OSCMessageType, OSCMessage
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC, resource_path
import numpy as np


# for clarity when indexing
X = 0
Y = 1


class CameraWidget:
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig, osc_queue: Queue):
        self.gui_camera_addr = f"-CAMERAADDR{widget_id}-"
        self.gui_rotation_slider = f"-ROTATIONSLIDER{widget_id}-"
        self.gui_rotation_ui_padding = f"-ROTATIONUIPADDING{widget_id}-"
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
            raise RuntimeError("\033[91m[WARN] Cannot have a camera widget represent both eyes!\033[0m")

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
            main_config,
            self.cancellation_event,
            self.capture_event,
            self.capture_queue,
            self.image_queue,
            self.eye_id,
            self.osc_queue,
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

        self.hover = None

        # cartesian co-ordinates in widget space are used during selection
        self.xy0 = None
        self.xy1 = None
        self.cartesian_needs_update = False
        # polar co-ordinates from the image center are the canonical representation
        self.cr, self.ca = None, None
        self.roi_size = None
        self.clip_size = None
        self.clip_pos = None
        self.padded_size = [244, 244]
        self.img_pos = None
        self.roi_image_center = None

        self.is_mouse_up = True
        self.hover_pos = None
        self.in_roi_mode = False
        self.movavg_fps_queue = deque(maxlen=120)
        self.movavg_bps_queue = deque(maxlen=120)

    def get_widget_layout(self):
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

    def get_roi_layout(self):
        self.roi_layout = [
            [
                # sg.Button(
                #    "Mark Out",
                #     key=self.gui_mask_markup,
                #      button_color="#6f4ca1",
                #       tooltip="Mark out stuff that is not your eye.",
                #    ),
                #    sg.Button(
                #        "Lighten",
                #        key=self.gui_mask_lighten,
                #       button_color="#6f4ca1",
                #      tooltip="Lighten shadowed areas.",
                #    ),
                sg.Text("Rotation", background_color="#424042"),
                sg.Slider(
                    range=(0, 360),
                    default_value=self.config.rotation_angle,
                    orientation="h",
                    key=self.gui_rotation_slider,
                    background_color="#424042",
                    tooltip="Adjust the rotation of your cameras, make them level.",
                ),
                sg.Checkbox(
                    "Camera Widget Padding",
                    default=self.config.gui_rotation_ui_padding,
                    tooltip="Pad the camera view widget enough to allow a full rotation.",
                    key=self.gui_rotation_ui_padding,
                    background_color="#424042",
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
                    motion_events=True,
                    background_color="#424042",
                ),
            ],
        ]

    def get_tracking_layout(self):
        # Define the window's contents
        self.tracking_layout = [
            [
                sg.Button(
                    "Start Calibration",
                    key=self.gui_restart_calibration,
                    button_color="#6f4ca1",
                    tooltip="Start eye calibration. Look all arround to all extreams without blinking until sound is heard.",
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
                sg.Text("Calibrating", key=self.gui_mode_readout, background_color="#424042"),
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

    def update_layouts(self):
        self.get_roi_layout()
        self.get_tracking_layout()
        self.get_widget_layout()

    def _movavg_fps(self, next_fps):
        self.movavg_fps_queue.append(next_fps)
        fps = round(sum(self.movavg_fps_queue) / len(self.movavg_fps_queue))
        millisec = round((1 / fps if fps else 0) * 1000)
        return f"{fps} Fps {millisec} ms"

    def _movavg_bps(self, next_bps):
        self.movavg_bps_queue.append(next_bps)
        return f"{sum(self.movavg_bps_queue) / len(self.movavg_bps_queue) * 0.001 * 0.001 * 8:.3f} Mbps"

    def _cartesian_to_polar(self):
        if not (self.xy0 is None or self.xy1 is None):
            roi_center = (self.xy0 + self.xy1) / 2 - self.roi_image_center
            self.cr = np.linalg.norm(roi_center)
            self.ca = math.atan2(roi_center[Y], roi_center[X]) + math.radians(self.config.rotation_angle)
            self.roi_size = np.abs(self.xy1 - self.xy0)

    def _polar_to_cartesian_at_angle(self, rotation_angle_radians):
        if not (self.cr is None or self.ca is None or self.roi_size is None):
            ca = self.ca - rotation_angle_radians
            cx = math.cos(ca) * self.cr + self.roi_image_center[X]
            cy = math.sin(ca) * self.cr + self.roi_image_center[Y]
            roi_pos = np.array((int(cx), int(cy))) - self.roi_size // 2
            return (roi_pos, roi_pos + self.roi_size)
        else:
            return (None, None)

    def _polar_to_cartesian(self):
        if not (self.cr is None or self.ca is None or self.roi_size is None):
            (self.xy0), (self.xy1) = self._polar_to_cartesian_at_angle(math.radians(self.config.rotation_angle))

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

    def on_config_update(self, data):
        keys = set(data.keys())
        model_keys = set(self.config.model_fields.keys())
        # we only want to restart our stuff, if our stuff got updated
        # at the model level
        if model_keys.intersection(keys):
            self.stop()
            self.start()

    def recenter_eyes(self, osc_message: OSCMessage):
        if osc_message.data is not bool:
            return  # just incase we get anything other than bool

    def recalibrate_eyes(self, osc_message: OSCMessage):
        if osc_message.data is not bool:
            return  # just incase we get anything other than bool

        if osc_message.data:
            self.ransac.ibo.clear_filter()
            self.ransac.calibration_frame_counter = self.config.calibration_samples
            PlaySound("Audio/start.wav", SND_FILENAME | SND_ASYNC)

    def render(self, window, event, values):
        changed = False

        if self.settings.gui_disable_gui == False:

            # If anything has changed in our configuration settings, change/update those.
            if event == self.gui_save_tracking_button and values[self.gui_camera_addr] != self.config.capture_source:
                print("\033[94m[INFO] New value: {}\033[0m".format(values[self.gui_camera_addr]))
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
                            self.config.capture_source = f"http://{values[self.gui_camera_addr]}/"
                        else:
                            self.config.capture_source = values[self.gui_camera_addr]
                changed = True

            if self.config.rotation_angle != int(values[self.gui_rotation_slider]):
                self.config.rotation_angle = int(values[self.gui_rotation_slider])
                changed = True
                self.cartesian_needs_update = True

            if self.config.gui_rotation_ui_padding != bool(values[self.gui_rotation_ui_padding]):
                self.config.gui_rotation_ui_padding = bool(values[self.gui_rotation_ui_padding])
                changed = True
                self.cartesian_needs_update = True

            # if self.config.gui_circular_crop != values[self.gui_circular_crop]:
            #     self.config.gui_circular_crop = values[self.gui_circular_crop]
            #    changed = True

            if changed:
                self.main_config.save()

            if event == self.gui_tracking_button:
                self.get_tracking_layout()
                print("\033[94m[INFO] Moving to tracking mode\033[0m")
                self.in_roi_mode = False
                self.camera.set_output_queue(self.capture_queue)
                window[self.gui_roi_layout].update(visible=False)
                window[self.gui_tracking_layout].update(visible=True)

            if event == self.gui_roi_button:
                self.get_roi_layout()
                print("\033[94m[INFO] Move to roi mode\033[0m")
                self.in_roi_mode = True
                self.camera.set_output_queue(self.roi_queue)
                window[self.gui_roi_layout].update(visible=True)
                window[self.gui_tracking_layout].update(visible=False)

            if event == "{}+UP".format(self.gui_roi_selection):
                # Event for mouse button up in ROI mode
                self.is_mouse_up = True
                print("UP")
                self.xy0 = np.clip(self.xy0, self.clip_pos, self.clip_pos + self.clip_size)
                self.xy1 = np.clip(self.xy1, self.clip_pos, self.clip_pos + self.clip_size)
                self._cartesian_to_polar()
                if all(abs(self.xy0 - self.xy1) != 0):
                    xy0, xy1 = self._polar_to_cartesian_at_angle(0)

                    self.config.roi_window_x, self.config.roi_window_y = (np.minimum(xy0, xy1) - self.img_pos).tolist()
                    self.config.roi_window_w, self.config.roi_window_h = (np.abs(xy0 - xy1)).tolist()
                    self.main_config.save()

            if event == self.gui_roi_selection:
                # Event for mouse button down or mouse drag in ROI mode
                self.hover_pos = None

                if self.is_mouse_up:
                    self.is_mouse_up = False
                    self.xy0 = np.array(values[self.gui_roi_selection])

                self.xy1 = np.array(values[self.gui_roi_selection])

                self._cartesian_to_polar()

            if event == "{}+MOVE".format(self.gui_roi_selection):
                if self.is_mouse_up:
                    self.hover_pos = np.array(values[self.gui_roi_selection])

                    if self.padded_size is not None:
                        if any(self.hover_pos > self.padded_size):
                            self.hover_pos = None

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

            #    if event == self.gui_mask_lighten:
            #       while True:
            #          try:
            #             maybe_image = self.roi_queue.get(block=False)
            #            imgbytes = cv2.imencode(".ppm", maybe_image[0])[1].tobytes()
            #           image = cv2.imdecode(
            #              np.frombuffer(imgbytes, np.uint8), cv2.IMREAD_COLOR
            #         )

            #        cv2.imshow("Image", image)
            #       cv2.waitKey(1)
            #      cv2.destroyAllWindows()
            #     print("lighen")
            # except Empty:
            #   pass
            # if event == self.gui_mask_markup:
            #    print("markup")

            if self.in_roi_mode:
                try:
                    if self.roi_queue.empty():
                        self.capture_event.set()
                    maybe_image = self.roi_queue.get(block=False)

                    if maybe_image:
                        image = maybe_image[0]

                        img_h, img_w, _ = image.shape

                        hyp = math.ceil((img_w**2 + img_h**2) ** 0.5)
                        rotation_matrix = cv2.getRotationMatrix2D(
                            ((img_w / 2), (img_h / 2)), self.config.rotation_angle, 1
                        )

                        # calculate position of all four corners of image

                        # calculate crop corner locations in original image space
                        x_coords, y_coords = np.matmul(
                            rotation_matrix,
                            np.transpose([[0, 0, 1], [img_w, 0, 1], [0, img_h, 1], [img_w, img_h, 1]]),
                        )

                        self.clip_size = np.array(
                            [math.ceil(max(x_coords) - min(x_coords)), math.ceil(max(y_coords) - min(y_coords))]
                        )
                        if self.config.gui_rotation_ui_padding:
                            self.padded_size = np.array([hyp, hyp])

                        else:
                            self.padded_size = self.clip_size

                        self.img_pos = ((self.padded_size - (img_w, img_h)) / 2).astype(np.int32)

                        self.clip_pos = ((self.padded_size - self.clip_size) / 2).astype(np.int32)

                        self.roi_image_center = self.padded_size / 2

                        # deferred to after roi_image_center is updated
                        if self.cartesian_needs_update:
                            self._polar_to_cartesian()
                            self.cartesian_needs_update = False

                        pad_matrix = np.float32([[1, 0, self.img_pos[X]], [0, 1, self.img_pos[Y]], [0, 0, 1]])
                        rotation_matrix_padded = cv2.getRotationMatrix2D(
                            self.roi_image_center, self.config.rotation_angle, 1
                        )
                        matrix = np.matmul(rotation_matrix_padded, pad_matrix)

                        image = cv2.warpAffine(
                            image,
                            matrix,
                            self.padded_size,
                            borderMode=cv2.BORDER_CONSTANT,
                            borderValue=(128, 128, 128),
                        )

                        maybe_image = (image, *maybe_image[1:])

                    imgbytes = cv2.imencode(".ppm", maybe_image[0])[1].tobytes()
                    graph = window[self.gui_roi_selection]
                    # INCREDIBLY IMPORTANT ERASE. Drawing images does NOT overwrite the buffer, the fucking
                    # graph keeps every image fed in until you call this. Therefore we have to make sure we
                    # erase before we redraw, otherwise we'll leak memory *very* quickly.
                    graph.erase()
                    graph.draw_image(data=imgbytes, location=(0, 0))

                    def make_dashed(spawn_item, dark="#000000", light="#ffffff", duty=1):
                        pixel_duty = math.floor(4 * duty)
                        for (color, dashoffset) in [(dark, 0), (light, 4)]:
                            item = spawn_item(color)
                            graph._TKCanvas2.itemconfig(item, dash=(pixel_duty, 8 - pixel_duty), dashoffset=dashoffset)

                    if self.xy0 is None or self.xy1 is None:
                        # roi_window rotates around roi center, we rotate around image center
                        # TODO: it would be nice if they were more consistent
                        roi_window_pos = (self.config.roi_window_x, self.config.roi_window_y)
                        roi_window_size = (self.config.roi_window_w, self.config.roi_window_h)
                        self.xy0 = roi_window_pos + self.img_pos
                        self.xy1 = self.xy0 + roi_window_size
                        self._cartesian_to_polar()
                        self.ca -= math.radians(self.config.rotation_angle)
                        self._polar_to_cartesian()

                    style = {}
                    if self.is_mouse_up:
                        style = {"dark": "#7f78ff", "light": "#d002ff", "duty": 0.5}
                    make_dashed(
                        lambda color: graph.draw_rectangle(
                            self.xy0,
                            self.xy1,
                            line_color=color,
                        ),
                        **style,
                    )
                    if self.is_mouse_up and self.hover_pos is not None:
                        make_dashed(
                            lambda color: graph.draw_line(
                                (self.hover_pos[X], 0), (self.hover_pos[X], self.padded_size[Y]), color=color
                            )
                        )
                        make_dashed(
                            lambda color: graph.draw_line(
                                (0, self.hover_pos[Y]), (self.padded_size[X], self.hover_pos[Y]), color=color
                            )
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

                    if eye_info.info_type != EyeInfoOrigin.FAILURE:  # and not eye_info.blink:
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
                                (-100, 100),  # Start at the bottom (-100)
                                (-100, (eye_info.blink * 200) - 100),  # Scale and adjust to the -100 to 100 range
                                color="#6f4ca1",
                                width=10,
                            )

                        else:
                            graph.draw_line((-100, 0.5 * 200), (-100, 100), color="#6f4ca1", width=10)

                        if eye_info.blink <= 0.0:
                            graph.update(background_color="#6f4ca1")

                    elif eye_info.info_type == EyeInfoOrigin.FAILURE:
                        graph.update(background_color="red")

                except Empty:
                    pass

        else:

            def back(*args):
                pass

            try:
                window[self.gui_roi_message].update(visible=False)
                window[self.gui_output_graph].update(visible=False)
                (maybe_image, eye_info) = self.image_queue.get(block=False)

            except Empty:
                pass
