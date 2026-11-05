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
