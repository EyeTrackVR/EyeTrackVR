"""The in-VR overlay and the data-collection voice prompts follow the app's
UI language: every lang/*.toml carries the prompt table, every prompt the
session uses exists, and the bundled overlay knows every shipped language."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "EyeTrackApp"
LANG = APP / "lang"
TABLE = "data_collection_prompts"


def _catalog(code):
    with open(LANG / f"{code}.toml", "rb") as fh:
        return tomllib.load(fh)


def _codes():
    return sorted(p.stem for p in LANG.glob("*.toml") if not p.stem.startswith("_"))


def test_every_language_translates_every_prompt():
    en = _catalog("en")[TABLE]
    for code in _codes() + ["_TEMPLATE"]:
        table = _catalog(code).get(TABLE, {})
        assert set(table) == set(en), code
        if code == "_TEMPLATE":
            continue
        for key, value in table.items():
            assert value.strip(), f"{code}: empty {key}"
            if key.endswith("_panel"):
                # Overlay card: a title and at most one subtitle line.
                assert value.count("\n") <= 1, f"{code}: {key}"


def test_session_prompt_keys_exist():
    data_collection = pytest.importorskip("data_collection")
    en = _catalog("en")[TABLE]
    keys = {key for _code, _label, key in data_collection.PROMPT_DATA}
    for _cmd, _prefix, key, _n in data_collection.OVERLAY_PASSES:
        keys |= {f"pass_{key}", f"panel_{key}"}
    keys |= {
        "now",
        "captured",
        "done",
        "blinkdot",
        "blinkdot_panel",
        "blink_no_overlay",
        "closed_roam",
        "closed_roam_panel",
        "headset_shift",
        "headset_shift_panel",
        "center_dot_panel",
    }
    assert keys <= set(en), sorted(keys - set(en))
    # Labels name the training files and must stay English and unique.
    labels = [label for _code, label, _key in data_collection.PROMPT_DATA]
    assert len(set(labels)) == len(labels)
    assert all(label.isascii() for label in labels)


def test_overlay_is_launched_in_the_app_language(monkeypatch):
    import localization
    from utils import overlay_launch

    monkeypatch.setattr(localization, "_active_code", "ja")
    argv = overlay_launch.overlay_command("finetune", executable="overlay")
    assert argv == ["overlay", "finetune", "--lang=ja"]


def _runnable_overlay():
    if sys.platform == "win32":
        return APP / "Tools" / "EyeTrackVR-Overlay.exe"
    if sys.platform == "linux" and os.uname().machine in ("x86_64", "AMD64"):
        return APP / "Tools" / "linux" / "EyeTrackVR-Overlay"
    return None


def test_bundled_overlay_supports_every_app_language():
    exe = _runnable_overlay()
    if exe is None or not exe.is_file():
        pytest.skip("no runnable overlay binary for this platform")
    out = subprocess.run(
        [str(exe), "--list-langs"], capture_output=True, text=True, timeout=30, check=True
    ).stdout.split()
    missing = set(_codes()) - set(out)
    assert not missing, f"overlay lacks built-in text for {sorted(missing)}; rebuild it"
