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

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import logging
import math
import time
from typing import Any, Dict, Optional, Iterable, Callable

import numpy as np
from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher

from config import EyeTrackConfig
from osc.OSCMessage import OSCMessage, OSCMessageType
from osc.VRCFTModuleMessenger import VRCFTModuleSender
from osc.VRChatOSCSender import VRChatOSCSender
from osc.PyVRCFTSender import PyVRCFTSender
import queue
import threading

logger = logging.getLogger(__name__)

# How often a repeating OSC failure (bad value, sendto error, ...) may be logged.
# The sender runs at tracking rate, so an unthrottled log would flood the file.
_LOG_INTERVAL_S = 5.0

# Sentinel: the message carries a NaN/inf and must not reach the wire.
_DROP = object()


class _ThrottledLog:
    """Log a repeating failure at most once per interval per key, and report
    how many identical events were suppressed in between."""

    def __init__(self, interval: float = _LOG_INTERVAL_S):
        self.interval = interval
        self._state: dict[str, tuple[float, int]] = {}

    def log(self, level: int, key: str, msg: str, *args, exc_info=False) -> None:
        now = time.monotonic()
        last, suppressed = self._state.get(key, (None, 0))
        if last is not None and now - last < self.interval:
            self._state[key] = (last, suppressed + 1)
            return
        if suppressed:
            msg += " (%d similar suppressed)"
            args = (*args, suppressed)
        logger.log(level, msg, *args, exc_info=exc_info)
        self._state[key] = (now, 0)


def _to_osc_arg(value: Any):
    """One OSC argument as a plain Python type python-osc can encode.

    numpy scalars (np.float32, np.int64, np.bool_) are rejected by python-osc's
    type inference with a ValueError, so unwrap them. Non-finite floats yield
    _DROP: a NaN/inf param can wedge avatar animators, and holding the last good
    value on the avatar is less disruptive than snapping to a neutral pose.
    """
    if isinstance(value, np.generic) or (
        isinstance(value, np.ndarray) and value.ndim == 0
    ):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return _DROP
    return value


def sanitize_osc_value(value: Any):
    """Sanitize a send_message() value (scalar or sequence); _DROP if unsendable."""
    if isinstance(value, np.ndarray) and value.ndim > 0:
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        out = [_to_osc_arg(v) for v in value]
        if any(v is _DROP for v in out):
            return _DROP
        return out if isinstance(value, list) else tuple(out)
    return _to_osc_arg(value)


def validate_osc_endpoint(label: str, address: Any, port: Any) -> tuple[str, int] | None:
    """Return (host, port) if usable, else log why and return None."""
    host = str(address).strip() if address is not None else ""
    if not host:
        logger.error("%s OSC output disabled: address is empty", label)
        return None
    try:
        port_int = int(port)
    except (TypeError, ValueError, OverflowError):
        port_int = None
    if port_int is None or not 1 <= port_int <= 65535:
        logger.error(
            "%s OSC output disabled: port %r is not in the range 1-65535", label, port
        )
        return None
    return host, port_int


def _sig_port(value):
    """Port for change-detection signatures; never raises on bad input
    (an invalid port must still restart the sender so it can log it)."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)


class SafeOSCClient:
    """Send boundary around a SimpleUDPClient: sanitizes arguments and turns
    per-message failures into throttled log lines instead of exceptions, so
    one bad value or a transient sendto error never stops the OSC sender.

    ``client`` may be None (invalid endpoint); sends are then no-ops.
    """

    def __init__(self, client, label: str, log: _ThrottledLog):
        self.client = client
        self.label = label
        self._log = log

    def send_message(self, address: str, value) -> None:
        if self.client is None:
            return
        clean = sanitize_osc_value(value)
        if clean is _DROP:
            self._log.log(
                logging.WARNING,
                f"nonfinite:{self.label}",
                "Dropped %s OSC message %s with non-finite value %r",
                self.label,
                address,
                value,
            )
            return
        try:
            self.client.send_message(address, clean)
        except Exception as exc:  # noqa: one failed send must not kill the thread
            self._log.log(
                logging.WARNING,
                f"send:{self.label}",
                "%s OSC send of %s failed: %s",
                self.label,
                address,
                exc,
            )


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
        self._last_sender_sig: tuple | None = None
        self._last_receiver_sig: tuple | None = None

    def start(self):
        self.setup_sender()
        self.setup_receiver()

    def _sender_signature(self) -> tuple:
        s = self.settings
        return (
            _sig_port(s.gui_osc_port),
            str(s.gui_VRCFTModuleIPAddress).strip(),
            _sig_port(s.gui_VRCFTModulePort),
            bool(s.gui_use_module),
            bool(s.gui_pyvrcft),
            str(s.gui_osc_address).strip(),
            _sig_port(s.gui_osc_receiver_port),
            # pyVRCFT binds the receiver port only while ROSC is off, so toggling
            # ROSC must restart the sender to release / reclaim that port.
            bool(s.gui_ROSC),
        )

    def _receiver_signature(self) -> tuple:
        s = self.settings
        return (
            bool(s.gui_ROSC),
            _sig_port(s.gui_osc_receiver_port),
            str(s.gui_osc_address).strip(),
        )

    def setup_sender(self):
        logger.info("Setting up OSC sender")
        self.sender_cancellation_event.clear()
        self.osc_sender = OSCSender(
            self.sender_cancellation_event, self.osc_message_in_queue, self.config
        )
        self.osc_sender_thread = threading.Thread(target=self.osc_sender.run)
        self.osc_sender_thread.start()
        self._last_sender_sig = self._sender_signature()

    def setup_receiver(self):
        if self.settings.gui_ROSC:
            self.receiver_cancellation_event.clear()
            logger.info("Setting up OSC receiver")
            self.osc_receiver = OSCReceiver(
                self.receiver_cancellation_event, self.config, self.listeners
            )
            self.osc_receiver_thread = threading.Thread(target=self.osc_receiver.run)
            self.osc_receiver_thread.start()
        else:
            self.osc_receiver = None
            self.osc_receiver_thread = None
        self._last_receiver_sig = self._receiver_signature()

    def register_listeners(self, osc_address: str, callbacks: Iterable[Callable]):
        if not self.listeners.get(osc_address):
            self.listeners[osc_address] = []

        self.listeners[osc_address].extend(callbacks)

    SENDER_TRIGGER_KEYS = frozenset(
        {
            "gui_osc_port",
            "gui_VRCFTModulePort",
            "gui_VRCFTModuleIPAddress",
            "gui_use_module",
            "gui_pyvrcft",
            "gui_osc_address",
            "gui_osc_receiver_port",
            "gui_ROSC",
        }
    )
    RECEIVER_TRIGGER_KEYS = frozenset(
        {
            "gui_ROSC",
            "gui_osc_receiver_port",
            "gui_osc_address",
        }
    )

    def update(self, data: dict):
        keys = set(data.keys())
        restart_sender = bool(
            self.SENDER_TRIGGER_KEYS.intersection(keys)
            and self._sender_signature() != self._last_sender_sig
        )
        restart_receiver = bool(
            self.RECEIVER_TRIGGER_KEYS.intersection(keys)
            and self._receiver_signature() != self._last_receiver_sig
        )
        # Release ports before anything rebinds them: the old receiver must let
        # go of the receiver port before a pyVRCFT sender (ROSC off) claims it,
        # and the old sender before a new receiver (ROSC on) binds it.
        if restart_receiver:
            self.stop_receiver()
        if restart_sender:
            self.stop_sender()
            self.setup_sender()
        if restart_receiver:
            self.setup_receiver()

    def shutdown(self):
        self.stop_sender()
        self.stop_receiver()

    def stop_sender(self):
        self.sender_cancellation_event.set()
        if self.osc_sender_thread is not None:
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
        self.pyvrcft_sender = PyVRCFTSender()

        self.vrc_client = None
        self.vrcft_client = None
        self._log = _ThrottledLog()

    @staticmethod
    def _make_client(label: str, address, port):
        """Create a SimpleUDPClient, or log clearly and return None.

        SimpleUDPClient resolves the host up front, so an unresolvable name
        (socket.gaierror) or bad port (OverflowError) surfaces here.
        """
        endpoint = validate_osc_endpoint(label, address, port)
        if endpoint is None:
            return None
        try:
            return udp_client.SimpleUDPClient(*endpoint)
        except Exception as exc:  # noqa
            logger.error(
                "%s OSC output disabled: cannot send to %s:%s (%s)",
                label,
                endpoint[0],
                endpoint[1],
                exc,
            )
            return None

    def run(self):
        self.vrc_client = self._make_client(
            "VRChat", self.config.gui_osc_address, self.config.gui_osc_port
        )
        self.vrcft_client = self._make_client(
            "VRCFT module",
            self.config.gui_VRCFTModuleIPAddress,
            self.config.gui_VRCFTModulePort,
        )
        # Senders only ever see the sanitizing wrappers; the raw clients stay
        # on self for inspection.
        safe_vrc = SafeOSCClient(self.vrc_client, "VRChat", self._log)
        safe_vrcft = SafeOSCClient(self.vrcft_client, "VRCFT module", self._log)

        vrc_osc_output_client = safe_vrc
        if self.config.gui_use_module:
            vrc_osc_output_client = safe_vrcft

        # Experimental: route through the embedded PY-VRCFT port instead of the
        # SimpleUDPClient param paths. It owns its own transport, so the vrc/
        # vrcft clients above are simply left idle when this is active.
        use_pyvrcft = bool(self.config.gui_pyvrcft)
        if use_pyvrcft and self.vrc_client is None:
            # Same host/port as the VRChat client, which already logged why.
            logger.error("pyVRCFT sender not started: VRChat OSC endpoint is invalid")
            use_pyvrcft = False
        elif use_pyvrcft:
            try:
                self.pyvrcft_sender.start(self.config)
            except Exception:  # noqa
                logger.exception(
                    "Failed to start pyVRCFT sender; no eye OSC output this run"
                )
                use_pyvrcft = False

        try:
            while not self.cancellation_event.is_set():
                try:
                    osc_message: OSCMessage = self.msg_queue.get(block=True, timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    match osc_message.type:
                        case OSCMessageType.EYE_INFO:
                            if use_pyvrcft:
                                self.pyvrcft_sender.output_osc_info(
                                    osc_message=osc_message,
                                    main_config=self.main_config,
                                    config=self.config,
                                )
                            else:
                                self.vrc_sender.output_osc_info(
                                    osc_message=osc_message,
                                    client=vrc_osc_output_client,
                                    main_config=self.main_config,
                                    config=self.config,
                                )
                        case OSCMessageType.VRCFT_MODULE_INFO:
                            self.module_sender.send(
                                osc_message=osc_message, client=safe_vrcft
                            )
                        case OSCMessageType.EYEBROW_INFO:
                            eye_id, brow_val = osc_message.data
                            if use_pyvrcft:
                                self.pyvrcft_sender.output_eyebrow_info(
                                    eye_id=eye_id,
                                    brow_val=brow_val,
                                    main_config=self.main_config,
                                )
                            else:
                                self.vrc_sender.output_eyebrow_info(
                                    eye_id=eye_id,
                                    brow_val=brow_val,
                                    client=vrc_osc_output_client,
                                    main_config=self.main_config,
                                )
                        case _:
                            logger.warning("Encountered OSC message without a handler: %s", osc_message.type)
                except TypeError:
                    # Historically swallowed silently (e.g. data not yet populated).
                    self._log.log(
                        logging.DEBUG,
                        "typeerror",
                        "Skipped malformed OSC message",
                        exc_info=True,
                    )
                except Exception:  # noqa: one bad message must never stop OSC output
                    self._log.log(
                        logging.ERROR,
                        f"handler:{getattr(osc_message, 'type', None)}",
                        "Failed to send OSC message %s",
                        getattr(osc_message, "type", None),
                        exc_info=True,
                    )
                finally:
                    # Lets callers (tests) wait on msg_queue.join() for delivery.
                    self.msg_queue.task_done()
        finally:
            if use_pyvrcft:
                self.pyvrcft_sender.stop()


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
        self.server = None
        try:
            # OSCUDPServer needs a dedicated serve_forever thread so shutdown can be
            # requested from the manager thread.
            self.server = osc_server.OSCUDPServer(
                (self.config.gui_osc_address, int(self.config.gui_osc_receiver_port)),
                self.dispatcher,
            )
        except Exception as exc:  # noqa
            logger.error(
                "Failed to start OSC receiver on %s:%s: %s",
                self.config.gui_osc_address,
                self.config.gui_osc_receiver_port,
                exc,
            )

    def shutdown(self):
        logger.info("Exiting OSC receiver")
        try:
            if self.server is not None:
                self.server.shutdown()
                # shutdown() only stops serve_forever; close the socket so the
                # port is free for a restarted pyVRCFT sender right away.
                self.server.server_close()
            if self.server_thread is not None:
                self.server_thread.join()
        except Exception:  # noqa
            pass

    def handle_osc_message(self, address, value):
        for listener in self.listeners.get(address, []):
            listener(OSCMessage(type=OSCMessageType.EYE_INFO, data=value))

    def run(self):
        if self.server is None:
            return

        try:
            self.dispatcher.set_default_handler(self.handle_osc_message)
            logger.info("OSC listening on %s", self.server.server_address)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.start()

            while not self.cancellation_event.is_set():
                self.cancellation_event.wait(10)

            self.shutdown()
        except Exception as exc:  # noqa:
            logger.error("OSC receiver stopped unexpectedly: %s", exc)
