from eyebrow import model_file_for_variant as eyebrow_model_file
from next_model import MODEL_VARIANTS, model_file_for_variant
from settings.modules.TrackingAlgorithmModule import _MODEL_VARIANTS


def test_psvr_is_a_selectable_next_model():
    assert "PSVR" in MODEL_VARIANTS
    assert "PSVR" in _MODEL_VARIANTS
    assert model_file_for_variant("PSVR") == "Models/NEXT_PSVR.onnx"


def test_psvr_does_not_require_a_separate_eyebrow_model():
    assert eyebrow_model_file("PSVR") == "Models/Eyebrow_ETVR.onnx"


def test_setup_auto_variants_exclude_psvr():
    # These are intentionally the only values assigned by setup-mode switching.
    source = open("EyeTrackApp/eyetrackapp.py", encoding="utf-8").read()
    assert 'default_variant = "BSB" if is_bigscreen else "ETVR"' in source
    assert 'default_variant = "PSVR"' not in source
