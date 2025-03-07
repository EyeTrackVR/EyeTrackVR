import cv2
import numpy as np
import queue
import serial
import serial.tools.list_ports
import threading
import time
from colorama import Fore
from config import EyeTrackCameraConfig
from enum import Enum
import psutil, os
import sys
from Camera.CameraState import CameraState
from abc import ABC, abstractmethod


# This is when C# dev does Python dev
class ICameraSource:
    def __init__(
        self,
        config: EyeTrackCameraConfig,
        camera_index: int,
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        camera_status_outgoing: "queue.Queue[CameraState]",
        camera_output_outgoing: "queue.Queue(maxsize=20)",
    ):
        self.camera_status = CameraState.CONNECTING
        self.config = config
        self.camera_index = camera_index
        self.camera_address = config.capture_source
        self.camera_status_outgoing = camera_status_outgoing
        self.camera_output_outgoing = camera_output_outgoing
        self.capture_event = capture_event
        self.cancellation_event = cancellation_event
        self.current_capture_source = config.capture_source
        self.cv2_camera: "cv2.VideoCapture" = None

        self.serial_connection = None
        self.last_frame_time = time.time()
        self.frame_number = 0
        self.fps = 0
        self.bps = 0
        self.start = True
        self.buffer = b""
        self.pf_fps = 0
        self.prevft = 0
        self.newft = 0
        self.fl = [0]

        self.extraInit()

        process = psutil.Process(os.getpid())  # set process priority to low
        try:
            sys.getwindowsversion()
        except AttributeError:
            process.nice(10)  # UNIX: 0 low 10 high
            process.nice()
        else:
            process.nice(psutil.HIGH_PRIORITY_CLASS)  # Windows
            process.nice()
            # See https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getpriorityclass#return-value for values


        self.error_message = f"{Fore.YELLOW}[WARN] Capture source {{}} not found, retrying...{Fore.RESET}"

    def __del__(self):
        pass

    def push_image_to_queue(self, image, frame_number, fps):
        # If there's backpressure, just yell. We really shouldn't have this unless we start getting
        # some sort of capture event conflict though.
        qsize = self.camera_output_outgoing.qsize()
        if qsize > 1:
            print(
                f"{Fore.YELLOW}[WARN] CAPTURE QUEUE BACKPRESSURE OF {qsize}. CHECK FOR CRASH OR TIMING ISSUES IN ALGORITHM.{Fore.RESET}"
            )
            pass
        self.camera_output_outgoing.put((image, frame_number, fps))
        self.capture_event.clear()

    @abstractmethod
    def run(self):
        pass

    def extraInit(self):
        pass

    def set_output_queue(self, camera_output_outgoing: "queue.Queue"):
        self.camera_output_outgoing = camera_output_outgoing

    def get_stream_fps(self):
        """Based on how many times this method gets called"""

        # Calculate the fps.
        current_frame_time = time.time()
        delta_time = current_frame_time - self.last_frame_time
        self.last_frame_time = current_frame_time

        # Avoid division by zero
        if delta_time > 0:
            fps = 1.0 / delta_time
        else:
            fps = 0

        # Smooth the FPS using a moving average
        self.fl.append(fps)
        if len(self.fl) > 60:
            self.fl.pop(0)  # Keep the list length constant

        # Compute average FPS
        fps = sum(self.fl) / len(self.fl)

        return fps
