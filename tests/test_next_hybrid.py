"""Regression checks against the shipped hardware-specific Hybrid exports."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from eye import EyeId
from eye_processor import EyeProcessor
from next_model import NEXT_cls, model_file_for_variant
from next_stereo_model import NEXT_Stereo_cls, StereoNextCoordinator, _Frame, stereo_model_file
import next_model
import next_stereo_model

HYBRID_VARIANTS = ("ETVR", "ETVR LITE", "BSB", "BSB LITE", "PSVR", "PSVR LITE")


class _IdentityFilter:
    def __init__(self, size):
        self.min_cutoff = np.zeros(size, dtype=np.float32)
        self.beta = np.zeros(size, dtype=np.float32)

    def __call__(self, values):
        return values


@pytest.fixture(params=HYBRID_VARIANTS)
def hybrid(request):
    model = NEXT_Stereo_cls(stereo_model_file(request.param))
    model.one_euro_filter = _IdentityFilter(8)
    return request.param, model


def _image(seed=1):
    return np.random.default_rng(seed).integers(0, 256, (64, 80, 3), dtype=np.uint8)


@pytest.mark.parametrize("base,stem", [
    ("ETVR", "NEXT_ETVR_HYBRID"),
    ("BSB", "NEXT_ETVR_HYBRID_BSB"),
    ("PSVR", "NEXT_ETVR_HYBRID_PSVR"),
])
def test_hardware_selects_one_hybrid_artifact_for_both_camera_modes(base, stem):
    for variant, suffix in ((base, ".onnx"), (base + " LITE", ".fp16.onnx")):
        expected = f"Models/{stem}{suffix}"
        assert model_file_for_variant(variant) == expected
        assert stereo_model_file(variant) == expected
    assert model_file_for_variant("TOBII") == "Models/NEXT_TOBII.onnx"


@pytest.mark.parametrize("base", ["ETVR", "BSB", "PSVR"])
def test_hybrid_lite_falls_back_to_full_precision(monkeypatch, base):
    monkeypatch.setattr(next_model.os.path, "exists", lambda path: not path.endswith(".fp16.onnx"))
    expected = model_file_for_variant(base)
    assert model_file_for_variant(base + " LITE") == expected
    assert stereo_model_file(base + " LITE") == expected


@pytest.mark.parametrize("eye", [EyeId.LEFT, EyeId.RIGHT])
def test_hybrid_single_eye_uses_correct_slot_and_monocular_gaze(hybrid, eye):
    _, model = hybrid
    assert model.supports_single_eye
    frame = _Frame(1.0, _image())
    actual = model.chw(frame)
    # Export takes raw RGB, with normalization already in its graph.
    constant = np.full((2, 2, 3), [10, 20, 30], dtype=np.uint8)
    np.testing.assert_array_equal(model.chw(_Frame(1.0, constant))[:, 0, 0], [30, 20, 10])
    assert np.count_nonzero(model.black) == 0
    pair = (actual, model.black) if eye == EyeId.LEFT else (model.black, actual)
    raw = model.forward(np.concatenate(pair, axis=0)[None])
    assert raw.shape == (12,)
    assert np.isfinite(raw).all()
    missing = slice(3, 6) if eye == EyeId.LEFT else slice(0, 3)
    own_gaze = slice(8, 10) if eye == EyeId.LEFT else slice(10, 12)
    missing_gaze = slice(10, 12) if eye == EyeId.LEFT else slice(8, 10)
    np.testing.assert_array_equal(raw[missing], 0.0)
    np.testing.assert_array_equal(raw[missing_gaze], 0.0)
    np.testing.assert_allclose(raw[6:8], raw[own_gaze], atol=1e-6)


def test_hybrid_filters_only_the_primary_eight_outputs(hybrid):
    _, model = hybrid
    actual = model.chw(_Frame(1.0, _image()))
    raw = model.forward(np.concatenate((actual, actual), axis=0)[None])
    original = raw.copy()
    out = model.postprocess(raw, {EyeId.LEFT: True, EyeId.RIGHT: True}, 0.0, 0.0)
    expected = original[:8].copy()
    expected[7] *= -1.0
    assert out.shape == (8,)
    np.testing.assert_allclose(out, expected, atol=1e-6)
    np.testing.assert_array_equal(raw, original)


@pytest.mark.parametrize("eye", [EyeId.LEFT, EyeId.RIGHT])
def test_per_eye_hybrid_fallback_matches_shared_inference(hybrid, eye):
    variant, shared = hybrid
    fallback = NEXT_cls(variant, eye_id=eye)
    fallback.one_euro_filter = _IdentityFilter(5)
    image = _image()
    actual = shared.chw(_Frame(1.0, image))
    pair = (actual, shared.black) if eye == EyeId.LEFT else (shared.black, actual)
    raw = shared.forward(np.concatenate(pair, axis=0)[None])
    base = 0 if eye == EyeId.LEFT else 3
    expected = [raw[6], -raw[7], *raw[base:base + 3]]
    np.testing.assert_allclose(fallback.run(image), expected, atol=1e-5)


@pytest.mark.parametrize("variant", HYBRID_VARIANTS)
def test_hybrid_tracks_connect_disconnect_and_moving_camera_skew(monkeypatch, variant):
    now = [1000.0]
    monkeypatch.setattr(next_stereo_model.time, "perf_counter", lambda: now[0])
    coord = StereoNextCoordinator(stereo_model_file(variant))
    coord.runner.one_euro_filter = _IdentityFilter(8)
    assert coord.supports_single_eye
    inputs = []
    forward = coord.runner.forward

    def record(x):
        inputs.append(x.copy())
        return forward(x)

    coord.runner.forward = record
    coord.submit(EyeId.LEFT, _image(), now[0])
    assert np.isfinite(coord.run(EyeId.LEFT, 0.0, 0.0)).all()
    assert coord.last_mode == "left-only"
    assert np.count_nonzero(inputs[-1][:, 3:6]) == 0

    now[0] += 0.01
    coord.submit(EyeId.RIGHT, _image(2), now[0])
    coord.run(EyeId.RIGHT, 0.0, 0.0)
    assert coord.last_mode == "both-synced"
    assert np.count_nonzero(inputs[-1][:, 0:3]) > 0
    assert np.count_nonzero(inputs[-1][:, 3:6]) > 0

    # A newer moving eye excludes a lagging camera instead of mixing moments.
    now[0] += 0.08
    coord.submit(EyeId.LEFT, _image(3), now[0])
    coord.run(EyeId.LEFT, 0.0, 0.0)
    assert coord.last_mode == "left-fresh"
    assert np.count_nonzero(inputs[-1][:, 3:6]) == 0

    # A disconnected peer remains on the same Hybrid session after one second.
    now[0] += 1.1
    coord.submit(EyeId.LEFT, _image(4), now[0])
    coord.run(EyeId.LEFT, 0.0, 0.0)
    assert not coord.peer_active(EyeId.LEFT)
    assert coord.last_mode == "left-only"
    assert np.count_nonzero(inputs[-1][:, 3:6]) == 0

    now[0] += 0.01
    coord.submit(EyeId.RIGHT, _image(5), now[0])
    coord.run(EyeId.RIGHT, 0.0, 0.0)
    assert coord.last_mode == "both-synced"
    assert np.count_nonzero(inputs[-1][:, 3:6]) > 0


@pytest.mark.parametrize("eye", [EyeId.LEFT, EyeId.RIGHT])
@pytest.mark.parametrize("hybrid_available", [True, False])
@pytest.mark.parametrize("variant", ["ETVR", "BSB", "PSVR"])
@pytest.mark.parametrize("setup", ["standard", "bigscreen"])
def test_processor_uses_hybrid_without_an_active_peer(monkeypatch, eye, hybrid_available, variant, setup):
    processor = EyeProcessor.__new__(EyeProcessor)
    processor.eye_id = eye
    processor.current_raw_frame = _image()
    processor.current_image_gray = np.zeros((64, 80), dtype=np.uint8)
    processor.current_capture_ts = 1000.0
    processor.settings = SimpleNamespace(
        gui_min_cutoff=0.0004, gui_speed_coefficient=0.9,
        gui_setup_mode=setup, gui_model_variant=variant, gui_use_gpu=False,
    )
    processor._next_apply = Mock()
    processor._next_mode_changed = Mock()
    processor.next_runner = Mock()
    processor.next_runner.run.return_value = (0.2, 0.3, 0.4, 0.5, 0.6)
    coord = SimpleNamespace(
        supports_single_eye=hybrid_available, submit=Mock(), run=Mock(), peer_active=Mock()
    )
    coord.run.return_value = (0.1, 0.2, 0.3, 0.4, 0.5)
    coord.peer_active.return_value = False
    monkeypatch.setattr("eye_processor.get_stereo_coordinator", lambda *args: coord)
    processor.NEXTM()
    coord.submit.assert_called_once()
    submitted_eye, submitted_frame, submitted_ts = coord.submit.call_args.args
    expected = processor.current_raw_frame
    if setup == "bigscreen":
        mid = expected.shape[1] // 2
        expected = expected[:, :mid] if eye == EyeId.LEFT else expected[:, mid:]
    assert submitted_eye == eye
    assert submitted_ts == 1000.0
    np.testing.assert_array_equal(submitted_frame, expected)
    if hybrid_available:
        coord.peer_active.assert_not_called()
        coord.run.assert_called_once_with(eye, 0.0004, 0.9)
        processor.next_runner.run.assert_not_called()
        processor._next_apply.assert_called_once_with(*coord.run.return_value)
    else:
        coord.run.assert_not_called()
        processor.next_runner.run.assert_called_once()
        processor._next_apply.assert_called_once_with(*processor.next_runner.run.return_value)


@pytest.mark.parametrize("variant", ["ETVR", "BSB", "PSVR"])
def test_processor_does_not_allocate_unused_per_eye_sessions(monkeypatch, variant):
    settings = SimpleNamespace(
        gui_AHRAC=False, gui_AHSF=False, gui_HSF=False, gui_HSRAC=False,
        gui_DADDY=False, gui_NEXT=True, gui_NEXT_BSB=False, gui_LEAP=False,
        gui_LEAP_lid=False, gui_RANSAC3D=False, gui_model_variant=variant, gui_use_gpu=False,
    )
    coord = SimpleNamespace(supports_single_eye=True)
    get_coord = Mock(return_value=coord)
    allocate = Mock(side_effect=AssertionError("Hybrid must share the coordinator's session"))
    monkeypatch.setattr("eye_processor.get_stereo_coordinator", get_coord)
    monkeypatch.setattr("eye_processor.External_Run_NEXT", allocate)
    for eye in (EyeId.LEFT, EyeId.RIGHT):
        processor = EyeProcessor.__new__(EyeProcessor)
        processor.eye_id = eye
        processor.settings = settings
        processor.hsf_runner = None
        processor.daddy_runner = None
        processor.next_runner = None
        processor.leap_runner = None
        processor._rebuild_algorithm_slots()
        assert processor.next_runner is None
        assert processor.NEXTM in processor._algorithm_slots
    allocate.assert_not_called()
    assert get_coord.call_count == 2
