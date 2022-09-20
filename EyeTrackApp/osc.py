from pythonosc import udp_client
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

class VRChatOSC:

    # Use a tuple of blink (true, blinking, false, not), x, y for now. Probably clearer as a class but
    # we're stuck in python 3.6 so still no dataclasses. God I hate python.
    def __init__(self, cancellation_event: "threading.Event", msg_queue: "queue.Queue[tuple[bool, int, int, int]]", main_config: EyeTrackConfig,):
        
        self.main_config = main_config
        self.config = main_config.settings
        self.client = udp_client.SimpleUDPClient(self.config.gui_osc_address, int(self.config.gui_osc_port)) # use OSC port and address that was set in the config
        self.cancellation_event = cancellation_event
        self.msg_queue = msg_queue
        
    def run(self):
        start = time.time()
        last_blink = 0
        yl = 621
        yr = 621
        sx = 0 
        sy = 0
        se = 0
        lec = 0
        rec = 0
        while True:
            if self.cancellation_event.is_set():
                print("Exiting OSC Queue")
                return
            try:
                (eye_id, eye_info) = self.msg_queue.get(block=True, timeout=0.1)
            except:
                continue


            if not eye_info.blink:
                if eye_id in [EyeId.RIGHT]:
                    sx = eye_info.x
                    yr = eye_info.y
                    sy = eye_info.y
                    rec = 1

                    self.client.send_message("/avatar/parameters/RightEyeX", eye_info.x)   
                    self.client.send_message("/avatar/parameters/RightEyeLid", float(0))# old param open right
                    self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0.8)) # open right eye
       
                   # self.client.send_message(
                   #     "/avatar/parameters/EyesDilation", eye_info.pupil_dialation
                    #)
                if eye_id in [EyeId.LEFT]:
                    sx = eye_info.x
                    yl = eye_info.y
                    sy = eye_info.y
                    lec = 1
                    self.client.send_message("/avatar/parameters/LeftEyeX", eye_info.x)
                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(0))# old param open left
                    self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0.8)) # open left eye

                if yr != 621 and yl != 621:
                    y = (yr + yl) / 2
                    self.client.send_message("/avatar/parameters/EyesY", y)
                    se = 0

                if rec == 0 or lec == 0:
                    se = 1
                    self.client.send_message("/avatar/parameters/LeftEyeX", sx)  # only one eye is detected or there is an error. Send mirrored data to both eyes.
                    self.client.send_message("/avatar/parameters/RightEyeX", sx)
                    self.client.send_message("/avatar/parameters/EyesY", sy)
                    self.client.send_message("/avatar/parameters/RightEyeLid", float(0))# old param open right
                    self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0.8)) # open r
                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(0))# old param open left
                    self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0.8)) # open left eye

                


            else:
                
                if eye_id in [EyeId.LEFT]:
                    if last_blink > 0.5:
                        for i in range(4):
                            self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0))
                    last_blink = time.time()
                if eye_id in [EyeId.RIGHT]:
                    if last_blink > 0.5:
                        for i in range(4):
                            self.client.send_message("/avatar/parameters/RightEyeLid", float(1))
                            self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0)) # close eye
                    last_blink = time.time()
                if se == 1:
                    if last_blink > 0.5:
                        for i in range(4):
                
                            self.client.send_message("/avatar/parameters/RightEyeLid", float(1)) #close eye
                            self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                            self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0)) # close eye
                            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0))
                    last_blink = time.time()

    
