import os
import socket
import sys

import pytest
import config
from config import (
    EyeTrackConfig,
    EyeTrackCameraConfig,
    EyeTrackSettingsConfig,
)
from utils import logging_utils, user_data


# Real locations, captured once at collection, before any test patches them.
_REAL_CONFIG_PATHS = {
    "CONFIG_FILE_NAME": config.CONFIG_FILE_NAME,
    "BACKUP_CONFIG_FILE_NAME": config.BACKUP_CONFIG_FILE_NAME,
}


@pytest.fixture(autouse=True)
def isolated_user_data(monkeypatch, tmp_path_factory):
    """Every test gets an empty user data folder of its own and runs from an
    empty working directory, so nothing a test saves (settings, calibration
    statistics, IBO/EBPD images, captures, logs, the VR manifest) lands in the
    developer's real EyeTrackVR folder or in the checkout, and nothing already
    there leaks into a test. A test that patches one of these names itself
    still wins: its patch is applied after this one and undone before it.
    Returns the folder."""
    folder = tmp_path_factory.mktemp("user_data")
    # user_data_path()/user_data_dir() read this at call time, which covers
    # ransac, intensity_based_openness, ellipse_based_pupil_dilation,
    # data_collection.capture_dir() and logging_utils.
    monkeypatch.setattr(user_data, "_USER_DATA_DIR", str(folder))
    # Copies taken at import (ovr.openvr_service, which needs the optional
    # openvr package, so it is only patched once something imported it).
    for module in list(sys.modules.values()):
        if module is not user_data and isinstance(getattr(module, "_USER_DATA_DIR", None), str):
            monkeypatch.setattr(module, "_USER_DATA_DIR", str(folder))
    for name, real in _REAL_CONFIG_PATHS.items():
        isolated = str(folder / os.path.basename(real))
        monkeypatch.setattr(config, name, isolated)
        # Modules that imported the name itself (settings.base_settings) keep their own copy.
        for module in list(sys.modules.values()):
            if module is not config and getattr(module, name, None) == real:
                monkeypatch.setattr(module, name, isolated)
    # Log files and the tracking-log switch live beside the app, i.e. in the checkout.
    monkeypatch.setattr(logging_utils, "_app_root", lambda: folder)
    workdir = tmp_path_factory.mktemp("cwd")
    monkeypatch.chdir(workdir)
    return folder


class _FakeRegistry:
    """Dict-backed stand-in for openxr_layer_registration.WindowsRegistry."""

    def __init__(self):
        self.data = {}

    def values(self):
        return dict(self.data)

    def set(self, name, value):
        self.data[name] = value

    def delete(self, name):
        del self.data[name]


@pytest.fixture(autouse=True)
def no_real_vr_config(monkeypatch, tmp_path_factory):
    """Starting OSCManager syncs the SteamVR driver registration and the OpenXR layer; never
    let a test touch this machine's openvrpaths.vrpath, OpenXR registry keys or layer folder."""
    from osc import foveation_gaze_sender
    from ovr import openxr_layer_registration, steamvr_driver_registration

    monkeypatch.setattr(foveation_gaze_sender, "_pm4a_yaw_bias_tan", 0.0)  # no headset in tests

    monkeypatch.setattr(steamvr_driver_registration, "openvrpaths_file", lambda: None)
    monkeypatch.setattr(openxr_layer_registration, "WindowsRegistry", _FakeRegistry)
    implicit = tmp_path_factory.mktemp("implicit.d")
    monkeypatch.setattr(openxr_layer_registration, "implicit_layer_dir", lambda: implicit)


@pytest.fixture(autouse=True)
def silent(monkeypatch):
    """No test plays a sound: a calibration that succeeds in a test would
    otherwise play its completion chime through the desktop's speakers. The
    stand-in takes what winsound.PlaySound takes, so a wrong call still fails."""
    from utils import misc_utils

    played = misc_utils.PlaySound

    def mute(sound, flags, /):
        pass

    monkeypatch.setattr(misc_utils, "PlaySound", mute)
    # Modules that imported the function itself keep their own reference.
    for module in list(sys.modules.values()):
        if getattr(module, "PlaySound", None) is played:
            monkeypatch.setattr(module, "PlaySound", mute)


@pytest.fixture(autouse=True)
def own_overlay_ports(monkeypatch):
    """Every test talks to stand-in overlays on free ports of its own, never
    on the real overlay's 2112 and 2113: a running EyeTrackVR or overlay on
    this machine would otherwise take the test's signals, or get its
    commands."""
    import data_collection
    import data_collection_passes
    from utils import overlay_launch

    sockets = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(2)]
    for sock in sockets:
        sock.bind(("127.0.0.1", 0))
    signal_port, cmd_port = (sock.getsockname()[1] for sock in sockets)
    for sock in sockets:
        sock.close()
    monkeypatch.setattr(overlay_launch, "OVERLAY_SIGNAL_PORT", signal_port)
    for module in (overlay_launch, data_collection, data_collection_passes):
        monkeypatch.setattr(module, "OVERLAY_CMD_PORT", cmd_port)


@pytest.fixture()
def eyetrack_settings_config():
    return EyeTrackSettingsConfig(
        gui_flip_x_axis_left=False,
        gui_flip_x_axis_right=False,
        gui_flip_y_axis=False,
        gui_RANSAC3D=False,
        gui_HSF=False,
        gui_BLINK=False,
        gui_HSRAC=False,
        gui_AHRAC=False,
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
        gui_recenter_eyes=False,
        tracker_single_eye=2,
        gui_AHRACP=1,
        gui_AHSFP=2,
        gui_HSRACP=3,
        gui_HSFP=4,
        gui_DADDYP=5,
        gui_RANSAC3DP=6,
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
        leap_calibration_duration=15,
        calibration_duration=15,
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
        gui_LEAP_lid=False,
        gui_osc_vrcft_v1=False,
        gui_osc_vrcft_v2=False,
        gui_vrc_native=False,
        # Legacy OSC protocol tests assert SimpleUDPClient output. Keep the
        # embedded pyVRCFT transport disabled in these fixtures.
        gui_pyvrcft=False,
        gui_pupil_dilation=True,
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


@pytest.fixture
def count_calls(monkeypatch):
    """``count_calls(owner, name)`` wraps ``owner.name`` for this test and
    returns the list that gets one entry per call, e.g. to check a tracker does
    not recompute np.percentile over its whole window every frame."""

    def count(owner, name):
        calls = []
        real = getattr(owner, name)

        def counted(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        monkeypatch.setattr(owner, name, counted)
        return calls

    return count


@pytest.fixture(autouse=True)
def isolated_gaze_outputs(monkeypatch, tmp_path):
    """Foveation gaze is on by default, so any test that starts an OSCManager
    publishes gaze: keep every test off the real shared memory block, mutex and
    UDP port 9020 that a running EyeTrackVR / PimaxMagic4All use."""
    from tests.osc_helpers import isolate_gaze_outputs

    isolate_gaze_outputs(monkeypatch, tmp_path)
