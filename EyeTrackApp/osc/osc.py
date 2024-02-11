from typing import Optional, Iterable, Callable

from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher

from config import EyeTrackConfig
from osc.OSCMessage import OSCMessage, OSCMessageType
from osc.VRCFTModuleMessenger import VRCFTModuleSender
from osc.VRChatOSCSender import VRChatOSCSender
import queue
import threading


# TODO
# make gui


class OSCManager:
    def __init__(
        self,
        osc_message_in_queue: queue.Queue[OSCMessage],
        config: EyeTrackConfig,
    ):
        self.cancellation_event = threading.Event()
        self.listeners = {}
        self.osc_message_in_queue = osc_message_in_queue
        self.config = config
        self.settings = config.settings
        self.osc_sender: OSCSender = None
        self.osc_receiver = None
        self.osc_sender_thread: Optional[threading.Thread] = None
        self.osc_receiver_thread: Optional[threading.Thread] = None

    def start(self):
        self.osc_sender = OSCSender(self.cancellation_event, self.osc_message_in_queue, self.config)
        self.osc_sender_thread = threading.Thread(target=self.osc_sender.run)
        self.osc_sender_thread.start()

        if self.settings.gui_ROSC:
            self.osc_receiver = OSCReceiver(self.cancellation_event, self.config, self.listeners)
            self.osc_receiver_thread = threading.Thread(target=self.osc_receiver.run)
            self.osc_receiver_thread.start()

    def register_listeners(self, osc_address: str, callbacks: Iterable[Callable]):
        if not self.listeners.get(osc_address):
            self.listeners[osc_address] = []

        self.listeners[osc_address].extend(callbacks)

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
        self.module_sender = VRCFTModuleSender()

        # idea is, we will use a single port.
        # if, the user selects in the settings that they want to use the module
        # we swap the port, and we're good
        # if they don't, we just output stuff as we'd normally
        # handlers are only here to handle different payloads pretty much
        self.client = udp_client.SimpleUDPClient(self.config.gui_osc_address, int(self.config.gui_osc_port))

    def run(self):
        while not self.cancellation_event.is_set():
            try:
                osc_message: OSCMessage = self.msg_queue.get(block=True, timeout=0.1)
                match osc_message.type:
                    case OSCMessageType.EYE_INFO:
                        self.vrc_sender.output_osc_info(
                            osc_message=osc_message,
                            client=self.client,
                            main_config=self.main_config,
                            config=self.config,
                        )
                    case OSCMessageType.VRCFT_MODULE_INFO:
                        self.module_sender.send(osc_message=osc_message, client=self.client)
                    case _:
                        raise Exception("Encountered message without a handler %s", osc_message.type)
            except queue.Empty:
                continue


class OSCReceiver:
    def __init__(
        self,
        cancellation_event: threading.Event,
        main_config: EyeTrackConfig,
        listeners,
    ):
        self.config = main_config.settings
        self.cancellation_event = cancellation_event
        self.dispatcher = dispatcher.Dispatcher()
        self.listeners = listeners
        try:
            self.server = osc_server.OSCUDPServer(
                (self.config.gui_osc_address, int(self.config.gui_osc_receiver_port)),
                self.dispatcher,
            )
        except Exception:  # noqa
            print(f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m")

    def shutdown(self):
        print("\033[94m[INFO] Exiting OSC Receiver\033[0m")
        try:
            self.server.shutdown()
        except Exception:  # noqa
            pass

    def handle_osc_message(self, address, value):
        for listener in self.listeners.get(address):
            listener(value)

    def run(self):
        try:
            self.dispatcher.set_default_handler(self.handle_osc_message)
            print("\033[92m[INFO] OSC Listening on {}\033[0m".format(self.server.server_address))
            self.server.serve_forever()
        except Exception:  # noqa:
            print(f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m")
