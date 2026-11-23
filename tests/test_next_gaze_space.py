"""Models stamped gaze_space=tan output the tangent of the gaze angle. The app
turns that into output gaze without a calibration, only applies a Smart Calib
fit to the kind of model it was made on, and sizes the gaze smoother's bands
to the model's units."""

import math
from types import SimpleNamespace

import pytest

from eye import EyeId
from next_processing import NextProcessingMixin
from next_smooth import GAZE_BAND
from next_stereo_model import GAZE_SPACE_TAN, NEXT_Stereo_cls

SETTINGS = SimpleNamespace(
    gui_gaze_yaw_max_deg=40.0,
    gui_gaze_pitch_up_deg=15.0,
    gui_gaze_pitch_down_deg=40.0,
    gui_flip_x_axis_left=False,
    gui_flip_x_axis_right=False,
    gui_flip_y_axis=False,
)
FIT_W, FIT_B = [0.676, -0.037, 0.021, 1.164, -0.003, 0.497], [0.004, 0.003]


class _Processor(NextProcessingMixin):
    def __init__(self, model="norm", fit=None, fit_space=None):
        self.eye_id = EyeId.LEFT
        self.settings = SETTINGS
        self._next_gaze_space = model
        self._next_smartcal_w, self._next_smartcal_b = fit if fit else (None, None)
        self._next_smartcal_warp = "angle" if fit else None
        self._next_smartcal_gaze_space = fit_space


def _tan(deg):
    return math.tan(math.radians(deg))


def test_tangent_model_without_a_fit_reads_as_angles():
    p = _Processor(model="tan")
    x, y, scaled = p._next_gaze_out(_tan(20.0), _tan(-20.0))
    assert scaled
    assert x == pytest.approx(_tan(20.0) / _tan(40.0))
    assert y == pytest.approx(-_tan(20.0) / _tan(40.0))
    # Up is a fraction of the smaller upward limit.
    assert p._next_gaze_out(0.0, _tan(15.0))[1] == pytest.approx(1.0)
    assert p._next_calibrate_flip(_tan(60.0), 0.0) == (1.0, 0.0)  # clipped to the limit


def test_position_model_without_a_fit_passes_through():
    assert _Processor()._next_gaze_out(0.3, -0.2) == (0.3, -0.2, False)
    assert _Processor()._next_calibrate_flip(0.3, -0.2) == (0.3, -0.2)


@pytest.mark.parametrize("model, fit_space", [("norm", None), ("norm", "norm"), ("tan", "tan")])
def test_a_fit_applies_to_the_kind_of_model_it_was_made_on(model, fit_space):
    p = _Processor(model=model, fit=(FIT_W, FIT_B), fit_space=fit_space)
    x, _y, scaled = p._next_gaze_out(0.5, 0.0)
    assert scaled and x == pytest.approx((0.676 * 0.5 + 0.004) / _tan(40.0))


@pytest.mark.parametrize("model, fit_space", [("tan", None), ("tan", "norm"), ("norm", "tan")])
def test_a_fit_from_the_other_kind_of_model_is_ignored(model, fit_space, caplog):
    p = _Processor(model=model, fit=(FIT_W, FIT_B), fit_space=fit_space)
    with caplog.at_level("WARNING"):
        first = p._next_gaze_out(0.2, 0.0)
        p._next_gaze_out(0.2, 0.0)
    assert sum("Re-run NEXT Smart Calib" in r.message for r in caplog.records) == 1  # said once
    unfitted = _Processor(model=model)._next_gaze_out(0.2, 0.0)
    assert first == unfitted


def test_smoother_bands_follow_the_model_units():
    runner = NEXT_Stereo_cls.__new__(NEXT_Stereo_cls)
    runner.init_eye_gaze_state()
    runner._set_smoother_scale(1.0)
    snap = runner._gaze_smoother.g["both"]
    assert (snap.tau, snap.d0, snap.d1) == pytest.approx(GAZE_BAND)
    runner.gaze_space = GAZE_SPACE_TAN
    runner._set_smoother_scale(1.0)
    assert snap.tau == pytest.approx(GAZE_BAND[0])  # time is not a gaze unit
    assert snap.d0 == pytest.approx(GAZE_BAND[1] * 0.5774) and snap.d1 == pytest.approx(GAZE_BAND[2] * 0.5774)
    assert runner._eye_gaze_snaps[0].d1 == pytest.approx(snap.d1)
    # The smoothing slider still scales time and band together.
    runner._set_smoother_scale(2.0)
    assert snap.tau == pytest.approx(2 * GAZE_BAND[0]) and snap.d1 == pytest.approx(2 * GAZE_BAND[2] * 0.5774)
