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
from Camera.SerialCamera import SerialCamera
from Camera.SystemCamera import SystemCamera
from Camera.ICameraSource import ICameraSource
from Camera.UDP_Camera.UDP_Camera import UDP_Camera

# Sorry for the (non-OOP) Python devs. Factory time!
class CameraFactory:
    @staticmethod
    def get_camera_from_string_type(sourceName: str) -> ICameraSource:
        sourceName = str(sourceName) # prevents int to be entered
        if sourceName.lower().startswith("com") or sourceName.lower().startswith("/dev/cu") or sourceName.lower().startswith("/dev/tty"):  # Windows  # macOS  # Linux
            print(f"{Fore.CYAN}[INFO] Serial camera selected {Fore.RESET}")
            return SerialCamera
        elif sourceName.lower() == "udp":
            print(f"{Fore.YELLOW}[WARN] UDP selected. Prepare for bugs from BOTAlex. Unfinished and extreme alpha. {Fore.RESET}")
            return UDP_Camera
        else:
            print(f"{Fore.CYAN}[INFO] System camera selected {Fore.RESET}")
            return SystemCamera