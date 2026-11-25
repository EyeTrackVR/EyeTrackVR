"""The classical trackers' gaze calibration (utils.calibration_elipse): fitting
the ellipse, loading a saved one, normalising a pupil position against it, and
the saved values a corrupted settings file can hold."""

import numpy as np
import pytest

from config import EyeTrackCameraConfig
from utils.calibration_elipse import CalibrationEllipse

GRID = [(x, y) for x in range(90, 111, 5) for y in range(90, 111, 5)]


def _fitted(samples=GRID):
    cal = CalibrationEllipse()
    for x, y in samples:
        cal.add_sample(x, y)
    cal.fit_ellipse()
    return cal


# ── fit ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("samples", [[], [(100, 100)]], ids=["no-samples", "one-sample"])
def test_fit_ellipse_needs_two_samples(samples):
    cal = CalibrationEllipse()
    for x, y in samples:
        cal.add_sample(x, y)

    evecs, axes = cal.fit_ellipse()

    # The (0, 0) marker is what cal_osc checks before overwriting a saved fit.
    assert (evecs, axes) == (0, 0)
    assert not cal.fitted


def test_fit_ellipse_is_axis_aligned_around_the_mean():
    xs = [90, 95, 100, 105, 110]
    cal = _fitted([(x, 50 + (x - 100) / 5) for x in xs])
    np.testing.assert_array_equal(cal.evecs, np.eye(2))
    np.testing.assert_allclose(cal.center, [100.0, 50.0])
    np.testing.assert_allclose(cal.axes, [2.5 * np.std(xs), 2.5 * np.std([48, 49, 50, 51, 52])])
    assert cal.fitted


def test_a_still_eye_still_gives_a_usable_fit():
    cal = _fitted([(100, 100), (100, 100)])
    assert np.all(cal.axes > 0)  # never a zero radius to divide by
    assert cal.normalize((100, 100)) == (0.0, 0.0)


def test_a_new_sample_invalidates_the_fit():
    cal = _fitted()
    cal.add_sample(120, 120)
    assert not cal.fitted and cal.normalize((100, 100)) == (0.0, 0.0)


# ── saved calibration ────────────────────────────────────────────────────────


def test_init_from_save_with_valid_data():
    cal = CalibrationEllipse()
    assert cal.init_from_save([[1.0, 0.0], [0.0, 1.0]], [10.0, 8.0])
    assert cal.fitted
    np.testing.assert_array_equal(cal.axes, [10.0, 8.0])


@pytest.mark.parametrize(
    "axes",
    [[0.0, 0.0], [10.0, float("nan")], [10.0], "abc", None],
    ids=["zero", "nan", "wrong-shape", "text", "none"],
)
def test_init_from_save_rejects_unusable_axes(axes):
    cal = CalibrationEllipse()
    assert not cal.init_from_save([[1.0, 0.0], [0.0, 1.0]], axes)
    assert not cal.fitted


def test_init_from_save_ignores_saved_rotation_shape():
    """Saved evecs are legacy data; axis-aligned calibration ignores them."""
    cal = CalibrationEllipse()

    assert cal.init_from_save([[1.0, 0.0]], [10.0, 8.0])

    assert cal.fitted
    np.testing.assert_array_equal(cal.evecs, np.eye(2))


# ── normalize ────────────────────────────────────────────────────────────────


def test_normalize_with_invalid_calibration():
    assert CalibrationEllipse().normalize((100, 100)) == (0.0, 0.0)


def test_normalize_with_zero_calibration():
    cal = CalibrationEllipse()
    cal.init_from_save([[0, 0], [0, 0]], [0, 0])
    assert cal.normalize((100, 100)) == (0.0, 0.0)


def test_normalize_with_corrupted_data_returns_safe_default():
    """Zero axes that got past loading must not divide by zero."""
    cal = CalibrationEllipse()
    cal.evecs = np.array([[0, 0], [0, 0]])
    cal.axes = np.array([0, 0])
    cal.fitted = True

    assert cal.normalize((100, 100)) == (0.0, 0.0)


def test_normalize_with_valid_calibration():
    cal = _fitted()
    rx, ry = cal.axes * cal.scale_factor

    assert cal.normalize((100, 100)) == (0.0, 0.0)  # the centre of the samples
    # Image x grows to the right, gaze x to the left; image y grows downward,
    # gaze y upward.
    assert cal.normalize((100 + rx / 2, 100)) == pytest.approx((-0.5, 0.0))
    assert cal.normalize((100, 100 - ry / 2)) == pytest.approx((0.0, 0.5))


def test_normalize_measures_from_the_recentred_point_and_clips_unless_asked():
    cal = _fitted()
    rx, _ = cal.axes * cal.scale_factor

    assert cal.normalize((120, 100), (120, 100)) == (0.0, 0.0)
    assert cal.normalize((100 - 3 * rx, 100)) == (1.0, 0.0)
    assert cal.normalize((100 - 3 * rx, 100), clip=False) == pytest.approx((3.0, 0.0))


# ── values in the settings file ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "stored, kept",
    [
        (0, None),  # what a corrupted eyetrack_settings.json held
        (None, None),
        ([15.5, 12.3], [15.5, 12.3]),
        (np.array([15.5, 12.3]), [15.5, 12.3]),
    ],
    ids=["integer-zero", "none", "list", "numpy"],
)
def test_saved_calibration_values_load_as_lists_or_none(stored, kept):
    config = EyeTrackCameraConfig(calib_axes=stored, calib_XOFF=74.36, calib_YOFF=36.55)
    assert config.calib_axes == kept
    assert (config.calib_XOFF, config.calib_YOFF) == (74.36, 36.55)


@pytest.mark.parametrize("stored", [0, None], ids=["integer-zero", "none"])
def test_a_file_without_a_usable_fit_loads_uncalibrated(stored):
    # Integer zeros are what the reported corrupted eyetrack_settings.json held.
    config = EyeTrackCameraConfig(calib_axes=stored, calib_evecs=stored)
    assert config.calib_axes is None and config.calib_evecs is None


def test_saved_calibration_round_trips_into_the_ellipse():
    config = EyeTrackCameraConfig(calib_axes=[15.5, 12.3], calib_evecs=[[0.9, 0.1], [0.1, 0.9]])
    assert isinstance(config.calib_evecs, list) and isinstance(config.calib_axes, list)
    cal = CalibrationEllipse()
    assert cal.init_from_save(config.calib_evecs, config.calib_axes)
    np.testing.assert_array_equal(cal.axes, [15.5, 12.3])
