from typing import List

from camera_widget import CameraWidget
from config import EyeTrackConfig
from pythonosc import dispatcher
from pythonosc import osc_server

import threading

from utils.eye_utils import trigger_recenter, trigger_recalibration


class VRChatOSCReceiver:
    def __init__(
        self, cancellation_event: threading.Event, main_config: EyeTrackConfig, eyes: List[CameraWidget]
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
        if type(osc_value) is bool and osc_value:
            trigger_recenter(self.eyes)

    def recalibrate_eyes(self, address, osc_value):
        if type(osc_value) is bool and osc_value:
            trigger_recalibration(self.eyes)

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
