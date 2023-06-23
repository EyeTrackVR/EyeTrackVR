import cv2
import numpy as np
import queue
import serial
import serial.tools.list_ports
import threading
import time
import asyncio
from colorama import Fore
from config import EyeTrackConfig
from enum import Enum
import concurrent.futures
WAIT_TIME = 0.1

# Serial communication protocol:
# header-begin (2 bytes)
# header-type (2 bytes)
# packet-size (2 bytes)
# packet (packet-size bytes)
ETVR_HEADER = b'\xff\xa0'
ETVR_HEADER_FRAME = b'\xff\xa1'
ETVR_HEADER_LEN = 6


class CameraState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class Camera:
    def __init__(
            self,
            config: EyeTrackConfig,
            camera_index: int,
            cancellation_event: "threading.Event",
            capture_event: "threading.Event",
            camera_status_outgoing: "queue.Queue[CameraState]",
            camera_output_outgoing: "queue.Queue",
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
        self.timeout = 5  # Timeout in seconds
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.serial_connection = None
        self.last_frame_time = time.time()
        self.frame_number = 0
        self.fps = 0
        self.bps = 0
        self.start = True
        self.buffer = b''
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

    async def async_open_capture_source(self):
        try:
            capture_source = self.current_capture_source
            capture = cv2.VideoCapture(capture_source)
            await asyncio.sleep(0)  # Allow event loop to run other tasks
            if capture.isOpened():
                return capture
            else:
                return None
        except Exception as e:
            print(f"Failed to open capture source: {str(e)}")
            return None

    def init_camera(self):
        if self.cv2_camera == None:
          #  time.sleep(0.5)  # Very important wait
            def init():
                return cv2.VideoCapture(self.current_capture_source)
            future = self.executor.submit(init)
            future.add_done_callback(self.done_callback)
        else:
            pass
    def done_callback(self, future):
        try:
            time.sleep(0.1) # Very important wait
            self.cv2_camera = future.result()
        except Exception:
            # Set cv2_camera to None if an exception occurred
            self.cv2_camera = None
    def run(self):
        while True:
            if self.cancellation_event.is_set():
                print(f"{Fore.CYAN}[INFO] Exiting Capture thread{Fore.RESET}")
                return
            should_push = True
            # If things aren't open, retry until they are. Don't let read requests come in any earlier
            # than this, otherwise we can deadlock ourselves.
            if (
                    self.config.capture_source != None and self.config.capture_source != ""
            ):
              #  if self.cv2_camera is not None:
               #     print(self.cv2_camera, self.cv2_camera.isOpened(),self.camera_status)
                if "COM" in str(self.current_capture_source):
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
                           # or self.camera_status == CameraState.DISCONNECTED
                            or self.config.capture_source != self.current_capture_source
                    ):

                        print(self.error_message.format(self.config.capture_source))
                        # This requires a wait, otherwise we can error and possible screw up the camera
                        # firmware. Fickle things.
                        if self.cancellation_event.wait(WAIT_TIME):
                            return
                        self.current_capture_source = self.config.capture_source
                        self.init_camera()
                        self.camera_status = CameraState.CONNECTED
                        #self.cv2_camera = cv2.VideoCapture(self.current_capture_source)
                        should_push = False
            else:
                # We don't have a capture source to try yet, wait for one to show up in the GUI.
                if self.cancellation_event.wait(WAIT_TIME):
                    self.camera_status = CameraState.DISCONNECTED
                    return
            # Assuming we can access our capture source, wait for another thread to request a capture.
            # Cycle every so often to see if our cancellation token has fired. This basically uses a
            # python event as a context-less, resettable one-shot channel.
            if should_push and not self.capture_event.wait(timeout=0.02):
                continue
            if self.config.capture_source != None:
                if "COM" in str(self.current_capture_source):
                    self.get_serial_camera_picture(should_push)
                else:
                    self.get_cv2_camera_picture(should_push)
                if not should_push:
                    # if we get all the way down here, consider ourselves connected
                    self.camera_status = CameraState.CONNECTED
    def get_cv2_camera_picture(self, should_push):
        try:
            ret, image = self.cv2_camera.read()
            if not ret:
                self.cv2_camera.set(cv2.CAP_PROP_POS_FRAMES, 0)
                raise RuntimeError("Problem while getting frame")
            self.newft = time.time()
            frame_number = self.cv2_camera.get(cv2.CAP_PROP_POS_FRAMES)
            # Calculate the fps.
            current_frame_time = time.time()
            delta_time = current_frame_time - self.last_frame_time
            self.last_frame_time = current_frame_time
            if delta_time > 0:
                self.bps = len(image) / delta_time
            self.frame_number = self.frame_number + 1
            self.fps = (self.fps + self.pf_fps) / 2
            if self.newft != self.prevft:
                self.fps = 1 / (self.newft - self.prevft)
                self.prevft = self.newft
                self.fps = int(self.fps)
                if len(self.fl) < 60:
                    self.fl.append(self.fps)
                else:
                    self.fl.pop(0)
                    self.fl.append(self.fps)
                self.fps = sum(self.fl) / len(self.fl)
            else:
                self.fps = 69
            #self.bps = image.nbytes
            if should_push:
                self.push_image_to_queue(image, frame_number, self.fps)
        except:
            print(f"{Fore.YELLOW}[WARN] Capture source problem, assuming camera disconnected, waiting for reconnect.{Fore.RESET}")
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
        jpeg = self.buffer[beg+ETVR_HEADER_LEN:end+ETVR_HEADER_LEN]
        self.buffer = self.buffer[end+ETVR_HEADER_LEN:]
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
                        self.buffer = b''
                    # Calculate the fps.
                    current_frame_time = time.time()
                    delta_time = current_frame_time - self.last_frame_time
                    self.last_frame_time = current_frame_time
                    if delta_time > 0:
                        self.bps = len(jpeg) / delta_time
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
                    self.frame_number = self.frame_number + 1
                    if should_push:
                        self.push_image_to_queue(image, self.frame_number, self.fps)
        except Exception:
            print(f"{Fore.YELLOW}[WARN] Serial capture source problem, assuming camera disconnected, waiting for reconnect.{Fore.RESET}")
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
            conn = serial.Serial(
                baudrate = 3000000,
                port = port,
                xonxoff=False,
                dsrdtr=False,
                rtscts=False)
            # Set explicit buffer size for serial.
            conn.set_buffer_size(rx_size = 32768, tx_size = 32768)

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
                f"{Fore.YELLOW}[WARN] CAPTURE QUEUE BACKPRESSURE OF {qsize}. CHECK FOR CRASH OR TIMING ISSUES IN ALGORITHM.{Fore.RESET}")
        self.camera_output_outgoing.put((image, frame_number, fps))
        self.capture_event.clear()
