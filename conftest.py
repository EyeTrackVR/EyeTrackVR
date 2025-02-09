import pytest
from config import (
    EyeTrackConfig,
    EyeTrackCameraConfig,
    EyeTrackSettingsConfig,
)


@pytest.fixture()
def eyetrack_settings_config():
    return EyeTrackSettingsConfig(
        gui_flip_x_axis_left=False,
        gui_flip_x_axis_right=False,
        gui_flip_y_axis=False,
        gui_RANSAC3D=False,
        gui_HSF=False,
        gui_BLOB=False,
        gui_BLINK=False,
        gui_HSRAC=False,
        gui_AHSFRAC=False,
        gui_AHSF=False,
        gui_DADDY=False,
        gui_LEAP=True,
        gui_HSF_radius=15,
        gui_HSF_radius_left=10,
        gui_HSF_radius_right=10,
        gui_min_cutoff="0.0004",
        gui_speed_coefficient="0.9",
        gui_osc_address="127.0.0.1",
        gui_osc_port=8889,
        gui_osc_receiver_port=9001,
        gui_osc_recenter_address="/avatar/parameters/etvr_recenter",
        gui_osc_recalibrate_address="/avatar/parameters/etvr_recalibrate",
        gui_blob_maxsize=25.0,
        gui_blob_minsize=10.0,
        gui_recenter_eyes=False,
        tracker_single_eye=2,
        gui_threshold=65,
        gui_AHSFRACP=1,
        gui_AHSFP=2,
        gui_HSRACP=3,
        gui_HSFP=4,
        gui_DADDYP=5,
        gui_RANSAC3DP=6,
        gui_BLOBP=7,
        gui_LEAPP=8,
        gui_IBO=True,
        gui_skip_autoradius=False,
        gui_thresh_add=11,
        gui_update_check=False,
        gui_ROSC=False,
        gui_circular_crop_right=False,
        gui_circular_crop_left=False,
        ibo_filter_samples=400,
        ibo_average_output_samples=0,
        ibo_fully_close_eye_threshold=0.3,
        calibration_samples=600,
        osc_right_eye_close_address="/avatar/parameters/RightEyeLidExpandedSqueeze",
        osc_left_eye_close_address="/avatar/parameters/LeftEyeLidExpandedSqueeze",
        osc_left_eye_x_address="/avatar/parameters/LeftEyeX",
        osc_right_eye_x_address="/avatar/parameters/RightEyeX",
        osc_eyes_y_address="/avatar/parameters/EyesY",
        osc_invert_eye_close=False,
        gui_RANSACBLINK=False,
        gui_right_eye_dominant=False,
        gui_left_eye_dominant=False,
        gui_outer_side_falloff=False,
        gui_eye_dominant_diff_thresh=0.3,
        gui_legacy_ransac=False,
        gui_legacy_ransac_thresh_right=80,
        gui_legacy_ransac_thresh_left=80,
        gui_LEAP_lid=False,
        gui_osc_vrcft_v1=False,
        gui_osc_vrcft_v2=False,
        gui_vrc_native=False,
        gui_pupil_dilation=True,

        #EyeTune
        gui_eyetune_maxin=1,
        gui_eyetune_maxout=1,
        gui_eyetune_maxup=1,
        gui_eyetune_maxdown=1,
        #Smart Inversion Tracking
        gui_smartinversion_enabled=False,
        gui_smartinversion_select_right=True,
        gui_smartinversion_frame_count=10,
        gui_smartinversion_smoothing_rate=0.025,
        gui_smartinversion_minthresh=0.3,
        gui_smartinversion_rotation_clamp=1.0,
    )


@pytest.fixture()
def eyetrack_camera_config():
    return EyeTrackCameraConfig(
        rotation_angle=250,
        roi_window_x=67,
        roi_window_y=27,
        roi_window_w=96,
        roi_window_h=117,
        focal_length=30,
        capture_source="http://192.168.0.31/",
        calib_XMAX=122.5,
        calib_XMIN=38.0,
        calib_YMAX=118.0,
        calib_YMIN=6.0,
        calib_XOFF=40.0,
        calib_YOFF=63.0,
        calibration_points=[],
    )


@pytest.fixture()
def main_config(eyetrack_camera_config, eyetrack_settings_config):
    return EyeTrackConfig(
        right_eye=eyetrack_camera_config,
        left_eye=eyetrack_camera_config,
        settings=eyetrack_settings_config,
        eye_display_id=0,
    )


@pytest.fixture()
def main_config_v1_params(main_config):
    main_config.settings.gui_osc_vrcft_v1 = True
    return main_config


@pytest.fixture()
def main_config_v2_params(main_config):
    main_config.settings.gui_osc_vrcft_v2 = True
    return main_config


@pytest.fixture()
def main_config_native_params(main_config):
    main_config.settings.gui_vrc_native = True
    return main_config
