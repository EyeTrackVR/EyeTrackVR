"""ONNX Runtime provider choice (utils.onnx_runtime): CPU unless the GPU is
asked for, accelerators in their order of preference, and a broken GPU
provider falling back to CPU instead of stopping tracking."""

import logging

import pytest

from utils import onnx_runtime as ort_utils


class _FakeSession:
    def __init__(self, providers):
        self._providers = [item[0] if isinstance(item, tuple) else item for item in providers]

    def get_providers(self):
        return self._providers


@pytest.fixture
def ort(monkeypatch):
    """onnxruntime with the given providers installed; ``ort.calls`` lists the
    provider lists sessions were requested with, ``ort.broken`` the providers
    whose sessions fail to build."""
    state = type("Ort", (), {})()
    state.calls = []
    state.broken = set()
    state.available = ["DmlExecutionProvider", "CPUExecutionProvider"]

    def fake_session(_path, sess_options, providers):
        state.calls.append(providers)
        first = providers[0][0] if isinstance(providers[0], tuple) else providers[0]
        if first in state.broken:
            raise RuntimeError("provider unavailable")
        return _FakeSession(providers)

    monkeypatch.setattr(ort_utils.onnxruntime, "InferenceSession", fake_session)
    monkeypatch.setattr(ort_utils.onnxruntime, "get_available_providers", lambda: state.available)
    return state


def _create(use_gpu):
    return ort_utils.create_inference_session(
        "model.onnx", object(), use_gpu=use_gpu, component="test", logger=logging.getLogger(__name__)
    )


def test_gpu_disabled_uses_cpu_only(ort):
    session, uses_dml = _create(use_gpu=False)

    assert ort.calls == [["CPUExecutionProvider"]]
    assert session.get_providers() == ["CPUExecutionProvider"]
    assert uses_dml is False


def test_gpu_enabled_prefers_directml_with_cpu_fallback(ort):
    session, uses_dml = _create(use_gpu=True)

    assert ort.calls == [
        [
            ("DmlExecutionProvider", {"enable_share_strategy": True}),
            "CPUExecutionProvider",
        ]
    ]
    assert session.get_providers()[0] == "DmlExecutionProvider"
    assert uses_dml is True


def test_accelerators_are_tried_in_order_of_preference(ort):
    ort.available = ["CoreMLExecutionProvider", "CPUExecutionProvider", "CUDAExecutionProvider", "AzureProvider"]

    session, uses_dml = _create(use_gpu=True)

    assert ort.calls == [["CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider"]]
    assert uses_dml is False


def test_broken_gpu_session_falls_back_to_cpu(ort, caplog):
    ort.broken = {"DmlExecutionProvider"}

    session, uses_dml = _create(use_gpu=True)

    assert len(ort.calls) == 2
    assert ort.calls[1] == ["CPUExecutionProvider"]
    assert session.get_providers() == ["CPUExecutionProvider"]
    assert uses_dml is False
    assert "falling back to CPU" in caplog.text
