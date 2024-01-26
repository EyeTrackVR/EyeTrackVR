from typing import Optional, Iterable

from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher

from camera_widget import CameraWidget
from config import EyeTrackConfig
from eye import EyeId
from osc.OSCMessage import OSCMessage, OSCMessageType
from osc.VRCFTModuleMessenger import VRCFTModule
from osc.VRChatOSCSender import VRChatOSCSender
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC
import queue
import threading
import time


class OSCManager:
    def __init__(
        self,
        osc_message_in_queue: queue.Queue[OSCMessage],
        osc_message_out_queue: queue.Queue[OSCMessage],
        eyes: Iterable[CameraWidget],
        config: EyeTrackConfig,
    ):
        self.cancellation_event = threading.Event()
        self.eyes = eyes
        self.osc_message_in_queue = osc_message_in_queue
        self.osc_message_out_queue = osc_message_out_queue
        self.config = config
        self.settings = config.settings
        self.osc_sender_thread: Optional[threading.Thread] = None
        self.osc_receiver_thread: Optional[threading.Thread] = None

    def start(self):
        osc_sender = OSCSender(
            self.cancellation_event, self.osc_message_in_queue, self.config
        )
        self.osc_sender_thread = threading.Thread(target=osc_sender.run)
        self.osc_sender_thread.start()

        if self.settings.gui_ROSC:
            osc_receiver = VRChatOSCReceiver(
                self.cancellation_event, self.config, self.eyes
            )
            self.osc_receiver_thread = threading.Thread(target=osc_receiver.run)
            self.osc_receiver_thread.start()

    def shutdown(self):
        self.cancellation_event.set()
        self.osc_sender_thread.join()
        if self.osc_receiver_thread:
            self.osc_receiver_thread.join()


class OSCSender:
    def __init__(
        self,
        cancellation_event: threading.Event,
        msg_queue: queue.Queue[OSCMessage],
        main_config: EyeTrackConfig,
    ):
        self.cancellation_event = cancellation_event
        self.msg_queue = msg_queue
        self.main_config = main_config
        self.config = main_config.settings
        self.vrc_sender = VRChatOSCSender()
        # self.module_sender = ModuleSender()

        # idea is, we will use a single port.
        # if, the user selects in the settings that they want to use the module
        # we swap the port and we gucci
        # if they don't, we just output stuff as we'd normally
        # handlers are only here to handle different payloads pretty much
        self.client = udp_client.SimpleUDPClient(
            self.config.gui_osc_address, int(self.config.gui_osc_port)
        )

        self.message_strategies = {
            OSCMessageType.EYE_INFO: self.output_osc_info_vrc,
            OSCMessageType.VRCFT_MODULE_INFO: self.output_osc_info_module,
        }

    def run(self):
        while not self.cancellation_event.is_set():
            try:
                osc_message = self.msg_queue.get(block=True, timeout=0.1)
                handler = self.message_strategies.get(osc_message.type)
                if not handler:
                    raise Exception(
                        "Encountered message without a handler %s", osc_message.type
                    )

                handler(osc_message)
            except queue.Empty:
                continue

    def output_osc_info_vrc(self, osc_message: OSCMessage):
        self.vrc_sender.output_osc_info(osc_message, self.client, self.config)

    def output_osc_info_module(self, osc_message: OSCMessage):
        pass


class OSCReceiver:
    pass


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
        except Exception:  # noqa
            print(
                f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m"
            )

    def shutdown(self):
        print("\033[94m[INFO] Exiting OSC Receiver\033[0m")
        try:
            self.server.shutdown()
        except Exception:  # noqa
            pass

    def recenter_eyes(self, address, osc_value):
        if osc_value is not bool:
            return  # just incase we get anything other than bool

        if osc_value:
            for eye in self.eyes:
                eye.settings.gui_recenter_eyes = True

    def recalibrate_eyes(self, address, osc_value):
        if osc_value is not bool:
            return  # just incase we get anything other than bool

        if osc_value:
            for eye in self.eyes:
                eye.ransac.ibo.clear_filter()
                eye.ransac.calibration_frame_counter = self.config.calibration_samples
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
        except Exception:  # noqa:
            print(
                f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m"
            )
