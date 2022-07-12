from pythonosc import udp_client
import queue
import threading


class VRChatOSC:
    # VRChat OSC Networking Info. For now, we'll assume it's always local.
    OSC_IP = "127.0.0.1"
    OSC_PORT = 9000  # VR Chat OSC port

    # Use a tuple of blink (true, blinking, false, not), x, y for now. Probably clearer as a class but
    # we're stuck in python 3.6 so still no dataclasses. God I hate python.
    def __init__(self, cancellation_event: "threading.Event", msg_queue: "queue.Queue[tuple[bool, int, int]]"):
        self.client = udp_client.SimpleUDPClient(VRChatOSC.OSC_IP, VRChatOSC.OSC_PORT)
        self.cancellation_event = cancellation_event
        self.msg_queue = msg_queue

    def run(self):
        # Set blinking status to true when we start, just so we make sure we get to an eyelid open state
        # no matter what.
        was_blinking = True
        while True:
            if self.cancellation_event.is_set():
                print("Exiting OSC Queue")
                return
            try:
                eye_info = self.msg_queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            # If we're not blinking, set position
            if not eye_info.blink:
                self.client.send_message("/avatar/parameters/RightEyeX", eye_info.x)
                self.client.send_message("/avatar/parameters/LeftEyeX", eye_info.x)
                self.client.send_message("/avatar/parameters/EyesY", eye_info.y)
                if was_blinking:
                    self.client.send_message("/avatar/parameters/LeftEyeLid", float(0))
                    self.client.send_message("/avatar/parameters/RightEyeLid", float(0))
                    was_blinking = False
            else:
                self.client.send_message("/avatar/parameters/LeftEyeLid", float(1))
                self.client.send_message("/avatar/parameters/RightEyeLid", float(1))
                was_blinking = True
