from queue import Queue
from types import SimpleNamespace

import cv2
import numpy as np

from config import (
    CURRENT_CONFIG_VERSION,
    EyeTrackSettingsConfig,
    _migrate_config_dict,
)
from eye import EyeId
from eye_processor import EyeProcessor, next_eyelid_tuning_active


def _processor(*, next_active: bool, setup_mode: str = "etvr", eye_id=EyeId.LEFT):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.settings = SimpleNamespace(
        gui_NEXT=next_active,
        gui_NEXT_BSB=False,
        gui_setup_mode=setup_mode,
    )
    processor.eye_id = eye_id
    processor.image_queue_outgoing = Queue(maxsize=2)
    processor._preview_min_interval_s = 0.0
    processor._preview_last_emit_ts = 0.0
    processor.previous_image = None
    processor.previous_rotation = None
    processor.config = SimpleNamespace(rotation_angle=37)
    return processor


def _visualized_stack(processor, threshold):
    processor.output_images_and_update(threshold, object())
    return processor.image_queue_outgoing.get_nowait()[0]


def test_next_visualizer_uses_raw_uncropped_unrotated_frame():
    processor = _processor(next_active=True)
    raw = np.zeros((12, 20, 3), dtype=np.uint8)
    raw[:, :10] = (10, 40, 200)
    raw[:, 10:] = (180, 30, 5)
    processor.current_raw_frame = raw
    processor.current_image = np.full((5, 6, 3), 255, dtype=np.uint8)
    processor.current_image_gray = np.full((5, 6), 255, dtype=np.uint8)

    stack = _visualized_stack(processor, np.full((5, 6), 123, dtype=np.uint8))
    expected = cv2.resize(
        cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY),
        (150, 150),
        interpolation=cv2.INTER_AREA,
    )

    np.testing.assert_array_equal(stack[:, :150], expected)
    np.testing.assert_array_equal(stack[:, 150:], expected)
    assert processor.config.rotation_angle == 37


def test_next_bigscreen_visualizer_uses_only_the_selected_eye_half():
    processor = _processor(
        next_active=True, setup_mode="bigscreen", eye_id=EyeId.RIGHT
    )
    raw = np.zeros((8, 18, 3), dtype=np.uint8)
    raw[:, :9] = (0, 0, 20)
    raw[:, 9:] = (0, 0, 220)
    processor.current_raw_frame = raw
    processor.current_image = raw
    processor.current_image_gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)

    stack = _visualized_stack(processor, processor.current_image_gray.copy())
    expected = cv2.resize(
        cv2.cvtColor(raw[:, 9:], cv2.COLOR_BGR2GRAY),
        (150, 150),
        interpolation=cv2.INTER_AREA,
    )

    np.testing.assert_array_equal(stack[:, :150], expected)


def test_non_next_visualizer_restores_cropped_rotated_working_image():
    processor = _processor(next_active=False)
    processor.current_raw_frame = np.zeros((12, 20, 3), dtype=np.uint8)
    processor.current_image = np.full((5, 6, 3), 71, dtype=np.uint8)
    processor.current_image_gray = np.full((5, 6), 71, dtype=np.uint8)
    threshold = np.full((5, 6), 29, dtype=np.uint8)

    stack = _visualized_stack(processor, threshold)

    assert np.all(stack[:, :150] == 71)
    assert np.all(stack[:, 150:] == 29)


def test_next_does_not_apply_or_replace_saved_classical_crop():
    processor = _processor(next_active=True, setup_mode="bigscreen")
    processor.config.roi_window_x = 23
    processor.config.roi_window_y = 17
    processor.config.roi_window_w = 91
    processor.config.roi_window_h = 73
    processor.config.bigscreen_auto_crop_frame = None
    processor.current_image = np.zeros((12, 20, 3), dtype=np.uint8)

    processor._maybe_apply_bigscreen_default_crop()

    assert (
        processor.config.roi_window_x,
        processor.config.roi_window_y,
        processor.config.roi_window_w,
        processor.config.roi_window_h,
    ) == (23, 17, 91, 73)
    assert processor.config.bigscreen_auto_crop_frame is None


def test_next_manual_eyelid_tuning_activates_only_off_defaults():
    settings = SimpleNamespace(
        leap_lid_close_threshold_left=0.1,
        leap_lid_widen_threshold_left=0.9,
        leap_lid_close_threshold_right=0.1,
        leap_lid_widen_threshold_right=0.9,
    )

    assert not next_eyelid_tuning_active(settings, EyeId.LEFT)
    assert not next_eyelid_tuning_active(settings, EyeId.RIGHT)

    settings.leap_lid_close_threshold_left = 0.15

    assert next_eyelid_tuning_active(settings, EyeId.LEFT)
    assert not next_eyelid_tuning_active(settings, EyeId.RIGHT)


def test_next_calibrates_via_smart_calib_by_default():
    settings = EyeTrackSettingsConfig()

    # The legacy ellipse path is off, which is what routes Start Calibration to
    # the Smart Calib overlay and lets the fitted transform be applied.
    assert settings.gui_NEXT_calibration is False
    assert settings.gui_NEXT is True


def test_config_migration_hands_next_calibration_to_smart_calib():
    raw = {"version": 4, "settings": {"gui_NEXT": True, "gui_NEXT_calibration": True}}

    migrated = _migrate_config_dict(raw)

    assert migrated["version"] == CURRENT_CONFIG_VERSION
    assert migrated["settings"]["gui_NEXT_calibration"] is False


def test_config_migration_preserves_explicit_legacy_next_calibration():
    raw = {
        "version": 2,
        "settings": {"gui_NEXT_calibration": True},
        "left_eye": {
            "calib_axes": [1.0, 2.0],
            "calib_evecs": [[1.0, 0.0], [0.0, 1.0]],
            "calib_XOFF": 3.0,
        },
        "right_eye": {},
    }

    migrated = _migrate_config_dict(raw)

    assert migrated["version"] == CURRENT_CONFIG_VERSION
    assert migrated["left_eye"]["next_classic_calibration_active"] is True
    assert migrated["right_eye"]["next_classic_calibration_active"] is False
