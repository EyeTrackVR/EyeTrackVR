import time

from pythonosc import udp_client
from EyeTrackApp.consts import PageType
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
        self.blink_last_time = None

    def handle_out(self, eye_info: EyeInfo, eye_id: int):
        if self.settings.gui_vrc_native:
            self.osc_output_vrc_native(eye_info.blink, eye_info.x, eye_info.y, eye_id)
        else:
            self.osc_output_legacy(eye_info.blink, eye_info.x, eye_info.y, eye_id)

    def osc_output_vrc_native(self, eye_blink, eye_x, eye_y, eye_id):
        # single eye mode
        if self.app_config.eye_display_id in [PageType.RIGHT, PageType.LEFT]:
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

        if eye_id in [PageType.LEFT] and not self.single_eye:
            self.left_eye_x = eye_x
            self.left_eye_blink = eye_blink
            self.left_eye_y = eye_y

            if self.left_eye_blink == 0.0:
                # when binary blink is on, blinks may be too fast for OSC, so we repeat them.
                if self.blink_last_time and self.blink_last_time > 0.7:
                    for _ in range(5):
                        self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))
                    self.blink_last_time = time.time() - self.blink_last_time if self.blink_last_time else time.time()
                if self.settings.gui_eye_falloff and self.right_eye_blink == 0.0:
                    self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))
                self.left_eye_x = self.right_eye_x

        elif eye_id in [PageType.RIGHT] and not self.single_eye:
            self.right_eye_x = eye_x
            self.right_eye_blink = eye_blink
            self.right_eye_y = eye_y

            if self.right_eye_blink == 0.0:
                if self.blink_last_time and self.blink_last_time > 0.7:  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for _ in range(5):
                        self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))
                    self.blink_last_time = time.time() - self.blink_last_time if self.blink_last_time else time.time()
                if self.settings.gui_eye_falloff and self.left_eye_blink == 0.0:
                    self.client.send_message("/tracking/eye/EyesClosedAmount", float(0))

                self.right_eye_x = self.left_eye_x
        if (
            self.app_config.eye_display_id in [PageType.BOTH]
            and self.right_eye_blink != 621
            and self.left_eye_blink != 621
        ):
            if self.right_eye_blink == 0.0 or self.left_eye_blink == 0.0:
                if self.blink_last_time and self.blink_last_time > 0.7:  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for _ in range(5):
                        self.client.send_message("/tracking/eye/EyesClosedAmount", float(1))
                    self.blink_last_time = time.time() - self.blink_last_time if self.blink_last_time else time.time()
            eye_blink = (self.right_eye_blink + self.left_eye_blink) / 2
            self.client.send_message("/tracking/eye/EyesClosedAmount", float(1 - eye_blink))

        if self.app_config.eye_display_id in [PageType.BOTH] and self.right_eye_y != 621 and self.left_eye_y != 621:
            eye_y = (self.right_eye_y + self.left_eye_y) / 2

        if not self.single_eye:
            self.client.send_message(
                "/tracking/eye/LeftRightVec",
                [
                    float(self.left_eye_x),
                    float(eye_y),
                    1.0,
                    float(self.right_eye_x),
                    float(eye_y),
                    1.0,
                ],
            )  # vrc native ET (z values may need tweaking, they act like a scalar)

    def osc_output_legacy(self, eye_blink, eye_x, eye_y, eye_id):
        if self.app_config.eye_display_id in [
            PageType.RIGHT,
            PageType.LEFT,
        ]:  # we are in single eye mode
            se = True

            self.client.send_message("/avatar/parameters/LeftEyeX", eye_x)
            self.client.send_message("/avatar/parameters/RightEyeX", eye_x)
            self.client.send_message("/avatar/parameters/EyesY", eye_y)

            self.client.send_message("/avatar/parameters/RightEyeLidExpandedSqueeze", float(eye_blink))
            self.client.send_message("/avatar/parameters/LeftEyeLidExpandedSqueeze", float(eye_blink))
        else:
            se = False

        if eye_id in [PageType.LEFT] and not se:  # left eye, send data to left
            self.left_eye_x = eye_x
            self.left_eye_x = eye_blink

            if self.left_eye_x == 0.0:
                if self.blink_last_time and self.blink_last_time > 0.7:  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for _ in range(5):
                        self.client.send_message(
                            "/avatar/parameters/LeftEyeLidExpandedSqueeze",
                            float(self.left_eye_x),
                        )
                    self.blink_last_time = time.time() - self.blink_last_time if self.blink_last_time else time.time()
                if self.settings.gui_eye_falloff and self.right_eye_blink == 0.0:  # if both eyes closed and DEF is enables, blink
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
        elif eye_id in [PageType.RIGHT] and not se:
            self.right_eye_x = eye_x
            self.right_eye_blink = eye_blink

            if self.right_eye_blink == 0.0:
                if self.blink_last_time and self.blink_last_time > 0.7:  # when binary blink is on, blinks may be too fast for OSC so we repeat them.
                    for _ in range(5):
                        self.client.send_message(
                            "/avatar/parameters/LeftEyeLidExpandedSqueeze",
                            float(self.right_eye_blink),
                        )
                    self.blink_last_time = time.time() - self.blink_last_time if self.blink_last_time else time.time()
                if self.settings.gui_eye_falloff and self.left_eye_x == 0.0:  # if both eyes closed and DEF is enables, blink
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

        if self.app_config.eye_display_id in [PageType.BOTH] and self.right_eye_y != 621 and self.left_eye_y != 621:
            y = (self.right_eye_y + self.left_eye_y) / 2
            self.client.send_message("/avatar/parameters/EyesY", y)
