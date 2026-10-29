"""Foveated rendering gets calibrated but unfiltered gaze (EyeInfo.dfr_x / dfr_y);
VRChat keeps the smoothed gaze (EyeInfo.x / y). Covers both NEXT runners, NEXT's
calibration step, the classic cal_osc path, and the foveation sender."""

import time
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

import osc_calibrate_filter as calibration
from config import EyeTrackCameraConfig
from eye import EyeId
from eye_processor import EyeProcessor
from next_model import External_Run_NEXT, NEXT_cls, TimedMedian
from next_stereo_model import StereoNextCoordinator, stereo_model_file
from osc.FoveationGazeSender import FoveationGazeSender
from osc.OSCMessage import OSCMessage, OSCMessageType
from tests import EyeInfoMock
from utils.calibration_elipse import CalibrationEllipse


class _HalvingFilter:
    """Stands in for the One-Euro filter: obviously different from its input."""

    def __init__(self, size):
        self.min_cutoff = np.zeros(size, dtype=np.float32)
        self.beta = np.zeros(size, dtype=np.float32)

    def __call__(self, values):
        return np.asarray(values, dtype=np.float32) * 0.5


class _Session:
    def __init__(self):
        self.values = None

    def run(self, _outputs, _inputs):
        return [np.asarray([self.values], dtype=np.float32)]


def _mono_model():
    model = NEXT_cls.__new__(NEXT_cls)
    model.input_size = 2
    model.raw_input = True
    model.temporal_frames = 1
    model.input_dtype = np.float32
    model.uses_directml = False
    model.input_name = "input"
    model.ort_session = _Session()
    model.one_euro_filter = _HalvingFilter(5)
    model._brow_window = TimedMedian(5)
    model._gaze_x_window = TimedMedian(3)
    model._gaze_y_window = TimedMedian(3)
    return model


def test_mono_runner_exposes_gaze_before_median_and_one_euro():
    model = _mono_model()
    runner = External_Run_NEXT.__new__(External_Run_NEXT)
    runner.algo = model
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    assert runner.raw_gaze is None

    outputs = []
    for gx in (0.1, 0.1, 0.9):  # a sudden jump the 3-sample median swallows at first
        model.ort_session.values = [0.0, 1.0, 0.0, gx, -0.3]
        outputs.append(runner.run(frame))
        assert runner.raw_gaze == pytest.approx((gx, -0.3))
    # The filtered output (OSC) still shows the old gaze (median 0.1, halved);
    # the raw tap already has the new one.
    assert outputs[2][0] == pytest.approx(0.05)
    assert outputs[2][1] == pytest.approx(-0.15)
    assert runner.raw_gaze[0] == pytest.approx(0.9)


def test_stereo_coordinator_exposes_shared_gaze_before_filtering():
    coord = StereoNextCoordinator(stereo_model_file("ETVR"))
    coord.runner.one_euro_filter = _HalvingFilter(8)
    assert coord.raw_gaze() is None
    rng = np.random.default_rng(3)
    image = rng.integers(0, 255, (120, 160, 3), dtype=np.uint8)
    coord.submit(EyeId.LEFT, image, time.perf_counter())
    gx, gy, *_ = coord.run(EyeId.LEFT, 0.0, 0.0)
    raw = coord.raw_gaze()
    assert raw is not None
    # First sample: the median is the value itself, so filtered == raw * 0.5 exactly.
    assert (gx, gy) == pytest.approx((raw[0] * 0.5, raw[1] * 0.5), abs=1e-6)


def _next_processor(**settings):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = settings.pop("eye_id", EyeId.LEFT)
    defaults = dict(
        gui_NEXT_calib_lids_brows=False,
        gui_flip_x_axis_left=False,
        gui_flip_x_axis_right=False,
        gui_flip_y_axis=False,
        gui_recenter_eyes=False,
        gui_NEXT=True,
        gui_NEXT_BSB=False,
        leap_lid_close_threshold_left=0.1,
        leap_lid_widen_threshold_left=0.9,
        leap_lid_close_threshold_right=0.1,
        leap_lid_widen_threshold_right=0.9,
    )
    processor.settings = SimpleNamespace(**{**defaults, **settings})
    processor.config = SimpleNamespace(next_classic_calibration_active=False)
    processor._next_smartcal_active_dot = None
    processor._next_smartcal_w = None
    processor._next_smartcal_b = None
    processor._next_smartcal_warp = None
    processor._next_smartcal_lid_neutral = None
    processor._next_smartcal_brow_neutral = None
    processor._next_recenter_offset_x = 0.0
    processor._next_recenter_offset_y = 0.0
    processor._next_recenter_armed_at = None
    processor.out_x = processor.out_y = 0.0
    processor.dfr_x = processor.dfr_y = None
    processor.osc_queue = Queue()
    return processor


def test_next_dfr_gaze_is_the_raw_gaze_through_the_same_calibration():
    p = _next_processor(gui_flip_x_axis_left=True, gui_flip_y_axis=True)
    # A Smart Calib affine (no warp): x' = 2x + 0.1, y' = y - 0.2.
    p._next_smartcal_w = [2.0, 0.0, 0.0, 1.0]
    p._next_smartcal_b = [0.1, -0.2]
    p._next_recenter_offset_x, p._next_recenter_offset_y = 0.05, -0.05

    p._next_apply(0.1, 0.1, 0.5, 0.9, 0.0, raw_gaze=(0.3, 0.4))

    # OSC: filtered 0.1 -> cal (0.3, -0.1) -> flips (-0.3, 0.1) -> recenter (-0.35, 0.15)
    assert (p.out_x, p.out_y) == pytest.approx((-0.35, 0.15))
    # DFR: raw 0.3 / 0.4 -> cal (0.7, 0.2) -> flips (-0.7, -0.2) -> recenter (-0.75, -0.15)
    assert (p.dfr_x, p.dfr_y) == pytest.approx((-0.75, -0.15))


def test_next_dfr_gaze_is_bounded_like_the_osc_gaze():
    p = _next_processor()
    p._next_smartcal_w = [3.0, 0.0, 0.0, 3.0]
    p._next_smartcal_b = [0.0, 0.0]
    p._next_apply(0.1, 0.1, 0.5, 0.9, 0.0, raw_gaze=(0.9, -0.9))
    assert (p.dfr_x, p.dfr_y) == (1.0, -1.0)


def test_next_without_a_raw_tap_falls_back_to_the_osc_gaze():
    p = _next_processor()
    p._next_apply(0.2, -0.3, 0.5, 0.9, 0.0)
    assert (p.dfr_x, p.dfr_y) == pytest.approx((0.2, -0.3))


def test_next_dfr_gaze_rides_on_the_osc_message():
    p = _next_processor()
    p._next_apply(0.1, 0.1, 0.5, 0.9, 0.0, raw_gaze=(0.6, -0.2))
    p.eyeopen, p.past_blink, p.prev_y_list = 0.9, 0.9, []
    p.avg_velocity, p.squeeze, p.pupil_dilation = 0.0, 0.0, 0.5
    p.current_algo = p.current_algorithm = None
    p.current_capture_ts = 123.0
    p.thresh = None
    p.settings.gui_BLINK = p.settings.gui_IBO = p.settings.gui_LEAP_lid = False
    p.settings.gui_pupil_dilation = False
    p._current_eyebrow = lambda: 0.0
    p.output_images_and_update = Mock()
    sent = []
    p._enqueue_osc_message = sent.append
    p.UPDATE()
    info = sent[0].data[1]
    assert (info.x, info.y) == pytest.approx((0.1, 0.1))
    assert (info.dfr_x, info.dfr_y) == pytest.approx((0.6, -0.2))
    assert info.capture_ts == 123.0


def test_classic_dfr_gaze_skips_the_one_euro_filter(monkeypatch, eyetrack_settings_config):
    settings = eyetrack_settings_config
    settings.gui_recenter_eyes = False
    settings.gui_flip_y_axis = True
    settings.gui_flip_x_axis_left = False
    settings.gui_flip_x_axis_right = False
    config = EyeTrackCameraConfig(
        calib_evecs=[[1.0, 0.0], [0.0, 1.0]],
        calib_axes=[20.0, 15.0],
        calib_XOFF=100.0,
        calib_YOFF=100.0,
    )
    processor = SimpleNamespace(
        settings=settings,
        config=config,
        cal=CalibrationEllipse(),
        eye_id=EyeId.LEFT,
        calibration_start_time=None,
        should_print_calibration_warning=False,
        _recenter_armed_at=None,
        _recenter_delay_s=0.2,
        baseconfig=SimpleNamespace(save=lambda: None),
        one_euro_filter=_HalvingFilter(2),
    )
    monkeypatch.setattr(calibration.TrackingLogger, "get", lambda: None)

    out_x, out_y, _ = calibration.cal.cal_osc(processor, 106.0, 103.0, 0.0)

    expected = processor.cal.normalize((106.0, 103.0), (100.0, 100.0), clip=False)
    assert (processor.dfr_x, processor.dfr_y) == pytest.approx((expected[0], -expected[1]))
    # VRChat's value went through the (halving) filter; the DFR value did not.
    assert (out_x, out_y) == pytest.approx((processor.dfr_x * 0.5, processor.dfr_y * 0.5))


def _eye_msg(eye_id=EyeId.RIGHT, **kw):
    fields = dict(x=0.0, y=0.0, blink=1.0, pupil_dilation=0.0, avg_velocity=0.0)
    fields.update(kw)
    return OSCMessage(type=OSCMessageType.EYE_INFO, data=(eye_id, EyeInfoMock(**fields)))


@pytest.fixture()
def sender(monkeypatch):
    from osc import GazeSharedMemory as shm

    monkeypatch.setattr(shm, "WIN32_NAME", "Local\\EyeTrackVR.Gaze.test.unfiltered")
    monkeypatch.setattr(shm, "POSIX_PATH", "/dev/shm/eyetrackvr_gaze_test_unfiltered")
    s = FoveationGazeSender()
    client = SimpleNamespace(messages=[])
    client.send_message = lambda address, value: client.messages.append(value)
    config = SimpleNamespace(
        gui_gaze_yaw_max_deg=40.0, gui_gaze_pitch_up_deg=15.0, gui_gaze_pitch_down_deg=40.0, osc_invert_eye_close=False
    )
    s.start(config, client)
    yield s, client, config
    s.stop()


def test_sender_uses_the_unfiltered_gaze(sender):
    s, client, config = sender
    main = SimpleNamespace(eye_display_id=EyeId.RIGHT)  # single-eye mode
    s.output_osc_info(_eye_msg(x=0.1, y=0.1, dfr_x=0.5, dfr_y=-0.25), main, config)
    s.output_osc_info(_eye_msg(x=0.5, y=-0.25), main, config)  # same gaze, filtered field only
    assert client.messages[0] == pytest.approx(client.messages[1])


def test_sender_falls_back_to_filtered_gaze_without_a_tap(sender):
    s, client, config = sender
    main = SimpleNamespace(eye_display_id=EyeId.RIGHT)
    s.output_osc_info(_eye_msg(x=0.3, y=0.2, dfr_x=float("nan"), dfr_y=0.0), main, config)
    s.output_osc_info(_eye_msg(x=0.3, y=0.2), main, config)
    assert client.messages[0] == pytest.approx(client.messages[1])
