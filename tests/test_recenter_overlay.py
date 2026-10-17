"""Exercise the tracking path used when LEAP recenters its pupil coordinates."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import osc_calibrate_filter as calibration
from config import EyeTrackCameraConfig
from utils.calibration_elipse import CalibrationEllipse


@pytest.mark.parametrize("use_overlay", [False, True])
@pytest.mark.parametrize("eye_id", [calibration.EyeId.LEFT, calibration.EyeId.RIGHT])
def test_recenter_respects_overlay_setting_and_saves_center(
    monkeypatch, eyetrack_settings_config, use_overlay, eye_id
):
    settings = eyetrack_settings_config
    settings.gui_use_overlay_cal = use_overlay
    settings.gui_recenter_eyes = True
    config = EyeTrackCameraConfig(
        calib_evecs=[[1.0, 0.0], [0.0, 1.0]],
        calib_axes=[20.0, 15.0],
        calib_XOFF=100.0,
        calib_YOFF=100.0,
    )
    saved_centers = []
    processor = SimpleNamespace(
        settings=settings,
        config=config,
        cal=CalibrationEllipse(),
        eye_id=eye_id,
        calibration_start_time=None,
        should_print_calibration_warning=False,
        _recenter_armed_at=None,
        _recenter_delay_s=0.2,
        baseconfig=SimpleNamespace(
            save=lambda: saved_centers.append((config.calib_XOFF, config.calib_YOFF))
        ),
    )
    overlay = Mock()
    sound = Mock()
    monkeypatch.setattr(calibration, "center_overlay_calibrate", overlay)
    monkeypatch.setattr(calibration, "PlaySound", sound)
    monkeypatch.setattr(calibration.TrackingLogger, "get", lambda: None)
    now = iter([10.0, 10.3])
    monkeypatch.setattr(calibration.time, "perf_counter", lambda: next(now))

    # Frames update the center during the settling delay, then finish once.
    calibration.cal.cal_osc(processor, 110.0, 115.0, 0.0)
    overlay.assert_not_called()
    assert saved_centers == []
    assert settings.gui_recenter_eyes
    x, y, _ = calibration.cal.cal_osc(processor, 120.0, 125.0, 0.0)

    assert (x, y) == (0.0, 0.0)
    assert saved_centers == [(120.0, 125.0)]
    assert config.calib_evecs == [[1.0, 0.0], [0.0, 1.0]]
    assert config.calib_axes == [20.0, 15.0]
    assert not settings.gui_recenter_eyes
    assert processor._recenter_armed_at is None
    if use_overlay:
        overlay.assert_called_once_with(processor)
    else:
        overlay.assert_not_called()
    sound.assert_called_once()

    calibration.cal.cal_osc(processor, 120.0, 125.0, 0.0)
    assert len(saved_centers) == 1
    assert overlay.call_count == int(use_overlay)
