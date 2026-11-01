from queue import Queue
from types import SimpleNamespace

import numpy as np
import pytest

from eye import EyeId
from eye_processor import EyeProcessor, NextExpressionTransform
from next_eye_coupling import (
    DEFAULT_SYNC,
    SYNC_MAX,
    NextExpressionCoupler,
    brow_sync_range,
    coupling_weight,
    lid_sync_range,
)
from next_stereo_model import SharedPass, StereoNextCoordinator, stereo_model_file

STEP_S = 1.0 / 60.0
# (sync_below, separate_above) gap ranges at the default slider position
LID = lid_sync_range(DEFAULT_SYNC)
BROW = brow_sync_range(DEFAULT_SYNC)


def _result(lid_l, lid_r, brow_l=0.5, brow_r=0.5, sq_l=0.0, sq_r=0.0):
    return np.array([brow_l, lid_l, sq_l, brow_r, lid_r, sq_r, 0.0, 0.0], dtype=np.float32)


class _Passes:
    """Feeds a coupler one shared pass per call, STEP_S apart."""

    def __init__(self, left=None, right=None):
        self.coupler = NextExpressionCoupler()
        self.coupler.publish(EyeId.LEFT, left or NextExpressionTransform())
        self.coupler.publish(EyeId.RIGHT, right or NextExpressionTransform())
        self.pass_id = 0
        self.ts = 100.0

    def shared(self, result, both=True, dt=STEP_S):
        self.pass_id += 1
        self.ts += dt
        return SharedPass(self.pass_id, result, both, self.ts)

    def __call__(self, result, both=True, dt=STEP_S):
        shared = self.shared(result, both, dt)
        left = self.coupler.couple(EyeId.LEFT, shared, LID, BROW)
        right = self.coupler.couple(EyeId.RIGHT, shared, LID, BROW)
        return left, right


def test_neutral_jitter_collapses_to_the_mean():
    passes = _Passes()
    rng = np.random.default_rng(0)
    for _ in range(120):
        lid_l, lid_r = 0.75 + rng.uniform(-0.04, 0.04), 0.72 + rng.uniform(-0.04, 0.04)
        brow_l, brow_r = 0.5 + rng.uniform(-0.03, 0.03), 0.47 + rng.uniform(-0.03, 0.03)
        (left, right) = passes(_result(lid_l, lid_r, brow_l, brow_r))
    # Both eyes read the same value: the mean of the two raw readings.
    assert left == pytest.approx(right, abs=1e-4)
    assert left[0] == pytest.approx((lid_l + lid_r) / 2, abs=1e-4)
    assert left[1] == pytest.approx((brow_l + brow_r) / 2, abs=1e-4)


def test_coupling_engages_gradually_instead_of_snapping():
    passes = _Passes()
    first, _ = passes(_result(0.75, 0.70))
    assert first[0] == pytest.approx(0.75)  # first pass: no history, weight 0
    left, _ = passes(_result(0.75, 0.70))
    assert 0.725 < left[0] < 0.75


@pytest.mark.parametrize("closed", ["left", "right"])
def test_wink_passes_through(closed):
    passes = _Passes()
    for _ in range(60):
        passes(_result(0.75, 0.74))
    lids = (0.02, 0.75) if closed == "left" else (0.75, 0.02)
    left, right = passes(_result(*lids))
    assert (left[0], right[0]) == pytest.approx(lids)


@pytest.mark.parametrize("raised", [0.85, 0.15])
def test_one_sided_brow_raise_passes_through(raised):
    passes = _Passes()
    for _ in range(60):
        passes(_result(0.75, 0.75, 0.5, 0.5))
    left, right = passes(_result(0.75, 0.75, 0.5, raised))
    assert (left[1], right[1]) == pytest.approx((0.5, raised))
    # The lids are still coupled while the brows are not.
    assert left[0] == pytest.approx(right[0])


def test_missing_eye_is_unaffected_from_the_start():
    passes = _Passes()
    for _ in range(30):
        left, right = passes(_result(0.75, 0.0, 0.5, 0.0), both=False)
        assert (left[0], left[1]) == pytest.approx((0.75, 0.5))


def test_missing_eye_releases_the_present_eye():
    passes = _Passes()
    for _ in range(60):
        passes(_result(0.75, 0.70))
    # The right camera drops out: its held 0.70 must not keep dragging the
    # left eye, which follows its own reading again within a few frames.
    outputs = [passes(_result(0.80, 0.70), both=False)[0][0] for _ in range(60)]
    assert outputs[-1] == pytest.approx(0.80, abs=1e-4)
    assert all(abs(b - a) < 0.02 for a, b in zip(outputs, outputs[1:]))


def test_blend_is_continuous_in_the_gap():
    passes = _Passes()
    for _ in range(10):
        passes(_result(0.75, 0.75), dt=10.0)
    gaps = np.linspace(0.0, 0.5, 501)
    lefts = []
    for gap in gaps:
        # A long step lets the weight settle on its target every pass.
        left, right = passes(_result(0.75, 0.75 - gap), dt=10.0)
        lefts.append(left[0])
        assert left[0] - right[0] == pytest.approx(gap * (1.0 - coupling_weight(gap, *LID)), abs=1e-6)
    steps = np.abs(np.diff(lefts))
    assert steps.max() < 3 * (gaps[1] - gaps[0])
    assert lefts[0] == pytest.approx(0.75)
    assert lefts[-1] == pytest.approx(0.75)  # past release: own value
    assert coupling_weight(LID[0], *LID) == 1.0
    assert coupling_weight(LID[1], *LID) == 0.0


def test_wink_onset_never_snaps():
    passes = _Passes()
    for _ in range(60):
        passes(_result(0.75, 0.75))
    # The largest shift coupling ever applies: weight x half the gap.
    gaps = np.linspace(0.0, LID[1], 1001)
    max_shift = max(coupling_weight(g, *LID) * g / 2 for g in gaps)
    assert max_shift < 0.075
    previous = (0.75, 0.75)
    step = 0.75 / 8
    for lid in np.linspace(0.75, 0.0, 9):  # a ~150 ms wink
        left, right = passes(_result(float(lid), 0.75))
        # The weight releases at once, so the closing eye catches up with its
        # input by at most that shift on top of the input's own step.
        assert abs(left[0] - previous[0]) <= step + max_shift
        assert abs(right[0] - previous[1]) <= max_shift
        previous = (left[0], right[0])
    assert previous == pytest.approx((0.0, 0.75))


def test_an_eye_served_a_pass_late_gets_the_same_answer():
    in_order, late = _Passes(), _Passes()
    for passes in (in_order, late):
        for _ in range(30):
            passes(_result(0.75, 0.70))
    expected = in_order(_result(0.74, 0.71))

    shared = late.shared(_result(0.74, 0.71))
    right = late.coupler.couple(EyeId.RIGHT, shared, LID, BROW)
    late(_result(0.60, 0.70))  # the peer already moved on to a newer pass
    left = late.coupler.couple(EyeId.LEFT, shared, LID, BROW)
    assert (left, right) == expected


def test_waits_for_both_transforms():
    coupler = NextExpressionCoupler()
    coupler.publish(EyeId.LEFT, NextExpressionTransform())
    assert coupler.couple(EyeId.LEFT, SharedPass(0, _result(0.7, 0.75), True, 1.0), LID, BROW) is None


def test_zero_separate_turns_a_channel_off():
    assert coupling_weight(0.0, 0.0, 0.0) == 0.0
    assert coupling_weight(0.01, 0.1, 0.0) == 0.0


def test_equal_ends_switch_hard_at_that_gap():
    assert coupling_weight(0.19, 0.2, 0.2) == 1.0
    assert coupling_weight(0.2, 0.2, 0.2) == 0.0


def test_default_slider_gives_the_chosen_ranges():
    assert LID == pytest.approx((0.12, 0.30))
    assert BROW == pytest.approx((0.10, 0.25))


def test_slider_zero_is_off_and_higher_syncs_more():
    for sync_range in (lid_sync_range, brow_sync_range):
        assert coupling_weight(0.05, *sync_range(0)) == 0.0
        weights = [coupling_weight(0.15, *sync_range(s)) for s in range(0, SYNC_MAX + 1, 10)]
        assert weights == sorted(weights)
        assert weights[-1] == 1.0


def test_strongest_sync_still_lets_a_wink_and_a_one_sided_raise_through():
    assert coupling_weight(0.70, *lid_sync_range(SYNC_MAX)) == 0.0
    assert coupling_weight(0.50, *brow_sync_range(SYNC_MAX)) == 0.0


def test_settings_default_on_and_reject_out_of_range():
    import pydantic

    from config import EyeTrackSettingsConfig
    from settings.modules.TrackingAlgorithmModule import TrackingAlgorithmValidationModel

    defaults = EyeTrackSettingsConfig()
    assert defaults.gui_NEXT_lid_sync == defaults.gui_NEXT_brow_sync == DEFAULT_SYNC > 0
    values = {f: getattr(defaults, f) for f in TrackingAlgorithmValidationModel.model_fields}
    TrackingAlgorithmValidationModel(**values)
    for bad in (-1, SYNC_MAX + 1):
        with pytest.raises(pydantic.ValidationError):
            TrackingAlgorithmValidationModel(**{**values, "gui_NEXT_lid_sync": bad})


def test_coupling_compares_calibrated_values():
    # Different resting raw readings per eye, which Smart Calib anchors both to
    # 0.75 / 0.5: compared raw they'd be released (0.2 apart), calibrated they
    # are equal and stay that way.
    passes = _Passes(
        NextExpressionTransform(lid_neutral=0.6, brow_neutral=0.4),
        NextExpressionTransform(lid_neutral=0.8, brow_neutral=0.6),
    )
    for _ in range(60):
        left, right = passes(_result(0.6, 0.8, 0.4, 0.6))
    assert left == pytest.approx((0.75, 0.5))
    assert right == pytest.approx((0.75, 0.5))


def _processor(eye_id, sync=DEFAULT_SYNC):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = eye_id
    processor.settings = SimpleNamespace(
        gui_NEXT_calib_lids_brows=True,
        gui_NEXT_lid_sync=sync,
        gui_NEXT_brow_sync=sync,
        gui_flip_x_axis_left=False,
        gui_flip_x_axis_right=False,
        gui_flip_y_axis=False,
        gui_recenter_eyes=False,
        leap_lid_close_threshold_left=0.1,
        leap_lid_widen_threshold_left=0.9,
        leap_lid_close_threshold_right=0.1,
        leap_lid_widen_threshold_right=0.9,
    )
    processor._next_smartcal_active_dot = None
    processor._next_smartcal_w = None
    processor._next_smartcal_b = None
    processor._next_smartcal_warp = None
    processor._next_smartcal_lid_neutral = None
    processor._next_smartcal_brow_neutral = None
    processor._next_recenter_offset_x = 0.0
    processor._next_recenter_offset_y = 0.0
    processor._next_recenter_armed_at = None
    processor.out_x = 0.0
    processor.out_y = 0.0
    processor.osc_queue = Queue()
    return processor


def _apply_pair(processors, coupler, shared):
    for eye, processor in processors.items():
        base = 0 if eye == EyeId.LEFT else 3
        brow, lid, squeeze = (float(v) for v in shared.result[base : base + 3])
        processor._next_apply(0.0, 0.0, brow, lid, squeeze, shared=(coupler, shared))
    return {eye: (p.eyeopen, p.next_eyebrow) for eye, p in processors.items()}


@pytest.mark.parametrize("sync", [DEFAULT_SYNC, 0])
def test_processors_sync_unless_the_slider_is_off(sync):
    coupler = NextExpressionCoupler()
    processors = {eye: _processor(eye, sync) for eye in (EyeId.LEFT, EyeId.RIGHT)}
    out = None
    for k in range(60):
        out = _apply_pair(processors, coupler, SharedPass(k, _result(0.76, 0.70, 0.52, 0.48), True, k * STEP_S))
    if sync:
        assert out[EyeId.LEFT] == pytest.approx((0.73, 0.5), abs=1e-3)
        assert out[EyeId.RIGHT] == pytest.approx((0.73, 0.5), abs=1e-3)
    else:
        assert out[EyeId.LEFT] == pytest.approx((0.76, 0.52), abs=1e-6)
        assert out[EyeId.RIGHT] == pytest.approx((0.70, 0.48), abs=1e-6)


def test_processor_wink_still_snaps_closed():
    coupler = NextExpressionCoupler()
    processors = {eye: _processor(eye) for eye in (EyeId.LEFT, EyeId.RIGHT)}
    for k in range(60):
        _apply_pair(processors, coupler, SharedPass(k, _result(0.75, 0.75), True, k * STEP_S))
    out = _apply_pair(processors, coupler, SharedPass(60, _result(0.05, 0.75), True, 60 * STEP_S))
    assert out[EyeId.LEFT][0] == 0.0
    assert out[EyeId.RIGHT][0] == pytest.approx(0.75)


def test_processor_near_closed_pair_snaps_together():
    # Coupled before the closed snap: a blink reads closed on both eyes or
    # neither, instead of one eye snapping and the other hovering.
    coupler = NextExpressionCoupler()
    processors = {eye: _processor(eye) for eye in (EyeId.LEFT, EyeId.RIGHT)}
    for k in range(60):
        out = _apply_pair(processors, coupler, SharedPass(k, _result(0.05, 0.10), True, k * STEP_S))
    assert out[EyeId.LEFT][0] == out[EyeId.RIGHT][0] == 0.0


def test_coordinator_marks_missing_eye_passes():
    coord = StereoNextCoordinator(stereo_model_file("ETVR"))
    image = np.random.default_rng(1).integers(0, 256, (64, 80, 3), dtype=np.uint8)
    coord.submit(EyeId.LEFT, image, None)
    coord.run(EyeId.LEFT, 0.0, 0.0)
    left_only = coord.served_pass(EyeId.LEFT)
    assert not left_only.both_eyes
    assert coord.served_pass(EyeId.RIGHT) is None

    coord.submit(EyeId.RIGHT, image, None)
    coord.run(EyeId.RIGHT, 0.0, 0.0)
    both = coord.served_pass(EyeId.RIGHT)
    assert both.both_eyes and both.pass_id > left_only.pass_id
    # The left eye reusing that pass is served the same one.
    coord.run(EyeId.LEFT, 0.0, 0.0)
    assert coord.served_pass(EyeId.LEFT) is both
