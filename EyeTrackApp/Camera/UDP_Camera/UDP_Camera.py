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
from .PacketHeader import PacketHeader # Python imports stupid. missed a single "."

WAIT_TIME = 0.1

IMAGE_BUFFER_SIZE = 1024
NUM_MAX_FRAGMENTS = 12
HEADER_FORMAT = "iiii"

RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"

# I do not like slow slow slow python - BOTAlex

class UDP_Camera(ICameraSource):
    def extraInit(self):
        self.host = "0.0.0.0"
        self.port = 3333
        self.num_loaded = 0
        self.packets = [None] * NUM_MAX_FRAGMENTS
        self.headerSize = struct.calcsize(HEADER_FORMAT)
        self.rawDataBuffer = np.zeros(IMAGE_BUFFER_SIZE + self.headerSize, dtype=np.uint8)
        self.rawFullDataBuffer = np.zeros(IMAGE_BUFFER_SIZE*NUM_MAX_FRAGMENTS, dtype=np.uint8)
        self.imageBuffView = memoryview(self.rawFullDataBuffer)
        self.currentFrameNum = 0
        self.totalDataSize = 0

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
        payload_start = self.headerSize
        payload_end = self.headerSize + packet.image_buf_size
        payload = dataView[payload_start:payload_end]
        
        #time.sleep(0.05)

        offset = IMAGE_BUFFER_SIZE * packet.id  # Adjust offset based on payload size
        self.imageBuffView[offset: offset + packet.image_buf_size] = payload
        # print(f"Packet {packet.id}: {offset}->{offset + packet.image_buf_size}")

    def resetImageBuffer(self):
        self.rawFullDataBuffer = np.zeros(IMAGE_BUFFER_SIZE*NUM_MAX_FRAGMENTS, dtype=np.uint8)
                
    def handle_packet(self, dataSize, senderAddr):
        bufferView = memoryview(self.rawDataBuffer)
        packet = PacketHeader(HEADER_FORMAT, bufferView, dataSize)
        if packet.id < 0 or packet.id >= NUM_MAX_FRAGMENTS:
            return
        
        # Send acknowledgment
        # self.sock.sendto(f"{packet.id}:{packet.frame_num}:ACK".encode(), senderAddr)
        # print(packet.id)

        # if self.num_loaded > 0 and packet.id != 0:
        #     self.sock.sendto(f"ERR".encode(), senderAddr)

        if (packet.id == 0 or packet.frame_num != self.currentFrameNum):
            self.packets: list[PacketHeader|None] = [None] * NUM_MAX_FRAGMENTS # Reset packets
            self.num_loaded = 0
            self.currentFrameNum = packet.frame_num
            self.rawFullDataBuffer[:] = 0
            # print(f"Reset frame capture. total packets: {packet.totalPackets}")

        # if self.packets[0] is not None:
        #     print(f"Got packet id: {packet.id} (total: {self.packets[0].totalPackets} loaded: {self.num_loaded})")
            
        if (self.packets is not None
            and self.currentFrameNum == packet.frame_num
            and self.packets[0] is not None
            and not packet in self.packets
            or packet.id == 0):
            self.num_loaded += 1
            self.packets[packet.id] = packet
            self.saveDataToBuff(bufferView, packet)

        if (packet.id < len(self.packets) and self.packets[0] is not None and self.num_loaded >= self.packets[0].totalPackets 
            or self.num_loaded >= NUM_MAX_FRAGMENTS):
            # if self.packets[0] is not None:
            #     formatted_list = "[" + ", ".join(f"{RED}x{RESET}" if item is None else f"{GREEN}x{RESET}" for item in self.packets[:self.packets[0].totalPackets]) + "]"
            #     print(formatted_list)

            self.process_and_push_image()

            self.num_loaded = 0
            self.packets: list[PacketHeader|None] = [None] * NUM_MAX_FRAGMENTS # Reset packets
            self.rawFullDataBuffer[:] = 0
            

    def process_and_push_image(self):
        image = cv2.imdecode(self.rawFullDataBuffer, cv2.IMREAD_UNCHANGED)
        if image is None:
            print(f"{Fore.YELLOW}[WARN] Frame drop. Corrupted JPEG.{Fore.RESET}")
            return
        
        # print("Frame")
        
        self.camera_status = CameraState.CONNECTED

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
        self.fps = sum(self.fl) / len(self.fl)

        # Compute bandwidth per second (bps)
        self.bps = image.nbytes * self.fps

        # Increment frame count
        self.frame_number += 1

        # Push the frame to queue
        self.push_image_to_queue(image, self.frame_number, self.fps)

