"""Regression tests for tracking-pipeline defects: HSF buffer sharing between
eye threads, LEAP "no result yet" frames, robust-calibration polynomial loss /
anchor misalignment, RANSAC axes + blink file, dilation axes and NEXT vs
standalone eyebrow output."""

import threading
from collections import deque
from queue import Queue
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import eye_processor as eye_processor_module
import haar_surround_feature
import ransac
from eye import EyeId, EyeInfoOrigin
from eye_processor import EyeProcessor
from leap import LEAP_C, LEAP_LID_METRIC_VERSION
from osc.OSCMessage import OSCMessageType
from utils.robust_calibration import (
    NUM_EXPRESS_TARGETS,
    CalibrationPhase,
    RobustCalibrationSession,
    _EXPRESS_GAZE_TARGETS,
)


# ── HSF: per-instance scratch buffers ────────────────────────────────────────


def _blob_image(cx, cy, shape=(100, 120), r=8):
    img = np.full(shape, 200, dtype=np.uint8)
    cv2.circle(img, (cx, cy), r, 10, -1)
    return img


def test_hsf_instances_do_not_share_scratch_buffers():
    a = haar_surround_feature.HSF_cls()
    b = haar_surround_feature.HSF_cls()
    key = ((100, 120), 40, 5, 5, 20, 60)

    bufs_a = a._get_buffers(*key)
    bufs_b = b._get_buffers(*key)

    # Same geometry must not mean the same mutable arrays across eyes (the
    # read-only index arrays may stay shared)...
    for arr_a, arr_b in zip(bufs_a, bufs_b):
        if arr_a.flags.writeable:
            assert not np.shares_memory(arr_a, arr_b)
        else:
            assert not arr_b.flags.writeable
    # ...but one instance reuses its own buffers frame to frame.
    assert a._get_buffers(*key)[0] is bufs_a[0]


def test_hsf_two_threads_each_find_their_own_pupil(monkeypatch):
    # External_Run_HSF writes these module globals; restore them afterwards.
    monkeypatch.setattr(haar_surround_feature, "skip_autoradius", False)
    monkeypatch.setattr(haar_surround_feature, "default_radius", 20)

    eyes = {
        "left": ((25, 30), _blob_image(25, 30)),
        "right": ((90, 70), _blob_image(90, 70)),
    }
    results = {name: [] for name in eyes}
    barrier = threading.Barrier(len(eyes))

    def worker(name):
        runner = haar_surround_feature.External_Run_HSF(True, 8)
        _, img = eyes[name]
        barrier.wait()
        for _ in range(250):
            # run() draws markers on its input, so hand it a fresh copy.
            x, y, _, _ = runner.run(img.copy())
            results[name].append((x, y))

    threads = [threading.Thread(target=worker, args=(n,)) for n in eyes]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    for name, ((cx, cy), _) in eyes.items():
        assert len(results[name]) == 250
        for x, y in results[name]:
            assert abs(x - cx) <= 10 and abs(y - cy) <= 10, (name, x, y)


# ── LEAP: no worker result yet ───────────────────────────────────────────────


def _bare_leap():
    leap = LEAP_C.__new__(LEAP_C)
    leap._last_result = None
    leap.last_lid = None
    leap.queues = [Queue(maxsize=1)]
    leap.output_queue = Queue(maxsize=1)
    leap.ort_session_cpu = None
    leap.ort_session_gpu = None
    leap.config = SimpleNamespace(
        settings=SimpleNamespace(gui_use_gpu=False, leap_calibration_duration=1.0),
        left_eye=None,
    )
    leap.eye_config = SimpleNamespace(
        leap_lid_metric_version=LEAP_LID_METRIC_VERSION,
        leap_calib_request_seq=0,
        leap_calibrated=True,
        leap_calibration_percentile_90=0.3,
        leap_calibration_percentile_2=-0.2,
    )
    leap._seen_calib_request_seq = 0
    leap.openlist = deque(maxlen=10)
    leap.one_euro_filter_float = lambda arr: arr
    leap.current_image_gray = np.zeros((40, 60), dtype=np.uint8)
    leap.current_image_gray_clean = np.zeros((40, 60), dtype=np.uint8)
    return leap


def test_leap_no_result_before_first_inference_is_none():
    leap = _bare_leap()
    _, x, y, lid = leap.leap_run()
    assert (x, y, lid) == (None, None, None)


def test_leap_no_result_repeats_last_valid_result():
    leap = _bare_leap()
    landmarks = np.full((12, 2), 0.5)
    # Lid points 1-3 / 2-4 0.2 apart -> half open against the stored range.
    landmarks[1], landmarks[3] = (0.5, 0.4), (0.5, 0.6)
    landmarks[2], landmarks[4] = (0.4, 0.4), (0.4, 0.6)
    landmarks[6] = (0.25, 0.75)
    leap.output_queue.put((None, landmarks))

    _, x1, y1, lid1 = leap.leap_run()
    assert (x1, y1) == (15.0, 30.0)
    assert lid1 > 0.0

    # Worker busy: the previous result comes back, not a blink + corner gaze.
    leap.queues[0].get_nowait()
    _, x2, y2, lid2 = leap.leap_run()
    assert (x2, y2, lid2) == (x1, y1, lid1)


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


# ── Robust calibration ───────────────────────────────────────────────────────


def _raw_for(gx, gy):
    # A known linear camera mapping (image Y grows downward).
    return 100.0 + 20.0 * gx, 50.0 - 10.0 * gy


def _trained_session():
    sess = RobustCalibrationSession()
    sess.poly_coeffs_x = np.arange(6, dtype=np.float64)
    sess.poly_coeffs_y = np.arange(6, dtype=np.float64) * 2
    sess.poly_trained = True
    sess._poly_source = "card"
    sess.phase = CalibrationPhase.DONE
    return sess


def test_failed_pursuit_keeps_previous_polynomial():
    sess = _trained_session()
    sess.start_pursuit()
    sess._pursuit_data = [(0.5, 100.0, 50.0, 0.0, 0.0)] * 10

    sess._fit_polynomial()

    assert sess.phase == CalibrationPhase.DONE
    assert "failed" in sess.status.lower()
    assert sess.poly_trained
    np.testing.assert_array_equal(sess.poly_coeffs_x, np.arange(6))
    saved = sess.to_dict()
    assert saved["poly_trained"] and saved["poly_coeffs_x"] == list(range(6))


def test_new_express_run_resets_polynomial():
    sess = _trained_session()
    sess.start_express()
    assert not sess.poly_trained
    assert sess.poly_coeffs_x is None and sess.poly_coeffs_y is None
    assert "poly_source" not in sess.to_dict()


def _express_with_missing_target(missing):
    sess = RobustCalibrationSession()
    sess.start_express(overlay_driven=True)
    for i, (gx, gy) in enumerate(_EXPRESS_GAZE_TARGETS):
        if i != missing:
            sess._express_raw[i] = [_raw_for(gx, gy)] * 30
    sess._finalize_express()
    return sess


def test_express_medians_stay_aligned_when_a_target_is_missing():
    sess = _express_with_missing_target(missing=1)

    meds = sess._express_target_medians
    assert len(meds) == NUM_EXPRESS_TARGETS
    assert meds[1] is None
    for i, (gx, gy) in enumerate(_EXPRESS_GAZE_TARGETS):
        if i != 1:
            assert meds[i] == pytest.approx(_raw_for(gx, gy))

    # Card fit pairs each median with its own target (ridge adds ~0.1 bias).
    assert sess.poly_trained
    for gx, gy in _EXPRESS_GAZE_TARGETS:
        assert sess.predict_poly(*_raw_for(gx, gy)) == pytest.approx((gx, gy), abs=0.2)


def test_missing_centre_target_falls_back_to_extent_midpoint():
    sess = _express_with_missing_target(missing=0)
    assert sess.express_calibrated
    assert (sess.express_center_x, sess.express_center_y) == pytest.approx(_raw_for(0, 0))


def test_pursuit_anchors_stay_aligned_when_a_target_is_missing():
    sess = _express_with_missing_target(missing=2)
    sess.start_pursuit()
    rng = np.random.default_rng(0)
    for gx, gy in rng.uniform(-1, 1, size=(120, 2)):
        sess._pursuit_data.append((0.5, *_raw_for(gx, gy), gx, gy))

    sess._fit_polynomial()

    assert sess.poly_trained and sess._poly_source == "pursuit"
    for gx, gy in _EXPRESS_GAZE_TARGETS:
        assert sess.predict_poly(*_raw_for(gx, gy)) == pytest.approx((gx, gy), abs=1e-3)


def test_indexed_medians_round_trip_and_legacy_short_list_is_dropped():
    sess = _express_with_missing_target(missing=3)
    loaded = RobustCalibrationSession.from_dict(sess.to_dict())
    assert loaded._express_target_medians == sess._express_target_medians

    legacy = sess.to_dict()
    legacy["express_target_medians"] = [m for m in sess._express_target_medians if m]
    assert RobustCalibrationSession.from_dict(legacy)._express_target_medians == []


# ── RANSAC: ellipse axes + blink file ────────────────────────────────────────


def _ransac_processor(eye_id):
    img = np.full((80, 80), 220, dtype=np.uint8)
    cv2.ellipse(img, (40, 40), (14, 8), 0, 0, 360, 0, -1)
    cv2.rectangle(img, (4, 4), (18, 34), 0, -1)  # second, differently-shaped contour
    return SimpleNamespace(
        eye_id=eye_id,
        rawx=40,
        rawy=40,
        radius=10,
        current_image_gray=img.copy(),
        current_image_gray_clean=img.copy(),
        settings=SimpleNamespace(gui_thresh_add=20, gui_RANSACBLINK=True),
        failed=0,
        detector_3d=SimpleNamespace(update_and_detect=lambda *_: (_ for _ in ()).throw(KeyError("x"))),
        last_projected_sphere={},
        current_frame_number=1,
        current_fps=60,
        ran_blink_check_for_file=True,
        blink_list=[],
    )


def test_ransac_returns_ellipse_axes_and_loads_own_blink_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ransac.ransac_blink_file_path(EyeId.LEFT)).write_text("0.1\n0.2\n")
    (tmp_path / ransac.ransac_blink_file_path(EyeId.RIGHT)).write_text("0.9\n")
    monkeypatch.setattr(ransac, "fit_rotated_ellipse_ransac", lambda data, rng: (40.0, 40.0, 7.5, 4.25, 0.0))

    proc = _ransac_processor(EyeId.LEFT)
    *_, w, h = ransac.RANSAC3D(proc, False)

    assert (w, h) == (7.5, 4.25)
    assert proc.blink_list[:2] == [0.1, 0.2]
    assert 0.9 not in proc.blink_list


def test_ransac_blink_percentile_computed_once_per_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    real_percentile = np.percentile

    def counting_percentile(*args, **kwargs):
        calls.append(1)
        return real_percentile(*args, **kwargs)

    monkeypatch.setattr(ransac.np, "percentile", counting_percentile)
    proc = _ransac_processor(EyeId.RIGHT)
    ransac.RANSAC3D(proc, False)
    assert len(proc.blink_list) >= 2  # several contours were sampled...
    assert len(calls) == 1  # ...but the percentile ran once

    # Frozen list (calibration complete): no recomputation at all.
    proc.blink_list = [0.01] * 10001
    proc._ransac_blink_p92 = None
    ransac.RANSAC3D(proc, False)
    ransac.RANSAC3D(proc, False)
    assert len(calls) == 2


# ── Dilation axes for trackers that don't measure them ───────────────────────


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


# ── Eyebrow: NEXT preferred over the standalone model ────────────────────────


class _FakeBrow:
    instances = []

    def __init__(self, variant):
        self.variant = variant
        self.stopped = False
        self.frames = 0
        _FakeBrow.instances.append(self)

    def submit(self, frame):
        self.frames += 1

    def get_result(self):
        return 0.123

    def stop(self):
        self.stopped = True


def _brow_processor(next_on):
    proc = EyeProcessor.__new__(EyeProcessor)
    proc.eye_id = EyeId.LEFT
    proc.settings = SimpleNamespace(
        gui_NEXT=next_on,
        gui_NEXT_BSB=False,
        gui_eyebrow=True,
        gui_model_variant="ETVR",
        gui_setup_mode="default",
    )
    proc.osc_queue = Queue()
    proc.eyebrow_runner = None
    proc.next_eyebrow = 0.77
    return proc


def _brow_messages(proc):
    msgs = []
    while not proc.osc_queue.empty():
        msg = proc.osc_queue.get_nowait()
        if msg.type == OSCMessageType.EYEBROW_INFO:
            msgs.append(msg)
    return msgs


def test_next_active_stops_standalone_eyebrow_and_reports_next_value(monkeypatch):
    monkeypatch.setattr(eye_processor_module, "EyeBrow", _FakeBrow)
    proc = _brow_processor(next_on=True)
    runner = _FakeBrow("ETVR")
    proc.eyebrow_runner = runner

    proc._service_eyebrow_runner(np.zeros((4, 4, 3), dtype=np.uint8))

    assert runner.stopped and proc.eyebrow_runner is None
    assert runner.frames == 0
    assert _brow_messages(proc) == []
    assert proc._current_eyebrow() == 0.77


def test_eyebrow_runner_unchanged_without_next(monkeypatch):
    monkeypatch.setattr(eye_processor_module, "EyeBrow", _FakeBrow)
    proc = _brow_processor(next_on=False)

    proc._service_eyebrow_runner(np.zeros((4, 4, 3), dtype=np.uint8))

    assert isinstance(proc.eyebrow_runner, _FakeBrow)
    assert proc.eyebrow_runner.frames == 1
    msgs = _brow_messages(proc)
    assert len(msgs) == 1 and msgs[0].data == (EyeId.LEFT, 0.123)
    assert proc._current_eyebrow() == 0.123
