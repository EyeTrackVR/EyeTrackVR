"""Shared ONNX Runtime provider selection for optional GPU inference."""

import logging
import threading

import onnxruntime


# DirectML can access-violate when multiple sessions enter inference at once.
# LEAP and both NEXT modes share this process-wide lock.
DML_INFERENCE_LOCK = threading.Lock()

_GPU_PROVIDER_ORDER = (
    "CUDAExecutionProvider",
    "OpenVINOExecutionProvider",
    "ROCMExecutionProvider",
    "DmlExecutionProvider",
    "CoreMLExecutionProvider",
)


def create_inference_session(
    model_path,
    options,
    *,
    use_gpu: bool,
    component: str,
    logger: logging.Logger,
):
    """Create an ORT session with LEAP-style GPU preference and CPU fallback.

    Returns ``(session, uses_directml)``. A missing/broken accelerator never
    prevents tracking: session creation is retried with CPU only.
    """
    providers = []
    if use_gpu:
        available = onnxruntime.get_available_providers()
        for provider in _GPU_PROVIDER_ORDER:
            if provider not in available:
                continue
            if provider == "DmlExecutionProvider":
                providers.append((provider, {"enable_share_strategy": True}))
            else:
                providers.append(provider)

    requested = providers + ["CPUExecutionProvider"]
    try:
        session = onnxruntime.InferenceSession(
            model_path,
            sess_options=options,
            providers=requested,
        )
    except Exception as exc:
        logger.warning(
            "%s GPU ONNX session unavailable (%s); falling back to CPU.",
            component,
            exc,
        )
        session = onnxruntime.InferenceSession(
            model_path,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

    active = session.get_providers()
    logger.info("%s ONNX providers: %s", component, active)
    return session, "DmlExecutionProvider" in active
