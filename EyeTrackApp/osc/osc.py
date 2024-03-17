from time import sleep
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


class OSCManager:
    def __init__(
        self,
        osc_message_in_queue: queue.Queue[OSCMessage],
        config: EyeTrackConfig,
    ):
        self.sender_cancellation_event = threading.Event()
        self.receiver_cancellation_event = threading.Event()
        self.listeners = {}
        self.osc_message_in_queue = osc_message_in_queue
        self.config = config
        self.settings = config.settings
        self.osc_sender: Optional[OSCSender] = None
        self.osc_receiver = None
        self.osc_sender_thread: Optional[threading.Thread] = None
        self.osc_receiver_thread: Optional[threading.Thread] = None

    def start(self):
        self.setup_sender()
        self.setup_receiver()

    def setup_sender(self):
        print(f"\033[92m[INFO] Setting up OSC sender\033[0m")
        self.osc_sender = OSCSender(self.sender_cancellation_event, self.osc_message_in_queue, self.config)
        self.osc_sender_thread = threading.Thread(target=self.osc_sender.run)
        self.osc_sender_thread.start()

    def setup_receiver(self):
        if self.settings.gui_ROSC:
            print(f"\033[92m[INFO] Setting up OSC receiver\033[0m")
            self.osc_receiver = OSCReceiver(self.receiver_cancellation_event, self.config, self.listeners)
            self.osc_receiver_thread = threading.Thread(target=self.osc_receiver.run)
            self.osc_receiver_thread.start()

    def register_listeners(self, osc_address: str, callbacks: Iterable[Callable]):
        if not self.listeners.get(osc_address):
            self.listeners[osc_address] = []

        self.listeners[osc_address].extend(callbacks)

    def update(self, data: dict):
        keys = set(data.keys())
        sender_trigger_keys = {
            "gui_osc_port",
            "gui_PortNumber",
            "gui_use_module",
        }
        if sender_trigger_keys.intersection(keys):
            self.stop_sender()
            self.setup_sender()

        receiver_trigger_keys = {
            "gui_ROSC",
            "gui_osc_receiver_port",
        }
        if receiver_trigger_keys.intersection(keys):
            self.stop_receiver()
            self.setup_receiver()

    def shutdown(self):
        self.stop_sender()
        self.stop_receiver()

    def stop_sender(self):
        self.sender_cancellation_event.set()
        self.osc_sender_thread.join()

    def stop_receiver(self):
        if self.osc_receiver_thread:
            self.receiver_cancellation_event.set()
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

        # idea is that we will use a single port.
        # if, the user selects in the settings that they want to use the module
        # we swap the port, and we're good
        # if they don't, we just output stuff as we'd normally
        # handlers are only here to handle different payloads pretty much
        self.client = None

    def run(self):
        osc_port = self.config.gui_osc_port if not self.config.gui_use_module else self.config.gui_PortNumber
        self.client = udp_client.SimpleUDPClient(self.config.gui_osc_address, int(osc_port))

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
        self.server_thread = None
        try:
            # this thing sucks ass god fucking damn it.
            # like, there is no way of shutting it down UNLESS you run it in a thread
            # which is kinda dumb, but oh well.
            # Also, it doesn't shutdown properly. It's STILL connected to the port
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
            self.server_thread.join()
        except Exception:  # noqa
            pass

    def handle_osc_message(self, address, value):
        for listener in self.listeners.get(address):
            listener(value)

    def run(self):
        try:
            self.dispatcher.set_default_handler(self.handle_osc_message)
            print("\033[92m[INFO] OSC Listening on {}\033[0m".format(self.server.server_address))
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.start()

            while not self.cancellation_event.is_set():
                sleep(10)

            self.shutdown()
        except Exception:  # noqa:
            print(f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m")