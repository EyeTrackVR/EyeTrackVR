import time

from pythonosc import udp_client
from EyeTrackApp.consts import EyeId
from config import EyeTrackConfig
from eye import EyeInfo


class OSCOutputHandler:
    def __init__(self, config: EyeTrackConfig):
        self.app_config = config
        self.settings = config.settings
        self.single_eye = False

        # use OSC port and address that was set in the config
        self.client = udp_client.SimpleUDPClient(self.settings.gui_osc_address, int(self.settings.gui_osc_port))

        self.left_eye_x = 0
        self.left_eye_y = 0
        self.left_eye_blink = 0.7

        self.right_eye_x = 0
        self.right_eye_y = 0
        self.right_eye_blink = 0.7

    def handle_out(self, eye_info: EyeInfo, eye_id: int):
        last_blink = time.time()   # TODO figure out if this is really needed
        if not self.settings.gui_vrc_native:
            self.osc_output_vrc_native(eye_info.blink, eye_info.x, eye_info.y, last_blink, eye_id)
        else:
            self.osc_output_legacy(eye_info.blink, eye_info.x, eye_info.y, last_blink, eye_id)

    def osc_output_vrc_native(self, eye_blink, eye_x, eye_y, last_blink, eye_id):
        # single eye mode
        if self.app_config.eye_display_id in [EyeId.RIGHT, EyeId.LEFT]:
            self.single_eye = True
            self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))
            self.client.send_message(
                "/tracking/eye/LeftRightVec",
                [
                    float(eye_x),
                    float(eye_y),
                    1.0,
                    float(eye_x),
                    float(eye_y),
                    1.0,
                ],
            )
        else:
            self.single_eye = False

        if eye_id in [EyeId.LEFT] and not self.single_eye:
            self.left_eye_x = eye_x
            self.left_eye_blink = eye_blink
            self.left_eye_y = eye_y

            if self.left_eye_blink == 0.0:
                # when binary blink is on, blinks may be too fast for OSC, so we repeat them.
                if last_blink > 0.7:
                    for i in range(5):
                        self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))
                    last_blink = time.time() - last_blink
                if self.settings.gui_eye_falloff:
                    if self.right_eye_blink == 0.0:  # if both eyes closed and DEF is enables, blink
                        self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))
                self.left_eye_x = self.right_eye_x

        elif eye_id in [EyeId.RIGHT] and not self.single_eye:
            self.right_eye_x = eye_x
            self.right_eye_blink = eye_blink
            self.right_eye_y = eye_y

            if self.right_eye_blink == 0.0:
                if last_blink > 0.7:  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for i in range(5):
                        self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))
                    last_blink = time.time() - last_blink
                if self.settings.gui_eye_falloff:
                    if self.left_eye_blink == 0.0:  # if both eyes closed and DEF is enables, blink
                        self.client.send_message("/tracking/eye/EyesClosedAmount", float(0))

                self.right_eye_x = self.left_eye_x
        if (
            self.app_config.eye_display_id in [EyeId.BOTH]
            and self.right_eye_blink != 621
            and self.left_eye_blink != 621
        ):
            if self.right_eye_blink == 0.0 or self.left_eye_blink == 0.0:
                if last_blink > 0.7:  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for i in range(5):
                        self.client.send_message("/tracking/eye/EyesClosedAmount", float(1))
                    last_blink = time.time() - last_blink  # this might be borked now
            eye_blink = (self.right_eye_blink + self.left_eye_blink) / 2
            self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))

        if self.app_config.eye_display_id in [EyeId.BOTH] and self.right_eye_y != 621 and self.left_eye_y != 621:
            eye_y = (self.right_eye_y + self.left_eye_y) / 2

        if not self.single_eye:
            self.client.send_message(
                "/tracking/eye/LeftRightVec",
                [
                    float(self.left_eye_x),
                    float(eye_y),
                    0.8,
                    float(self.right_eye_x),
                    float(eye_y),
                    0.8,
                ],
            )  # vrc native ET (z values may need tweaking, they act like a scalar)

    def osc_output_legacy(self, eye_blink, eye_x, eye_y, last_blink, eye_id):

        if self.app_config.eye_display_id in [
            EyeId.RIGHT,
            EyeId.LEFT,
        ]:  # we are in single eye mode
            se = True

            self.client.send_message("/avatar/parameters/LeftEyeX", eye_x)
            self.client.send_message("/avatar/parameters/RightEyeX", eye_x)
            self.client.send_message("/avatar/parameters/EyesY", eye_y)

            self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(eye_blink))
            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(eye_blink))
        else:
            se = False

        if eye_id in [EyeId.LEFT] and not se:  # left eye, send data to left
            self.left_eye_x = eye_x
            self.left_eye_x = eye_blink

            if self.left_eye_x == 0.0:
                if last_blink > 0.7:  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for i in range(5):
                        self.client.send_message(
                            "/avatar/parameters/LeftEyeLidExpandedSqueeze",
                            float(self.left_eye_x),
                        )
                    last_blink = time.time() - last_blink
                if self.settings.gui_eye_falloff:
                    if self.right_eye_blink == 0.0:  # if both eyes closed and DEF is enables, blink
                        self.client.send_message(
                            "/avatar/parameters/LeftEyeLidExpandedSqueeze",
                            float(self.left_eye_x),
                        )
                        self.client.send_message(
                            "/avatar/parameters/RightEyeLidExpandedSqueeze",
                            float(self.left_eye_x),
                        )
                self.left_eye_x = self.right_eye_x

            self.client.send_message("/avatar/parameters/LeftEyeX", self.left_eye_x)
            self.left_eye_y = eye_y

            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(self.left_eye_x))

        # Right eye, send data to right
        elif eye_id in [EyeId.RIGHT] and not se:
            self.right_eye_x = eye_x
            self.right_eye_blink = eye_blink

            if self.right_eye_blink == 0.0:
                if last_blink > 0.7:  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for i in range(5):
                        self.client.send_message(
                            "/avatar/parameters/LeftEyeLidExpandedSqueeze",
                            float(self.right_eye_blink),
                        )
                    last_blink = time.time() - last_blink
                if self.settings.gui_eye_falloff:
                    if self.left_eye_x == 0.0:  # if both eyes closed and DEF is enables, blink
                        self.client.send_message(
                            "/avatar/parameters/LeftEyeLidExpandedSqueeze",
                            float(self.right_eye_blink),
                        )
                        self.client.send_message(
                            "/avatar/parameters/RightEyeLidExpandedSqueeze",
                            float(self.right_eye_blink),
                        )

                self.right_eye_x = self.left_eye_x

            self.client.send_message("/avatar/parameters/RightEyeX", eye_x)
            self.right_eye_y = eye_y

            self.client.send_message(
                "/avatar/parameters/RightEyeLidExpandedSqueeze",
                float(self.right_eye_blink),
            )

        if self.app_config.eye_display_id in [EyeId.BOTH] and self.right_eye_y != 621 and self.left_eye_y != 621:
            y = (self.right_eye_y + self.left_eye_y) / 2
            self.client.send_message("/avatar/parameters/EyesY", y)
