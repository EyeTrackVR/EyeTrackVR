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
# Serial communication protocol:
# header-begin (2 bytes)
# header-type (2 bytes)
# packet-size (2 bytes)
# packet (packet-size bytes)
ETVR_HEADER = b"\xff\xa0"
ETVR_HEADER_FRAME = b"\xff\xa1"
ETVR_HEADER_LEN = 6

class SerialCamera(ICameraSource):
    def run(self):
        while True:
            if self.cancellation_event.is_set():
                print(f"{Fore.CYAN}[INFO] Exiting Capture thread{Fore.RESET}")
                # openCV won't switch to a new source if provided with one
                # so, we have to manually release the camera on exit

                return
            should_push = True
            # If things aren't open, retry until they are. Don't let read requests come in any earlier
            # than this, otherwise we can deadlock ourselves.
            if self.config.capture_source != None and self.config.capture_source != "":
                self.current_capture_source = self.config.capture_source
                addr = str(self.current_capture_source)

                if (
                    self.serial_connection is None
                    or self.camera_status == CameraState.DISCONNECTED
                    or self.config.capture_source != self.current_capture_source
                ):
                    port = self.config.capture_source
                    self.current_capture_source = port
                    self.start_serial_connection(port)
                
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
                self.get_serial_camera_picture(should_push)
                if not should_push:
                    # if we get all the way down here, consider ourselves connected
                    self.camera_status = CameraState.CONNECTED

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
                    
                    fps = self.get_stream_fps()

                    if should_push:
                        self.push_image_to_queue(image, self.frame_number, fps)
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