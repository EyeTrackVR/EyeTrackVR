from time import sleep

import numpy

from config import RansacConfig
import requests
from enum import Enum
import threading
import queue
import runpy
import cv2


class CameraState(Enum):
    CONNECTED = 1
    DISCONNECTED = 2


class Camera:
    def __init__(self, config: RansacConfig, camera_index: int, cancellation_event: "threading.Event",
                 capture_event: "threading.Event", camera_status_outgoing: "queue.Queue[CameraState]",
                 camera_output_outgoing: "queue.Queue"):
        self.config = config
        self.camera_index = camera_index
        self.camera_address = config.capture_source
        self.camera_status_outgoing = camera_status_outgoing
        self.camera_output_outgoing = camera_output_outgoing
        self.capture_event = capture_event
        self.cancellation_event = cancellation_event
        self.current_capture_source = config.capture_source
        self.wired_camera: "cv2.VideoCapture" = cv2.VideoCapture(config.capture_source)
        self.stream = None
        self.stream_frame_number = 0
        self.stream_bytes = bytes()
        self.error_message = "Capture source {} not found, retrying in 500ms"

    def set_output_queue(self, camera_output_outgoing: "queue.Queue"):
        self.camera_output_outgoing = camera_output_outgoing

    def run(self):
        while True:
            if self.cancellation_event.is_set():
                print("Exiting capture thread")
                return

            # If things aren't open, retry until they are. Don't let read requests come in any earlier
            # than this, otherwise we can deadlock ourselves.
            if type(self.config.capture_source) == str and "http" in self.config.capture_source:
                try:
                    self.stream = requests.get(self.config.capture_source, stream=True)
                except requests.exceptions.RequestException:
                    print(self.error_message.format(self.config.capture_source))
            else:
                # so, they might have switched to a wired camera for some reason, no need to keep the stream running
                self.cleanup_stream()

                if not self.wired_camera.isOpened() or self.config.capture_source != self.current_capture_source:
                    print(self.error_message.format(self.config.capture_source))
                    sleep(0.5)
                    self.current_capture_source = self.config.capture_source
                    self.wired_camera = cv2.VideoCapture(self.current_capture_source)
                    continue

            # Assuming we can access our capture source, wait for another thread to request a capture.
            # Cycle every so often to see if our cancellation token has fired. This basically uses a
            # python event as a contextless, resettable one-shot channel.
            if not self.capture_event.wait(timeout=0.02):
                continue

            if self.stream:
                self.get_stream_picture()
            else:
                self.get_wired_camera_picture()

    def get_stream_picture(self):
        for chunk in self.stream.iter_content(chunk_size=1024):
            self.stream_bytes += chunk
            # mjpeg streams are encoded into frames starting and ending with those bytes
            starting_section = self.stream_bytes.find(b'\xff\xd8')
            closing_section = self.stream_bytes.find(b'\xff\xd9')

            if starting_section != -1 and closing_section != -1:
                # we extract the encoded image first, and then prepare the buffer for another frame
                jpg_data = self.stream_bytes[starting_section:closing_section+2]
                self.stream_frame_number += 1
                self.stream_bytes = self.stream_bytes[closing_section+2:]
                image = cv2.imdecode(numpy.fromstring(jpg_data, dtype=numpy.uint8), cv2.IMREAD_COLOR)
                self.push_image_to_queue(image, self.stream_frame_number, 60)

    def get_wired_camera_picture(self):
        try:
            ret, image = self.wired_camera.read()
            if not ret:
                self.wired_camera.set(cv2.CAP_PROP_POS_FRAMES, 0)
                raise RuntimeError("Problem while getting frame")
            frame_number = self.wired_camera.get(cv2.CAP_PROP_POS_FRAMES)
            fps = self.wired_camera.get(cv2.CAP_PROP_FPS)
            self.push_image_to_queue(image, frame_number, fps)
        except:
            # print("Capture source problem, assuming camera disconnected, waiting for reconnect.")
            pass

    def cleanup_stream(self):
        if self.stream:
            self.stream.close()
            self.stream_bytes = None
            self.stream_frame_number = 0

    def push_image_to_queue(self, image, frame_number, fps):
        # If there's backpressure, just yell. We really shouldn't have this unless we start getting
        # some sort of capture event conflict though.
        qsize = self.camera_output_outgoing.qsize()
        if qsize > 1:
            print(f"CAPTURE QUEUE BACKPRESSURE OF {qsize}. CHECK FOR CRASH OR TIMING ISSUES IN ALGORITHM.")
        self.camera_output_outgoing.put((image, frame_number, fps))
        self.capture_event.clear()