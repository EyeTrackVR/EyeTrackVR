from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher
from winsound import PlaySound, SND_FILENAME, SND_ASYNC
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
                if self.config.tracker_single_eye == 1 or self.config.tracker_single_eye == 2:
                    self.client.send_message("/avatar/parameters/LeftEyeX", eye_info.x)  # only one eye is detected or there is an error. Send mirrored data to both eyes.
                    self.client.send_message("/avatar/parameters/RightEyeX", eye_info.x)
                    self.client.send_message("/avatar/parameters/EyesY", eye_info.y)
                    self.client.send_message("/avatar/parameters/RightEyeLid", float(0))# old param open right
                    self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0.8)) # open r
                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(0))# old param open left
                    self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0.8)) # open left eye
                if self.config.gui_blink_sync and not rb and not lb:
                    self.client.send_message("/avatar/parameters/RightEyeLid", float(0))# old param open right
                    self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0.8)) # open r
                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(0))# old param open left
                    self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0.8)) # open left eye

                else:
                    if eye_id in [EyeId.RIGHT]:
                        yr = eye_info.y
                        sx = eye_info.x
                        sy = eye_info.y
                        rb = False
                        self.client.send_message("/avatar/parameters/RightEyeX", eye_info.x)
                        if not self.config.gui_blink_sync or self.config.gui_blink_sync and not lb:   
                            self.client.send_message("/avatar/parameters/RightEyeLid", float(0))# old param open right
                            self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0.8)) # open right eye

                    if eye_id in [EyeId.LEFT]:
                        yl = eye_info.y
                        sx = eye_info.x
                        sy = eye_info.y
                        lb = False
                        self.client.send_message("/avatar/parameters/LeftEyeX", eye_info.x)
                        if not self.config.gui_blink_sync or self.config.gui_blink_sync and not rb:
                            self.client.send_message("/avatar/parameters/LeftEyeLid", float(0))# old param open left
                            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0.8)) # open left eye

                    if (yr != 621 and yl != 621) and (lb == False and rb == False):
                        y = (yr + yl) / 2
                        self.client.send_message("/avatar/parameters/EyesY", y)
            else:
                print(last_blink)
                if self.config.gui_blink_sync:
                    if eye_id in [EyeId.LEFT]:
                        lb = True
                    if eye_id in [EyeId.RIGHT]:
                        rb = True
                    if rb == True and lb == True : # If both eyes are closed, blink
                        if last_blink > 0.5:
                            for i in range(4):
                                self.client.send_message("/avatar/parameters/RightEyeLid", float(1)) #close eye
                                self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                                self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0)) # close eye
                                self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0))
                        last_blink = time.time() - last_blink
                else:
                    
                    if self.config.tracker_single_eye == 1 or self.config.tracker_single_eye == 2:
                        if last_blink > 0.5:
                            for i in range(4):
                                self.client.send_message("/avatar/parameters/RightEyeLid", float(1)) #close eye
                                self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                                self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0)) # close eye
                                self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0))
                        last_blink = time.time() - last_blink

                    if not self.config.gui_eye_falloff:
                        
                        if eye_id in [EyeId.LEFT]:
                            lb = True
                            if last_blink > 0.7:
                                for i in range(5):
                                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                                    self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0))
                            last_blink = time.time() - last_blink


                        if eye_id in [EyeId.RIGHT]:
                            rb = True
                            if last_blink > 0.7:
                                for i in range(5):
                                    self.client.send_message("/avatar/parameters/RightEyeLid", float(1))
                                    self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0)) # close eye
                            last_blink = time.time() - last_blink

                    else:
                        if eye_id in [EyeId.LEFT]:
                            lb = True
                        if eye_id in [EyeId.RIGHT]:
                            rb = True
                        if rb or lb: # If one eye closed and fall off is enabled, mirror data
                            self.client.send_message("/avatar/parameters/LeftEyeX", sx)  #Send mirrored data to both eyes.
                            self.client.send_message("/avatar/parameters/RightEyeX", sx)
                            self.client.send_message("/avatar/parameters/EyesY", sy)
                            self.client.send_message("/avatar/parameters/RightEyeLid", float(0))# old param open right
                            self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0.8)) # open r
                            self.client.send_message("/avatar/parameters/LeftEyeLid", float(0))# old param open left
                            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0.8)) # open left eye
                        if rb and lb: # If both eyes are closed, blink
                            if last_blink > 0.5:
                                for i in range(4):
                                    self.client.send_message("/avatar/parameters/RightEyeLid", float(1)) #close eye
                                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                                    self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(0)) # close eye
                                    self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(0))
                            last_blink = time.time() - last_blink


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
