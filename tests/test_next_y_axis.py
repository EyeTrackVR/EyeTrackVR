from collections import deque
from queue import Queue
from types import SimpleNamespace

import numpy as np

from eye import EyeId
from eye_processor import EyeProcessor
from next_model import NEXT_cls
from next_stereo_model import NEXT_Stereo_cls


class _IdentityFilter:
    def __init__(self, size):
        self.min_cutoff = np.zeros(size, dtype=np.float32)
        self.beta = np.zeros(size, dtype=np.float32)

    def __call__(self, values):
        return values


class _StaticSession:
    def __init__(self, values):
        self.values = np.asarray([values], dtype=np.float32)

    def run(self, _outputs, _inputs):
        return [self.values.copy()]


def test_mono_next_preserves_model_y_axis():
    model = NEXT_cls.__new__(NEXT_cls)
    model.input_size = 2
    model.raw_input = True
    model.temporal_frames = 1
    model.input_dtype = np.float32
    model.uses_directml = False
    model.input_name = "input"
    model.ort_session = _StaticSession([0.1, 0.2, 0.3, 0.4, 0.65])
    model.one_euro_filter = _IdentityFilter(5)
    model._brow_window = deque(maxlen=5)
    model._gaze_x_window = deque(maxlen=3)
    model._gaze_y_window = deque(maxlen=3)

    _, gaze_y, _, _, _ = model.run(np.zeros((2, 2, 3), dtype=np.uint8))

    assert gaze_y == np.float32(0.65)


def _stereo_model(*, gaze_y_sign=1.0):
    model = NEXT_Stereo_cls.__new__(NEXT_Stereo_cls)
    model.input_size = 2
    model.raw_input = True
    model.temporal_frames = 1
    model.frame_stride = 2
    model.input_dtype = np.float32
    model.uses_directml = False
    model.input_name = "input"
    model.ort_session = _StaticSession(
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, -0.65]
    )
    model.gaze_y_sign = gaze_y_sign
    model.one_euro_filter = _IdentityFilter(8)
    model._brow_l_window = deque(maxlen=5)
    model._brow_r_window = deque(maxlen=5)
    model._gaze_x_window = deque(maxlen=3)
    model._gaze_y_window = deque(maxlen=3)
    model._last_expr = {EyeId.LEFT: None, EyeId.RIGHT: None}
    return model


def _stereo_run(model):
    """Both eyes present, so no expression hold kicks in."""
    raw = model.forward(np.zeros((1, 6, 2, 2), dtype=np.float32))
    valid = {EyeId.LEFT: True, EyeId.RIGHT: True}
    return model.postprocess(raw, valid, 0.0, 0.0)


def test_stereo_next_preserves_model_y_axis():
    # No gaze_y_axis metadata, or gaze_y_axis=up (BSB stereo): already the app
    # convention, so the model's Y is passed through untouched.
    assert _stereo_run(_stereo_model())[7] == np.float32(-0.65)


def test_stereo_next_normalizes_y_down_models():
    # A stereo export declaring gaze_y_axis=down (ETVR stereo, trained on the
    # newer screen-space contract) is negated onto the app convention, so
    # switching between the mono and stereo model can't flip Y.
    assert _stereo_run(_stereo_model(gaze_y_sign=-1.0))[7] == np.float32(0.65)


def test_stereo_next_holds_expressions_for_a_blacked_out_eye():
    model = _stereo_model()
    _stereo_run(model)  # both eyes valid: records the real expression triples

    model.ort_session = _StaticSession([0.9, 0.9, 0.9, 0.0, 0.0, 0.0, 0.7, -0.65])
    raw = model.forward(np.zeros((1, 6, 2, 2), dtype=np.float32))
    out = model.postprocess(
        raw, {EyeId.LEFT: True, EyeId.RIGHT: False}, 0.0, 0.0
    )

    # Left tracks the new values (its eyebrow through the running median of
    # 0.1 and 0.9), right holds its last real triple instead of reporting the
    # black-frame zeros as a blink.
    assert [round(float(v), 3) for v in out[0:3]] == [0.5, 0.9, 0.9]
    assert [round(float(v), 3) for v in out[3:6]] == [0.4, 0.5, 0.6]


def _next_processor(*, flip_y=False):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = EyeId.LEFT
    processor.settings = SimpleNamespace(
        gui_NEXT_calibration=False,
        gui_flip_x_axis_left=False,
        gui_flip_x_axis_right=False,
        gui_flip_y_axis=flip_y,
        gui_recenter_eyes=False,
        leap_lid_close_threshold_left=0.1,
        leap_lid_widen_threshold_left=0.9,
        leap_lid_close_threshold_right=0.1,
        leap_lid_widen_threshold_right=0.9,
    )
    processor.config = SimpleNamespace(
        next_classic_calibration_active=False,
        calib_evecs=None,
        calib_axes=None,
        calib_XOFF=None,
    )
    processor.calibration_start_time = None
    processor._ellipse_collect_active = False
    processor._next_smartcal_active_dot = None
    processor._next_smartcal_w = None
    processor._next_smartcal_b = None
    processor._next_smartcal_warp = None
    processor._next_recenter_offset_x = 0.0
    processor._next_recenter_offset_y = 0.0
    processor._next_recenter_armed_at = None
    processor.out_x = 0.0
    processor.out_y = 0.0
    processor.osc_queue = Queue()
    return processor


def test_next_postprocessing_only_flips_y_when_requested():
    processor = _next_processor()
    processor._next_apply(0.25, 0.6, 0.5, 0.5, 0.0)
    assert processor.out_y == 0.6

    processor = _next_processor(flip_y=True)
    processor._next_apply(0.25, 0.6, 0.5, 0.5, 0.0)
    assert processor.out_y == -0.6
