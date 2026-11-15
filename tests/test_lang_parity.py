"""Every locale carries every English string with the same placeholders, so the
UI never falls back to English mid-screen or fails to format a translation."""

from pathlib import Path
import re
import tomllib

import pytest

LANG = Path(__file__).resolve().parents[1] / "eyetrackapp" / "lang"
LOCALES = sorted(path.stem for path in LANG.glob("*.toml") if path.stem not in ("en", "_template"))
PLACEHOLDER = re.compile(r"(?<!\{)\{(\w*)[^{}]*\}(?!\})")


def _strings(name):
    def flatten(table, prefix=""):
        for key, value in table.items():
            if isinstance(value, dict):
                yield from flatten(value, f"{prefix}{key}.")
            else:
                yield f"{prefix}{key}", value

    with open(LANG / f"{name}.toml", "rb") as file:
        return dict(flatten(tomllib.load(file)))


ENGLISH = _strings("en")


def test_there_are_locales_to_check():
    assert LOCALES


def test_template_lists_every_string():
    assert set(_strings("_template")) == set(ENGLISH)


@pytest.mark.parametrize("locale", LOCALES)
def test_locale_has_exactly_the_english_strings(locale):
    strings = _strings(locale)
    assert sorted(set(ENGLISH) - set(strings)) == []
    assert sorted(set(strings) - set(ENGLISH)) == []


@pytest.mark.parametrize("locale", LOCALES)
def test_locale_keeps_the_english_placeholders(locale):
    strings = _strings(locale)
    mismatched = [
        key
        for key, text in ENGLISH.items()
        if isinstance(text, str)
        and isinstance(strings.get(key), str)
        and strings[key]
        and set(PLACEHOLDER.findall(text)) != set(PLACEHOLDER.findall(strings[key]))
    ]
    assert mismatched == []


APP = LANG.parent
# Files whose window text was moved into the language files. Each must only name keys that exist.
KEYED_FILES = [
    "contributions/window.py",
    "contributions/report_window.py",
    "contributions/client.py",
    "contributions/verification.py",
    "data_collection.py",
    "setup_wizard.py",
    "update_dialog.py",
    "ovr/dfr.py",
    "ovr/vr_dashboard.py",
    "settings/dfr_panel.py",
    "settings/modules/general_settings_module.py",
]
TR_CALL = re.compile(r"""\btr(?:_english)?\(\s*["']([^"']+)["']""")
# Keys built with an f-string, e.g. tr(f"dfr.state_{status.state}"); expanded by _built_keys().
TR_FSTRING_CALL = re.compile(r"""\btr(?:_english)?\(\s*f["']([^"']+)["']""")
# Keys kept in tables or constants and translated where shown, e.g. "contributions.state_pending".
KEY_LITERAL = re.compile(r"""["']([a-z_]+)\.([a-z0-9_]+)["']""")


def _built_keys():
    """Every value each f-string key can take, and the keys behind label tables that
    a file shows without calling tr() itself."""
    from ovr import dfr, dfr_setup, vr_dashboard
    from settings import dfr_panel
    from settings.modules import general_settings_module

    states = [
        dfr.UNSUPPORTED,
        dfr.STEAMVR_OFF,
        dfr.NO_GAME,
        dfr.TOOL_MISSING,
        dfr.NEEDS_SYSTEM_FILES,
        dfr.DFR_UI_RUNNING,
        dfr.BLOCKED,
        dfr.OFF,
        dfr.GAZE_OFF,
        dfr.ATTACHING,
        dfr.ATTACHED,
        dfr.ATTACH_FAILED,
        dfr.IDLE,
        dfr.NATIVE,
        dfr.OPENXR,
        dfr.RENDERER,
        dfr.DISABLED,
    ]
    setup_errors = [
        dfr_setup.DOWNLOAD_FAILED,
        dfr_setup.BAD_DOWNLOAD,
        dfr_setup.WRITE_FAILED,
        dfr_setup.STEAMVR_RUNNING,
        dfr_setup.SYSTEM_FILES_FAILED,
    ]
    leaves = list(general_settings_module._LEAF.values())
    templates = {
        "dfr.state_{status.state}": states,
        "dfr.quality_{mode}": list(dfr.MODES),
        "dfr.quality_{key}": list(dfr_panel.QUALITY_ORDER),
        "dfr.setup_{error}": setup_errors,
        "settings_general.{_LEAF[field]}": leaves,
        "settings_general.{_LEAF[field]}_tip": leaves,
    }
    expanded = {
        template: {re.sub(r"\{[^{}]*\}", value, template) for value in values} for template, values in templates.items()
    }
    # ovr/dfr.py fills the dashboard panel's labels from these keys.
    tables = {
        "ovr/vr_dashboard.py": {
            f"dfr.{name}" if name.startswith("quality_") else f"dashboard.{name}"
            for name in vr_dashboard.DEFAULT_LABELS
        },
    }
    return expanded, tables


@pytest.mark.parametrize("name", KEYED_FILES)
def test_every_key_named_in_the_code_exists_in_english(name):
    source = (APP / name).read_text(encoding="utf-8")
    sections = {key.split(".")[0] for key in ENGLISH}
    expanded, tables = _built_keys()
    keys = set(TR_CALL.findall(source))
    keys |= {f"{section}.{key}" for section, key in KEY_LITERAL.findall(source) if section in sections}
    templates = set(TR_FSTRING_CALL.findall(source))
    assert sorted(templates - set(expanded)) == [], "list the values of these f-string keys in _built_keys()"
    for template in templates:
        keys |= expanded[template]
    keys |= tables.get(name, set())
    assert keys, "no language keys found; the pattern no longer matches the code"
    assert sorted(key for key in keys if key not in ENGLISH) == []
