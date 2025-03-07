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
from .DataPacket import PacketHeader # Python imports stupid. missed a single "."

WAIT_TIME = 0.1

BUFFER_SIZE = 1024
NUM_FRAGMENTS = 48
HEADER_FORMAT = "iii"

RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"

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
        self.num_loaded = 0
        self.packets = [None] * NUM_FRAGMENTS
        self.rawDataBuffer = np.zeros(BUFFER_SIZE, dtype=np.uint8)
        self.rawFullDataBuffer = np.zeros(BUFFER_SIZE*NUM_FRAGMENTS, dtype=np.uint8)
        self.imageBuffView = memoryview(self.rawFullDataBuffer)
        self.currentFrameNum = 0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))

    def run(self):
        while True:
            if self.cancellation_event.is_set():
                print(f"{Fore.CYAN}[INFO] Exiting Capture thread{Fore.RESET}")
                # openCV won't switch to a new source if provided with one
                # so, we have to manually release the camera on exit

                return
            
            
            bufferView = memoryview(self.rawDataBuffer)
            n, senderAddr = self.sock.recvfrom_into(bufferView)
            self.handle_packet(n, senderAddr)

    def saveDataToBuff(self, dataView: memoryview, packet: PacketHeader):
        header_size = struct.calcsize(HEADER_FORMAT)
        payload_start = header_size
        payload_end = header_size + packet.image_buf_size
        payload = dataView[payload_start:payload_end]
        
        #time.sleep(0.05)

        offset = self.packets[0].image_buf_size * packet.id  # Adjust offset based on payload size
        self.imageBuffView[offset: offset + packet.image_buf_size] = payload
        # print(f"Packet {packet.id}: {offset}->{offset + packet.image_buf_size}")

    def resetImageBuffer(self):
        self.rawFullDataBuffer = np.zeros(BUFFER_SIZE*NUM_FRAGMENTS, dtype=np.uint8)
                
    def handle_packet(self, dataSize, senderAddr):
        bufferView = memoryview(self.rawDataBuffer)
        packet = PacketHeader(HEADER_FORMAT, bufferView, dataSize)
        if packet.id < 0 or packet.id >= NUM_FRAGMENTS:
            return
        
        # Send acknowledgment
        self.sock.sendto(f"{packet.id}:{packet.frame_num}:ACK".encode(), senderAddr)
        # print(packet.id)

        if self.num_loaded > 0 and packet.id != 0:
            self.sock.sendto(f"ERR".encode(), senderAddr)

        if packet.id == 0 or packet.frame_num != self.currentFrameNum:
            self.packets: list[PacketHeader|None] = [None] * NUM_FRAGMENTS # Reset packets
            self.num_loaded = 0
            self.currentFrameNum = packet.frame_num
            self.rawFullDataBuffer.fill(0)
            # print("Reset frame capture")
            
        if (self.packets[packet.id] is None 
            and self.packets[0] is not None
            or packet.id == 0 ):
            self.num_loaded += 1
            self.packets[packet.id] = packet
            self.saveDataToBuff(bufferView, packet)

        # print(f"Got packet id: {packet.id} (total: )")

        # if (self.num_loaded > NUM_FRAGMENTS * 0.75):
        #     formatted_list = "[" + ", ".join(f"{RED}x{RESET}" if item is None else f"{GREEN}x{RESET}" for item in self.packets) + "]"
        #     print(formatted_list)

        if self.num_loaded >= NUM_FRAGMENTS:
            if self.packets[0] is None:
                return
            current_frame = self.packets[0].frame_num

            if any(p is None or p.frame_num != current_frame for p in self.packets):
                print("Packet loss detected.")
                pass
            else:
                #print("Whole data received. Processing...")
                self.process_and_push_image()

            self.num_loaded = 0
            self.packets: list[PacketHeader|None] = [None] * NUM_FRAGMENTS # Reset packets
            

    def process_and_push_image(self):
        image = cv2.imdecode(self.rawFullDataBuffer, cv2.IMREAD_UNCHANGED)
        if image is None:
            print(f"{Fore.YELLOW}[WARN] Frame drop. Corrupted JPEG.{Fore.RESET}")
            return
        
        self.camera_status = CameraState.CONNECTED

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
