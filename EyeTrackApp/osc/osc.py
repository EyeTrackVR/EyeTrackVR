

from eye import EyeInfo
from osc.osc_output import OSCOutputHandler

import queue
import threading

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
