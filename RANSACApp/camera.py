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

WAIT_TIME = 0.1

class Camera:
    def __init__(
        self,
        config: RansacConfig,
        camera_index: int,
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        camera_status_outgoing: "queue.Queue[CameraState]",
        camera_output_outgoing: "queue.Queue",
    ):
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
        self.previous_frame = None
        self.error_message = "Capture source {} not found, retrying in 500ms"

    def set_output_queue(self, camera_output_outgoing: "queue.Queue"):
        self.camera_output_outgoing = camera_output_outgoing

    def run(self):
        while True:
            if self.cancellation_event.is_set():
                print("Exiting capture thread")
                return
            should_push = True
            # If things aren't open, retry until they are. Don't let read requests come in any earlier
            # than this, otherwise we can deadlock ourselves.
            if (
                self.config.capture_source != None and self.config.capture_source != ""
            ):
                if (
                    self.wired_camera is None
                    or not self.wired_camera.isOpened()
                    
                    or self.config.capture_source != self.current_capture_source
                ):
                    print(self.error_message.format(self.config.capture_source))
                    # This requires a wait, otherwise we can error and possible screw up the camera
                    # firmware. Fickle things.
                    if self.cancellation_event.wait(WAIT_TIME):
                        return
                    self.current_capture_source = self.config.capture_source
                    self.wired_camera = cv2.VideoCapture(self.current_capture_source)
      
                # We don't have a capture source to try yet, wait for one to show up in the GUI.
    
            # Assuming we can access our capture source, wait for another thread to request a capture.
            # Cycle every so often to see if our cancellation token has fired. This basically uses a
            # python event as a contextless, resettable one-shot channel.
            if should_push and not self.capture_event.wait(timeout=0.02):
                continue

            self.get_wired_camera_picture()
            #if not should_push:
                # if we get all the way down here, consider ourselves connected
                
           

    
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
            self.previous_frame = None
            self.stream_frame_number = 0

    @staticmethod
    def check_is_image_valid(image):
        try:
            return bool(len(image))
        except TypeError:
            return False

    @staticmethod
    def decode_image(data):
        try:
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
        except:
            return None

    def push_image_to_queue(self, image, frame_number, fps):
        # If there's backpressure, just yell. We really shouldn't have this unless we start getting
        # some sort of capture event conflict though.
        qsize = self.camera_output_outgoing.qsize()
        if qsize > 1:
            print(
                f"CAPTURE QUEUE BACKPRESSURE OF {qsize}. CHECK FOR CRASH OR TIMING ISSUES IN ALGORITHM."
            )
        self.camera_output_outgoing.put((image, frame_number, fps))
        self.capture_event.clear()
