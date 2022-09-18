from pythonosc import udp_client
import queue
import threading
from enum import IntEnum


class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3


class VRChatOSC:
    # VRChat OSC Networking Info. For now, we'll assume it's always local.
    OSC_IP = "127.0.0.1"
    OSC_PORT = 9000  # VR Chat OSC port

    # Use a tuple of blink (true, blinking, false, not), x, y for now. Probably clearer as a class but
    # we're stuck in python 3.6 so still no dataclasses. God I hate python.
    def __init__(
        self,
        cancellation_event: "threading.Event",
        msg_queue: "queue.Queue[tuple[bool, int, int, int]]",
    ):
        self.client = udp_client.SimpleUDPClient(VRChatOSC.OSC_IP, VRChatOSC.OSC_PORT)
        self.cancellation_event = cancellation_event
        self.msg_queue = msg_queue

    def run(self):
    
        yl = 621
        yr = 621
        sx = 0 
        sy = 0
        se = 0
        lec = 1
        rec = 1
        while True:
            if self.cancellation_event.is_set():
                print("Exiting OSC Queue")
                return
            try:
                (eye_id, eye_info) = self.msg_queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue


            if not eye_info.blink:

                if eye_id in [EyeId.RIGHT, EyeId.BOTH]:
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
                if eye_id in [EyeId.LEFT, EyeId.BOTH]:
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

                if rec == 1 and lec == 1:
                    se = 1
                    self.client.send_message("/avatar/parameters/LeftEyeX", sx)  # only one eye is detected or there is an error. Send mirrored data to both eyes.
                    self.client.send_message("/avatar/parameters/RightEyeX", sx)
                    self.client.send_message("/avatar/parameters/EyesY", sy)
                


            else:
                
                if eye_id in [EyeId.LEFT, EyeId.BOTH]:
                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                    self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0))

                if eye_id in [EyeId.RIGHT, EyeId.BOTH]:
                    self.client.send_message("/avatar/parameters/RightEyeLid", float(1))
                    self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0)) # close eye

                if se == 1:
                    self.client.send_message("/avatar/parameters/RightEyeLid", float(1)) #close eye
                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                    self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0)) # close eye
                    self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0))


    
