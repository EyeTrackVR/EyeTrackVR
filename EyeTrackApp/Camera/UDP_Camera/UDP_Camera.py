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
from .DataPacket import DataPacket # Python imports stupid. missed a single "."

WAIT_TIME = 0.1


# I HATE PYTHON!!!! slow fucking... 
# Never know when value passed by value or ref
# EVERYTHING is lowercase, EXCEPT True and False. ok
# const is UPPERCASE, but still modifiable. ok
# Unreadable sudo code language
# forced upon me by every industry. VR, AI, Websites? bruh
# Rant over

class UDP_Camera(ICameraSource):
    def extraInit(self):
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

        self.host = "0.0.0.0"
        self.port = 3333
        self.num_fragments = 48
        self.num_loaded = 0
        self.packets = [None] * self.num_fragments

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))

    def run(self):
        while True:
            if self.cancellation_event.is_set():
                print(f"{Fore.CYAN}[INFO] Exiting Capture thread{Fore.RESET}")
                # openCV won't switch to a new source if provided with one
                # so, we have to manually release the camera on exit

                return
            
            else:
                # We don't have a capture source to try yet, wait for one to show up in the GUI.
                if self.cancellation_event.wait(WAIT_TIME):
                    self.camera_status = CameraState.DISCONNECTED
                    return
                
            data, addr = self.sock.recvfrom(1024)
            self.handle_packet(data, addr)
                
    def handle_packet(self, data, addr):
        packet = DataPacket(data, 0, len(data))
        if packet.data is None or packet.id < 0 or packet.id >= self.num_fragments:
            return

        if packet.id == 0:
            self.num_loaded = 1
            self.packets = [None] * self.num_fragments
            self.packets[packet.id] = packet
        elif self.packets[packet.id] is None:
            self.packets[packet.id] = packet
            self.num_loaded += 1

        if self.num_loaded >= self.num_fragments:
            if self.packets[0] is None:
                return
            current_frame = self.packets[0].frame_num

            if any(p is None or p.frame_num != current_frame for p in self.packets):
                print("Packet loss detected.")
            else:
                print("Whole data received. Processing...")
                full_buffer = b''.join(p.data for p in self.packets)
                np_buffer = np.frombuffer(full_buffer, dtype=np.uint8)
                self.process_and_push_image(np_buffer)


            self.num_loaded = 0

        # Send acknowledgment
        self.sock.sendto(f"{packet.id}:ACK".encode(), addr)

    def process_and_push_image(self, buf: np.ndarray):
        image = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        if image is None:
            print(f"{Fore.YELLOW}[WARN] Frame drop. Corrupted JPEG.{Fore.RESET}")
            return
        
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
        
        self.push_image_to_queue(image, self.frame_number, self.fps)
