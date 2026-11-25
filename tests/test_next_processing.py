"""NEXT on the eye processor (next_processing): which model pass feeds each
eye and in which gaze mode, the frame it submits, gaze units and Smart Calib
fits, Y flips, lid/brow calibration, recenter and the squint hold."""

import math
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from eye import EyeId
from eye_processor import EyeProcessor
from next_eye_gaze import GAZE_MODE_DOMINANT, GAZE_MODE_FUSED, GAZE_MODE_INDEPENDENT
from next_processing import NextProcessingMixin
from next_stereo_model import SharedPass
from tests.next_stubs import next_processor

# Esotropia-like right eye: points 0.2 further toward +x than the left.
DEVIATION = np.array([0.2, 0.0])


def _image(seed=1):
    return np.random.default_rng(seed).integers(0, 256, (64, 80, 3), dtype=np.uint8)


# ── which pass feeds the eye ─────────────────────────────────────────────────


def _routing_processor(eye, mode=GAZE_MODE_FUSED, dominant="left", setup="standard", rotation=0):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = eye
    processor.config = SimpleNamespace(rotation_angle=rotation)
    processor.current_raw_frame = _image()
    processor.current_image_gray = np.zeros((64, 80), dtype=np.uint8)
    processor.current_capture_ts = 1000.0
    processor.settings = SimpleNamespace(
        gui_NEXT_gaze_mode=mode,
        gui_NEXT_dominant_eye=dominant,
        gui_min_cutoff=0.0004,
        gui_speed_coefficient=0.9,
        gui_setup_mode=setup,
        gui_model_variant="ETVR",
        gui_use_gpu=False,
    )
    processor._next_apply = Mock()
    processor._next_mode_changed = Mock()
    return processor


def _coord(served, supports_single_eye=True):
    return SimpleNamespace(
        supports_single_eye=supports_single_eye,
        submit=Mock(),
        run=Mock(return_value=(0.05, 0.06, 0.3, 0.4, 0.5)),
        peer_active=Mock(return_value=False),
        raw_gaze=Mock(return_value=(0.07, 0.08)),
        dfr_gaze=Mock(return_value=(0.075, 0.085)),
        expression_coupler=Mock(),
        served_pass=Mock(return_value=served),
    )


def _served():
    return SharedPass(
        1,
        np.zeros(8, dtype=np.float32),
        True,
        1.0,
        np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        np.array([0.11, 0.21, 0.31, 0.41], dtype=np.float32),
        np.array([0.12, 0.22, 0.32, 0.42], dtype=np.float32),
    )


@pytest.mark.parametrize("eye", [EyeId.LEFT, EyeId.RIGHT])
@pytest.mark.parametrize("hybrid_available", [True, False])
@pytest.mark.parametrize("setup", ["standard", "bigscreen"])
@pytest.mark.parametrize("rotation", [0, 90])
def test_processor_uses_hybrid_without_an_active_peer(monkeypatch, eye, hybrid_available, setup, rotation):
    processor = _routing_processor(eye, setup=setup, rotation=rotation)
    processor.next_runner = Mock()
    processor.next_runner.run.return_value = (0.2, 0.3, 0.4, 0.5, 0.6)
    processor.next_runner.raw_gaze = (0.25, 0.35)
    coord = _coord("pass", hybrid_available)
    coord.run.return_value = (0.1, 0.2, 0.3, 0.4, 0.5)
    coord.raw_gaze.return_value = (0.15, 0.25)
    coord.dfr_gaze.return_value = (0.16, 0.26)
    monkeypatch.setattr("next_processing.get_stereo_coordinator", lambda *args: coord)

    processor.NEXTM()

    coord.submit.assert_called_once()
    submitted_eye, submitted_frame, submitted_ts = coord.submit.call_args.args
    expected = processor.current_raw_frame
    if setup == "bigscreen":
        mid = expected.shape[1] // 2
        expected = expected[:, :mid] if eye == EyeId.LEFT else expected[:, mid:]
    if rotation:
        # This eye's half first, then turned upright (counter-clockwise, like the classical trackers).
        expected = cv2.rotate(expected, cv2.ROTATE_90_COUNTERCLOCKWISE)
    assert submitted_eye == eye
    assert submitted_ts == 1000.0
    np.testing.assert_array_equal(submitted_frame, expected)
    if hybrid_available:
        coord.peer_active.assert_not_called()
        coord.run.assert_called_once_with(eye, 0.0004, 0.9)
        processor.next_runner.run.assert_not_called()
        processor._next_apply.assert_called_once_with(
            *coord.run.return_value,
            raw_gaze=(0.15, 0.25),
            dfr_gaze=(0.16, 0.26),
            shared=(coord.expression_coupler, "pass"),
        )
        coord.served_pass.assert_called_once_with(eye)
    else:
        coord.run.assert_not_called()
        processor.next_runner.run.assert_called_once()
        processor._next_apply.assert_called_once_with(*processor.next_runner.run.return_value, raw_gaze=(0.25, 0.35))


def test_a_new_rotation_restarts_the_next_frame_history(monkeypatch):
    processor = _routing_processor(EyeId.LEFT)
    processor.next_runner = Mock()
    processor.next_runner.run.return_value = (0.2, 0.3, 0.4, 0.5, 0.6)
    coord = Mock(supports_single_eye=True)
    coord.run.return_value = (0.1, 0.2, 0.3, 0.4, 0.5)
    monkeypatch.setattr("next_processing.get_stereo_coordinator", lambda *args: coord)
    processor.NEXTM()
    processor.NEXTM()
    coord.reset_eye.assert_not_called()
    processor.config.rotation_angle = 270
    processor.NEXTM()
    coord.reset_eye.assert_called_once_with(EyeId.LEFT)
    processor.next_runner.reset_history.assert_called_once()
    assert coord.submit.call_args.args[1].shape[:2] == (80, 64)  # turned a quarter
    processor.NEXTM()
    coord.reset_eye.assert_called_once()


@pytest.mark.parametrize("eye", [EyeId.LEFT, EyeId.RIGHT])
def test_fused_mode_routes_the_shared_gaze_unchanged(monkeypatch, eye):
    processor = _routing_processor(eye, GAZE_MODE_FUSED)
    served = _served()
    coord = _coord(served)
    monkeypatch.setattr("next_processing.get_stereo_coordinator", lambda *args: coord)
    processor.NEXTM()
    processor._next_apply.assert_called_once_with(
        0.05,
        0.06,
        0.3,
        0.4,
        0.5,
        raw_gaze=(0.07, 0.08),
        dfr_gaze=(0.075, 0.085),
        shared=(coord.expression_coupler, served),
    )


@pytest.mark.parametrize(
    "mode,dominant,eye,gaze,raw",
    [
        (GAZE_MODE_INDEPENDENT, "left", EyeId.LEFT, (0.1, 0.2), (0.11, 0.21)),
        (GAZE_MODE_INDEPENDENT, "left", EyeId.RIGHT, (0.3, 0.4), (0.31, 0.41)),
        (GAZE_MODE_DOMINANT, "right", EyeId.LEFT, (0.3, 0.4), (0.31, 0.41)),
        (GAZE_MODE_DOMINANT, "left", EyeId.RIGHT, (0.1, 0.2), (0.11, 0.21)),
    ],
)
def test_per_eye_modes_route_the_monocular_gaze(monkeypatch, mode, dominant, eye, gaze, raw):
    processor = _routing_processor(eye, mode, dominant)
    served = _served()
    coord = _coord(served)
    monkeypatch.setattr("next_processing.get_stereo_coordinator", lambda *args: coord)
    processor.NEXTM()
    args, kwargs = processor._next_apply.call_args
    assert args[:2] == pytest.approx(gaze)
    assert args[2:] == (0.3, 0.4, 0.5)
    assert kwargs["raw_gaze"] == pytest.approx(raw)
    assert kwargs["dfr_gaze"] == pytest.approx((raw[0] + 0.01, raw[1] + 0.01))
    reference = (0.3, 0.4) if dominant == "right" else (0.1, 0.2)
    assert kwargs["recenter_gaze"] == pytest.approx(reference)
    assert kwargs["shared"] == (coord.expression_coupler, served)


def test_per_eye_mode_without_per_eye_channels_stays_fused(monkeypatch):
    # Legacy 8-output stereo: nothing to route, so the fused gaze is kept.
    processor = _routing_processor(EyeId.RIGHT, GAZE_MODE_INDEPENDENT)
    served = SharedPass(1, np.zeros(8, dtype=np.float32), True, 1.0)
    coord = _coord(served)
    monkeypatch.setattr("next_processing.get_stereo_coordinator", lambda *args: coord)
    processor.NEXTM()
    processor._next_apply.assert_called_once_with(
        0.05,
        0.06,
        0.3,
        0.4,
        0.5,
        raw_gaze=(0.07, 0.08),
        dfr_gaze=(0.075, 0.085),
        shared=(coord.expression_coupler, served),
    )


# ── gaze units and Smart Calib fits ──────────────────────────────────────────
# Models stamped gaze_space=tan output the tangent of the gaze angle. The app
# turns that into output gaze without a calibration, and only applies a Smart
# Calib fit to the kind of model it was made on.

GAZE_LIMITS = SimpleNamespace(
    gui_gaze_yaw_max_deg=40.0,
    gui_gaze_pitch_up_deg=15.0,
    gui_gaze_pitch_down_deg=40.0,
    gui_flip_x_axis_left=False,
    gui_flip_x_axis_right=False,
    gui_flip_y_axis=False,
)
FIT_W, FIT_B = [0.676, -0.037, 0.021, 1.164, -0.003, 0.497], [0.004, 0.003]


class _GazeOut(NextProcessingMixin):
    def __init__(self, model="norm", fit=None, fit_space=None):
        self.eye_id = EyeId.LEFT
        self.settings = GAZE_LIMITS
        self._next_gaze_space = model
        self._next_smartcal_w, self._next_smartcal_b = fit if fit else (None, None)
        self._next_smartcal_warp = "angle" if fit else None
        self._next_smartcal_gaze_space = fit_space


def _tan(deg):
    return math.tan(math.radians(deg))


def test_tangent_model_without_a_fit_reads_as_angles():
    p = _GazeOut(model="tan")
    x, y, scaled = p._next_gaze_out(_tan(20.0), _tan(-20.0))
    assert scaled
    assert x == pytest.approx(_tan(20.0) / _tan(40.0))
    assert y == pytest.approx(-_tan(20.0) / _tan(40.0))
    # Up is a fraction of the smaller upward limit.
    assert p._next_gaze_out(0.0, _tan(15.0))[1] == pytest.approx(1.0)
    assert p._next_calibrate_flip(_tan(60.0), 0.0) == (1.0, 0.0)  # clipped to the limit


def test_position_model_without_a_fit_passes_through():
    assert _GazeOut()._next_gaze_out(0.3, -0.2) == (0.3, -0.2, False)
    assert _GazeOut()._next_calibrate_flip(0.3, -0.2) == (0.3, -0.2)


@pytest.mark.parametrize("model, fit_space", [("norm", None), ("norm", "norm"), ("tan", "tan")])
def test_a_fit_applies_to_the_kind_of_model_it_was_made_on(model, fit_space):
    p = _GazeOut(model=model, fit=(FIT_W, FIT_B), fit_space=fit_space)
    x, _y, scaled = p._next_gaze_out(0.5, 0.0)
    assert scaled and x == pytest.approx((0.676 * 0.5 + 0.004) / _tan(40.0))


@pytest.mark.parametrize("model, fit_space", [("tan", None), ("tan", "norm"), ("norm", "tan")])
def test_a_fit_from_the_other_kind_of_model_is_ignored(model, fit_space, caplog):
    p = _GazeOut(model=model, fit=(FIT_W, FIT_B), fit_space=fit_space)
    with caplog.at_level("WARNING"):
        first = p._next_gaze_out(0.2, 0.0)
        p._next_gaze_out(0.2, 0.0)
    assert sum("Re-run NEXT Smart Calib" in r.message for r in caplog.records) == 1  # said once
    unfitted = _GazeOut(model=model)._next_gaze_out(0.2, 0.0)
    assert first == unfitted


# ── flips and lid/brow calibration ───────────────────────────────────────────


def test_next_postprocessing_only_flips_y_when_requested():
    processor = next_processor()
    processor._next_apply(0.25, 0.6, 0.5, 0.5, 0.0)
    assert processor.out_y == 0.6

    processor = next_processor(gui_flip_y_axis=True)
    processor._next_apply(0.25, 0.6, 0.5, 0.5, 0.0)
    assert processor.out_y == -0.6


@pytest.mark.parametrize("eye, flip", [(EyeId.LEFT, "gui_flip_x_axis_left"), (EyeId.RIGHT, "gui_flip_x_axis_right")])
def test_each_eye_flips_x_on_its_own_setting(eye, flip):
    flipped = next_processor(eye, **{flip: True})
    other = next_processor(eye, **{"gui_flip_x_axis_left": True, "gui_flip_x_axis_right": True, flip: False})
    flipped._next_apply(0.25, 0.6, 0.5, 0.5, 0.0)
    other._next_apply(0.25, 0.6, 0.5, 0.5, 0.0)
    assert (flipped.out_x, other.out_x) == (-0.25, 0.25)


def test_next_lid_brow_calibration_anchors_the_captured_neutral():
    processor = next_processor()
    processor._next_smartcal_lid_neutral = 0.5
    processor._next_smartcal_brow_neutral = 0.25

    # Feeding the captured neutral back in must produce the target outputs.
    processor._next_apply(0.0, 0.0, 0.25, 0.5, 0.0)
    assert round(processor.eyeopen, 3) == 0.75
    assert round(processor.next_eyebrow, 3) == 0.5

    # The ends of the range stay put: a full blink still reaches 0.
    processor._next_apply(0.0, 0.0, 1.0, 1.0, 0.0)
    assert round(processor.eyeopen, 3) == 1.0
    assert round(processor.next_eyebrow, 3) == 1.0
    processor._next_apply(0.0, 0.0, 0.0, 0.0, 0.0)
    assert processor.eyeopen == 0.0
    assert round(processor.next_eyebrow, 3) == 0.0


def test_next_lid_brow_calibration_is_skipped_when_disabled():
    processor = next_processor(gui_NEXT_calib_lids_brows=False)
    processor._next_smartcal_lid_neutral = 0.5
    processor._next_smartcal_brow_neutral = 0.25

    processor._next_apply(0.0, 0.0, 0.25, 0.5, 0.0)

    assert round(processor.eyeopen, 3) == 0.5
    assert round(processor.next_eyebrow, 3) == 0.25


def test_next_lid_brow_calibration_is_a_noop_before_it_runs():
    processor = next_processor()

    processor._next_apply(0.0, 0.0, 0.25, 0.5, 0.0)

    assert round(processor.eyeopen, 3) == 0.5
    assert round(processor.next_eyebrow, 3) == 0.25


def test_a_squeeze_reads_as_a_more_closed_eye():
    open_eye, squinting = next_processor(), next_processor()
    open_eye._next_apply(0.0, 0.0, 0.5, 0.6, 0.0)
    squinting._next_apply(0.0, 0.0, 0.5, 0.6, 0.5)
    assert squinting.eyeopen == pytest.approx(open_eye.eyeopen / 2)
    assert squinting.squeeze == 0.5


# ── recenter ─────────────────────────────────────────────────────────────────


def test_recenter_keeps_the_deviation_in_independent_mode():
    left_gaze, right_gaze = (0.05, -0.02), (0.25, -0.02)
    left = next_processor(EyeId.LEFT, gui_NEXT_calib_lids_brows=False, gui_recenter_eyes=True)
    right = next_processor(EyeId.RIGHT, gui_NEXT_calib_lids_brows=False, gui_recenter_eyes=True)
    left._next_apply(*left_gaze, 0.5, 0.8, 0.0, recenter_gaze=left_gaze)
    right._next_apply(*right_gaze, 0.5, 0.8, 0.0, recenter_gaze=left_gaze)
    assert (left.out_x, left.out_y) == pytest.approx((0.0, 0.0))
    assert (right.out_x, right.out_y) == pytest.approx(tuple(DEVIATION))


def test_recenter_without_reference_zeroes_each_eye():
    processor = next_processor(EyeId.RIGHT, gui_NEXT_calib_lids_brows=False, gui_recenter_eyes=True)
    processor._next_apply(0.25, -0.02, 0.5, 0.8, 0.0)
    assert (processor.out_x, processor.out_y) == pytest.approx((0.0, 0.0))


def test_recenter_holds_for_both_eyes_then_clears_and_keeps_its_offset(monkeypatch):
    now = [10.0]
    monkeypatch.setattr("next_processing.time.perf_counter", lambda: now[0])
    processor = next_processor(gui_NEXT_calib_lids_brows=False, gui_recenter_eyes=True)

    processor._next_apply(0.3, 0.1, 0.5, 0.8, 0.0)  # arms the recenter
    now[0] += 0.1
    processor._next_apply(0.3, 0.1, 0.5, 0.8, 0.0)  # within the hold: the other eye can still catch it
    assert processor.settings.gui_recenter_eyes
    now[0] += 0.15
    processor._next_apply(0.3, 0.1, 0.5, 0.8, 0.0)
    assert not processor.settings.gui_recenter_eyes

    processor._next_apply(0.5, 0.1, 0.5, 0.8, 0.0)  # the offset stays after the hold
    assert (processor.out_x, processor.out_y) == pytest.approx((0.2, 0.0))


# ── squint Y hold ────────────────────────────────────────────────────────────


class _Peer:
    def __init__(self, peer_openness):
        self.value = peer_openness

    def peer_openness(self, _eye_id, _served):
        return self.value


def _squint_processor(mode=GAZE_MODE_FUSED, enabled=True, openness=0.0):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = EyeId.LEFT
    processor.eyeopen = openness
    processor.settings = SimpleNamespace(gui_NEXT_squint_y_hold=enabled, gui_NEXT_gaze_mode=mode)
    return processor


def _held_y(processor, shared=None):
    processor.eyeopen, closed = 1.0, processor.eyeopen
    processor._next_squint_y(0.5, shared)
    processor.eyeopen = closed
    return processor._next_squint_y(-0.5, shared)


def test_squint_hold_is_off_by_default():
    processor = _squint_processor()
    processor.settings = SimpleNamespace()
    assert processor._next_squint_y(-0.5, None) == -0.5


def test_processor_holds_gaze_once_enabled():
    assert _held_y(_squint_processor()) == pytest.approx(0.5, abs=0.05)


def test_a_wink_does_not_freeze_the_shared_gaze():
    shared = (_Peer(0.9), object())
    assert _held_y(_squint_processor(), shared) == -0.5


def test_independent_eyes_only_trust_their_own_lid():
    shared = (_Peer(0.9), object())
    held = _held_y(_squint_processor(GAZE_MODE_INDEPENDENT), shared)
    assert held == pytest.approx(0.5, abs=0.05)
