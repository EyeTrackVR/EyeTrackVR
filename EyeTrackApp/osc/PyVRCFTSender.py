"""
Experimental "pyVRCFT" output mode.

Instead of emitting a handful of hard-coded ``/avatar/parameters/v2/*`` messages
(the VRCFT-v2 mode) or feeding an external VRCFaceTracking module, this sender
embeds the PY-VRCFT port (vendored under ``EyeTrackApp/pyvrcft``) and talks to
VRChat the same way VRCFaceTracking does: it discovers the active avatar via
OSCQuery/mDNS, resolves which Unified Expressions parameters the avatar actually
declares (and whether each wants float / bool / binary-bit encoding), and streams
send-on-change OSC bundles to VRChat's input port.

This *replaces* VRCFT for eye tracking. Do not run VRCFT alongside it. Because
the port owns its own background send/receive threads, this sender is driven
purely by updating a shared ``UnifiedTrackingData`` frame; the actual OSC output
happens on the port's own timer (~100 Hz), decoupled from tracking framerate.
"""

import logging

from eye import EyeId
from osc.OSCMessage import OSCMessage
from osc.VRChatOSCSender import VRChatOSCSender

from pyvrcft import UnifiedTrackingData, VRCFTClient

logger = logging.getLogger(__name__)


class PyVRCFTSender:
    def __init__(self):
        self.client: VRCFTClient | None = None
        self.data = UnifiedTrackingData()
        # Advertise eye tracking as active so VRCFT-style avatars enable it.
        self.data.eye_tracking_active = True
        self.is_single_eye = False

    def start(self, config):
        """Spin up the embedded VRCFT client's background threads.

        Sends to VRChat's OSC input (gui_osc_address:gui_osc_port) and listens
        on the OSC receiver port for /avatar/change. If that port is already
        bound (e.g. a real VRCFT install), the port silently disables receive
        and falls back to OSCQuery/mDNS avatar discovery.

        When EyeTrackVR's own OSC receiver is enabled (gui_ROSC) it owns the
        receiver port for in-VR recenter/recalibrate, and it is set up *after*
        this sender. We yield that port here with an ephemeral bind and let the
        embedded port rely on OSCQuery for avatar detection instead of fighting
        for it.
        """
        recv_port = int(config.gui_osc_receiver_port)
        if config.gui_ROSC:
            recv_port = 0
        self.client = VRCFTClient(
            send_host=str(config.gui_osc_address),
            send_port=int(config.gui_osc_port),
            recv_port=recv_port,
        )
        # Map normalized calibrated gaze (±1) to true FOV angles on the native
        # /tracking/eye/LeftRightPitchYaw endpoint, so full gaze reflects the
        # real headset/calibration FOV instead of VRCFT's default 45°. Mirrors
        # the overlay finetune FOV caps. Normalized v1/v2 params are unaffected.
        self.data.gaze_yaw_max_deg = float(config.gui_gaze_yaw_max_deg)
        self.data.gaze_pitch_up_deg = float(config.gui_gaze_pitch_up_deg)
        self.data.gaze_pitch_down_deg = float(config.gui_gaze_pitch_down_deg)

        self.client.start()
        logger.info(
            "pyVRCFT sender started -> %s:%s (recv :%s%s)",
            config.gui_osc_address,
            config.gui_osc_port,
            recv_port,
            " [OSCQuery-only, ROSC owns receiver]" if config.gui_ROSC else "",
        )

    def stop(self):
        if self.client is not None:
            self.client.stop()
            self.client = None
            logger.info("pyVRCFT sender stopped")

    @staticmethod
    def _apply_eye(eye, eye_info, openness):
        eye.gaze = (float(eye_info.x), float(eye_info.y))
        eye.openness = float(openness)
        # EyeTrackVR's pupil_dilation is already ~normalized; the port re-runs
        # VRCFT's stateful min/max normalization on top, treating this as a
        # diameter. Good enough for the experimental mode.
        eye.pupil_diameter_mm = float(eye_info.pupil_dilation)

    def output_osc_info(self, osc_message: OSCMessage, main_config, config):
        if self.client is None:
            return
        eye_id, eye_info = osc_message.data
        self.is_single_eye = VRChatOSCSender.get_is_single_eye(
            main_config.eye_display_id
        )

        # eye_info.blink is openness (1 = open, 0 = closed); mirror the eyelid
        # inversion setting the other modes apply via _eyelid_transformer.
        openness = (
            1.0 - eye_info.blink if config.osc_invert_eye_close else eye_info.blink
        )
        squeeze = float(eye_info.squeeze)

        if self.is_single_eye:
            self._apply_eye(self.data.eye.left, eye_info, openness)
            self._apply_eye(self.data.eye.right, eye_info, openness)
            self.data.shapes["EyeSquintLeft"] = squeeze
            self.data.shapes["EyeSquintRight"] = squeeze
            self.data.shapes["CheekSquintLeft"] = squeeze
            self.data.shapes["CheekSquintRight"] = squeeze
        elif eye_id == EyeId.LEFT:
            self._apply_eye(self.data.eye.left, eye_info, openness)
            self.data.shapes["EyeSquintLeft"] = squeeze
            self.data.shapes["CheekSquintLeft"] = squeeze
        elif eye_id == EyeId.RIGHT:
            self._apply_eye(self.data.eye.right, eye_info, openness)
            self.data.shapes["EyeSquintRight"] = squeeze
            self.data.shapes["CheekSquintRight"] = squeeze

        # Recomputes the full v2 parameter set from the shared frame and queues
        # only changed values; the port's send thread puts them on the wire.
        self.client.update_tracking(self.data)

    def output_eyebrow_info(self, eye_id, brow_val: float, main_config):
        if self.client is None:
            return
        is_single = VRChatOSCSender.get_is_single_eye(main_config.eye_display_id)
        brow_val = float(brow_val)
        # The other modes drive v2/BrowExpression directly. Here we set the
        # underlying brow shapes so the pipeline derives the same value:
        # BrowExpression = min(1, innerUp*0.5 + outerUp*0.5) - browDown.
        if is_single or eye_id == EyeId.LEFT:
            self.data.shapes["BrowInnerUpLeft"] = brow_val
            self.data.shapes["BrowOuterUpLeft"] = brow_val
        if is_single or eye_id == EyeId.RIGHT:
            self.data.shapes["BrowInnerUpRight"] = brow_val
            self.data.shapes["BrowOuterUpRight"] = brow_val
        self.client.update_tracking(self.data)
