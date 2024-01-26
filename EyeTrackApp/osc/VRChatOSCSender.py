from pythonosc.udp_client import SimpleUDPClient

from config import EyeTrackConfig, EyeTrackSettingsConfig
from eye import EyeId
from osc.OSCMessage import OSCMessage, OSCMessageType

import time


class VRChatOSCSender:
    # Use a tuple of blink (true, blinking, false, not), x, y for now.
    def __init__(self):
        self.eye_id = EyeId.RIGHT
        self.left_y = 621
        self.right_y = 621
        self.r_eye_x = 0
        self.l_eye_x = 0
        self.r_eye_blink = 0.7
        self.l_eye_blink = 0.7
        self.l_eye_velocity = 0
        self.r_eye_velocity = 1
        self.last_blink = time.time()

    def output_osc_info(
        self,
        osc_message: OSCMessage,
        client: SimpleUDPClient,
        main_config: EyeTrackConfig,
        config: EyeTrackSettingsConfig,
    ):
        eye_x = osc_message.data.eye_x
        eye_y = osc_message.data.eye_y
        eye_blink = osc_message.data.eye_blink
        pupil_dilation = osc_message.data.pupil_dilation
        avg_velocity = osc_message.data.avg_velocity

        if config.gui_osc_vrcft_v1:
            return self.output_vrcft1(
                main_config,
                config,
                client,
                eye_x,
                eye_y,
                eye_blink,
                pupil_dilation,
                avg_velocity,
            )

        if config.gui_osc_vrcft_v2:
            return self.output_vrcft2(
                main_config,
                config,
                client,
                eye_x,
                eye_y,
                eye_blink,
                pupil_dilation,
                avg_velocity,
            )

        if config.gui_vrc_native:  # VRC NATIVE
            return self.output_native(
                main_config,
                config,
                client,
                eye_x,
                eye_y,
                eye_blink,
                avg_velocity,
            )

    def eyelid_transformer(self, eye_blink, osc_invert_eye_close):
        if osc_invert_eye_close:
            return float(1 - eye_blink)
        else:
            return float(eye_blink)

    def get_is_single_eye_mode(self, eye_display_id) -> bool:
        return eye_display_id in [
            EyeId.RIGHT,
            EyeId.LEFT,
        ]

    def handle_binary_blink(self, eye_blink, client):
        if eye_blink == 0.0:
            # when binary blink is on, blinks may be too fast for OSC, so we repeat them.
            if self.last_blink > 0.2:
                for _ in range(5):
                    client.send_message(
                        "/tracking/eye/EyesClosedAmount", float(1 - eye_blink)
                    )
                    eye_blink += 0.02  # TODO finish tuning value
                self.last_blink = time.time() - self.last_blink
        else:
            client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))

    def output_native(
        self, main_config, config, client, eye_x, eye_y, eye_blink, avg_velocity
    ):
        single_eye_mode = self.get_is_single_eye_mode(config.eye_display_id)

        if single_eye_mode:
            self.handle_binary_blink(eye_blink, client)
            client.send_message(
                "/tracking/eye/LeftRightVec",
                [float(eye_x), float(eye_y), 1.0, float(eye_x), float(eye_y), 1.0],
            )

        if (
            self.eye_id in [EyeId.LEFT] and not single_eye_mode
        ):  # left eye, send data to left
            self.l_eye_x = eye_x
            self.l_eye_blink = eye_blink
            self.left_y = eye_y
            self.l_eye_velocity = avg_velocity
            client.send_message(
                config.osc_left_eye_close_address,
                self.eyelid_transformer(
                    eye_blink, osc_invert_eye_close=config.osc_invert_eye_close
                ),
            )

            if self.l_eye_blink == 0.0:
                if (
                    self.last_blink > 0.2
                ):  # when binary blink is on, blinks may be too fast for OSC, so we repeat them.
                    for _ in range(5):
                        client.send_message(
                            "/tracking/eye/EyesClosedAmount", float(1 - eye_blink)
                        )
                    self.last_blink = time.time() - self.last_blink
                if config.gui_outer_side_falloff:
                    if (
                        self.r_eye_blink == 0.0
                    ):  # if both eyes closed and DEF is enabled, blink
                        client.send_message(
                            "/tracking/eye/EyesClosedAmount", float(1 - eye_blink)
                        )
                self.l_eye_x = self.r_eye_x

        elif (
            self.eye_id in [EyeId.RIGHT] and not single_eye_mode
        ):  # Right eye, send data to right
            self.r_eye_x = eye_x
            self.r_eye_blink = eye_blink
            self.right_y = eye_y
            self.r_eye_velocity = avg_velocity
            client.send_message(
                config.osc_right_eye_close_address,
                self.eyelid_transformer(
                    eye_blink, osc_invert_eye_close=config.osc_invert_eye_close
                ),
            )

            if self.r_eye_blink == 0.0:
                if (
                    self.last_blink > 0.2
                ):  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for i in range(5):
                        client.send_message(
                            "/tracking/eye/EyesClosedAmount", float(1 - eye_blink)
                        )
                    self.last_blink = time.time() - self.last_blink
                if config.gui_outer_side_falloff:
                    if (
                        self.l_eye_blink == 0.0
                    ):  # if both eyes closed and DEF is enabled, blink
                        client.send_message("/tracking/eye/EyesClosedAmount", float(0))

                self.r_eye_x = self.l_eye_x

        if (
            main_config.eye_display_id in [EyeId.BOTH]
            and self.r_eye_blink != 621
            and self.r_eye_blink != 621
        ):
            if self.r_eye_blink == 0.0 or self.l_eye_blink == 0.0:
                if (
                    self.last_blink > 0.2
                ):  # when binary blink is on, blinks may be too fast for OSC, so we repeat them.
                    for _ in range(5):
                        client.send_message("/tracking/eye/EyesClosedAmount", float(1))
                    self.last_blink = time.time() - self.last_blink
            eye_blink = (self.r_eye_blink + self.l_eye_blink) / 2
            client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))

        # is this used?
        if (
            main_config.eye_display_id in [EyeId.BOTH]
            and self.right_y != 621
            and self.left_y != 621
        ):
            eye_y = (self.right_y + self.left_y) / 2

        if not single_eye_mode:
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

    def output_vrcft1(
        self,
        main_config,
        config,
        client,
        eye_x,
        eye_y,
        eye_blink,
        pupil_dilation,
        avg_velocity,
    ):
        single_eye_mode = self.get_is_single_eye_mode(config.eye_display_id)

        if single_eye_mode:
            client.send_message(config.osc_left_eye_x_address, eye_x)
            client.send_message(config.osc_right_eye_x_address, eye_x)
            client.send_message(config.osc_eyes_y_address, eye_y)

            client.send_message(
                config.osc_right_eye_close_address,
                self.eyelid_transformer(
                    eye_blink,
                    config.osc_invert_eye_close,
                ),
            )
            client.send_message(
                config.osc_left_eye_close_address,
                self.eyelid_transformer(
                    eye_blink,
                    config.osc_invert_eye_close,
                ),
            )

        if (
            self.eye_id in [EyeId.LEFT] and not single_eye_mode
        ):  # left eye, send data to left
            self.l_eye_x = eye_x
            self.l_eye_blink = eye_blink
            self.l_eye_velocity = avg_velocity

            if self.l_eye_blink == 0.0:
                if (
                    self.last_blink > 0.15
                ):  # when binary blink is on, blinks may be too fast for OSC, so we repeat them.
                    for _ in range(4):
                        client.send_message(
                            config.osc_left_eye_close_address,
                            self.eyelid_transformer(
                                self.l_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )
                    self.last_blink = time.time() - self.last_blink

                self.l_eye_x = self.r_eye_x

            client.send_message(config.osc_left_eye_x_address, self.l_eye_x)
            self.left_y = eye_y

            client.send_message(
                config.osc_left_eye_close_address,
                self.eyelid_transformer(
                    self.l_eye_blink,
                    config.osc_invert_eye_close,
                ),
            )

        elif (
            self.eye_id in [EyeId.RIGHT] and not single_eye_mode
        ):  # Right eye, send data to right
            self.r_eye_x = eye_x
            self.r_eye_blink = eye_blink
            self.l_eye_velocity = avg_velocity

            if self.r_eye_blink == 0.0:
                if (
                    self.last_blink > 0.15
                ):  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    # print("REPEATING R BLINK")
                    for _ in range(4):
                        client.send_message(
                            config.osc_right_eye_close_address,
                            self.eyelid_transformer(
                                self.r_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )
                    self.last_blink = time.time() - self.last_blink
                if config.gui_outer_side_falloff:
                    if (
                        self.l_eye_blink == 0.0
                    ):  # if both eyes closed and DEF is enabled, blink
                        client.send_message(
                            config.osc_left_eye_close_address,
                            self.eyelid_transformer(
                                self.r_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )
                        client.send_message(
                            config.osc_right_eye_close_address,
                            self.eyelid_transformer(
                                self.r_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )

                self.r_eye_x = self.l_eye_x

            client.send_message(config.osc_right_eye_x_address, eye_x)
            self.right_y = eye_y

            client.send_message(
                config.osc_right_eye_close_address,
                self.eyelid_transformer(
                    self.r_eye_blink,
                    config.osc_invert_eye_close,
                ),
            )

        if (
            main_config.eye_display_id in [EyeId.BOTH]
            and self.right_y != 621
            and self.left_y != 621
        ):
            y = (self.right_y + self.left_y) / 2
            client.send_message(config.osc_eyes_y_address, y)

    def output_vrcft2(
        self,
        main_config,
        config,
        client,
        eye_x,
        eye_y,
        eye_blink,
        pupil_dilation,
        avg_velocity,
    ):
        single_eye_mode = self.get_is_single_eye_mode(config.eye_display_id)

        if single_eye_mode:
            client.send_message("/avatar/parameters/v2/EyeX", eye_x)
            client.send_message("/avatar/parameters/v2/EyeLeftX", eye_x)
            client.send_message("/avatar/parameters/v2/EyeRightX", eye_x)
            client.send_message("/avatar/parameters/v2/EyeLeftY", eye_y)
            client.send_message("/avatar/parameters/v2/EyeRightY", eye_y)
            client.send_message(
                "/avatar/parameters/v2/EyeLid",
                self.eyelid_transformer(
                    eye_blink,
                    config.osc_invert_eye_close,
                ),
            )

        if (
            self.eye_id in [EyeId.LEFT] and not single_eye_mode
        ):  # left eye, send data to left
            self.l_eye_x = eye_x
            self.l_eye_blink = eye_blink
            self.r_eye_velocity = avg_velocity

            if self.l_eye_blink == 0.0:
                if (
                    self.last_blink > 0.15
                ):  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for i in range(4):
                        client.send_message(
                            "/avatar/parameters/v2/EyeLidLeft",
                            self.eyelid_transformer(
                                self.l_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )
                    self.last_blink = time.time() - self.last_blink
                if config.gui_outer_side_falloff:
                    if (
                        self.r_eye_blink == 0.0
                    ):  # if both eyes closed and DEF is enables, blink
                        client.send_message(
                            "/avatar/parameters/v2/EyeLidLeft",
                            self.eyelid_transformer(
                                self.l_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )
                        client.send_message(
                            "/avatar/parameters/v2/EyeLidRight",
                            self.eyelid_transformer(
                                self.l_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )
                self.l_eye_x = self.r_eye_x

            client.send_message("/avatar/parameters/v2/EyeLeftX", self.l_eye_x)
            self.left_y = eye_y

            if self.left_y != 621:
                client.send_message("/avatar/parameters/FT/v2/EyeLeftY", self.left_y)

            client.send_message(
                "/avatar/parameters/FT/v2/EyeLidLeft",
                self.eyelid_transformer(
                    self.l_eye_blink,
                    config.osc_invert_eye_close,
                ),
            )

        elif (
            self.eye_id in [EyeId.RIGHT] and not single_eye_mode
        ):  # Right eye, send data to right
            self.r_eye_x = eye_x
            self.r_eye_blink = eye_blink
            self.r_eye_velocity = avg_velocity

            if self.r_eye_blink == 0.0:
                if (
                    self.last_blink > 0.15
                ):  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    #   print("REPEATING R BLINK")
                    for i in range(4):
                        client.send_message(
                            "/avatar/parameters/v2/EyeLidRight",
                            self.eyelid_transformer(
                                self.r_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )
                    self.last_blink = time.time() - self.last_blink
                if config.gui_outer_side_falloff:
                    if (
                        self.l_eye_blink == 0.0
                    ):  # if both eyes closed and DEF is enabled, blink
                        client.send_message(
                            "/avatar/parameters/v2/EyeLidLeft",
                            self.eyelid_transformer(
                                self.r_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )
                        client.send_message(
                            "/avatar/parameters/v2/EyeLidRight",
                            self.eyelid_transformer(
                                self.r_eye_blink,
                                config.osc_invert_eye_close,
                            ),
                        )

                self.r_eye_x = self.l_eye_x

            client.send_message("/avatar/parameters/v2/EyeRightX", self.r_eye_x)
            self.right_y = eye_y

            if self.right_y != 621:
                client.send_message("/avatar/parameters/v2/EyeRightY", self.right_y)

            client.send_message(
                "/avatar/parameters/v2/EyeLidRight",
                self.eyelid_transformer(
                    self.r_eye_blink,
                    config.osc_invert_eye_close,
                ),
            )

        if (
            main_config.eye_display_id in [EyeId.BOTH]
            and self.right_y != 621
            and self.left_y != 621
        ):
            y = (self.right_y + self.left_y) / 2
            client.send_message("/avatar/parameters/v2/EyeY", y)
