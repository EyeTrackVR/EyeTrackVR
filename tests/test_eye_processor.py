"""EyeProcessor: the order the enabled trackers are tried in and the same-frame
fallback when one fails, runners freed when their tracker is turned off,
frames LEAP has no result for, pupil axes for dilation, and which eyebrow
model reports while NEXT is the tracker."""

import math
from types import SimpleNamespace

import numpy as np
import pytest

import eye_processor as eye_processor_module
from eye import EyeId, EyeInfoOrigin
from eye_processor import EyeProcessor

CLASSICAL = ("AHRAC", "AHSF", "HSF", "HSRAC", "DADDY", "LEAP", "RANSAC3D")
# The method each tracker runs as, in the order they are tried.
METHODS = ("AHRACM", "AHSFM", "HSFM", "HSRACM", "DADDYM", "LEAPM", "RANSAC3DM")


def _settings(*enabled, **extra):
    flags = {f"gui_{name}": name in enabled for name in (*CLASSICAL, "NEXT")}
    flags.update(
        gui_NEXT_BSB=False,
        gui_LEAP_lid=False,
        gui_skip_autoradius=False,
        gui_HSF_radius_left=10,
        gui_HSF_radius_right=10,
        gui_model_variant="ETVR",
        gui_use_gpu=False,
    )
    flags.update(extra)
    return SimpleNamespace(**flags)


class _Runner:
    def __init__(self, *args):
        self.stopped = False

    def shutdown(self):
        self.stopped = True


@pytest.fixture
def trackers(monkeypatch):
    """Each tracker method replaced by one that records it ran and fails
    unless its name is in ``trackers.working``; model-backed runners stubbed."""
    for runner in ("External_Run_HSF", "External_Run_DADDY", "External_Run_LEAP"):
        monkeypatch.setattr(eye_processor_module, runner, _Runner)
    state = SimpleNamespace(ran=[], working=set())

    def tracker(name):
        def run(self):
            state.ran.append(name)
            if name not in state.working:
                self.failed += 1

        return run

    for name in METHODS:
        monkeypatch.setattr(EyeProcessor, name, tracker(name))
    return state


def _processor(settings, eye=EyeId.LEFT):
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.eye_id = eye
    proc.settings = settings
    proc.config = SimpleNamespace()
    proc.baseconfig = SimpleNamespace()
    proc.hsf_runner = proc.ahsf_runner = proc.daddy_runner = proc.next_runner = proc.leap_runner = None
    proc.failed = 0
    return proc


def _frame(proc):
    proc._rebuild_algorithm_slots()
    proc.ALGOSELECT()


# ── tracker order and fallback ───────────────────────────────────────────────


def test_failing_trackers_fall_through_in_order_within_one_frame(trackers):
    proc = _processor(_settings(*CLASSICAL))

    _frame(proc)

    assert trackers.ran == list(METHODS)
    assert proc.failed == 0  # all failed: the next frame starts from the first again


def test_the_first_tracker_that_works_ends_the_frame(trackers):
    trackers.working = {"HSRACM", "RANSAC3DM"}
    proc = _processor(_settings(*CLASSICAL))

    _frame(proc)

    assert trackers.ran == ["AHRACM", "AHSFM", "HSFM", "HSRACM"]


def test_the_next_frame_starts_with_the_tracker_that_worked(trackers):
    trackers.working = {"RANSAC3DM"}
    proc = _processor(_settings("HSF", "RANSAC3D"))
    _frame(proc)
    trackers.ran.clear()

    _frame(proc)

    assert trackers.ran == ["RANSAC3DM"]


def test_only_enabled_trackers_run(trackers):
    proc = _processor(_settings("LEAP", "HSF"))

    _frame(proc)

    assert trackers.ran == ["HSFM", "LEAPM"]


def test_no_tracker_enabled_is_a_quiet_frame(trackers):
    proc = _processor(_settings())
    proc.failed = 5  # left over from a tracker that has since been turned off

    _frame(proc)

    assert trackers.ran == [] and proc.failed == 0


def test_turning_a_tracker_off_frees_its_runner(trackers):
    settings = _settings("LEAP", "HSF", "DADDY")
    proc = _processor(settings)
    _frame(proc)
    leap_runner = proc.leap_runner
    assert proc.hsf_runner is not None and proc.daddy_runner is not None

    settings.gui_LEAP = settings.gui_HSF = settings.gui_DADDY = False
    _frame(proc)

    assert leap_runner.stopped and proc.leap_runner is None
    assert proc.hsf_runner is None and proc.daddy_runner is None


def test_leap_lid_alone_keeps_the_leap_runner_without_tracking_gaze(trackers):
    proc = _processor(_settings("HSF", gui_LEAP_lid=True))

    _frame(proc)

    assert proc.leap_runner is not None
    assert trackers.ran == ["HSFM"]


@pytest.mark.parametrize("variant", ["ETVR", "BSB", "PSVR"])
def test_processor_does_not_allocate_unused_per_eye_sessions(monkeypatch, variant):
    coord = SimpleNamespace(supports_single_eye=True)
    asked = []

    def get_coord(*args):
        asked.append(args)
        return coord

    def allocate(*args):
        raise AssertionError("Hybrid must share the coordinator's session")

    monkeypatch.setattr("eye_processor.get_stereo_coordinator", get_coord)
    monkeypatch.setattr("eye_processor.External_Run_NEXT", allocate)
    settings = _settings("NEXT", gui_model_variant=variant)
    for eye in (EyeId.LEFT, EyeId.RIGHT):
        processor = _processor(settings, eye)
        processor._rebuild_algorithm_slots()
        assert processor.next_runner is None
        assert processor.NEXTM in processor._algorithm_slots
    assert len(asked) == 2


# ── LEAP frames without a result ─────────────────────────────────────────────


def test_leapm_skips_update_when_leap_has_no_result():
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.eye_id = EyeId.LEFT
    proc.settings = SimpleNamespace(gui_use_gpu=False, gui_LEAP_lid=True)
    proc.current_image_gray = np.zeros((10, 10), dtype=np.uint8)
    proc.current_image_gray_clean = proc.current_image_gray
    proc.leap_runner = SimpleNamespace(run=lambda img, clean, gpu: (img, None, None, None))
    proc.rawx, proc.rawy = 12.0, 34.0
    proc.out_x, proc.out_y = 0.3, -0.2
    proc.eyeopen = 0.8

    proc.LEAPM()

    assert (proc.rawx, proc.rawy) == (12.0, 34.0)
    assert (proc.out_x, proc.out_y) == (0.3, -0.2)
    assert proc.eyeopen == 0.8
    assert proc.current_algorithm == EyeInfoOrigin.LEAP


# ── pupil axes for dilation ──────────────────────────────────────────────────


def test_dilation_axes_follow_radius_for_non_ransac_trackers():
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.current_algorithm = EyeInfoOrigin.RANSAC
    proc.pupil_width, proc.pupil_height = 30.0, 12.0
    proc.radius = 7
    proc._ensure_pupil_axes_for_dilation()
    assert (proc.pupil_width, proc.pupil_height) == (30.0, 12.0)

    # Switching to HSF: stale RANSAC axes must not freeze the input.
    proc.current_algorithm = EyeInfoOrigin.HSF
    proc._ensure_pupil_axes_for_dilation()
    assert (proc.pupil_width, proc.pupil_height) == (14.0, 14.0)
    proc.radius = 11
    proc._ensure_pupil_axes_for_dilation()
    assert (proc.pupil_width, proc.pupil_height) == (22.0, 22.0)


@pytest.mark.parametrize("radius", [None, "x", 0, 0.4])
def test_a_missing_radius_gives_a_default_pupil_size(radius):
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.current_algorithm = EyeInfoOrigin.HSF
    proc.radius = radius
    proc._ensure_pupil_axes_for_dilation()
    assert (proc.pupil_width, proc.pupil_height) == (20.0, 20.0)


# ── eyebrow: only NEXT reports one ───────────────────────────────────────────


@pytest.mark.parametrize("next_on,expected", [(True, 0.77), (False, None)])
def test_eyebrow_comes_from_next_or_is_absent(next_on, expected):
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.settings = SimpleNamespace(gui_NEXT=next_on, gui_NEXT_BSB=False)
    proc.next_eyebrow = 0.77

    brow = proc._current_eyebrow()

    assert math.isnan(brow) if expected is None else brow == expected
