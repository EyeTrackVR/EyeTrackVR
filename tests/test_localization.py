"""Language files (localization.py): the chosen language, then English, then the key
itself; placeholders that can't be filled never crash; a missing or broken file falls
back instead of taking the app down; and the language list the settings offer."""

import logging

import pytest

import localization
from localization import tr, tr_english

EN = """
[meta]
code = "en"
name = "English"
native_name = "English"

[app]
hello = "Hello"
greet = "Hello, {name}"
only_english = "Only in English"
"""
DE = """
[meta]
code = "de"
name = "German"
native_name = "Deutsch"

[app]
hello = "Hallo"
greet = "Hallo, {name}"
"""


@pytest.fixture
def lang_dir(monkeypatch, tmp_path):
    """A language folder of the test's own; the app's catalogs are put back afterwards."""
    for name in ("_base_catalog", "_active_catalog", "_active_code", "_warned_keys"):
        monkeypatch.setattr(localization, name, getattr(localization, name))
    monkeypatch.setattr(localization, "_lang_dir", lambda: str(tmp_path))
    (tmp_path / "en.toml").write_text(EN, encoding="utf-8")
    (tmp_path / "de.toml").write_text(DE, encoding="utf-8")
    return tmp_path


def test_the_chosen_language_then_english_then_the_key(lang_dir, caplog):
    localization.init_localization("de")
    assert localization.get_active_language() == "de"
    assert tr("app.hello") == "Hallo"
    assert tr("app.only_english") == "Only in English"
    with caplog.at_level(logging.WARNING, logger="localization"):
        assert tr("app.nowhere") == "app.nowhere"
        assert tr("app.nowhere") == "app.nowhere"
        assert tr("app") == "app"  # a table, not a string
    assert caplog.text.count("Missing translation key: app.nowhere") == 1  # once, not every frame


def test_placeholders(lang_dir):
    localization.init_localization("de")
    assert tr("app.greet", name="Ada") == "Hallo, Ada"
    assert tr("app.greet", other="x") == "Hallo, {name}"  # a placeholder it can't fill: shown as is
    assert tr("app.hello", name="unused") == "Hallo"
    assert tr_english("app.greet", name="Ada") == "Hello, Ada"  # whatever the active language
    assert tr_english("app.nowhere") == "app.nowhere"


@pytest.mark.parametrize("code", ["xx", None, "", "  "])
def test_an_unknown_language_is_english(lang_dir, code):
    localization.init_localization(code)
    assert localization.get_active_language() == "en"
    assert tr("app.hello") == "Hello"


def test_a_broken_language_file_falls_back_to_english(lang_dir):
    (lang_dir / "de.toml").write_text('[app]\nhello = "Hallo', encoding="utf-8")  # unterminated string
    localization.init_localization("de")
    assert tr("app.hello") == "Hello"


def test_without_english_the_keys_show(lang_dir):
    (lang_dir / "en.toml").unlink()
    localization.init_localization("en")
    assert tr("app.hello") == "app.hello"


def test_the_language_list(lang_dir):
    (lang_dir / "_template.toml").write_text(EN, encoding="utf-8")  # for translators, not a language
    (lang_dir / "de_copy.toml").write_text(DE, encoding="utf-8")  # same code again
    (lang_dir / "ja.toml").write_text(
        '[meta]\ncode = "ja"\nname = "Japanese"\nnative_name = "日本語"\n', encoding="utf-8"
    )
    (lang_dir / "notes.txt").write_text("x", encoding="utf-8")

    langs = localization.available_languages()

    # English first, then by native name.
    assert [lang["code"] for lang in langs] == ["en", "de", "ja"]
    assert langs[1] == {"code": "de", "name": "German", "native_name": "Deutsch"}


def test_english_is_always_offered_first(lang_dir):
    (lang_dir / "en.toml").unlink()
    langs = localization.available_languages()
    assert langs[0] == {"code": "en", "name": "English", "native_name": "English"}
    assert [lang["code"] for lang in langs] == ["en", "de"]
