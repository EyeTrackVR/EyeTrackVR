"""The shared NEXT model (next_stereo_model) against the shipped exports: the
12-output per-eye-gaze contract, the single-eye slots, the Y sign, expressions
held for a blacked-out eye, and the coordinator that serves both eye threads
(connect/disconnect, camera skew, paired cameras, history resets)."""

import threading
import time
from collections import deque

import numpy as np
import pytest

import next_stereo_model
from eye import EyeId
from next_model import MODEL_SIZES, NEXT_cls, compose_variant
from next_stereo_model import NEXT_Stereo_cls, StereoNextCoordinator, _Frame, stereo_model_file
from tests.next_stubs import IdentityFilter, StaticSession, stereo_runner

# Every shipped headset x model size, so each export is held to the same contract.
HYBRID_VARIANTS = tuple(compose_variant(hmd, size) for hmd in ("ETVR", "BSB", "PSVR") for size in MODEL_SIZES)
BOTH = {EyeId.LEFT: True, EyeId.RIGHT: True}


@pytest.fixture(params=HYBRID_VARIANTS)
def hybrid(request):
    model = NEXT_Stereo_cls(stereo_model_file(request.param))
    model.one_euro_filter = IdentityFilter(8)
    return request.param, model


@pytest.fixture
def etvr():
    """The ETVR export with identity One-Euro filters, so outputs don't depend
    on the wall-clock spacing between calls."""
    model = NEXT_Stereo_cls(stereo_model_file("ETVR"))
    model.one_euro_filter = IdentityFilter(8)
    return model


def _image(seed=1):
    return np.random.default_rng(seed).integers(0, 256, (64, 80, 3), dtype=np.uint8)


# ── the exports ──────────────────────────────────────────────────────────────


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
    # The present eye's slots answer to its own image: a different image moves
    # them. The absent eye's slots carry no meaning (the app holds that eye's
    # last real expressions and rebuilds its gaze, see postprocess / next_eye_gaze).
    other = model.chw(_Frame(1.0, _image(7)))
    pair2 = (other, model.black) if eye == EyeId.LEFT else (model.black, other)
    raw2 = model.forward(np.concatenate(pair2, axis=0)[None])
    own = slice(0, 3) if eye == EyeId.LEFT else slice(3, 6)
    own_gaze = slice(8, 10) if eye == EyeId.LEFT else slice(10, 12)
    assert np.abs(raw2[own] - raw[own]).max() > 1e-4
    assert np.abs(raw2[own_gaze] - raw[own_gaze]).max() > 1e-4


def test_hybrid_filters_only_the_primary_eight_outputs(hybrid):
    _, model = hybrid
    actual = model.chw(_Frame(1.0, _image()))
    raw = model.forward(np.concatenate((actual, actual), axis=0)[None])
    original = raw.copy()
    out = model.postprocess(raw, BOTH, 0.0, 0.0)
    expected = original[:8].copy()
    expected[7] *= -1.0
    assert out.shape == (8,)
    np.testing.assert_allclose(out, expected, atol=1e-6)
    np.testing.assert_array_equal(raw, original)


@pytest.mark.parametrize("eye", [EyeId.LEFT, EyeId.RIGHT])
def test_per_eye_hybrid_fallback_matches_shared_inference(hybrid, eye):
    variant, shared = hybrid
    fallback = NEXT_cls(variant, eye_id=eye)
    fallback.one_euro_filter = IdentityFilter(5)
    image = _image()
    actual = shared.chw(_Frame(1.0, image))
    pair = (actual, shared.black) if eye == EyeId.LEFT else (shared.black, actual)
    raw = shared.forward(np.concatenate(pair, axis=0)[None])
    base = 0 if eye == EyeId.LEFT else 3
    expected = [raw[6], -raw[7], *raw[base : base + 3]]
    np.testing.assert_allclose(fallback.run(image), expected, atol=1e-5)


def _raw12(rng):
    raw = rng.uniform(0.2, 0.9, 12).astype(np.float32)
    raw[6:] = rng.uniform(-0.6, 0.6, 6)
    return raw


def test_fused_outputs_ignore_the_per_eye_channels(etvr):
    # Same [0:8] stream through two fresh runners, one with wildly different
    # per-eye channels and one with none at all: the fused result is identical.
    other, legacy = NEXT_Stereo_cls(stereo_model_file("ETVR")), NEXT_Stereo_cls(stereo_model_file("ETVR"))
    for runner in (other, legacy):
        runner.one_euro_filter = IdentityFilter(8)
    rng = np.random.default_rng(3)
    for _ in range(30):
        raw = _raw12(rng)
        alt = raw.copy()
        alt[8:12] = rng.uniform(-1.0, 1.0, 4)
        a = etvr.postprocess(raw, BOTH, 0.5, 0.2)
        b = other.postprocess(alt, BOTH, 0.5, 0.2)
        c = legacy.postprocess(raw[:8].copy(), BOTH, 0.5, 0.2)
        # Expressions and the DFR gaze chain (identity filter + medians) are
        # time-independent; the VRChat gaze smoother is not compared here.
        np.testing.assert_array_equal(a[:6], b[:6])
        np.testing.assert_array_equal(a[:6], c[:6])
        assert etvr.last_dfr_gaze == other.last_dfr_gaze == legacy.last_dfr_gaze
    assert legacy.last_eye_gaze is None
    assert etvr.last_eye_gaze is not None


# ── Y axis ───────────────────────────────────────────────────────────────────


def _static_stereo(gaze_y_sign=-1.0):
    model = stereo_runner(gaze_y_sign=gaze_y_sign)
    model.input_size = 2
    model.raw_input = True
    model.temporal_frames = 1
    model.frame_stride = 2
    model.input_dtype = np.float32
    model.uses_directml = False
    model.input_name = "input"
    model.ort_session = StaticSession([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, -0.65])
    model.one_euro_filter = IdentityFilter(8)
    return model


def _stereo_run(model, valid=BOTH):
    raw = model.forward(np.zeros((1, 6, 2, 2), dtype=np.float32))
    return model.postprocess(raw, valid, 0.0, 0.0)


def test_stereo_next_negates_y_onto_the_mono_convention():
    # Every shipped stereo export is inverted against the mono NEXT models the
    # app's convention comes from, whatever gaze_y_axis they declare, so the
    # stereo path always negates Y. Otherwise Y would flip whenever the tracker
    # hands over between the mono and the stereo model.
    assert _stereo_run(_static_stereo())[7] == np.float32(0.65)


def test_stereo_next_y_sign_is_the_single_switch():
    # The negation lives in one place, so a future export that changes
    # convention is a one-line fix rather than a hunt.
    assert _stereo_run(_static_stereo(gaze_y_sign=1.0))[7] == np.float32(-0.65)


def test_per_eye_y_uses_the_shared_gaze_y_sign(etvr):
    # The exporter negates channels 7, 9 and 11 together, so all three take
    # the app's one Y sign.
    etvr.eye_gaze_filter = IdentityFilter(4)
    raw = np.array([0.5, 0.8, 0.0, 0.5, 0.8, 0.0, 0.1, 0.2, 0.11, 0.21, 0.31, 0.41], dtype=np.float32)
    out = etvr.postprocess(raw.copy(), BOTH, 0.0, 0.0)
    s = etvr.gaze_y_sign
    assert out[7] == pytest.approx(0.2 * s)
    assert etvr.last_dfr_gaze[1] == pytest.approx(0.2 * s)
    np.testing.assert_allclose(etvr.last_dfr_eye_gaze, [0.11, 0.21 * s, 0.31, 0.41 * s], atol=1e-6)
    np.testing.assert_allclose(etvr.last_eye_gaze, [0.11, 0.21 * s, 0.31, 0.41 * s], atol=1e-6)
    np.testing.assert_allclose(etvr.last_raw_eye_gaze, [0.11, 0.21 * s, 0.31, 0.41 * s], atol=1e-6)


# ── a blacked-out eye ────────────────────────────────────────────────────────


def test_stereo_next_holds_expressions_for_a_blacked_out_eye():
    model = _static_stereo()
    _stereo_run(model)  # both eyes valid: records the real expression triples

    model.ort_session = StaticSession([0.9, 0.9, 0.9, 0.0, 0.0, 0.0, 0.7, -0.65])
    out = _stereo_run(model, {EyeId.LEFT: True, EyeId.RIGHT: False})

    # Left tracks the new values (its eyebrow through the running median of
    # 0.1 and 0.9), right holds its last real triple instead of reporting the
    # black-frame zeros as a blink.
    assert [round(float(v), 3) for v in out[0:3]] == [0.5, 0.9, 0.9]
    assert [round(float(v), 3) for v in out[3:6]] == [0.4, 0.5, 0.6]


def test_black_eye_never_reaches_the_per_eye_filter(etvr):
    etvr.eye_gaze_filter = IdentityFilter(4)
    s = etvr.gaze_y_sign
    for _ in range(60):
        raw = np.array([0.5, 0.8, 0.0, 0.5, 0.8, 0.0, 0.1, 0.0, 0.0, 0.0, 0.2, 0.0], dtype=np.float32)
        etvr.postprocess(raw, BOTH, 0.0, 0.0)
    # Right camera blacked out: the model zeroes its expressions and gaze.
    raw = np.array([0.5, 0.8, 0.0, 0.0, 0.0, 0.0, -0.3, 0.1, -0.3, 0.1, 0.0, 0.0], dtype=np.float32)
    for _ in range(5):
        etvr.postprocess(raw.copy(), {EyeId.LEFT: True, EyeId.RIGHT: False}, 0.0, 0.0)
    np.testing.assert_allclose(etvr.last_dfr_eye_gaze, [-0.3, 0.1 * s, -0.1, 0.1 * s], atol=1e-5)


# ── the coordinator ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("variant", HYBRID_VARIANTS)
def test_hybrid_tracks_connect_disconnect_and_moving_camera_skew(monkeypatch, variant):
    now = [1000.0]
    monkeypatch.setattr(next_stereo_model.time, "perf_counter", lambda: now[0])
    coord = StereoNextCoordinator(stereo_model_file(variant))
    coord.runner.one_euro_filter = IdentityFilter(8)
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


@pytest.mark.parametrize("paired", [True, False])
def test_paired_cameras_cost_one_pass_per_pair(monkeypatch, paired):
    """Steam Frame delivers both eyes of a pair together: the first eye waits
    briefly for its partner, so one pass covers both and the other eye reuses it."""
    monkeypatch.setattr(next_stereo_model, "_PAIR_WAIT_S", 5.0)  # never the deciding factor here
    coord = StereoNextCoordinator(stereo_model_file("ETVR"))
    coord.paired = paired
    passes = []
    forward = coord.runner.forward
    coord.runner.forward = lambda x: passes.append(1) or forward(x)
    waiting = threading.Event()

    class _Watched(threading.Condition):
        def wait_for(self, predicate, timeout=None):
            waiting.set()  # the left eye now waits for its partner
            return super().wait_for(predicate, timeout)

    coord._submitted = _Watched(coord._state_lock)

    # A previous pair, so each eye has a peer that is streaming.
    ts = time.perf_counter()
    coord.submit(EyeId.LEFT, _image(1), ts - 0.03)
    coord.submit(EyeId.RIGHT, _image(2), ts - 0.03)
    coord.run(EyeId.LEFT, 0.0, 0.0)
    passes.clear()
    waiting.clear()

    # The left eye's frame arrives first and its thread runs before the right
    # eye's frame is in.
    coord.submit(EyeId.LEFT, _image(1), ts)
    left = threading.Thread(target=coord.run, args=(EyeId.LEFT, 0.0, 0.0))
    left.start()
    if paired:
        assert waiting.wait(5)
    else:
        left.join(5)
        assert not waiting.is_set()  # an unpaired eye never waits
    coord.submit(EyeId.RIGHT, _image(2), ts)
    left.join(5)
    coord.run(EyeId.RIGHT, 0.0, 0.0)
    assert len(passes) == (1 if paired else 2)
    assert coord.last_mode == "both-synced"

    # A paired eye whose partner never shows up still runs, after a short wait.
    monkeypatch.setattr(next_stereo_model, "_PAIR_WAIT_S", 0.05)
    start = time.perf_counter()
    coord.submit(EyeId.LEFT, _image(3), start)
    coord.run(EyeId.LEFT, 0.0, 0.0)
    assert time.perf_counter() - start < 1.0


def test_coordinator_reset_eye_drops_only_that_eyes_history():
    coord = StereoNextCoordinator.__new__(StereoNextCoordinator)
    coord._state_lock = threading.Lock()
    coord._hist = {EyeId.LEFT: deque([_Frame(1.0, _image(1))]), EyeId.RIGHT: deque([_Frame(1.0, _image(2))])}
    coord.reset_eye(EyeId.LEFT)
    assert not coord._hist[EyeId.LEFT] and len(coord._hist[EyeId.RIGHT]) == 1
