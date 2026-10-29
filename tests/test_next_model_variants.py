import pytest
from types import SimpleNamespace

from config import _migrate_config_dict
from eyebrow import MODEL_VARIANTS as EYEBROW_MODEL_VARIANTS
from eyebrow import model_file_for_variant as eyebrow_model_file
from next_model import (
    EXPERIMENTAL_MODEL_SIZES,
    HMD_TYPES,
    MODEL_SIZES,
    MODEL_VARIANTS,
    compose_variant,
    model_file_for_variant,
    split_variant,
    variant_from_settings,
)
from settings.modules.TrackingAlgorithmModule import _MODEL_VARIANTS


@pytest.mark.parametrize("variant,suffix", [("PSVR", ".onnx"), ("PSVR LITE", ".fp16.onnx")])
def test_psvr_is_a_selectable_next_model(variant, suffix):
    assert variant in MODEL_VARIANTS
    assert split_variant(variant)[0] in _MODEL_VARIANTS
    assert model_file_for_variant(variant) == f"Models/NEXT_ETVR_HYBRID_PSVR{suffix}"


@pytest.mark.parametrize("variant", ["PSVR", "PSVR LITE", "PSVR NANO"])
def test_psvr_does_not_require_a_separate_eyebrow_model(variant):
    assert eyebrow_model_file(variant) == "Models/Eyebrow_ETVR.onnx"


@pytest.mark.parametrize("variant", ["BSB", "BSB LITE", "BSB MICRO"])
def test_eyebrow_model_ignores_next_model_size(variant):
    assert eyebrow_model_file(variant) == "Models/Eyebrow_BSB.onnx"


def test_gui_and_inference_offer_the_same_headsets():
    assert HMD_TYPES == _MODEL_VARIANTS == EYEBROW_MODEL_VARIANTS


def test_model_size_slider_runs_lightest_to_best():
    # The GUI slider maps index 0 (left) to the lightest and the last index
    # (right) to the best, most compute-hungry model.
    assert MODEL_SIZES == ("NANO", "MICRO", "MINI", "SMALL", "LITE", "NORMAL")
    assert set(EXPERIMENTAL_MODEL_SIZES) == set(MODEL_SIZES[: MODEL_SIZES.index("LITE")])


def test_every_hybrid_size_resolves_to_a_shipped_file():
    import os
    from utils.misc_utils import resource_path

    files = set()
    for hmd in ("ETVR", "BSB", "PSVR"):
        for size in MODEL_SIZES:
            path = model_file_for_variant(compose_variant(hmd, size))
            assert os.path.exists(resource_path(path)), path
            files.add(path)
    assert len(files) == 3 * len(MODEL_SIZES)


@pytest.mark.parametrize(
    "hmd,size,expected",
    [
        ("ETVR", "NORMAL", "ETVR"),
        ("BSB", "LITE", "BSB LITE"),
        ("PSVR", "nano", "PSVR NANO"),
        ("TOBII", "NANO", "PSVR NANO"),
        ("bogus", "bogus", "ETVR"),
    ],
)
def test_compose_variant(hmd, size, expected):
    assert compose_variant(hmd, size) == expected
    assert expected in MODEL_VARIANTS


def test_variant_from_settings_combines_headset_and_size():
    assert variant_from_settings(SimpleNamespace(gui_model_variant="BSB", gui_model_size="MINI")) == "BSB MINI"
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
    # These are intentionally the only values assigned by setup-mode switching.
    source = open("EyeTrackApp/eyetrackapp.py", encoding="utf-8").read()
    assert 'default_variant = "BSB" if is_bigscreen else "ETVR"' in source
    assert 'default_variant = "PSVR"' not in source
