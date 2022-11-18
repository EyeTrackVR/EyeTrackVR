from typing import Union, Dict
from osc import EyeId
import os.path
import json
from pydantic import BaseModel
CONFIG_FILE_NAME: str = "eyetrack_settings.json"


class EyeTrackCameraConfig(BaseModel):
    threshold: int = 50
    rotation_angle: int = 0
    roi_window_x: int = 0
    roi_window_y: int = 0
    roi_window_w: int = 0
    roi_window_h: int = 0
    focal_length: int = 30
    capture_source: Union[int, str, None] = None
    gui_circular_crop: bool = False


class EyeTrackSettingsConfig(BaseModel):
    gui_flip_x_axis_left: bool = False
    gui_flip_x_axis_right: bool = False
    gui_flip_y_axis: bool = False
    gui_blob_fallback: bool = True
    gui_min_cutoff: str = "0.0004"
    gui_speed_coefficient: str = "0.9"
    gui_osc_address: str = "127.0.0.1"
    gui_osc_port: int = 9000
    gui_osc_receiver_port: int = 9001
    gui_osc_recenter_address: str = "/avatar/parameters/etvr_recenter"
    gui_osc_recalibrate_address: str = "/avatar/parameters/etvr_recalibrate"
    gui_blob_maxsize: float = 25
    gui_blob_minsize: float = 10
    gui_recenter_eyes: bool = False
    gui_eye_falloff: bool = False
    tracker_single_eye: int = 0
    gui_blink_sync: bool = False


class EyeTrackConfig(BaseModel):
    version: int = 1
    right_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    left_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    settings: EyeTrackSettingsConfig = EyeTrackSettingsConfig()
    eye_display_id: EyeId = EyeId.RIGHT

    @staticmethod
    def load():
        if not os.path.exists(CONFIG_FILE_NAME):
            print("No settings file, using base settings")
            return EyeTrackConfig()
        with open(CONFIG_FILE_NAME, "r") as settings_file:
            return EyeTrackConfig(**json.load(settings_file))

    def save(self):
        with open(CONFIG_FILE_NAME, "w+") as settings_file:
            json.dump(obj=self.dict(), fp=settings_file)
