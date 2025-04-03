"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2025 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""


from time import sleep
from typing import Dict, Optional, Iterable, Callable

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
        self.sender_cancellation_event.clear()
        self.osc_sender = OSCSender(self.sender_cancellation_event, self.osc_message_in_queue, self.config)
        self.osc_sender_thread = threading.Thread(target=self.osc_sender.run)
        self.osc_sender_thread.start()

    def setup_receiver(self):
        if self.settings.gui_ROSC:
            self.receiver_cancellation_event.clear()
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
            "gui_VRCFTModulePort",
            "gui_VRCFTModuleIPAddress",
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

        self.vrc_client = None
        self.vrcft_client = None

    def run(self):
        self.vrc_client = udp_client.SimpleUDPClient(self.config.gui_osc_address, int(self.config.gui_osc_port))
        self.vrcft_client = udp_client.SimpleUDPClient(
            self.config.gui_VRCFTModuleIPAddress,
            int(self.config.gui_VRCFTModulePort),
        )

        vrc_osc_output_client = self.vrc_client
        if self.config.gui_use_module:
            vrc_osc_output_client = self.vrcft_client

        while not self.cancellation_event.is_set():
            try:
                osc_message: OSCMessage = self.msg_queue.get(block=True, timeout=0.1)
                match osc_message.type:
                    case OSCMessageType.EYE_INFO:
                        self.vrc_sender.output_osc_info(
                            osc_message=osc_message,
                            client=vrc_osc_output_client,
                            main_config=self.main_config,
                            config=self.config,
                        )
                    case OSCMessageType.VRCFT_MODULE_INFO:
                        self.module_sender.send(osc_message=osc_message, client=self.vrcft_client)
                    case _:
                        raise Exception("Encountered message without a handler %s", osc_message.type)
            except TypeError:
                continue
            except queue.Empty:
                continue


class OSCReceiver:
    def __init__(
        self,
        cancellation_event: threading.Event,
        main_config: EyeTrackConfig,
        listeners: Dict[str, Callable[[OSCMessage], None]],
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
        for listener in self.listeners.get(address, []):
            listener(OSCMessage(type=OSCMessageType.EYE_INFO, data=value))

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
