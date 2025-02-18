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

Copyright (c) 2025 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

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
from ctypes import windll
import win32gui
import win32ui

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

WAIT_TIME = 0.1
# Serial communication protocol:
# header-begin (2 bytes)
# header-type (2 bytes)
# packet-size (2 bytes)
# packet (packet-size bytes)
ETVR_HEADER = b"\xff\xa0"
ETVR_HEADER_FRAME = b"\xff\xa1"
ETVR_HEADER_LEN = 6


class CameraState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


def is_serial_capture_source(addr: str) -> bool:
    """
    Returns True if the capture source address is a serial port.
    """
    return (
        addr.startswith("COM") or addr.startswith("/dev/cu") or addr.startswith("/dev/tty")  # Windows  # macOS  # Linux
    )

def is_aseevr_capture_source(addr: str) -> bool:
    """
    Returns True if the capture source address is ASeeVR/Droolon Pi 1
    """
    if addr == "aseevrleft" or addr == "aseevrright":
        return(True)        
    else:
        return(False)

class Camera:
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
        self.aseevr_camera = None
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



        self.error_message = f"{Fore.YELLOW}[WARN] Capture source {{}} not found, retrying...{Fore.RESET}"

    def __del__(self):
        if self.serial_connection is not None:
            self.serial_connection.close()

    def set_output_queue(self, camera_output_outgoing: "queue.Queue"):
        self.camera_output_outgoing = camera_output_outgoing

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
                if is_serial_capture_source(addr):
                    pass # TODO: find a nicer way to stop the com port
                  #  self.serial_connection.close()
                elif is_aseevr_capture_source(addr):
                    # We don't need any special release for ASeeVR, each capture event is fully closed within itself
                    pass
                else:
                    self.cv2_camera.release()

                return
            should_push = True
            # If things aren't open, retry until they are. Don't let read requests come in any earlier
            # than this, otherwise we can deadlock ourselves.
            if self.config.capture_source != None and self.config.capture_source != "":
                self.current_capture_source = self.config.capture_source
                addr = str(self.current_capture_source)
                if is_serial_capture_source(addr):
                    if (
                        self.serial_connection is None
                        or self.camera_status == CameraState.DISCONNECTED
                        or self.config.capture_source != self.current_capture_source
                    ):
                        port = self.config.capture_source
                        self.current_capture_source = port
                        self.start_serial_connection(port)
                elif is_aseevr_capture_source(addr):
                    if (
                        self.aseevr_camera is None
                        or self.camera_status == CameraState.DISCONNECTED
                        or self.config.capture_source != self.current_capture_source
                    ):
                        self.current_capture_source = self.config.capture_source
                        
                        # Determine if we want the left or the right video feed and
                        # set the pimax_camera variable to the window title of that eye
                        if ( self.current_capture_source == "aseevrleft"):
                            self.aseevr_camera = "draw Image1"
                        elif (self.current_capture_source == "aseevrright"):
                            self.aseevr_camera = "draw Image2"
                        else:
                            # This should be a completely impossible scenario, but... I guess I need to do something here
                            print("There is only aseevrleft and aseevrright.")
                        should_push = False
                else:
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
                if is_serial_capture_source(addr):
                    self.get_serial_camera_picture(should_push)
                elif is_aseevr_capture_source(addr):
                    self.get_aseevr_camera_picture(should_push)
                else:
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

    def get_aseevr_camera_picture(self, should_push):
        try:
            # We probably need to be DPI aware to capture the window correctly for
            # users that have window scaling set to something else than 100%
            windll.user32.SetProcessDPIAware()
            
            # Find the right window and then capture it to a bitmap using win32gui
            hwnd = win32gui.FindWindow(None, self.aseevr_camera)
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, 320, 240)
            save_dc.SelectObject(bitmap)
            result = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)
            
            # Convert the created bitmap into a format that ETVR likes
            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            image = np.frombuffer(bmpstr, dtype=np.uint8).reshape((bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4))
            image = np.ascontiguousarray(image)[..., :-1]
            
            # Clean up after writing the image
            win32gui.DeleteObject(bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
          
            # Calculate the aspect ratio
            height, width = image.shape[:2]  

            # Calculate the fps.
            current_frame_time = time.time()
            delta_time = current_frame_time - self.last_frame_time
            self.last_frame_time = current_frame_time
            if delta_time > 0:
                self.bps = len(image) / delta_time
            self.frame_number = self.frame_number + 1
            self.fps = (self.fps + self.pf_fps) / 2
            self.newft = time.time()
            self.fps = 1 / (self.newft - self.prevft)
            self.prevft = self.newft
            self.fps = int(self.fps)
            if len(self.fl) < 60:
                self.fl.append(self.fps)
            else:
                self.fl.pop(0)
                self.fl.append(self.fps)
            self.fps = sum(self.fl) / len(self.fl)
            #  self.bps = image.nbytes
            frame_number = self.frame_number
            if should_push:
                self.push_image_to_queue(image, frame_number, self.fps)
        except:
            print(
                f"{Fore.YELLOW}[WARN] Capture source problem, assuming camera disconnected, waiting for reconnect.{Fore.RESET}"
            )
            self.camera_status = CameraState.DISCONNECTED
            pass

    def get_next_packet_bounds(self):
        beg = -1
        while beg == -1:
            self.buffer += self.serial_connection.read(2048)
            beg = self.buffer.find(ETVR_HEADER + ETVR_HEADER_FRAME)
        # Discard any data before the frame header.
        if beg > 0:
            self.buffer = self.buffer[beg:]
            beg = 0
        # We know exactly how long the jpeg packet is
        end = int.from_bytes(self.buffer[4:6], signed=False, byteorder="little")
        self.buffer += self.serial_connection.read(end - len(self.buffer))
        return beg, end

    def get_next_jpeg_frame(self):
        beg, end = self.get_next_packet_bounds()
        jpeg = self.buffer[beg + ETVR_HEADER_LEN : end + ETVR_HEADER_LEN]
        self.buffer = self.buffer[end + ETVR_HEADER_LEN :]
        return jpeg

    def get_serial_camera_picture(self, should_push):
        conn = self.serial_connection
        if conn is None:
            return
        try:
            if conn.in_waiting:
                jpeg = self.get_next_jpeg_frame()
                if jpeg:
                    # Create jpeg frame from byte string
                    image = cv2.imdecode(np.fromstring(jpeg, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if image is None:
                        print(f"{Fore.YELLOW}[WARN] Frame drop. Corrupted JPEG.{Fore.RESET}")
                        return
                    # Discard the serial buffer. This is due to the fact that it
                    # may build up some outdated frames. A bit of a workaround here tbh.
                    if conn.in_waiting >= 32768:
                        print(f"{Fore.CYAN}[INFO] Discarding the serial buffer ({conn.in_waiting} bytes){Fore.RESET}")
                        conn.reset_input_buffer()
                        self.buffer = b""
                    # Calculate the fps.
                    current_frame_time = time.time()
                    delta_time = current_frame_time - self.last_frame_time
                    self.last_frame_time = current_frame_time
                    self.fps = (self.fps + self.pf_fps) / 2
                    self.newft = time.time()
                    self.fps = 1 / (self.newft - self.prevft)
                    self.prevft = self.newft
                    self.fps = int(self.fps)
                    if len(self.fl) < 60:
                        self.fl.append(self.fps)
                    else:
                        self.fl.pop(0)
                        self.fl.append(self.fps)
                    self.fps = sum(self.fl) / len(self.fl)
                    self.bps = image.nbytes * self.fps
                    self.frame_number = self.frame_number + 1
                    if should_push:
                        self.push_image_to_queue(image, self.frame_number, self.fps)
        except Exception:
            print(
                f"{Fore.YELLOW}[WARN] Serial capture source problem, assuming camera disconnected, waiting for reconnect.{Fore.RESET}"
            )
            conn.close()
            self.camera_status = CameraState.DISCONNECTED
            pass

    def start_serial_connection(self, port):
        if self.serial_connection is not None and self.serial_connection.is_open:
            # Do nothing. The connection is already open on this port.
            if self.serial_connection.port == port:
                return
            # Otherwise, close the connection before trying to reopen.
            self.serial_connection.close()
        com_ports = [tuple(p) for p in list(serial.tools.list_ports.comports())]
        # Do not try connecting if no such port i.e. device was unplugged.
        if not any(p for p in com_ports if port in p):
            return
        try:
            rate = 115200 if sys.platform == "darwin" else 3000000  # Higher baud rate not working on macOS
            conn = serial.Serial(baudrate=rate, port=port, xonxoff=False, dsrdtr=False, rtscts=False)
            # Set explicit buffer size for serial.
            if sys.platform == "win32":
                buffer_size = 32768
                conn.set_buffer_size(rx_size=buffer_size, tx_size=buffer_size)

            print(f"{Fore.CYAN}[INFO] ETVR Serial Tracker device connected on {port}{Fore.RESET}")
            self.serial_connection = conn
            self.camera_status = CameraState.CONNECTED
        except Exception:
            print(f"{Fore.CYAN}[INFO] Failed to connect on {port}{Fore.RESET}")
            self.camera_status = CameraState.DISCONNECTED

    def push_image_to_queue(self, image, frame_number, fps):
        # If there's backpressure, just yell. We really shouldn't have this unless we start getting
        # some sort of capture event conflict though.
        qsize = self.camera_output_outgoing.qsize()
        if qsize > 1:
            print(
                f"{Fore.YELLOW}[WARN] CAPTURE QUEUE BACKPRESSURE OF {qsize}. CHECK FOR CRASH OR TIMING ISSUES IN ALGORITHM.{Fore.RESET}"
            )
        self.camera_output_outgoing.put((image, frame_number, fps))
        self.capture_event.clear()
