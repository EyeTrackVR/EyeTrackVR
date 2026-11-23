"""The app's dark and light colours (Settings > Light mode)."""

import re

import pytest

import ui_theme
from config import EyeTrackSettingsConfig


@pytest.fixture(autouse=True)
def back_to_dark():
    yield
    ui_theme.set_light(False)


def test_dark_is_the_default():
    assert EyeTrackSettingsConfig().gui_light_mode is False
    assert not ui_theme.is_light()


def test_both_modes_name_the_same_colours():
    # A colour only one mode defines would fail in the other at runtime.
    assert set(ui_theme.DARK) == set(ui_theme.LIGHT)
    for palette in (ui_theme.DARK, ui_theme.LIGHT):
        assert all(re.fullmatch(r"#[0-9a-f]{6}", value) for value in palette.values())


def test_light_mode_switches_the_colours_and_the_ttk_theme():
    assert ui_theme.set_light(True) == "light"
    assert ui_theme.is_light() and ui_theme.color("bg") == ui_theme.LIGHT["bg"]
    assert ui_theme.set_light(False) == "dark"
    assert ui_theme.color("bg") == ui_theme.DARK["bg"]
