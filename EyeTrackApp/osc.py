
from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher
from utils.misc_utils import PlaySound,SND_FILENAME,SND_ASYNC
import queue
import threading
from enum import IntEnum
import time

class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3
from config import EyeTrackConfig

se = False
def output_osc(eye_x, eye_y, eye_blink, last_blink, self):
        global se
        if self.main_config.eye_display_id in [EyeId.RIGHT, EyeId.LEFT]: #we are in single eye mode
            se = True
        #    self.client.send_message("/tracking/eye/LeftRightPitchYaw", [float(eye_y * 100), float(eye_x * 100), float(eye_y * 100), float(eye_x * 101)]) #vrc native ET test
        #   self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))

            self.client.send_message("/avatar/parameters/LeftEyeX", eye_x)
            self.client.send_message("/avatar/parameters/RightEyeX", eye_x)
            self.client.send_message("/avatar/parameters/EyesY", eye_y)

            self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(eye_blink))
            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(eye_blink))

        if self.eye_id in [EyeId.LEFT] and not se: #left eye, send data to left
            self.l_eye_x = eye_x
            self.l_eye_blink = eye_blink

            if self.l_eye_blink == 0.0:
                if last_blink > 0.7: #when bianary blink is on, blinks may be too fast for OSC so we repeate them.
                    for i in range(5):
                        self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(self.l_eye_blink))
                    last_blink = time.time() - last_blink
                if self.config.gui_eye_falloff:
                    if self.r_eye_blink == 0.0: #if both eyes closed and DEF is enables, blink
                        self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(self.l_eye_blink)) 
                        self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(self.l_eye_blink)) 
                self.l_eye_x = self.r_eye_x

            self.client.send_message("/avatar/parameters/LeftEyeX", self.l_eye_x) 
            self.left_y = eye_y

            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(self.l_eye_blink)) 


        elif self.eye_id in [EyeId.RIGHT] and not se: #Right eye, send data to right
            self.r_eye_x = eye_x
            self.r_eye_blink = eye_blink

            if self.r_eye_blink == 0.0:
                if last_blink > 0.7: #when bianary blink is on, blinks may be too fast for OSC so we repeate them.
                    for i in range(5):
                        self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(self.r_eye_blink))
                    last_blink = time.time() - last_blink
                if self.config.gui_eye_falloff:
                    if self.l_eye_blink == 0.0: #if both eyes closed and DEF is enables, blink
                        self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(self.r_eye_blink)) 
                        self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(self.r_eye_blink)) 
                    
                self.r_eye_x = self.l_eye_x

            self.client.send_message("/avatar/parameters/RightEyeX", eye_x) 
            self.right_y = eye_y

            self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(self.r_eye_blink)) 

        if self.main_config.eye_display_id in [EyeId.BOTH] and self.right_y != 621 and self.left_y != 621:
            y = (self.right_y + self.left_y) / 2
            self.client.send_message("/avatar/parameters/EyesY", y)


class VRChatOSC:
    # Use a tuple of blink (true, blinking, false, not), x, y for now. 
    def __init__(self, cancellation_event: threading.Event, msg_queue: queue.Queue[tuple[bool, int, int]], main_config: EyeTrackConfig,):
        self.main_config = main_config
        self.config = main_config.settings
        self.client = udp_client.SimpleUDPClient(self.config.gui_osc_address, int(self.config.gui_osc_port)) # use OSC port and address that was set in the config
        self.cancellation_event = cancellation_event
        self.msg_queue = msg_queue
        self.eye_id = EyeId.RIGHT
        self.left_y = 621
        self.right_y = 621
        self.r_eye_x = 0
        self.l_eye_x = 0
        self.r_eye_blink = 0.7
        self.l_eye_blink = 0.7


    def run(self):
        start = time.time()
        last_blink = time.time()
        while True:
            if self.cancellation_event.is_set():
                print("\033[94m[INFO] Exiting OSC Queue\033[0m")
                return
            try:
                (self.eye_id, eye_info) = self.msg_queue.get(block=True, timeout=0.1)
            except:
                continue

            output_osc(eye_info.x, eye_info.y, eye_info.blink, last_blink, self)


class VRChatOSCReceiver:
    def __init__(self, cancellation_event: threading.Event, main_config: EyeTrackConfig, eyes: []):
        self.config = main_config.settings
        self.cancellation_event = cancellation_event
        self.dispatcher = dispatcher.Dispatcher()
        self.eyes = eyes  # we cant import CameraWidget so any type it is
        try:
            self.server = osc_server.OSCUDPServer((self.config.gui_osc_address, int(self.config.gui_osc_receiver_port)), self.dispatcher)
        except:
            print(f"\033[91m[ERROR] OSC Recieve port: {self.config.gui_osc_receiver_port} occupied.\033[0m")

    def shutdown(self):
        print("\033[94m[INFO] Exiting OSC receiver\033[0m")
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
            print("\033[92m[INFO] VRChatOSCReceiver serving on {}\033[0m".format(self.server.server_address))
            self.server.serve_forever()
            
        except:
            print(f"\033[91m[ERROR] OSC Recieve port: {self.config.gui_osc_receiver_port} occupied.\033[0m")