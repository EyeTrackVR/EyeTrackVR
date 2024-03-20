from pythonosc.udp_client import SimpleUDPClient

from eye import EyeId
from osc.OSCMessage import OSCMessage

from pythonosc import osc_server
from pythonosc import dispatcher
from config import EyeTrackConfig, EyeTrackSettingsConfig
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC
from enum import IntEnum
import threading
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
        self.last_blink = time.time()

    def output_osc_info(
        self,
        osc_message: OSCMessage,
        client: SimpleUDPClient,
        main_config: EyeTrackConfig,
        config: EyeTrackSettingsConfig,
    ):

        eye_id, eye_info = osc_message.data.items()
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
            )

    @staticmethod
    def get_is_single_eye(eye_display_id):
        return eye_display_id in [EyeId.RIGHT, EyeId.LEFT]

    def send_eye_blink_data(
        self,
        eye_id: EyeId,
        client,
        config,
        eye_blink,
        params_version: OutputType,
        left_eye_blink_address,
        right_eye_blink_address,
        both_eyes_mode=False,
    ):
        falloff_eye = self.r_eye_blink if eye_id == EyeId.LEFT else self.l_eye_blink
        saved_side_eye_blink = self.l_eye_blink if eye_id == EyeId.LEFT else self.r_eye_blink
        blink_address = left_eye_blink_address if eye_blink == EyeId.LEFT else right_eye_blink_address

        def send_blink_message(blink_value):
            for _ in range(5):
                client.send_message(blink_address, float(1 - blink_value))
                blink_value += 0.02

        client.send_message(blink_address, _eyelid_transformer(config, eye_blink))

        # dual eye blink
        if both_eyes_mode:
            if self.r_eye_blink == 0.0 or self.l_eye_blink == 0.0:
                if self.last_blink > 0.2:
                    send_blink_message(blink_value=1)
                    self.last_blink = time.time() - self.last_blink
                eye_blink = (self.r_eye_blink + self.l_eye_blink) / 2
                client.send_message(blink_address, float(1 - eye_blink))
        elif saved_side_eye_blink == 0.0:
            # when binary blink is on, blinks may be too fast for OSC, so we repeat them.
            if self.last_blink > 0.2:
                send_blink_message(eye_blink)
                self.last_blink = time.time() - self.last_blink
            elif self.is_single_eye:
                client.send_message(blink_address, float(1 - eye_blink))

            # outer side falloff was designed to help out in dual eye mode, so for single eye we can skip it
            # we also check for being in single_eye since what dual eye mode does is basically
            # run both instances "next to" each other
            if config.gui_outer_side_falloff and not self.is_single_eye:
                # if both eyes closed and DEF is enabled, blink
                if falloff_eye == 0.0:
                    if params_version == OutputType.NATIVE_PARAMS:
                        client.send_message(blink_address, float(0))
                    else:
                        client.send_message(left_eye_blink_address, float(eye_blink))
                        client.send_message(right_eye_blink_address, float(eye_blink))

    def update_eye_state(self, eye_id, eye_x, eye_y, eye_blink, avg_velocity):
        if eye_id == EyeId.LEFT:
            self.l_eye_x = eye_x
            self.l_eye_blink = eye_blink
            self.left_y = eye_y  # in v1 and v2 we do not save this, maybe we shouldn't here either?
            self.l_eye_velocity = avg_velocity
        if eye_id == EyeId.RIGHT:
            self.r_eye_x = eye_x
            self.r_eye_blink = eye_blink
            self.right_y = eye_y
            self.r_eye_velocity = avg_velocity

    def mirror_eye_x_direction(self, eye_id: EyeId):
        if eye_id == EyeId.LEFT:
            self.l_eye_x = self.r_eye_x
        if eye_id == EyeId.RIGHT:
            self.r_eye_x = self.l_eye_x

    def output_native(self, main_config, config, client, eye_x, eye_y, eye_blink, avg_velocity, eye_id):
        default_eye_blink_params = {
            "eye_id": eye_id,
            "client": client,
            "config": config,
            "eye_blink": eye_blink,
            "left_eye_blink_address": "/tracking/eye/EyesClosedAmount",
            "right_eye_blink_address": "/tracking/eye/EyesClosedAmount",
            "params_version": OutputType.NATIVE_PARAMS,
        }
        if self.is_single_eye:
            self.send_eye_blink_data(
                **default_eye_blink_params,
            )
            client.send_message(
                "/tracking/eye/LeftRightVec",
                [float(eye_x), float(eye_y), 1.0, float(eye_x), float(eye_y), 1.0],
            )

        if eye_id in [EyeId.LEFT, EyeId.RIGHT] and not self.is_single_eye:
            self.update_eye_state(
                eye_id=eye_id,
                eye_x=eye_x,
                eye_y=eye_y,
                eye_blink=eye_blink,
                avg_velocity=avg_velocity,
            )
            self.send_eye_blink_data(**default_eye_blink_params)
            self.mirror_eye_x_direction(eye_id=eye_id)

        if main_config.eye_display_id == EyeId.BOTH and self.r_eye_blink != 621 and self.r_eye_blink != 621:
            self.send_eye_blink_data(
                **default_eye_blink_params,
                both_eyes_mode=True,
            )

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

    def output_v1_params(self, main_config, config, client, eye_x, eye_y, eye_blink, avg_velocity, eye_id):
        default_eye_blink_params = {
            "eye_id": eye_id,
            "client": client,
            "config": config,
            "eye_blink": eye_blink,
            "left_eye_blink_address": config.osc_left_eye_close_address,
            "right_eye_blink_address": config.osc_right_eye_close_address,
            "params_version": OutputType.V1_PARAMS,
        }

        if self.is_single_eye:
            client.send_message(config.osc_left_eye_x_address, eye_x)
            client.send_message(config.osc_right_eye_x_address, eye_x)
            client.send_message(config.osc_eyes_y_address, eye_y)
            self.send_eye_blink_data(**default_eye_blink_params)

        if eye_id in [EyeId.LEFT, EyeId.RIGHT] and not self.is_single_eye:
            self.update_eye_state(
                eye_id=eye_id,
                eye_x=eye_x,
                eye_y=eye_y,
                eye_blink=eye_blink,
                avg_velocity=avg_velocity,
            )
            self.send_eye_blink_data(**default_eye_blink_params)
            self.mirror_eye_x_direction(eye_id=eye_id)

            if eye_id == EyeId.LEFT:
                client.send_message(config.osc_left_eye_x_address, self.l_eye_x)
                self.left_y = eye_y
                client.send_message(
                    config.osc_left_eye_close_address,
                    _eyelid_transformer(config, self.l_eye_blink),
                )

            if eye_id == EyeId.RIGHT:
                client.send_message(config.osc_right_eye_x_address, eye_x)
                self.right_y = eye_y

                client.send_message(
                    config.osc_right_eye_close_address,
                    _eyelid_transformer(config, self.r_eye_blink),
                )

        if main_config.eye_display_id == EyeId.BOTH and self.right_y != 621 and self.left_y != 621:
            y = (self.right_y + self.left_y) / 2
            client.send_message(config.osc_eyes_y_address, y)

    def output_v2_params(self, main_config, config, client, eye_x, eye_y, eye_blink, avg_velocity, eye_id):
        default_eye_blink_params = {
            "eye_id": eye_id,
            "client": client,
            "config": config,
            "eye_blink": eye_blink,
            "left_eye_blink_address": "/avatar/parameters/v2/EyeLid",
            "right_eye_blink_address": "/avatar/parameters/v2/EyeLid",
            "params_version": OutputType.V2_PARAMS,
        }

        if self.is_single_eye:
            client.send_message("/avatar/parameters/v2/EyeX", eye_x)
            client.send_message("/avatar/parameters/v2/EyeY", eye_y)
            self.send_eye_blink_data(**default_eye_blink_params)

        if eye_id in [EyeId.LEFT, EyeId.RIGHT] and not self.is_single_eye:
            self.update_eye_state(
                eye_id=eye_id,
                eye_x=eye_x,
                eye_y=eye_y,
                eye_blink=eye_blink,
                avg_velocity=avg_velocity,
            )
            self.send_eye_blink_data(
                **default_eye_blink_params,
                left_eye_blink_address="/avatar/parameters/v2/EyeLidLeft",
                right_eye_blink_address="/avatar/parameters/v2/EyeLidRight",
            )
            self.mirror_eye_x_direction(eye_id)

            if eye_id == EyeId.LEFT:
                client.send_message("/avatar/parameters/v2/EyeLeftX", self.l_eye_x)
                if self.left_y != 621:
                    client.send_message("/avatar/parameters/v2/EyeLeftY", eye_y)

                client.send_message(
                    "/avatar/parameters/v2/EyeLidLeft",
                    _eyelid_transformer(config, self.l_eye_blink),
                )

            if eye_id == EyeId.RIGHT:
                client.send_message("/avatar/parameters/v2/EyeRightX", self.r_eye_x)
                if eye_y != 621:
                    client.send_message("/avatar/parameters/v2/EyeRightY", eye_y)

                client.send_message(
                    "/avatar/parameters/v2/EyeLidRight",
                    _eyelid_transformer(config, self.r_eye_blink),
                )


class VRChatOSCReceiver:
    def __init__(self, cancellation_event: threading.Event, main_config: EyeTrackConfig, eyes: []):
        self.config = main_config.settings
        self.cancellation_event = cancellation_event
        self.dispatcher = dispatcher.Dispatcher()
        self.eyes = eyes  # we cant import CameraWidget so any type it is
        try:
            self.server = osc_server.OSCUDPServer(
                (self.config.gui_osc_address, int(self.config.gui_osc_receiver_port)),
                self.dispatcher,
            )
        except:
            print(f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m")

    def shutdown(self):
        print("\033[94m[INFO] Exiting OSC Receiver\033[0m")
        try:
            self.server.shutdown()
        except:
            pass

    def recenter_eyes(self, address, osc_value):
        if type(osc_value) is not bool:
            return  # just incase we get anything other than bool
        if osc_value:
            for eye in self.eyes:
                eye.settings.gui_recenter_eyes = True

    def recalibrate_eyes(self, address, osc_value):
        if type(osc_value) is not bool:
            return  # just incase we get anything other than bool
        if osc_value:
            for eye in self.eyes:
                eye.ransac.ibo.clear_filter()
                eye.ransac.calibration_frame_counter = self.config.calibration_samples
                PlaySound("Audio/start.wav", SND_FILENAME | SND_ASYNC)

    def run(self):
        try:
            self.dispatcher.map(self.config.gui_osc_recalibrate_address, self.recalibrate_eyes)
            self.dispatcher.map(self.config.gui_osc_recenter_address, self.recenter_eyes)
            # start the server
            print("\033[92m[INFO] VRChatOSCReceiver serving on {}\033[0m".format(self.server.server_address))
            self.server.serve_forever()

        except:
            print(f"\033[91m[ERROR] OSC Receive port: {self.config.gui_osc_receiver_port} occupied.\033[0m")
