import logging

from utils import onnx_runtime as ort_utils


class _FakeSession:
    def __init__(self, providers):
        self._providers = [
            item[0] if isinstance(item, tuple) else item for item in providers
        ]

    def get_providers(self):
        return self._providers


def test_gpu_disabled_uses_cpu_only(monkeypatch):
    calls = []

    def fake_session(_path, sess_options, providers):
        calls.append(providers)
        return _FakeSession(providers)

    monkeypatch.setattr(ort_utils.onnxruntime, "InferenceSession", fake_session)
    monkeypatch.setattr(
        ort_utils.onnxruntime,
        "get_available_providers",
        lambda: ["DmlExecutionProvider", "CPUExecutionProvider"],
    )

    session, uses_dml = ort_utils.create_inference_session(
        "model.onnx",
        object(),
        use_gpu=False,
        component="test",
        logger=logging.getLogger(__name__),
    )

    assert calls == [["CPUExecutionProvider"]]
    assert session.get_providers() == ["CPUExecutionProvider"]
    assert uses_dml is False


def test_gpu_enabled_prefers_directml_with_cpu_fallback(monkeypatch):
    calls = []

    def fake_session(_path, sess_options, providers):
        calls.append(providers)
        return _FakeSession(providers)

    monkeypatch.setattr(ort_utils.onnxruntime, "InferenceSession", fake_session)
    monkeypatch.setattr(
        ort_utils.onnxruntime,
        "get_available_providers",
        lambda: ["DmlExecutionProvider", "CPUExecutionProvider"],
    )

    session, uses_dml = ort_utils.create_inference_session(
        "model.onnx",
        object(),
        use_gpu=True,
        component="test",
        logger=logging.getLogger(__name__),
    )

    assert calls == [
        [
            ("DmlExecutionProvider", {"enable_share_strategy": True}),
            "CPUExecutionProvider",
        ]
    ]
    assert session.get_providers()[0] == "DmlExecutionProvider"
    assert uses_dml is True


def test_broken_gpu_session_falls_back_to_cpu(monkeypatch):
    calls = []

    def fake_session(_path, sess_options, providers):
        calls.append(providers)
        if providers[0] != "CPUExecutionProvider":
            raise RuntimeError("provider unavailable")
        return _FakeSession(providers)

    monkeypatch.setattr(ort_utils.onnxruntime, "InferenceSession", fake_session)
    monkeypatch.setattr(
        ort_utils.onnxruntime,
        "get_available_providers",
        lambda: ["DmlExecutionProvider", "CPUExecutionProvider"],
    )

    session, uses_dml = ort_utils.create_inference_session(
        "model.onnx",
        object(),
        use_gpu=True,
        component="test",
        logger=logging.getLogger(__name__),
    )

    assert len(calls) == 2
    assert calls[1] == ["CPUExecutionProvider"]
    assert session.get_providers() == ["CPUExecutionProvider"]
    assert uses_dml is False
