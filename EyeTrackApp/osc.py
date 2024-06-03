from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher
from winsound import PlaySound, SND_FILENAME, SND_ASYNC
import queue
import threading
from enum import IntEnum
import time
import csv

class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3
from config import EyeTrackConfig

start_time_millis = int(round(time.time() * 1000))

def log_eye_data(eye_id, x, y, eyelid_expanded_squeeze):
    print('LOG')
    # Calculate the elapsed time since start_time_millis
    time_elapsed_millis = int(round(time.time() * 1000)) - start_time_millis
    with open('eye_data.csv', mode='a', newline='') as file:
        writer = csv.writer(file)
        # Include the elapsed time in milliseconds in the row
        writer.writerow([time_elapsed_millis, eye_id, x, y, eyelid_expanded_squeeze])

class VRChatOSC:
    # Use a tuple of blink (true, blinking, false, not), x, y for now. Probably clearer as a class but
    # we're stuck in python 3.6 so still no dataclasses. God I hate python.
    def __init__(self, cancellation_event: threading.Event, msg_queue: queue.Queue[tuple[bool, int, int]], main_config: EyeTrackConfig,):
        self.main_config = main_config
        self.config = main_config.settings
        self.client = udp_client.SimpleUDPClient(self.config.gui_osc_address, int(self.config.gui_osc_port)) # use OSC port and address that was set in the config
        self.cancellation_event = cancellation_event
        self.msg_queue = msg_queue
        
    def run(self):
        start = time.time()
        last_blink = time.time()
        yl = 621
        yr = 621
        sx = 0 
        sy = 0
        se = 0
        lec = 0
        rec = 0
        rb = False
        lb = False
        while True:
            if self.cancellation_event.is_set():
                print("Exiting OSC Queue")
                return
            try:
                (eye_id, eye_info) = self.msg_queue.get(block=True, timeout=0.1)
            except:
                continue

            if not eye_info.blink:
                    print(eye_info.x)
                    self.client.send_message("/avatar/parameters/LeftEyeX", float(eye_info.x))
                    self.client.send_message("/avatar/parameters/RightEyeX", float(eye_info.x))
                    self.client.send_message("/avatar/parameters/EyesY", float(eye_info.y))
                    log_eye_data(eye_id, eye_info.x, eye_info.y, 1.0)


class VRChatOSCReceiver:
    def __init__(self, cancellation_event: threading.Event, main_config: EyeTrackConfig, eyes: []):
        self.config = main_config.settings
        self.cancellation_event = cancellation_event
        self.dispatcher = dispatcher.Dispatcher()
        self.eyes = eyes  # we cant import CameraWidget so any type it is
        try:
            self.server = osc_server.OSCUDPServer((self.config.gui_osc_address, int(self.config.gui_osc_receiver_port)), self.dispatcher)
        except:
            print(f"[ERROR] OSC Recieve port: {self.config.gui_osc_receiver_port} occupied. ")

    def shutdown(self):
        print("Shutting down OSC receiver")
        try:
            self.server.shutdown()
        except:
            pass

    def recenter_eyes(self, address, osc_value):
        if type(osc_value) != bool: return  # just incase we get anything other than bool
        if osc_value:
            for eye in self.eyes:
                eye.settings.gui_recenter_eyes = True

    def recalibrate_eyes(self, address, osc_value):
        if type(osc_value) != bool: return  # just incase we get anything other than bool
        if osc_value:
            for eye in self.eyes:
                eye.ransac.calibration_frame_counter = 300
                PlaySound('Audio/start.wav', SND_FILENAME | SND_ASYNC)

    def run(self):
        
        # bind what function to run when specified OSC message is received
        try:
            self.dispatcher.map(self.config.gui_osc_recalibrate_address, self.recalibrate_eyes)
            self.dispatcher.map(self.config.gui_osc_recenter_address, self.recenter_eyes)
            # start the server
            print("VRChatOSCReceiver serving on {}".format(self.server.server_address))
            self.server.serve_forever()
            
        except:
            print(f"[ERROR] OSC Recieve port: {self.config.gui_osc_receiver_port} occupied. ")
