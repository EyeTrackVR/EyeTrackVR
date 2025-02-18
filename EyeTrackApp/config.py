"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2025 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import json
import os.path
import shutil

from colorama import Fore
from pydantic import BaseModel
from typing import Any, Union, List
import os

from eye import EyeId

CONFIG_FILE_NAME: str = "eyetrack_settings.json"
BACKUP_CONFIG_FILE_NAME: str = "eyetrack_settings.backup"


class EyeTrackCameraConfig(BaseModel):
    gui_rotation_ui_padding: bool = True
    rotation_angle: int = 0
    roi_window_x: int = 0
    roi_window_y: int = 0
    roi_window_w: int = 240
    roi_window_h: int = 240
    focal_length: int = 30
    capture_source: Union[int, str, None] = None
    calib_XMAX: Union[float, None] = None
    calib_XMIN: Union[float, None] = None
    calib_YMAX: Union[float, None] = None
    calib_YMIN: Union[float, None] = None
    calib_XOFF: Union[float, None] = None
    calib_YOFF: Union[float, None] = None
    calibration_points: List[List[Union[float, None]]] = []
    calibration_points_3d: List[List[Union[float, None]]] = []
    leap_calibration_percentile_90: float = 0
    leap_calibration_percentile_2: float = 0
    leap_calibrated: bool = False


    def update_capture_source(self, new_camera_address: str):
        if not new_camera_address:
            self.capture_source = None
            return

        if new_camera_address.isnumeric():
            self.capture_source = int(new_camera_address)
            return

        # we were passed an IP, probably, lets add HTTP:// to it
        if len(new_camera_address) > 5 and not (
            not new_camera_address.startswith(("http", "/dev")) or not new_camera_address.endswith(".mp4")
        ):
            self.capture_source = f"http://{new_camera_address}"
            return

        self.capture_source = new_camera_address

    def update(self, data: dict[str, Any]) -> bool:
        """
        Updates the model one field at a time based on the provided data dict.
        The dict has to be defined like
        ```
        data = {
          "model_field": value
        }
        ```

        If stale data is provided,
        ex. User clicked on save and restart but didn't provide a new field

        we skip it, assuming that it was just a call to restart the tracking, or a miss-click.

        Some fields may require more validation, we take care of that with special methods.
        defining a method like

        ```
        def update_custom_field(value: type):
            pass
        ```

        will cause it to be picked up by this method and called with the current value.
        Return values are ignored.

        """
        for key, value in data.items():
            old_value = getattr(self, key, None)
            # no reason to update if it's the same value
            if old_value == value:
                return False

            if hasattr(self, f"update_{key}"):
                update_attr = getattr(self, f"update_{key}")
                if callable(update_attr):
                    update_attr(value)
                else:
                    setattr(self, "key", value)
                return True
            else:
                print(f"\033[93m[WARN] Field {key} does not exist on {self}.\033[0m")
                return False


class EyeTrackSettingsConfig(BaseModel):
    gui_flip_x_axis_left: bool = False
    gui_flip_x_axis_right: bool = False
    gui_flip_y_axis: bool = False
    gui_RANSAC3D: bool = False
    gui_HSF: bool = False
    gui_BLOB: bool = False
    gui_BLINK: bool = False
    gui_HSRAC: bool = False
    gui_AHSFRAC: bool = True
    gui_AHSF: bool = False
    gui_DADDY: bool = False
    gui_LEAP: bool = False
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
    gui_3d_calibration: bool = False
    grab_3d_point: bool = False
    tracker_single_eye: int = 0
    gui_threshold: int = 65
    gui_AHSFRACP: int = 1
    gui_AHSFP: int = 2
    gui_HSRACP: int = 3
    gui_HSFP: int = 4
    gui_DADDYP: int = 5
    gui_RANSAC3DP: int = 6
    gui_BLOBP: int = 7
    gui_LEAPP: int = 8
    gui_IBO: bool = False
    gui_skip_autoradius: bool = False
    gui_thresh_add: int = 11
    gui_update_check: bool = False
    gui_ROSC: bool = False
    gui_circular_crop_right: bool = False
    gui_circular_crop_left: bool = False
    ibo_filter_samples: int = 400
    ibo_average_output_samples: int = 0
    ibo_fully_close_eye_threshold: float = 0.3
    leap_calibration_samples: int = 2000
    calibration_samples: int = 600
    osc_right_eye_close_address: str = "/avatar/parameters/RightEyeLidExpandedSqueeze"
    osc_left_eye_close_address: str = "/avatar/parameters/LeftEyeLidExpandedSqueeze"
    osc_left_eye_x_address: str = "/avatar/parameters/LeftEyeX"
    osc_right_eye_x_address: str = "/avatar/parameters/RightEyeX"
    osc_eyes_y_address: str = "/avatar/parameters/EyesY"
    osc_eyes_pupil_dilation_address: str = "/avatar/parameters/EyesDilation"
    osc_invert_eye_close: bool = False
    gui_RANSACBLINK: bool = False

    gui_disable_gui: bool = False

    gui_right_eye_dominant: bool = False
    gui_left_eye_dominant: bool = False
    gui_outer_side_falloff: bool = False
    gui_eye_dominant_diff_thresh: float = 0.3

    gui_legacy_ransac: bool = False
    gui_legacy_ransac_thresh_right: int = 80
    gui_legacy_ransac_thresh_left: int = 80
    gui_LEAP_lid: bool = True
    gui_osc_vrcft_v1: bool = False
    gui_osc_vrcft_v2: bool = False
    gui_vrc_native: bool = True
    gui_pupil_dilation: bool = True

    gui_VRCFTModulePort: int = 8889
    gui_VRCFTModuleIPAddress: str = "127.0.0.1"
    gui_ShouldEmulateEyeWiden: bool = False
    gui_ShouldEmulateEyeSquint: bool = False
    gui_ShouldEmulateEyebrows: bool = False
    gui_WidenThresholdV1_min: float = 0.60
    gui_WidenThresholdV1_max: float = 1
    gui_WidenThresholdV2_min: float = 0.60
    gui_WidenThresholdV2_max: float = 1.05
    gui_SqueezeThresholdV1_min: float = 0.07
    gui_SqueezeThresholdV1_max: float = 0.5
    gui_SqueezeThresholdV2_min: float = 0.07
    gui_SqueezeThresholdV2_max: float = -1
    gui_EyebrowThresholdRising: float = 0.8
    gui_EyebrowThresholdLowering: float = 0.15
    gui_OutputMultiplier: float = 1
    gui_use_module: bool = False


class EyeTrackConfig(BaseModel):
    version: int = 1
    right_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    left_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    settings: EyeTrackSettingsConfig = EyeTrackSettingsConfig()
    eye_display_id: EyeId = EyeId.RIGHT
    __listeners = []

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

    def validate_camera_address_conflict(self, eye_id, capture_source):
        match eye_id:
            case EyeId.RIGHT:
                if self.left_eye.capture_source == capture_source:
                    print(
                        f"{Fore.YELLOW}[WARN] Capture source {capture_source} already in use by the left camera.{Fore.RESET}"
                    )
                    return False
            case EyeId.LEFT:
                if self.right_eye.capture_source == capture_source:
                    print(
                        f"{Fore.YELLOW}[WARN] Capture source {capture_source} already in use by the right camera.{Fore.RESET}"
                    )
                    return False
            case _:
                return False
        return True

    def update_eye_model_config(self, eye_id: EyeId, data: dict, should_save=True, should_notify=True) -> bool:
        """
        A more granular method for updating a particular model so that everything that relies on it
        will get notified about any changes. Note, it acts a bit like pub-sub,
        we don't care what changes got passed, we will notify the listeners with them.

        It's the listeners job to check if they want that update.
        """

        # The app really doesn't like address clashes, so we have to validate it as soon as possible
        # otherwise we crash
        if "capture_source" in data and not self.validate_camera_address_conflict(eye_id, data["capture_source"]):
            return False

        match eye_id:
            case EyeId.RIGHT:
                changed = self.right_eye.update(data)
            case EyeId.LEFT:
                changed = self.left_eye.update(data)
            case _:
                return False

        if should_save:
            self.save()

        if should_notify:
            self.__notify_listeners(data)

        return changed

    def update(self, data, save=False):
        """
        More of an internal method for modules to be able to update the config
        and have other parts of the system react to changes
        """
        for field, value in data.items():
            setattr(self.settings, field, value)
        self.__notify_listeners(data)
        if save:
            self.save()

    def save(self):
        # make sure this is only called if there is a change
        if os.path.exists(CONFIG_FILE_NAME):
            try:
                # Verify existing configuration files.
                with open(CONFIG_FILE_NAME, "r") as settings_file:
                    EyeTrackConfig(**json.load(settings_file))
                shutil.copy(CONFIG_FILE_NAME, BACKUP_CONFIG_FILE_NAME)
                # print("Backed up settings files.") # Comment out because it's too loud.
            except shutil.SameFileError:
                pass
            except json.JSONDecodeError:
                # No backup because the saved settings file is broken.
                pass
        with open(CONFIG_FILE_NAME, "w") as settings_file:
            json.dump(obj=self.model_dump(warnings=False), fp=settings_file)
        print(f"\033[92m[INFO] Config Saved Successfully\033[0m")

    def register_listener_callback(self, callback):
        print(f"[DEBUG] Registering listener {callback}")
        self.__listeners.append(callback)

    def __notify_listeners(self, data: dict):
        for listener in self.__listeners:
            listener(data)
