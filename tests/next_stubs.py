"""Stand-ins shared by the NEXT tests: filters and sessions that pass values
straight through, a shared-model runner without an ONNX session, and an eye
processor with only what NEXT's post-processing reads."""

from queue import Queue
from types import SimpleNamespace

import numpy as np

import one_euro_filter
from eye import EyeId
from eye_processor import EyeProcessor
from next_eye_coupling import DEFAULT_SYNC
from next_model import TimedMedian
from next_stereo_model import NEXT_Stereo_cls


class IdentityFilter:
    """A One-Euro filter that changes nothing (keeps the runner's
    min_cutoff/beta bookkeeping working)."""

    def __init__(self, size):
        self.min_cutoff = np.zeros(size, dtype=np.float32)
        self.beta = np.zeros(size, dtype=np.float32)

    def __call__(self, values):
        return np.asarray(values, dtype=np.float32)


class StaticSession:
    """An ONNX session that always answers ``values``."""

    def __init__(self, values):
        self.values = np.asarray([values], dtype=np.float32)

    def run(self, _outputs, _inputs):
        return [self.values.copy()]


def stereo_runner(monkeypatch=None, clock=None, step_s=1 / 120, gaze_y_sign=1.0):
    """The shared model's post-processing without a model. With ``clock`` (a
    one-item list holding the time), every filter reads that time."""
    if clock is not None:
        monkeypatch.setattr(one_euro_filter, "perf_counter", lambda: clock[0])
        monkeypatch.setattr("next_stereo_model.time.perf_counter", lambda: clock[0])
    model = NEXT_Stereo_cls.__new__(NEXT_Stereo_cls)
    model.gaze_y_sign = gaze_y_sign
    model.one_euro_filter = one_euro_filter.OneEuroFilter(np.zeros(8, dtype=np.float32), step_s=step_s)
    model._brow_l_window, model._brow_r_window = TimedMedian(5), TimedMedian(5)
    model._gaze_x_window, model._gaze_y_window = TimedMedian(3), TimedMedian(3)
    model._last_expr = {EyeId.LEFT: None, EyeId.RIGHT: None}
    model.init_eye_gaze_state()
    return model


def next_processor(eye=EyeId.LEFT, **settings):
    """An EyeProcessor holding just the state _next_apply reads: no Smart Calib
    fit, no recenter, model lid/brow calibration on, eyes coupled at the default
    strength. ``settings`` override the defaults."""
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = eye
    processor.settings = SimpleNamespace(
        **{
            "gui_NEXT_calib_lids_brows": True,
            "gui_NEXT_lid_sync": DEFAULT_SYNC,
            "gui_NEXT_brow_sync": DEFAULT_SYNC,
            "gui_flip_x_axis_left": False,
            "gui_flip_x_axis_right": False,
            "gui_flip_y_axis": False,
            "gui_recenter_eyes": False,
            "leap_lid_close_threshold_left": 0.1,
            "leap_lid_widen_threshold_left": 0.9,
            "leap_lid_close_threshold_right": 0.1,
            "leap_lid_widen_threshold_right": 0.9,
            **settings,
        }
    )
    processor.config = SimpleNamespace(
        next_classic_calibration_active=False, calib_evecs=None, calib_axes=None, calib_XOFF=None
    )
    processor.calibration_start_time = None
    processor._ellipse_collect_active = False
    processor._next_smartcal_trace = None
    processor._next_smartcal_w = None
    processor._next_smartcal_b = None
    processor._next_smartcal_warp = None
    processor._next_smartcal_lid_neutral = None
    processor._next_smartcal_brow_neutral = None
    processor._next_recenter_offset_x = 0.0
    processor._next_recenter_offset_y = 0.0
    processor._next_recenter_armed_at = None
    processor._recenter_delay_s = 0.2
    processor.out_x = 0.0
    processor.out_y = 0.0
    processor.osc_queue = Queue()
    return processor
