from dataclasses import dataclass
from typing import Union, Dict
from dacite import from_dict, Config
from osc import EyeId
import os.path
import json


# TODO Who even needs synchronization? (We do.)


@dataclass
class EyeTrackCameraConfig:
    threshold: "int" = 0
    rotation_angle: "int" = 50
    roi_window_x: "int" = 0
    roi_window_y: "int" = 0
    roi_window_w: "int" = 0
    roi_window_h: "int" = 0
    focal_length: "int" = 30
    capture_source: "Union[int, str, None]" = None
    gui_flip_x_axis_left: "bool" = False
    gui_flip_x_axis_right: "bool" = False
    gui_flip_y_axis: "bool" = False
    gui_blob_fallback: "bool" = True
    gui_min_cutoff: "str" = "0.0004"
    gui_speed_coefficient: "str" = "0.9"
    gui_osc_address: "str" = "127.0.0.1"
    gui_osc_port: "str" = "9000"
    
CONFIG_FILE_NAME = "eyetrack_settings.json"


@dataclass
class EyeTrackConfig:
    version: "int" = 1
    right_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    left_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    settings: EyeTrackCameraConfig = EyeTrackCameraConfig()
    eye_display_id: "EyeId" = EyeId.RIGHT

    @staticmethod
    def load():
        if not os.path.exists(CONFIG_FILE_NAME):
            print("No settings file, using base settings")
            return EyeTrackConfig()
        with open(CONFIG_FILE_NAME, "r") as settings_file:
            try:
                config: EyeTrackConfig = from_dict(
                    data_class=EyeTrackConfig, data=json.load(settings_file), config=Config(type_hooks={EyeId: EyeId})
                )
                if config.version != EyeTrackConfig().version:
                    raise RuntimeError(
                        "Configuration does not contain version number, consider invalid"
                    )
                return config
            except:
                print("Configuration invalid, creating new config")
                return EyeTrackConfig()

    def save(self):
        with open(CONFIG_FILE_NAME, "w+") as settings_file:
            json.dump(obj=self.__dict__, fp=settings_file, default=lambda x: x.__dict__)
