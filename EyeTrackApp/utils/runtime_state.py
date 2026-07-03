"""Process-local live state shared between camera threads and the settings UI.
Not persisted; values flow one-way from producer (eye processor) to consumer
(tk canvas). A single lock protects the dict; writes are tiny floats."""
from __future__ import annotations
from threading import Lock

_lock = Lock()
_state: dict[str, float] = {}


def set_value(key: str, value: float) -> None:
    with _lock:
        _state[key] = float(value)


def get_value(key: str, default: float | None = None) -> float | None:
    with _lock:
        return _state.get(key, default)
