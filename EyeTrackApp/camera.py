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
BUFFER_SIZE = 32768
# Serial communication protocol:
#  header-begin (2 bytes) '\xff\xa0'
#  header-type (2 bytes)  '\xff\xa1'
#  packet-size (2 bytes)
#  packet (packet-size bytes)
ETVR_HEADER = b'\xff\xa0\xff\xa1'
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


class Camera:
    def __init__(
        self,
        config: EyeTrackCameraConfig,
        camera_index: int,
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        camera_status_outgoing: "queue.Queue[CameraState]",
        camera_output_outgoing: "queue.Queue(maxsize=2)",
    ):

        self.camera_status = CameraState.CONNECTING
        self.config = config
        self.camera_index = camera_index
        self.camera_status_outgoing = camera_status_outgoing
        self.camera_output_outgoing = camera_output_outgoing
        self.capture_event = capture_event
        self.cancellation_event = cancellation_event
        self.current_capture_source = config.capture_source
        self.cv2_camera: "cv2.VideoCapture" = None

        self.serial_connection = None
        self.last_frame_time = time.time()
        self.fps = 0
        self.bps = 0
        self.start = True
        self.buffer = b""
        self.sp_max = 2560  # Most ETVR frames are ~4298-4800 bytes (Keep lower!)

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
            current_frame_time = time.time()    # Should be using "time.perf_counter()", not worth ~3x cycles?
            delta_time = current_frame_time - self.last_frame_time
            self.last_frame_time = current_frame_time
            current_fps = 1 / delta_time if delta_time > 0 else 0
            # Exponential moving average (EMA). ~1100ns savings, delicious..
            self.fps = current_fps if not self.fps else 0.2 * current_fps + (1 - 0.2) * self.fps
            self.bps = image.nbytes * self.fps

            if should_push:
                self.push_image_to_queue(image, frame_number, self.fps)
        except Exception:
            print(f"{Fore.YELLOW}[WARN] Capture source problem, assuming camera disconnected, waiting for reconnect.{Fore.RESET}")
            self.camera_status = CameraState.DISCONNECTED
            pass

    def serial_read(self, rb):
        self.buffer += self.serial_connection.read(rb)
        return len(self.buffer)

    def serial_sleep(self, sb):
        if sb > 0:
            sb /= 256000    # Sleeping for 0.01s increases ".in_waiting" buffer by ~2560 bytes. Most ETVR frames are ~4298-4800
            time.sleep(sb)

    def get_next_jpeg_frame(self, conn):
        # Erm, so yah...
        self.serial_sleep(self.sp_max - (conn.in_waiting + len(self.buffer)))
        buffer_len = self.serial_read(conn.in_waiting)
        if buffer_len >= ETVR_HEADER_LEN:
            if buffer_len > (self.sp_max * 2.3):
                # Skip frames:
                #  Ad hoc to catch up to latest frames. Got a feelin there's going to be unforeseen consequences for this one
                beg = self.buffer.rfind(ETVR_HEADER)
            else:
                beg = self.buffer.find(ETVR_HEADER)
            if beg != -1:
                self.buffer = self.buffer[beg:]
                buffer_len = len(self.buffer)
                if buffer_len >= ETVR_HEADER_LEN:
                    end = int.from_bytes(self.buffer[4:ETVR_HEADER_LEN], signed=False, byteorder="little") + ETVR_HEADER_LEN
                    if conn.in_waiting + buffer_len < end:
                        self.serial_sleep(end - (conn.in_waiting + buffer_len))
                    if conn.in_waiting >= end:
                        buffer_len = self.serial_read(conn.in_waiting)
                    if buffer_len >= end and self.buffer[end-2:end] == b'\xff\xd9':
                        if end > self.sp_max:
                            self.sp_max = end
                        jpeg = self.buffer[ETVR_HEADER_LEN:end]
                        self.buffer = self.buffer[end:]
                        return jpeg
                    # Sometime we end up here ~44 times in a row, because "buffer_len" < "end" or EOL '\xff\xd9' was not found. Loosing 2.3-2.5 frames before things get normal
                    if end > self.sp_max:
                        self.sp_max = end
        return False

    def get_serial_camera_picture(self, should_push):
        # Stop spamming "Serial capture source problem" if connection is lost
        if self.serial_connection is None or self.camera_status == CameraState.DISCONNECTED:
            return
        try:
            if self.serial_connection.in_waiting:
                jpeg = self.get_next_jpeg_frame(self.serial_connection)
                if jpeg:
                    # Create jpeg frame from byte string
                    image = cv2.imdecode(np.fromstring(jpeg, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if image is None:
                        print(f"{Fore.YELLOW}[WARN] Frame drop. Corrupted JPEG.{Fore.RESET}")
                        return
                    # Calculate the fps.
                    current_frame_time = time.time()    # Should be using "time.perf_counter()", not worth ~3x cycles?
                    delta_time = current_frame_time - self.last_frame_time
                    self.last_frame_time = current_frame_time
                    current_fps = 1 / delta_time if delta_time > 0 else 0
                    # Exponential moving average (EMA). ~1100ns savings, delicious..
                    self.fps = current_fps if not self.fps else 0.2 * current_fps + (1 - 0.2) * self.fps
                    self.bps = len(jpeg) * self.fps

                    if should_push:
                        self.push_image_to_queue(image, current_frame_time, self.fps)
                # Discard the serial buffer. This is due to the fact that it,
                # may build up some outdated frames. A bit of a workaround here tbh.
                # Do this at the end to give buffer time to refill.
                if self.serial_connection.in_waiting >= BUFFER_SIZE:
                    print(f"{Fore.CYAN}[INFO] Discarding the serial buffer ({self.serial_connection.in_waiting} bytes){Fore.RESET}")
                    self.serial_connection.reset_input_buffer()
                    self.buffer = b''

        except Exception:
            print(f"{Fore.YELLOW}[WARN] Serial capture source problem, assuming camera disconnected, waiting for reconnect.{Fore.RESET}")
            self.serial_connection.close()
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
            conn.set_buffer_size(rx_size=BUFFER_SIZE, tx_size=BUFFER_SIZE)

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
            print(f"{Fore.YELLOW}[WARN] CAPTURE QUEUE BACKPRESSURE OF {qsize}. CHECK FOR CRASH OR TIMING ISSUES IN ALGORITHM.{Fore.RESET}")
        self.camera_output_outgoing.put((image, frame_number, fps))
        self.capture_event.clear()
