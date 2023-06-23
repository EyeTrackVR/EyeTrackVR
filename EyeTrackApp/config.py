import json
import os.path
import shutil

from eye import EyeId
from pydantic import BaseModel
from typing import Union

CONFIG_FILE_NAME: str = "eyetrack_settings.json"
BACKUP_CONFIG_FILE_NAME: str = "eyetrack_settings.backup"


class EyeTrackCameraConfig(BaseModel):
    rotation_angle: int = 0
    roi_window_x: int = 0
    roi_window_y: int = 0
    roi_window_w: int = 0
    roi_window_h: int = 0
    focal_length: int = 30
    capture_source: Union[int, str, None] = None
    calib_XMAX: int = None
    calib_XMIN: int = None
    calib_YMAX: int = None
    calib_YMIN: int = None
    calib_XOFF: int = None
    calib_YOFF: int = None


class EyeTrackSettingsConfig(BaseModel):
    gui_flip_x_axis_left: bool = False
    gui_flip_x_axis_right: bool = False
    gui_flip_y_axis: bool = False
    gui_RANSAC3D: bool = False
    gui_HSF: bool = False
    gui_BLOB: bool = False
    gui_BLINK: bool = False
    gui_HSRAC: bool = True
    gui_DADDY: bool = False
    gui_MOMMY: bool = False
    gui_HSF_radius: int = 15
    gui_HSF_radius_left: int = 10
    gui_HSF_radius_right: int = 10
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
    gui_threshold: int = 65
    gui_HSRACP: int = 1
    gui_HSFP: int = 2
    gui_DADDYP: int = 3
    gui_RANSAC3DP: int = 4
    gui_BLOBP: int = 5
    gui_MOMMYP: int = 6
    gui_IBO: bool = True
    gui_skip_autoradius: bool = False
    gui_thresh_add: int = 11
    gui_update_check: bool = False
    gui_ROSC: bool = False
    gui_vrc_native: bool = True
    gui_circular_crop_right: bool = False
    gui_circular_crop_left: bool = False
    ibo_filter_samples: int = 400
    ibo_average_output_samples: int = 0
    ibo_fully_close_eye_threshold: float = 0.3
    calibration_samples: int = 600
    osc_right_eye_close_address: str = "/avatar/parameters/RightEyeLidExpandedSqueeze"
    osc_left_eye_close_address: str = "/avatar/parameters/LeftEyeLidExpandedSqueeze"
    osc_invert_eye_close: bool = False


class EyeTrackConfig(BaseModel):
    version: int = 1
    right_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    left_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    settings: EyeTrackSettingsConfig = EyeTrackSettingsConfig()
  #  algo_settings: EyeTrackSettingsConfig = EyeTrackSettingsConfig()
    eye_display_id: EyeId = EyeId.RIGHT

    @staticmethod
    def load():
        if not os.path.exists(CONFIG_FILE_NAME):
            print("No settings file, using base settings")
            return EyeTrackConfig()
        try:
            with open(CONFIG_FILE_NAME, "r") as settings_file:
                return EyeTrackConfig(**json.load(settings_file))
        except json.JSONDecodeError:
            print("[INFO] Failed to load settings file")
            load_config = None
            if os.path.exists(BACKUP_CONFIG_FILE_NAME):
                try:
                    with open(BACKUP_CONFIG_FILE_NAME, "r") as settings_file:
                        load_config = EyeTrackConfig(**json.load(settings_file))
                    print("[INFO] Using backup settings")
                except json.JSONDecodeError:
                    pass
            if load_config is None:
                print("[INFO] using base settings")
                load_config = EyeTrackConfig()
            return load_config

    def save(self):
        # make sure this is only called if there is a change
        if os.path.exists(CONFIG_FILE_NAME):
            try:
                # Verify existing configuration files.
                with open(CONFIG_FILE_NAME, "r") as settings_file:
                    EyeTrackConfig(**json.load(settings_file))
                shutil.copy(CONFIG_FILE_NAME, BACKUP_CONFIG_FILE_NAME)
                # print("Backed up settings files.") # Comment out because it's too loud.
            except json.JSONDecodeError:
                # No backup because the saved settings file is broken.
                pass
        with open(CONFIG_FILE_NAME, "w") as settings_file:
            json.dump(obj=self.dict(), fp=settings_file)
        print("[INFO] Config Saved Successfully")
