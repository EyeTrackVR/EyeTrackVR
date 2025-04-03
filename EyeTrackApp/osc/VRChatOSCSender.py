from pythonosc.udp_client import SimpleUDPClient

from eye import EyeId
from osc.OSCMessage import OSCMessage

from config import EyeTrackConfig, EyeTrackSettingsConfig
from enum import IntEnum
import time


def _eyelid_transformer(config, eye_blink):
    if config.osc_invert_eye_close:
        return float(1 - eye_blink)
    else:
        return float(eye_blink)


class OutputType(IntEnum):
    V1_PARAMS = 1
    V2_PARAMS = 2
    NATIVE_PARAMS = 3


class VRChatOSCSender:
    def __init__(self):
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
        self.left_last_blink = time.time()
        self.right_last_blink = time.time()
        self.r_dilation = 0
        self.l_dilation = 0

    def output_osc_info(
        self,
        osc_message: OSCMessage,
        client: SimpleUDPClient,
        main_config: EyeTrackConfig,
        config: EyeTrackSettingsConfig,
    ):
        eye_id, eye_info = osc_message.data
        self.is_single_eye = self.get_is_single_eye(main_config.eye_display_id)


        output_method = None

        if config.gui_vrc_native:
            output_method = self.output_native
        if config.gui_osc_vrcft_v1:
            output_method = self.output_v1_params
        if config.gui_osc_vrcft_v2:
            output_method = self.output_v2_params

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
            )

    @staticmethod
    def get_is_single_eye(eye_display_id):
        return eye_display_id in [EyeId.RIGHT, EyeId.LEFT, 0, 1]

    def update_eye_state(self, eye_id, eye_x, eye_y, eye_blink, avg_velocity, pupil_dilation):
        if eye_id == EyeId.LEFT:
            self.l_eye_x = eye_x
            self.l_eye_blink = eye_blink
            self.left_y = eye_y
            self.l_eye_velocity = avg_velocity
            self.l_dilation = pupil_dilation

        if eye_id == EyeId.RIGHT:
            self.r_eye_x = eye_x
            self.r_eye_blink = eye_blink
            self.right_y = eye_y
            self.r_eye_velocity = avg_velocity
            self.r_dilation = pupil_dilation

    def output_native(self, main_config, config, client, eye_x, eye_y, eye_blink, avg_velocity, eye_id, pupil_dilation):
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
        )

        if self.is_single_eye:
            self.output_osc_native_blink(
                **default_eye_blink_params,
            )
            client.send_message(
                "/tracking/eye/LeftRightVec",
                [float(eye_x), float(eye_y), 1.0, float(eye_x), float(eye_y), 1.0],
            )

        if eye_id in [EyeId.LEFT, EyeId.RIGHT, EyeId.BOTH] and not self.is_single_eye:
            self.output_osc_native_blink(**default_eye_blink_params, single_eye_mode=False)

        if not self.is_single_eye:
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
        )

        if self.is_single_eye:
            client.send_message(config.osc_left_eye_x_address, eye_x)
            client.send_message(config.osc_right_eye_x_address, eye_x)
            client.send_message(config.osc_eyes_y_address, eye_y)
            client.send_message(config.osc_eyes_pupil_dilation_address, pupil_dilation)
            self.output_vrcft_blink_data(**default_eye_blink_params)

        if eye_id in [EyeId.LEFT, EyeId.RIGHT] and not self.is_single_eye:
            self.output_vrcft_blink_data(**default_eye_blink_params, single_eye_mode=False)

            if eye_id == EyeId.LEFT:
                client.send_message(config.osc_left_eye_x_address, self.l_eye_x)
                self.left_y = eye_y
                self.l_dilation = pupil_dilation
                client.send_message(
                    config.osc_left_eye_close_address,
                    _eyelid_transformer(config, self.l_eye_blink),
                )

            if eye_id == EyeId.RIGHT:
                client.send_message(config.osc_right_eye_x_address, self.r_eye_x)
                self.right_y = eye_y
                self.r_dilation = pupil_dilation
                client.send_message(
                    config.osc_right_eye_close_address,
                    _eyelid_transformer(config, self.r_eye_blink),
                )

        if main_config.eye_display_id == EyeId.BOTH and self.right_y != 621 and self.left_y != 621:
            y = (self.right_y + self.left_y) / 2
            client.send_message(config.osc_eyes_y_address, y)

            avg_dilation = (self.r_dilation + self.l_dilation) / 2  # i am unsure of this tbh.
            client.send_message(config.osc_eyes_pupil_dilation_address, avg_dilation)  # single param for both eyes.


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
        )

        if self.is_single_eye:
            client.send_message("/avatar/parameters/v2/EyeX", eye_x)
            client.send_message("/avatar/parameters/v2/EyeY", eye_y)
            client.send_message("/avatar/parameters/v2/PupilDilation", pupil_dilation)


            self.output_vrcft_blink_data(
                **default_eye_blink_params,
                left_eye_blink_address="/avatar/parameters/v2/EyeLid",
                right_eye_blink_address="/avatar/parameters/v2/EyeLid",
            )

        if eye_id in [EyeId.LEFT, EyeId.RIGHT] and not self.is_single_eye:
            self.output_vrcft_blink_data(
                **default_eye_blink_params,
                left_eye_blink_address="/avatar/parameters/v2/EyeLidLeft",
                right_eye_blink_address="/avatar/parameters/v2/EyeLidRight",
                single_eye_mode=False,
            )

            if eye_id == EyeId.LEFT:
                self.l_dilation = pupil_dilation
                client.send_message("/avatar/parameters/v2/EyeLeftX", self.l_eye_x)
                if self.left_y != 621:
                    client.send_message("/avatar/parameters/v2/EyeLeftY", eye_y)

                client.send_message(
                    "/avatar/parameters/v2/EyeLidLeft",
                    _eyelid_transformer(config, self.l_eye_blink),
                )

            if eye_id == EyeId.RIGHT:
                self.r_dilation = pupil_dilation
                client.send_message("/avatar/parameters/v2/EyeRightX", self.r_eye_x)
                if eye_y != 621:
                    client.send_message("/avatar/parameters/v2/EyeRightY", eye_y)

                client.send_message(
                    "/avatar/parameters/v2/EyeLidRight",
                    _eyelid_transformer(config, self.r_eye_blink),
                )

            avg_pupil_dilation = (self.l_dilation + self.r_dilation) / 2
            client.send_message("/avatar/parameters/v2/PupilDilation", avg_pupil_dilation)



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

        side_name = "left" if eye_id == EyeId.RIGHT else "right"
        last_side_blink = getattr(self, f"{side_name}_last_blink")

        if single_eye_mode:
            # in case of v1 params, we have to send the same data do each eye separately.
            # so in case of v2 params, we will be generating one unnecessary call more
            client.send_message(left_eye_blink_address, _eyelid_transformer(config, active_eye_blink))
            client.send_message(right_eye_blink_address, _eyelid_transformer(config, active_eye_blink))

        elif eye_id in [EyeId.RIGHT, EyeId.LEFT] and not single_eye_mode:
            if active_eye_blink == 0.0:
                if last_side_blink > 0.20:
                    for _ in range(5):
                        client.send_message(blink_address, _eyelid_transformer(config, active_eye_blink))
                    setattr(self, f"{side_name}_last_blink", time.time() - last_side_blink)
                if config.gui_outer_side_falloff:
                    if falloff_blink == 0.0:
                        client.send_message(left_eye_blink_address, _eyelid_transformer(config, self.l_eye_blink))
                        client.send_message(right_eye_blink_address, _eyelid_transformer(config, self.r_eye_blink))
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

        side_name = "left" if eye_id == EyeId.RIGHT else "right"
        last_side_blink = getattr(self, f"{side_name}_last_blink")

        def send_native_binary_blink(address: str, blink_value):
            if last_side_blink > 0.2:
                for _ in range(5):
                    client.send_message(address, float(1 - blink_value))
                setattr(self, f"{side_name}_last_blink", time.time() - last_side_blink)

        if single_eye_mode:
            if active_eye_blink == 0.0:
                send_native_binary_blink(blink_address, active_eye_blink)
            else:
                client.send_message(blink_address, float(1 - active_eye_blink))

        if eye_id in [EyeId.RIGHT, EyeId.LEFT] and not single_eye_mode:
            # in dual eye mode we need to average the blink to prevent flickering.
            # VRC also **currently** doesn't support separate eyelids, so it's fine
            if self.r_eye_blink or self.l_eye_blink:
                averaged_eye_blink = (self.r_eye_blink + self.l_eye_blink) / 2
            else:
                averaged_eye_blink = 0

            client.send_message(
                blink_address,
                _eyelid_transformer(config, 1 - averaged_eye_blink),
            )

            if averaged_eye_blink == 0.0:
                send_native_binary_blink(blink_address, averaged_eye_blink)
                if config.gui_outer_side_falloff:
                    if falloff_blink == 0.0:
                        client.send_message(blink_address, float(1 - averaged_eye_blink))

        if eye_id == EyeId.BOTH and self.r_eye_blink != 621 and self.r_eye_blink != 621:
            if self.r_eye_blink == 0.0 or self.l_eye_blink == 0.0:
                send_native_binary_blink(blink_address, active_eye_blink)
            # this has a nasty habit of permanent-squint FIXME
            averaged_eye_blink = (self.r_eye_blink + self.l_eye_blink) / 2
            client.send_message(blink_address, float(1 - averaged_eye_blink))
