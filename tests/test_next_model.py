"""NEXT model selection (next_model): headset x size -> the shipped ONNX
export, fallbacks when an export is missing, settings migration, and the mono
runner's Y axis."""

import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import next_model
from config import _migrate_config_dict
from next_model import (
    HMD_TYPES,
    MODEL_SIZES,
    MODEL_VARIANTS,
    NEXT_cls,
    TimedMedian,
    compose_variant,
    model_file_for_variant,
    variant_from_settings,
)
from next_stereo_model import stereo_model_file
from settings.modules.tracking_algorithm_module import _MODEL_VARIANTS
from tests.next_stubs import IdentityFilter, StaticSession
from utils.misc_utils import resource_path

# ── variants ─────────────────────────────────────────────────────────────────


def test_gui_and_inference_offer_the_same_headsets():
    assert HMD_TYPES == _MODEL_VARIANTS


def test_model_size_slider_runs_lightest_to_best():
    # The GUI slider maps index 0 (left) to the lightest and the last index
    # (right) to the best, most compute-hungry model.
    assert MODEL_SIZES == ("LITE", "NORMAL", "LARGE", "XL")


@pytest.mark.parametrize(
    "hmd,size,expected",
    [
        ("ETVR", "NORMAL", "ETVR"),
        ("BSB", "LITE", "BSB LITE"),
        ("PSVR", "large", "PSVR LARGE"),
        ("TOBII", "XL", "PSVR XL"),
        ("ETVR", "NANO", "ETVR"),
        ("bogus", "bogus", "ETVR"),
    ],
)
def test_compose_variant(hmd, size, expected):
    assert compose_variant(hmd, size) == expected
    assert expected in MODEL_VARIANTS


def test_variant_from_settings_combines_headset_and_size():
    assert variant_from_settings(SimpleNamespace(gui_model_variant="BSB", gui_model_size="XL")) == "BSB XL"
    # Settings saved before the size field existed keep their Lite choice.
    assert variant_from_settings(SimpleNamespace(gui_model_variant="PSVR LITE")) == "PSVR LITE"


@pytest.mark.parametrize("stored,size", [("TOBII", None), ("TOBII LITE", "LITE")])
def test_tobii_migrates_to_psvr(stored, size):
    data = {"version": 5, "settings": {"gui_model_variant": stored}}
    _migrate_config_dict(data)
    assert data["settings"]["gui_model_variant"] == "PSVR"
    assert data["settings"].get("gui_model_size") == size


def test_lite_variants_migrate_to_headset_and_size():
    data = {"version": 5, "settings": {"gui_model_variant": "BSB LITE"}}
    _migrate_config_dict(data)
    assert data["settings"]["gui_model_variant"] == "BSB"
    assert data["settings"]["gui_model_size"] == "LITE"
    plain = {"version": 5, "settings": {"gui_model_variant": "ETVR"}}
    _migrate_config_dict(plain)
    assert plain["settings"] == {"gui_model_variant": "ETVR"}


def test_setup_auto_variants_exclude_psvr():
    # Setup-mode switching picks the variant inside a Tk callback with no
    # callable of its own, so the source is the cheapest guard that it never
    # auto-selects PSVR (a headset the user must choose explicitly).
    app = Path(__file__).resolve().parent.parent / "eyetrackapp" / "eyetrackapp.py"
    source = app.read_text(encoding="utf-8")
    assert 'default_variant = "BSB" if is_bigscreen else "ETVR"' in source
    assert 'default_variant = "PSVR"' not in source


# ── model files ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("base", ["ETVR", "BSB", "PSVR"])
def test_hardware_selects_one_artifact_for_both_camera_modes(base):
    for variant, name in (
        (base, f"NEXT_{base}_111526.onnx"),
        (base + " LITE", f"NEXT_{base}_111526.fp16.onnx"),
        (base + " LARGE", f"NEXT_LARGE_{base}_111526.onnx"),
    ):
        assert variant in MODEL_VARIANTS
        expected = f"assets/models/{name}"
        assert model_file_for_variant(variant) == expected
        assert stereo_model_file(variant) == expected
    # Tobii shares the PSVR family (trained on the Tobii dataset).
    assert model_file_for_variant("TOBII") == "assets/models/NEXT_PSVR_111526.onnx"


@pytest.mark.parametrize("base", ["ETVR", "BSB"])
def test_xl_uses_the_xl_export(base):
    assert model_file_for_variant(f"{base} XL") == f"assets/models/NEXT_XL_{base}_111526.onnx"


def test_every_size_resolves_to_a_shipped_file():
    files = set()
    for hmd in ("ETVR", "BSB", "PSVR"):
        for size in MODEL_SIZES:
            path = model_file_for_variant(compose_variant(hmd, size))
            assert os.path.exists(resource_path(path)), path
            files.add(path)
    # PSVR has no XL export: its XL is the Large model.
    assert len(files) == 3 * len(MODEL_SIZES) - 1
    assert model_file_for_variant("PSVR XL") == model_file_for_variant("PSVR LARGE")


@pytest.mark.parametrize("base", ["ETVR", "BSB", "PSVR"])
@pytest.mark.parametrize("size", ["LARGE", "XL"])
def test_missing_large_export_falls_back_to_normal(monkeypatch, base, size):
    monkeypatch.setattr(next_model.os.path, "exists", lambda path: "_LARGE_" not in path and "_XL_" not in path)
    assert model_file_for_variant(f"{base} {size}") == model_file_for_variant(base)


@pytest.mark.parametrize("base", ["ETVR", "BSB", "PSVR"])
def test_hybrid_lite_falls_back_to_full_precision(monkeypatch, base):
    monkeypatch.setattr(next_model.os.path, "exists", lambda path: not path.endswith(".fp16.onnx"))
    expected = model_file_for_variant(base)
    assert model_file_for_variant(base + " LITE") == expected
    assert stereo_model_file(base + " LITE") == expected


# ── mono runner ──────────────────────────────────────────────────────────────


def test_mono_next_preserves_model_y_axis():
    model = NEXT_cls.__new__(NEXT_cls)
    model.input_size = 2
    model.raw_input = True
    model.temporal_frames = 1
    model.input_dtype = np.float32
    model.uses_directml = False
    model.input_name = "input"
    model.ort_session = StaticSession([0.1, 0.2, 0.3, 0.4, 0.65])
    model.one_euro_filter = IdentityFilter(5)
    model._brow_window = TimedMedian(5)
    model._gaze_x_window = TimedMedian(3)
    model._gaze_y_window = TimedMedian(3)

    _, gaze_y, _, _, _ = model.run(np.zeros((2, 2, 3), dtype=np.uint8))

    assert gaze_y == np.float32(0.65)
