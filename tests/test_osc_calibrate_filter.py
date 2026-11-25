"""cal_osc, the classical trackers' calibrated output: a calibration run, a
stop without samples (Recenter Eyes), the recenter delay, and frames without a
pupil position."""

import time
from types import SimpleNamespace

import pytest

import osc_calibrate_filter as calibration
from config import EyeTrackCameraConfig
from utils.calibration_elipse import CalibrationEllipse

SAVED_EVECS = [[0.9, 0.1], [0.1, 0.9]]
SAVED_AXES = [15.5, 12.3]


@pytest.fixture
def chimes(monkeypatch):
    """Every completion chime cal_osc plays."""
    played = []
    monkeypatch.setattr(calibration, "PlaySound", lambda *args: played.append(args))
    return played


def _processor(settings, eye_id=calibration.EyeId.LEFT, **config):
    config = EyeTrackCameraConfig(
        **{"calib_evecs": SAVED_EVECS, "calib_axes": SAVED_AXES, "calib_XOFF": 100.0, "calib_YOFF": 100.0, **config}
    )
    saves = []
    return SimpleNamespace(
        settings=settings,
        config=config,
        cal=CalibrationEllipse(),
        eye_id=eye_id,
        calibration_start_time=None,
        should_print_calibration_warning=True,
        _recenter_armed_at=None,
        _recenter_delay_s=0.2,
        one_euro_filter=lambda point: point,  # outputs read straight off the calibration
        baseconfig=SimpleNamespace(save=lambda: saves.append((config.calib_XOFF, config.calib_YOFF))),
        saves=saves,
    )


# ── calibration runs ─────────────────────────────────────────────────────────


def test_stopping_a_calibration_without_samples_keeps_the_saved_fit(eyetrack_settings_config, chimes):
    """Recenter Eyes / Stop Calibration without Start: only the centre moves."""
    proc = _processor(eyetrack_settings_config)
    proc.calibration_start_time = time.time() - 60  # the run has already ended

    calibration.cal.cal_osc(proc, 120.0, 130.0, 0.0)

    assert proc.config.calib_evecs == SAVED_EVECS
    assert proc.config.calib_axes == SAVED_AXES
    assert proc.saves == [(120.0, 130.0)]
    assert proc.calibration_start_time is None
    assert chimes == []  # nothing was calibrated


def test_a_calibration_run_saves_its_fit_and_centre(eyetrack_settings_config, chimes):
    proc = _processor(eyetrack_settings_config)
    proc.calibration_start_time = time.time()
    for x in range(90, 111, 5):
        for y in range(80, 121, 10):
            calibration.cal.cal_osc(proc, float(x), float(y), 0.0)
    assert proc.saves == []  # still collecting

    proc.calibration_start_time = time.time() - 60
    calibration.cal.cal_osc(proc, 300.0, 300.0, 0.0)

    assert proc.config.calib_axes != SAVED_AXES and proc.config.calib_axes[0] < proc.config.calib_axes[1]
    assert proc.config.calib_evecs == [[1.0, 0.0], [0.0, 1.0]]
    assert proc.saves == [(100.0, 100.0)]  # centred on the samples, not the last frame
    assert proc.config.next_classic_calibration_active is False
    assert len(chimes) == 1


def test_gaze_keeps_using_the_saved_fit_while_a_run_collects(eyetrack_settings_config):
    proc = _processor(eyetrack_settings_config)
    before = calibration.cal.cal_osc(proc, 110.0, 100.0, 0.0)[:2]

    proc.calibration_start_time = time.time()
    during = calibration.cal.cal_osc(proc, 110.0, 100.0, 0.0)[:2]

    assert during == before and before[0] != 0.0


def test_an_uncalibrated_eye_asks_for_calibration_once(eyetrack_settings_config, caplog):
    proc = _processor(eyetrack_settings_config, calib_evecs=0, calib_axes=0)

    outputs = [calibration.cal.cal_osc(proc, 110.0, 95.0, 0.0)[:2] for _ in range(3)]

    assert outputs == [(0.0, 0.0)] * 3
    assert sum("please calibrate" in r.getMessage() for r in caplog.records) == 1


def test_a_frame_without_a_pupil_repeats_the_last_output(eyetrack_settings_config):
    proc = _processor(eyetrack_settings_config)
    last = calibration.cal.cal_osc(proc, 110.0, 95.0, 0.0)

    assert calibration.cal.cal_osc(proc, None, None, 0.0) == pytest.approx(last)


def test_flip_settings_mirror_this_eyes_output(eyetrack_settings_config):
    plain = calibration.cal.cal_osc(_processor(eyetrack_settings_config), 110.0, 95.0, 0.0)[:2]
    eyetrack_settings_config.gui_flip_x_axis_left = True
    eyetrack_settings_config.gui_flip_y_axis = True

    flipped = calibration.cal.cal_osc(_processor(eyetrack_settings_config), 110.0, 95.0, 0.0)[:2]
    right_eye = calibration.cal.cal_osc(_processor(eyetrack_settings_config, calibration.EyeId.RIGHT), 110.0, 95.0, 0.0)

    assert flipped == pytest.approx((-plain[0], -plain[1]))
    assert right_eye[:2] == pytest.approx((plain[0], -plain[1]))  # x flips per eye, y for both


# ── recenter ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("use_overlay", [False, True])
@pytest.mark.parametrize("eye_id", [calibration.EyeId.LEFT, calibration.EyeId.RIGHT])
def test_recenter_respects_overlay_setting_and_saves_center(
    monkeypatch, eyetrack_settings_config, chimes, use_overlay, eye_id
):
    """The tracking path used when LEAP recenters its pupil coordinates."""
    settings = eyetrack_settings_config
    settings.gui_use_overlay_cal = use_overlay
    settings.gui_recenter_eyes = True
    proc = _processor(settings, eye_id, calib_evecs=[[1.0, 0.0], [0.0, 1.0]], calib_axes=[20.0, 15.0])
    overlay_runs = []
    monkeypatch.setattr(calibration, "center_overlay_calibrate", overlay_runs.append)
    now = [10.0]
    monkeypatch.setattr(calibration.time, "perf_counter", lambda: now[0])

    # Frames update the center during the settling delay, then finish once.
    calibration.cal.cal_osc(proc, 110.0, 115.0, 0.0)
    assert overlay_runs == []
    assert proc.saves == []
    assert settings.gui_recenter_eyes
    now[0] += 0.3
    x, y, _ = calibration.cal.cal_osc(proc, 120.0, 125.0, 0.0)

    assert (x, y) == (0.0, 0.0)
    assert proc.saves == [(120.0, 125.0)]
    assert proc.config.calib_evecs == [[1.0, 0.0], [0.0, 1.0]]
    assert proc.config.calib_axes == [20.0, 15.0]
    assert not settings.gui_recenter_eyes
    assert proc._recenter_armed_at is None
    assert overlay_runs == ([proc] if use_overlay else [])
    assert len(chimes) == 1

    calibration.cal.cal_osc(proc, 120.0, 125.0, 0.0)
    assert len(proc.saves) == 1
    assert len(overlay_runs) == int(use_overlay)
