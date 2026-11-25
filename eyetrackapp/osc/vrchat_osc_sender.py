from pythonosc.udp_client import SimpleUDPClient

from eye import EyeId
from osc.osc_message import OSCMessage

from config import EyeTrackConfig, EyeTrackSettingsConfig
from enum import IntEnum
import math
import time

# A closed eye is resent as a 5x burst (lost UDP packets must not leave the
# avatar's eyes open), at most once per this many seconds per eye.
BLINK_BURST_INTERVAL_S = 0.2


def _eyelid_transformer(config, eye_blink):
    if config.osc_invert_eye_close:
        return float(1 - eye_blink)
    else:
        return float(eye_blink)


def brow_expression(brow_val) -> float | None:
    """Tracker brow (0..1, 0.5 = neutral) -> VRCFT BrowExpression (-1..+1, 0 = neutral).

    The brow source (NEXT) is 0 = fully
    lowered, 0.5 = rest, 1 = fully raised. Sent raw, a resting face read as a
    half raise and a full lower only reached the avatar's neutral.

    None for NaN/inf: callers skip the frame so the avatar holds its last brow.
    The clamp would otherwise turn NaN into 1.0 (a full raise), which no
    downstream non-finite filter can catch.
    """
    brow_val = float(brow_val)
    if not math.isfinite(brow_val):
        return None
    return max(-1.0, min(1.0, 2.0 * brow_val - 1.0))


class OutputType(IntEnum):
    V1_PARAMS = 1
    V2_PARAMS = 2
    NATIVE_PARAMS = 3


class VRChatOSCSender:
    def __init__(self):
        self._osc_output_sig = None
        self._cached_output_method = None
        self.is_single_eye = False
        self.falloff_enabled = False
        self.left_y = 621
        self.right_y = 621
        self.r_eye_x = 0
        self.l_eye_x = 0
        self.r_eye_blink = 0.7
        self.l_eye_blink = 0.7
        self.l_eye_velocity = 0
        self.r_eye_velocity = 1
        # time.monotonic() of the last closed-eye burst, per eye slot.
        self.left_last_blink = float("-inf")
        self.right_last_blink = float("-inf")
        self.r_dilation = 0
        self.l_dilation = 0
        self.r_squeeze = 0.0
        self.l_squeeze = 0.0
        self.l_brow = 0.0
        self.r_brow = 0.0

    def output_osc_info(
        self,
        osc_message: OSCMessage,
        client: SimpleUDPClient,
        main_config: EyeTrackConfig,
        config: EyeTrackSettingsConfig,
    ):
        eye_id, eye_info = osc_message.data
        self.is_single_eye = self.get_is_single_eye(main_config.eye_display_id)

        sig = (
            bool(config.gui_vrc_native),
            bool(config.gui_osc_vrcft_v1),
            bool(config.gui_osc_vrcft_v2),
        )
        if sig != self._osc_output_sig:
            self._osc_output_sig = sig
            output_method = None
            if config.gui_vrc_native:
                output_method = self.output_native
            if config.gui_osc_vrcft_v1:
                output_method = self.output_v1_params
            if config.gui_osc_vrcft_v2:
                output_method = self.output_v2_params
            self._cached_output_method = output_method
        output_method = self._cached_output_method

        if output_method:
            output_method(
                main_config=main_config,
                config=config,
                client=client,
                eye_x=eye_info.x,
                eye_y=eye_info.y,
                eye_blink=eye_info.blink,
                avg_velocity=eye_info.avg_velocity,
                eye_id=eye_id,
                pupil_dilation=eye_info.pupil_dilation,
                eye_squeeze=eye_info.squeeze,
            )

    @staticmethod
    def get_is_single_eye(eye_display_id):
        return eye_display_id in [EyeId.RIGHT, EyeId.LEFT, 0, 1]

    def _mirror_eye(self, eye_id) -> bool:
        """True when this eye's values go to both eyes: single-eye mode, or two
        cameras are configured but the other one has not delivered a frame yet
        (unplugged, wrong address). 621 is "no data yet"."""
        if self.is_single_eye:
            return True
        if eye_id == EyeId.LEFT:
            return self.left_y != 621 and self.right_y == 621
        if eye_id == EyeId.RIGHT:
            return self.right_y != 621 and self.left_y == 621
        return False

    def _blink_burst_due(self, side_name: str) -> bool:
        """True (and the burst is recorded) when this eye's last burst is older than the interval."""
        now = time.monotonic()
        attr = f"{side_name}_last_blink"
        if now - getattr(self, attr) <= BLINK_BURST_INTERVAL_S:
            return False
        setattr(self, attr, now)
        return True

    def update_eye_state(self, eye_id, eye_x, eye_y, eye_blink, avg_velocity, pupil_dilation, eye_squeeze=0.0):
        if eye_id == EyeId.LEFT:
            self.l_eye_x = eye_x
            self.l_eye_blink = eye_blink
            self.left_y = eye_y
            self.l_eye_velocity = avg_velocity
            self.l_dilation = pupil_dilation
            self.l_squeeze = eye_squeeze

        if eye_id == EyeId.RIGHT:
            self.r_eye_x = eye_x
            self.r_eye_blink = eye_blink
            self.right_y = eye_y
            self.r_eye_velocity = avg_velocity
            self.r_dilation = pupil_dilation
            self.r_squeeze = eye_squeeze

    def output_native(
        self,
        main_config,
        config,
        client,
        eye_x,
        eye_y,
        eye_blink,
        avg_velocity,
        eye_id,
        pupil_dilation,
        eye_squeeze=0.0,
    ):
        default_eye_blink_params = {
            "eye_id": eye_id,
            "client": client,
            "config": config,
        }

        self.update_eye_state(
            eye_id=eye_id,
            eye_x=eye_x,
            eye_y=eye_y,
            eye_blink=eye_blink,
            avg_velocity=avg_velocity,
            pupil_dilation=pupil_dilation,
            eye_squeeze=eye_squeeze,
        )

        mirror = self._mirror_eye(eye_id)
        if mirror:
            self.output_osc_native_blink(
                **default_eye_blink_params,
            )
            client.send_message(
                "/tracking/eye/LeftRightVec",
                [float(eye_x), float(eye_y), 1.0, float(eye_x), float(eye_y), 1.0],
            )

        if eye_id in [EyeId.LEFT, EyeId.RIGHT, EyeId.BOTH] and not mirror:
            self.output_osc_native_blink(**default_eye_blink_params, single_eye_mode=False)

        # 621 is "no data yet" and would point that eye straight up. One silent
        # eye is covered by the mirror above.
        if not mirror and self.left_y != 621 and self.right_y != 621:
            # vrc native ET (z values may need tweaking, they act like a scalar)
            client.send_message(
                "/tracking/eye/LeftRightVec",
                [
                    float(self.l_eye_x),
                    float(self.left_y),
                    1.0,
                    float(self.r_eye_x),
                    float(self.right_y),
                    1.0,
                ],
            )

    def output_v1_params(
        self,
        main_config,
        config,
        client,
        eye_x,
        eye_y,
        eye_blink,
        avg_velocity,
        eye_id,
        pupil_dilation,
        eye_squeeze=0.0,
    ):
        default_eye_blink_params = {
            "eye_id": eye_id,
            "client": client,
            "config": config,
            "left_eye_blink_address": config.osc_left_eye_close_address,
            "right_eye_blink_address": config.osc_right_eye_close_address,
        }

        self.update_eye_state(
            eye_id=eye_id,
            eye_x=eye_x,
            eye_y=eye_y,
            eye_blink=eye_blink,
            avg_velocity=avg_velocity,
            pupil_dilation=pupil_dilation,
            eye_squeeze=eye_squeeze,
        )

        mirror = self._mirror_eye(eye_id)
        if mirror:
            client.send_message(config.osc_left_eye_x_address, eye_x)
            client.send_message(config.osc_right_eye_x_address, eye_x)
            client.send_message(config.osc_eyes_y_address, eye_y)
            client.send_message(config.osc_eyes_pupil_dilation_address, pupil_dilation)
            self.output_vrcft_blink_data(**default_eye_blink_params)

        if eye_id in [EyeId.LEFT, EyeId.RIGHT] and not mirror:
            self.output_vrcft_blink_data(**default_eye_blink_params, single_eye_mode=False)

            # The eyelid itself went out with output_vrcft_blink_data above.
            if eye_id == EyeId.LEFT:
                client.send_message(config.osc_left_eye_x_address, self.l_eye_x)
                self.left_y = eye_y
                self.l_dilation = pupil_dilation

            if eye_id == EyeId.RIGHT:
                client.send_message(config.osc_right_eye_x_address, self.r_eye_x)
                self.right_y = eye_y
                self.r_dilation = pupil_dilation

        if main_config.eye_display_id == EyeId.BOTH and self.right_y != 621 and self.left_y != 621:
            y = (self.right_y + self.left_y) / 2
            client.send_message(config.osc_eyes_y_address, y)

            # V1 exposes one pupil dilation parameter, so dual-eye mode sends the average.
            avg_dilation = (self.r_dilation + self.l_dilation) / 2
            client.send_message(config.osc_eyes_pupil_dilation_address, avg_dilation)

    def output_v2_params(
        self,
        main_config,
        config,
        client,
        eye_x,
        eye_y,
        eye_blink,
        avg_velocity,
        eye_id,
        pupil_dilation,
        eye_squeeze=0.0,
    ):
        default_eye_blink_params = {
            "eye_id": eye_id,
            "client": client,
            "config": config,
        }

        self.update_eye_state(
            eye_id=eye_id,
            eye_x=eye_x,
            eye_y=eye_y,
            eye_blink=eye_blink,
            avg_velocity=avg_velocity,
            pupil_dilation=pupil_dilation,
            eye_squeeze=eye_squeeze,
        )

        mirror = self._mirror_eye(eye_id)
        if mirror:
            client.send_message("/avatar/parameters/v2/EyeX", eye_x)
            client.send_message("/avatar/parameters/v2/EyeY", eye_y)
            client.send_message("/avatar/parameters/v2/PupilDilation", pupil_dilation)
            client.send_message("/avatar/parameters/v2/CheekSquintLeft", eye_squeeze)
            client.send_message("/avatar/parameters/v2/CheekSquintRight", eye_squeeze)
            client.send_message("/avatar/parameters/v2/EyeSquintLeft", eye_squeeze)
            client.send_message("/avatar/parameters/v2/EyeSquintRight", eye_squeeze)
            client.send_message("/avatar/parameters/v2/EyeSquint", eye_squeeze)

            self.output_vrcft_blink_data(
                **default_eye_blink_params,
                left_eye_blink_address="/avatar/parameters/v2/EyeLid",
                right_eye_blink_address="/avatar/parameters/v2/EyeLid",
            )
            if not self.is_single_eye:
                # Two cameras configured, one silent: also fill the per-eye
                # parameters a two-eye avatar reads.
                for side in ("Left", "Right"):
                    client.send_message(f"/avatar/parameters/v2/Eye{side}X", eye_x)
                    client.send_message(f"/avatar/parameters/v2/Eye{side}Y", eye_y)
                self.output_vrcft_blink_data(
                    **default_eye_blink_params,
                    left_eye_blink_address="/avatar/parameters/v2/EyeLidLeft",
                    right_eye_blink_address="/avatar/parameters/v2/EyeLidRight",
                )

        if eye_id in [EyeId.LEFT, EyeId.RIGHT] and not mirror:
            self.output_vrcft_blink_data(
                **default_eye_blink_params,
                left_eye_blink_address="/avatar/parameters/v2/EyeLidLeft",
                right_eye_blink_address="/avatar/parameters/v2/EyeLidRight",
                single_eye_mode=False,
            )

            # The eyelid itself went out with output_vrcft_blink_data above.
            if eye_id == EyeId.LEFT:
                self.l_dilation = pupil_dilation
                client.send_message("/avatar/parameters/v2/EyeLeftX", self.l_eye_x)
                if self.left_y != 621:
                    client.send_message("/avatar/parameters/v2/EyeLeftY", eye_y)
                client.send_message("/avatar/parameters/v2/CheekSquintLeft", self.l_squeeze)
                client.send_message("/avatar/parameters/v2/EyeSquintLeft", self.l_squeeze)

            if eye_id == EyeId.RIGHT:
                self.r_dilation = pupil_dilation
                client.send_message("/avatar/parameters/v2/EyeRightX", self.r_eye_x)
                if eye_y != 621:
                    client.send_message("/avatar/parameters/v2/EyeRightY", eye_y)
                client.send_message("/avatar/parameters/v2/CheekSquintRight", self.r_squeeze)
                client.send_message("/avatar/parameters/v2/EyeSquintRight", self.r_squeeze)

            avg_pupil_dilation = (self.l_dilation + self.r_dilation) / 2
            client.send_message("/avatar/parameters/v2/PupilDilation", avg_pupil_dilation)
            avg_squeeze = (self.l_squeeze + self.r_squeeze) / 2
            client.send_message("/avatar/parameters/v2/EyeSquint", avg_squeeze)

    def output_vrcft_blink_data(
        self,
        eye_id: EyeId,
        client: SimpleUDPClient,
        config,
        left_eye_blink_address,
        right_eye_blink_address,
        single_eye_mode=True,
    ):
        active_eye_blink = self.r_eye_blink if eye_id == EyeId.RIGHT else self.l_eye_blink
        falloff_blink = self.r_eye_blink if eye_id == EyeId.LEFT else self.l_eye_blink
        blink_address = right_eye_blink_address if eye_id == EyeId.RIGHT else left_eye_blink_address

        # Only a per-eye key for the burst timer; which slot each eye uses does not matter.
        side_name = "left" if eye_id == EyeId.RIGHT else "right"

        if single_eye_mode:
            # in case of v1 params, we have to send the same data do each eye separately.
            # so in case of v2 params, we will be generating one unnecessary call more
            client.send_message(left_eye_blink_address, _eyelid_transformer(config, active_eye_blink))
            client.send_message(right_eye_blink_address, _eyelid_transformer(config, active_eye_blink))

        elif eye_id in [EyeId.RIGHT, EyeId.LEFT] and not single_eye_mode:
            if active_eye_blink == 0.0:
                if self._blink_burst_due(side_name):
                    for _ in range(5):
                        client.send_message(blink_address, _eyelid_transformer(config, active_eye_blink))
                if config.gui_outer_side_falloff:
                    if falloff_blink == 0.0:
                        client.send_message(
                            left_eye_blink_address,
                            _eyelid_transformer(config, self.l_eye_blink),
                        )
                        client.send_message(
                            right_eye_blink_address,
                            _eyelid_transformer(config, self.r_eye_blink),
                        )
            client.send_message(blink_address, _eyelid_transformer(config, active_eye_blink))

    def output_osc_native_blink(
        self,
        eye_id: EyeId,
        client,
        config,
        single_eye_mode=True,
    ):
        blink_address = "/tracking/eye/EyesClosedAmount"
        active_eye_blink = self.r_eye_blink if eye_id == EyeId.RIGHT else self.l_eye_blink
        falloff_blink = self.r_eye_blink if eye_id == EyeId.LEFT else self.l_eye_blink

        # Only a per-eye key for the burst timer; which slot each eye uses does not matter.
        side_name = "left" if eye_id == EyeId.RIGHT else "right"

        def send_native_binary_blink(address: str, blink_value) -> bool:
            if not self._blink_burst_due(side_name):
                return False
            for _ in range(5):
                client.send_message(address, float(1 - blink_value))
            return True

        if single_eye_mode:
            # Between bursts a closed eye still goes out once per frame.
            if active_eye_blink != 0.0 or not send_native_binary_blink(blink_address, active_eye_blink):
                client.send_message(blink_address, float(1 - active_eye_blink))

        if eye_id in [EyeId.RIGHT, EyeId.LEFT] and not single_eye_mode:
            # in dual eye mode we need to average the blink to prevent flickering.
            # VRC also **currently** doesn't support separate eyelids, so it's fine
            if self.r_eye_blink or self.l_eye_blink:
                averaged_eye_blink = (self.r_eye_blink + self.l_eye_blink) / 2
            else:
                averaged_eye_blink = 0

            # EyesClosedAmount has a fixed meaning in VRChat (1 = closed), so the
            # avatar-param invert setting does not apply. Inverting only this
            # send made a held blink alternate with the raw burst below.
            client.send_message(blink_address, float(1 - averaged_eye_blink))

            if averaged_eye_blink == 0.0:
                send_native_binary_blink(blink_address, averaged_eye_blink)
                if config.gui_outer_side_falloff:
                    if falloff_blink == 0.0:
                        client.send_message(blink_address, float(1 - averaged_eye_blink))

        if eye_id == EyeId.BOTH and self.r_eye_blink != 621 and self.l_eye_blink != 621:
            if self.r_eye_blink == 0.0 or self.l_eye_blink == 0.0:
                send_native_binary_blink(blink_address, active_eye_blink)
            # FIXME: This path can stick in a squint state after a full blink.
            averaged_eye_blink = (self.r_eye_blink + self.l_eye_blink) / 2
            client.send_message(blink_address, float(1 - averaged_eye_blink))

    def output_eyebrow_info(self, eye_id, brow_val: float, client, main_config):
        self.is_single_eye = self.get_is_single_eye(main_config.eye_display_id)
        expr = brow_expression(brow_val)
        if expr is None:
            return  # NaN/inf: hold the last sent brow

        if eye_id == EyeId.LEFT:
            self.l_brow = float(brow_val)
        elif eye_id == EyeId.RIGHT:
            self.r_brow = float(brow_val)
        brow_val = expr

        if self.is_single_eye:
            client.send_message("/avatar/parameters/v2/BrowExpression", brow_val)
        elif self._mirror_eye(eye_id):
            client.send_message("/avatar/parameters/v2/BrowExpressionLeft", brow_val)
            client.send_message("/avatar/parameters/v2/BrowExpressionRight", brow_val)
        elif eye_id == EyeId.LEFT:
            client.send_message("/avatar/parameters/v2/BrowExpressionLeft", brow_val)
        elif eye_id == EyeId.RIGHT:
            client.send_message("/avatar/parameters/v2/BrowExpressionRight", brow_val)
