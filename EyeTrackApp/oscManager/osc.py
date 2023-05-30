from pythonosc import osc_server
from pythonosc import dispatcher

from eye import EyeInfo
from oscManager.osc_output_handler import OSCOutputHandler

from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC
import queue
import threading

import time
from config import EyeTrackConfig


class VRChatOSC:
    # Use a tuple of blink (true, blinking, false, not), x, y for now.
    def __init__(
        self,
        cancellation_event: threading.Event,
        message_queue: queue.Queue[tuple[int, EyeInfo]],
        main_config: EyeTrackConfig,
    ):
        self.output_handler = OSCOutputHandler(main_config)
        self.cancellation_event = cancellation_event
        self.message_queue = message_queue
        # self.eye_id = EyeId.RIGHT  # I dunno if we need that

    def run(self):
        while True:
            if self.cancellation_event.is_set():
                print("\033[94m[INFO] Exiting OSC Queue\033[0m")
                return
            try:
                eye_id, eye_info = self.message_queue.get(block=True, timeout=0.1)
            except:
                continue
            self.output_handler.handle_out(eye_info, eye_id=eye_id)


class VRChatOSCReceiver:
    def __init__(
        self, cancellation_event: threading.Event, main_config: EyeTrackConfig, eyes: []
    ):
        self.config = main_config.settings
        self.cancellation_event = cancellation_event
        self.dispatcher = dispatcher.Dispatcher()
        self.eyes = eyes  # we cant import CameraWidget so any type it is
        try:
            self.server = osc_server.OSCUDPServer(
                (self.config.gui_osc_address, int(self.config.gui_osc_receiver_port)),
                self.dispatcher,
            )
        except:
            print(
                f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m"
            )

    def shutdown(self):
        print("\033[94m[INFO] Exiting OSC Receiver\033[0m")
        try:
            self.server.shutdown()
        except:
            pass

    def recenter_eyes(self, address, osc_value):
        if type(osc_value) != bool:
            return  # just incase we get anything other than bool
        if osc_value:
            for eye in self.eyes:
                eye.settings.gui_recenter_eyes = True

    def recalibrate_eyes(self, address, osc_value):
        if type(osc_value) != bool:
            return  # just incase we get anything other than bool
        if osc_value:
            for eye in self.eyes:
                eye.ransac.calibration_frame_counter = 300
                PlaySound("Audio/start.wav", SND_FILENAME | SND_ASYNC)

    def run(self):

        # bind what function to run when specified OSC message is received
        try:
            self.dispatcher.map(
                self.config.gui_osc_recalibrate_address, self.recalibrate_eyes
            )
            self.dispatcher.map(
                self.config.gui_osc_recenter_address, self.recenter_eyes
            )
            # start the server
            print(
                "\033[92m[INFO] VRChatOSCReceiver serving on {}\033[0m".format(
                    self.server.server_address
                )
            )
            self.server.serve_forever()
        except:
            print(
                f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m"
            )
