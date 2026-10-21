import pytest

from eyebrow import MODEL_VARIANTS as EYEBROW_MODEL_VARIANTS
from eyebrow import model_file_for_variant as eyebrow_model_file
from next_model import MODEL_VARIANTS, model_file_for_variant
from settings.modules.TrackingAlgorithmModule import _MODEL_VARIANTS


@pytest.mark.parametrize("variant,suffix", [("PSVR", ".onnx"), ("PSVR LITE", ".fp16.onnx")])
def test_psvr_is_a_selectable_next_model(variant, suffix):
    assert variant in MODEL_VARIANTS
    assert variant in _MODEL_VARIANTS
    assert model_file_for_variant(variant) == f"Models/NEXT_ETVR_HYBRID_PSVR{suffix}"


@pytest.mark.parametrize("variant", ["PSVR", "PSVR LITE"])
def test_psvr_does_not_require_a_separate_eyebrow_model(variant):
    assert eyebrow_model_file(variant) == "Models/Eyebrow_ETVR.onnx"


def test_gui_and_inference_offer_the_same_variants():
    assert MODEL_VARIANTS == _MODEL_VARIANTS == EYEBROW_MODEL_VARIANTS


def test_setup_auto_variants_exclude_psvr():
    # These are intentionally the only values assigned by setup-mode switching.
    source = open("EyeTrackApp/eyetrackapp.py", encoding="utf-8").read()
    assert 'default_variant = "BSB" if is_bigscreen else "ETVR"' in source
    assert 'default_variant = "PSVR"' not in source
