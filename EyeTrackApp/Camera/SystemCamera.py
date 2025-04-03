import struct
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
from Camera.ICameraSource import ICameraSource
import socket

WAIT_TIME = 0.1

class SystemCamera(ICameraSource):
    def run(self):
        OPENCV_PARAMS = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            5000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            5000,
        ]
        while True:
            if self.cancellation_event.is_set():
                print(f"{Fore.CYAN}[INFO] Exiting Capture thread{Fore.RESET}")
                # openCV won't switch to a new source if provided with one
                # so, we have to manually release the camera on exit

                addr = str(self.current_capture_source)
                self.cv2_camera.release()

                return
            should_push = True
            # If things aren't open, retry until they are. Don't let read requests come in any earlier
            # than this, otherwise we can deadlock ourselves.
            if self.config.capture_source != None and self.config.capture_source != "":
                self.current_capture_source = self.config.capture_source
                addr = str(self.current_capture_source)

                if (
                    self.cv2_camera is None
                    or not self.cv2_camera.isOpened()
                    or self.camera_status == CameraState.DISCONNECTED
                    or self.config.capture_source != self.current_capture_source
                ):
                    print(self.error_message.format(self.config.capture_source))
                    # This requires a wait, otherwise we can error and possible screw up the camera
                    # firmware. Fickle things.
                    if self.cancellation_event.wait(WAIT_TIME):
                        return
                    self.current_capture_source = self.config.capture_source
                    #   self.cv2_camera = cv2.VideoCapture(self.current_capture_source)

                    self.cv2_camera = cv2.VideoCapture()
                    self.cv2_camera.setExceptionMode(True)
                    # https://github.com/opencv/opencv/blob/4.8.0/modules/videoio/include/opencv2/videoio.hpp#L803
                    self.cv2_camera.open(self.current_capture_source)
                    should_push = False
            else:
                # We don't have a capture source to try yet, wait for one to show up in the GUI.
                if self.cancellation_event.wait(WAIT_TIME):
                    self.camera_status = CameraState.DISCONNECTED
                    return
            # Assuming we can access our capture source, wait for another thread to request a capture.
            # Cycle every so often to see if our cancellation token has fired. This basically uses a
            # python event as a context-less, resettable one-shot channel.
            if should_push and not self.capture_event.wait(timeout=0.001):
                continue
            if self.config.capture_source != None:
                addr = str(self.current_capture_source)
                self.get_cv2_camera_picture(should_push)
                if not should_push:
                    # if we get all the way down here, consider ourselves connected
                    self.camera_status = CameraState.CONNECTED

    def get_cv2_camera_picture(self, should_push):
        try:
            ret, image = self.cv2_camera.read()
            height, width = image.shape[:2]  # Calculate the aspect ratio
            if int(width) > 680:
                aspect_ratio = float(width) / float(
                    height
                )  # Determine the new height based on the desired maximum width
                new_height = int(680 / aspect_ratio)
                image = cv2.resize(image, (680, new_height))
            if not ret:
                self.cv2_camera.set(cv2.CAP_PROP_POS_FRAMES, 0)
                raise RuntimeError("Problem while getting frame")
            frame_number = self.cv2_camera.get(cv2.CAP_PROP_POS_FRAMES)
            current_frame_time = time.time()
            delta_time = current_frame_time - self.last_frame_time
            if delta_time > 0:
                current_fps = 1 / delta_time
            else:
                current_fps = 0
            self.last_frame_time = current_frame_time

            if len(self.fl) < 60:
                self.fl.append(current_fps)
            else:
                self.fl.pop(0)
                self.fl.append(current_fps)

            self.fps = sum(self.fl) / len(self.fl)
            self.bps = image.nbytes * self.fps


            if should_push:
                self.push_image_to_queue(image, frame_number, self.fps)
        except:
            print(
                f"{Fore.YELLOW}[WARN] Capture source problem, assuming camera disconnected, waiting for reconnect.{Fore.RESET}"
            )
            self.camera_status = CameraState.DISCONNECTED
            pass