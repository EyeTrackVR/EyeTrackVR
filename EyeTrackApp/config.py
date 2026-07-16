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

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import json
import logging
import os.path
import shutil
import sys
import numpy as np
from pydantic import (
    BaseModel,
    PrivateAttr,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)
from typing import Any, Union, List
import os
from eye import EyeId

logger = logging.getLogger(__name__)

def _user_data_dir() -> str:
    """Directory holding the settings file.

    Windows keeps the historical behavior: bare filenames relative to the CWD,
    which is the install dir when launched from the Start-menu shortcut (the
    installer marks it user-writable). On Linux/macOS a system install usually
    is NOT writable and the launch CWD is arbitrary (e.g. $HOME from a .desktop
    entry), so the config belongs in the XDG config dir. A config file already
    present in the CWD wins on every platform: source checkouts and portable
    unpacked installs keep working exactly as before.
    """
    if os.name == "nt" or os.path.exists("eyetrack_settings.json"):
        return ""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, "EyeTrackVR")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return ""
    return path


_USER_DATA_DIR = _user_data_dir()
CONFIG_FILE_NAME: str = os.path.join(_USER_DATA_DIR, "eyetrack_settings.json")
BACKUP_CONFIG_FILE_NAME: str = os.path.join(_USER_DATA_DIR, "eyetrack_settings.backup")
DEFAULT_LID_CLOSE_THRESHOLD = 0.1
DEFAULT_LID_WIDEN_THRESHOLD = 0.9

# Bump this whenever a release changes the *semantics* of an existing field
# (renames, metric reworks, etc.) so that configs from older versions can be
# migrated rather than silently misinterpreted. New fields with safe defaults
# do NOT need a bump; pydantic fills those in automatically.
#
# Migration history:
#   1 -> 2: leap lid metric was reworked alongside per-eye lid thresholds. Old
#           configs may carry stale leap_calibration_percentile_* values whose
#           semantics no longer match leap.py's expectations, but the new
#           leap_lid_metric_version field defaults to the current version on
#           load, so the in-code "metric changed, recalibrate" guard misses
#           them. Wipe the stored calibration on this hop to force a fresh one.
#   2 -> 3: NEXT classic calibration became available by default but only
#           applies after NEXT itself has been calibrated. Preserve an existing
#           opted-in NEXT calibration without treating classical-tracker fits
#           as NEXT fits.
CURRENT_CONFIG_VERSION: int = 3


def _migrate_config_dict(data: dict) -> dict:
    """Apply forward migrations to a raw config dict so it conforms to the
    current schema's semantic expectations. Mutates and returns ``data``.

    Migrations are idempotent and stack: a config at v1 will run every
    migration step in order up to ``CURRENT_CONFIG_VERSION``."""
    if not isinstance(data, dict):
        return data
    stored = data.get("version", 1)
    try:
        stored = int(stored)
    except (TypeError, ValueError):
        stored = 1

    if stored < 2:
        # Reset leap lid calibration on every eye-config-shaped subtree.
        # We don't enumerate them by name because bsb2e exists and future
        # eyes may be added; we just clear any dict that looks like an eye
        # camera config.
        for key in ("left_eye", "right_eye", "bsb2e"):
            eye = data.get(key)
            if isinstance(eye, dict):
                eye["leap_calibrated"] = False
                eye["leap_calibration_percentile_90"] = 0
                eye["leap_calibration_percentile_2"] = 0
                # Force the in-code metric-version guard to recognise this as
                # pre-versioning data; leap.py will bump it on the next frame.
                eye["leap_lid_metric_version"] = 0
        logger.info("Migrated config from v1: reset leap lid calibration")

    if stored < 3:
        settings = data.get("settings")
        legacy_next_cal = (
            isinstance(settings, dict)
            and bool(settings.get("gui_NEXT_calibration", False))
        )
        for key in ("left_eye", "right_eye", "bsb2e"):
            eye = data.get(key)
            if not isinstance(eye, dict):
                continue
            has_fit = (
                eye.get("calib_axes") is not None
                and eye.get("calib_evecs") is not None
                and eye.get("calib_XOFF") is not None
            )
            eye["next_classic_calibration_active"] = bool(
                legacy_next_cal and has_fit
            )
        logger.info("Migrated config from v2: recorded NEXT calibration ownership")

    data["version"] = CURRENT_CONFIG_VERSION
    return data


class EyeTrackCameraConfig(BaseModel):
    gui_rotation_ui_padding: bool = False
    rotation_angle: int = 0
    roi_window_x: int = 0
    roi_window_y: int = 0
    roi_window_w: int = 240
    roi_window_h: int = 240
    # Stamp set by the Bigscreen auto-crop so we know which (frame_w, frame_h)
    # the current ROI was derived from. None means "user-set or not yet auto-
    # cropped": auto-crop refuses to touch an ROI unless the stamp matches a
    # previous auto-apply we made, or the ROI looks untouched-default.
    bigscreen_auto_crop_frame: Union[List[int], None] = None
    # focal_length is in PIXELS (pye3d's CameraModel expects pixel focal length,
    # not millimeters). Default 30 px works for the typical low-res IR tracker
    # cams shipped with ETVR. Field name preserved for backward compatibility
    # with existing eyetrack_settings.json files.
    focal_length: int = 30
    capture_source: Union[int, str, None] = None
    calib_axes: Union[List[float], None] = None
    calib_evecs: Union[List[List[float]], None] = None
    calib_center: Union[List[float], None] = None
    calib_XOFF: Union[float, None] = None
    calib_YOFF: Union[float, None] = None
    calibration_points: List[List[Union[float, None]]] = []
    calibration_points_3d: List[List[Union[float, None]]] = []
    # Prevent a calibration fitted for LEAP/another pixel tracker from being
    # applied to NEXT merely because classic NEXT calibration is available.
    next_classic_calibration_active: bool = False
    leap_calibration_percentile_90: float = 0
    leap_calibration_percentile_2: float = 0
    leap_calibrated: bool = False
    leap_lid_metric_version: int = 1
    # Bumped by the "Redo Eyelid Calib" button. LEAP_C tracks the last value
    # it saw and resets its sampling window when the two diverge, forcing a
    # fresh calibration without restarting the app or fiddling with the
    # metric-version migration mechanism.
    leap_calib_request_seq: int = 0
    # Robust calibration session state (serialized RobustCalibrationSession.to_dict())
    robust_calib_data: Union[dict, None] = None
    # NEXT Smart Calibration: a (warp + affine) transform mapping the raw NEXT
    # model gaze (right/up positive, [-1, 1]) to calibrated gaze that lands on
    # the known overlay dot positions. next_smartcal_w is the 2x2 weight matrix
    # in row-major order [w11, w12, w21, w22]; next_smartcal_b is the [b1, b2]
    # bias. next_smartcal_warp selects the space the affine was fit in:
    # "atanh" un-saturates the model's tanh output before the affine (current
    # fits), None = legacy raw-space affine saved by older builds. See
    # osc_calibrate_filter.next_smartcal_apply. All None until "NEXT Smart Calib".
    next_smartcal_w: Union[List[float], None] = None
    next_smartcal_b: Union[List[float], None] = None
    next_smartcal_warp: Union[str, None] = None

    @field_validator("calib_axes", "calib_evecs", "calib_center", mode="before")
    @classmethod
    def convert_numpy_to_list(cls, v):
        """Convert NumPy arrays to lists for JSON serialization and handle invalid values"""
        if v is None:
            return None
        # Handle invalid scalar values (e.g., integer 0 from corrupted config files)
        # These should be treated as None (uncalibrated)
        if isinstance(v, int) and v == 0:
            return None
        if isinstance(v, np.ndarray):
            return v.tolist()
        if hasattr(v, "tolist") and callable(v.tolist):
            return v.tolist()
        return v

    @field_serializer("calib_axes", "calib_evecs", "calib_center")
    def serialize_arrays(self, value):
        """Serialize arrays to lists when saving"""
        if value is None:
            return None
        if isinstance(value, np.ndarray):
            return value.tolist()
        if hasattr(value, "tolist") and callable(value.tolist):
            return value.tolist()
        return value

    def get_calib_axes_array(self) -> Union[np.ndarray, None]:
        """Get calib_axes as a NumPy array"""
        if self.calib_axes is None:
            return None
        return np.array(self.calib_axes, dtype=float)

    def get_calib_evecs_array(self) -> Union[np.ndarray, None]:
        """Get calib_evecs as a NumPy array"""
        if self.calib_evecs is None:
            return None
        return np.array(self.calib_evecs, dtype=float)

    def get_calib_center_array(self) -> Union[np.ndarray, None]:
        """Get calib_center as a NumPy array"""
        if self.calib_center is None:
            return None
        return np.array(self.calib_center, dtype=float)

    def set_calibration_data(
        self, axes: np.ndarray, evecs: np.ndarray, center: np.ndarray
    ):
        """Set all calibration data from NumPy arrays (auto-converts to lists)"""
        self.calib_axes = axes.tolist()
        self.calib_evecs = evecs.tolist()
        self.calib_center = center.tolist()

    def has_calibration_data(self) -> bool:
        """Check if calibration data is present"""
        return (
            self.calib_axes is not None
            and self.calib_evecs is not None
            and self.calib_center is not None
        )

    def update_capture_source(self, new_camera_address: str):
        if not new_camera_address:
            self.capture_source = None
            return

        if isinstance(new_camera_address, int):
            self.capture_source = new_camera_address
            return

        new_camera_address = str(new_camera_address).strip()

        if new_camera_address.isnumeric():
            self.capture_source = int(new_camera_address)
            return

        if (
            new_camera_address.startswith(("COM", "/dev"))
            or "://" in new_camera_address
        ):
            self.capture_source = new_camera_address
            return

        if new_camera_address.endswith(".mp4"):
            self.capture_source = new_camera_address
            return

        # We were passed a host/IP camera address; normalize it to a URL once.
        if len(new_camera_address) > 5:
            self.capture_source = f"http://{new_camera_address}/"
            return

        self.capture_source = new_camera_address

    def update(self, data: dict[str, Any]) -> bool:
        """
        Updates the model one field at a time based on the provided data dict.
        """
        changed = False
        for key, value in data.items():
            update_attr = getattr(self, f"update_{key}", None)
            if not callable(update_attr) and key not in type(self).model_fields:
                logger.warning("Field %s does not exist on %s.", key, self)
                continue

            old_value = getattr(self, key, None)
            if old_value == value:
                continue

            if callable(update_attr):
                update_attr(value)
            else:
                setattr(self, key, value)

            changed = changed or old_value != getattr(self, key, None)

        return changed


class EyeTrackSettingsConfig(BaseModel):
    gui_flip_x_axis_left: bool = False
    gui_flip_x_axis_right: bool = False
    gui_flip_y_axis: bool = False
    gui_RANSAC3D: bool = False
    gui_HSF: bool = False
    gui_BLINK: bool = False
    gui_HSRAC: bool = False
    gui_AHRAC: bool = False
    gui_AHSF: bool = False
    gui_DADDY: bool = False
    gui_LEAP: bool = False
    gui_NEXT: bool = True
    # NEXT BSB (stereo) end-to-end model: both eyes in one time-synced pass.
    gui_NEXT_BSB: bool = False
    # Calibration is available without a GUI opt-in. The NEXT processor only
    # applies it once a calibration is running/fitted, so raw default output is
    # unchanged on a fresh install.
    gui_NEXT_calibration: bool = True
    # Shared model variant for both NEXT and eyebrow models: ETVR / BSB / TOBII.
    # Selects Models/NEXT_<VARIANT>.onnx and Models/Eyebrow_<VARIANT>.onnx.
    gui_model_variant: str = "ETVR"
    # True once the user has manually picked a model variant. While False, the
    # variant tracks the main-tracking setup mode (bigscreen -> BSB, etvr -> ETVR).
    gui_model_variant_user_set: bool = False
    gui_max_tracking_speed: int = 60
    gui_HSF_radius: int = 15
    gui_HSF_radius_left: int = 10
    gui_HSF_radius_right: int = 10
    # Raw OneEuroFilter parameters. Surface in the GUI is a single
    # "Smoothing Intensity" slider (0..100) that derives these via the curve in
    # OneEuroSettingsModule. Kept as fields here because eye_processor / leap /
    # ibo all read them directly on startup.
    gui_min_cutoff: str = "0.003162"
    gui_speed_coefficient: str = "1.5250"
    gui_smoothing_intensity: int = 50
    gui_osc_address: str = "127.0.0.1"
    gui_osc_port: int = 9000
    gui_osc_receiver_port: int = 9001
    gui_osc_recenter_address: str = "/avatar/parameters/etvr_recenter"
    gui_osc_recalibrate_address: str = "/avatar/parameters/etvr_recalibrate"
    gui_recenter_eyes: bool = False
    gui_3d_calibration: bool = False
    grab_3d_point: bool = False
    tracker_single_eye: int = 0
    gui_AHRACP: int = 1
    gui_AHSFP: int = 2
    gui_HSRACP: int = 3
    gui_HSFP: int = 4
    gui_DADDYP: int = 5
    gui_RANSAC3DP: int = 6
    gui_LEAPP: int = 8
    gui_IBO: bool = False
    gui_skip_autoradius: bool = False
    gui_thresh_add: int = 11
    gui_update_check: bool = True
    gui_ROSC: bool = False
    gui_circular_crop_right: bool = False
    gui_circular_crop_left: bool = False
    ibo_filter_samples: int = 400
    ibo_average_output_samples: int = 0
    ibo_fully_close_eye_threshold: float = 0.3
    leap_lid_close_threshold: float = DEFAULT_LID_CLOSE_THRESHOLD
    leap_lid_widen_threshold: float = DEFAULT_LID_WIDEN_THRESHOLD
    leap_lid_close_threshold_left: float = DEFAULT_LID_CLOSE_THRESHOLD
    leap_lid_close_threshold_right: float = DEFAULT_LID_CLOSE_THRESHOLD
    leap_lid_widen_threshold_left: float = DEFAULT_LID_WIDEN_THRESHOLD
    leap_lid_widen_threshold_right: float = DEFAULT_LID_WIDEN_THRESHOLD
    leap_lid_min_calibration_span: float = 0.02
    leap_calibration_duration: int = 15
    calibration_duration: int = 15
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
    # Enabled by default: velocity-based falloff mirrors the cleaner eye when
    # the two tracked positions diverge, which is the right behavior for almost
    # every dual-eye setup. Users with very mismatched cameras can disable.
    gui_outer_side_falloff: bool = True
    gui_eye_dominant_diff_thresh: float = 0.3

    gui_LEAP_lid: bool = False
    gui_osc_vrcft_v1: bool = False
    gui_osc_vrcft_v2: bool = False
    gui_vrc_native: bool = False
    # Default output mode: send Unified Expressions straight to VRChat via the
    # embedded PY-VRCFT port (osc/PyVRCFTSender.py), replacing VRCFT. Auto-adapts
    # to v2 / legacy v1 / native-eye avatars from one tracking frame.
    gui_pyvrcft: bool = True
    gui_pupil_dilation: bool = False

    gui_VRCFTModulePort: int = 8889
    gui_VRCFTModuleIPAddress: str = "127.0.0.1"
    # Output full-scale FOV edge (degrees): the angle calibrated gaze ±1 maps to.
    # Two roles, kept consistent:
    #   1. pyVRCFT native /tracking/eye/LeftRightPitchYaw maps ±1 to degrees via
    #      atan(gaze * tan(max)), so full gaze reflects a real angle instead of
    #      VRCFT's default 45°. (Normalized v1/v2 eye params carry ±1 directly;
    #      the avatar rig owns what ±1 rotates to there.)
    #   2. next_smartcal_targets() derives each calibration dot's fit target as
    #      its fraction of THIS full-scale, so the inset overlay dots are NOT
    #      treated as ≈max output — leaving headroom for the eye to drive output
    #      out to ±1 at the FOV edge instead of clipping at the overlay's
    #      oculomotor dot caps. Headroom is PER-AXIS by how far the eye can
    #      actually rotate: yaw/down are set wider than the overlay caps
    #      (30/35) so lateral/downward gaze reaches ±1 near the FOV edge, but
    #      UP is kept at its cap (15) — upward eye rotation maxes out ~15°, so
    #      any up headroom just makes full-up unreachable ("doesn't go high
    #      enough"). Changing these needs a re-cal (Reset Smart Calib) so the
    #      saved affine matches.
    gui_gaze_yaw_max_deg: float = 40.0
    gui_gaze_pitch_up_deg: float = 15.0
    gui_gaze_pitch_down_deg: float = 40.0
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
    gui_use_gpu: bool = True  # simple checkbox vs drop down with cuda, openvino etc.
    gui_eyebrow: bool = False

    gui_openvr_autostart: bool = False
    gui_show_et_debug: bool = False

    # Calibration mode. "classic" preserves existing ellipse behaviour.
    # "express" uses 5-point min-max normalization from RobustCalibrationSession.
    # "robust"  uses BS detector routing: express primary, SVR fallback.
    calib_mode: str = "classic"
    # DFR (Dynamic Foveated Rendering) unclamped gaze vector output via UDP.
    gui_dfr_enabled: bool = False
    gui_dfr_port: int = 9002
    gui_dfr_address: str = "127.0.0.1"
    # Hold last valid calibrated position when the tracker snaps from an extreme
    # gaze angle back to near-center in a single frame (characteristic failure mode
    # at extreme angles). Requires robust or express calibration to be active.
    gui_snap_hold_enabled: bool = True
    gui_use_overlay_cal: bool = True

    # Setup mode picked on the Tracking tab. Persisted so a user who picked
    # Bigscreen Beyond doesn't relaunch into normal ETVR mode (which would
    # then load whatever was saved as the right eye's source, in BSB that's
    # the same camera as the left, producing the "both eyes on one webcam"
    # state).
    gui_setup_mode: str = "etvr"

    # UI language, as a locale code matching a file in the lang/ folder
    # (e.g. "en", "es"). Default English. Applied at startup by
    # localization.init_localization(); changing it in the GUI prompts a
    # restart. See localization.py.
    gui_language: str = "en"

    @model_validator(mode="before")
    @classmethod
    def copy_legacy_leap_lid_thresholds(cls, data):
        if not isinstance(data, dict):
            return data

        if "leap_lid_close_threshold" in data:
            data.setdefault(
                "leap_lid_close_threshold_left", data["leap_lid_close_threshold"]
            )
            data.setdefault(
                "leap_lid_close_threshold_right", data["leap_lid_close_threshold"]
            )
        if "leap_lid_widen_threshold" in data:
            data.setdefault(
                "leap_lid_widen_threshold_left", data["leap_lid_widen_threshold"]
            )
            data.setdefault(
                "leap_lid_widen_threshold_right", data["leap_lid_widen_threshold"]
            )
        return data


class EyeTrackConfig(BaseModel):
    version: int = CURRENT_CONFIG_VERSION
    right_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    left_eye: EyeTrackCameraConfig = EyeTrackCameraConfig()
    bsb2e: EyeTrackCameraConfig = (
        EyeTrackCameraConfig()
    )  # should we do independent per bsb eye?
    settings: EyeTrackSettingsConfig = EyeTrackSettingsConfig()
    eye_display_id: EyeId = EyeId.RIGHT
    _listeners: list = PrivateAttr(default_factory=list)

    @staticmethod
    def load():
        if not os.path.exists(CONFIG_FILE_NAME):
            logger.info("No settings file, using base settings")
            return EyeTrackConfig()
        try:
            with open(CONFIG_FILE_NAME, "r") as settings_file:
                raw = json.load(settings_file)
            return EyeTrackConfig(**_migrate_config_dict(raw))
        except (json.JSONDecodeError, ValidationError):
            logger.info("Failed to load settings file")
            load_config = None
            if os.path.exists(BACKUP_CONFIG_FILE_NAME):
                try:
                    with open(BACKUP_CONFIG_FILE_NAME, "r") as settings_file:
                        raw = json.load(settings_file)
                    load_config = EyeTrackConfig(**_migrate_config_dict(raw))
                    logger.info("Using backup settings")
                except (json.JSONDecodeError, ValidationError):
                    pass
            if load_config is None:
                logger.info("Using base settings")
                load_config = EyeTrackConfig()
            return load_config

    def validate_camera_address_conflict(self, eye_id, capture_source):
        match eye_id:
            case EyeId.RIGHT:
                if self.left_eye.capture_source == capture_source:
                    logger.warning(
                        "Capture source %s already in use by the left camera.",
                        capture_source,
                    )
                    return False
            case EyeId.LEFT:
                if self.right_eye.capture_source == capture_source:
                    logger.warning(
                        "Capture source %s already in use by the right camera.",
                        capture_source,
                    )
                    return False
            case _:
                return False
        return True

    def update_eye_model_config(
        self, eye_id: EyeId, data: dict, should_save=True, should_notify=True
    ) -> bool:
        """
        A more granular method for updating a particular model so that everything that relies on it
        will get notified about any changes. This acts like a small pub-sub layer:
        listeners receive the changed keys and decide whether they are relevant.
        """

        # The app really doesn't like address clashes, so we have to validate it as soon as possible
        # otherwise we crash
        if "capture_source" in data and not self.validate_camera_address_conflict(
            eye_id, data["capture_source"]
        ):
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
                shutil.copy(CONFIG_FILE_NAME, BACKUP_CONFIG_FILE_NAME)
            except shutil.SameFileError:
                pass
            except (OSError, IOError):
                pass
        with open(CONFIG_FILE_NAME, "w") as settings_file:
            json.dump(obj=self.model_dump(warnings=False), fp=settings_file)
        logger.info("Config saved successfully")

    def register_listener_callback(self, callback):
        logger.debug("Registering listener %s", callback)
        self._listeners.append(callback)

    def __notify_listeners(self, data: dict):
        for listener in self._listeners:
            listener(data)
