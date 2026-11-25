"""Shared fixtures for the contribution tests.

CI runs this folder on its own (``--confcutdir=tests/contributions``), so the
isolation in tests/conftest.py does not apply here; ``private_data`` repeats the
part these tests need."""

import pytest

import localization
from tests import tk_support


@pytest.fixture(autouse=True)
def english(monkeypatch):
    """The windows and service messages read their text from the language files; load English
    as the app does at startup, and put the previous catalogs back afterwards."""
    for name in ("_base_catalog", "_active_catalog", "_active_code", "_warned_keys"):
        monkeypatch.setattr(localization, name, getattr(localization, name))
    localization.init_localization("en")


@pytest.fixture(autouse=True)
def private_data(monkeypatch, tmp_path_factory):
    """Receipts, bug-report receipts and the logs a report attaches come from a
    temporary folder, never the developer's own EyeTrackVR data."""
    from contributions import client
    from utils import logging_utils

    home = tmp_path_factory.mktemp("data_home")
    monkeypatch.setattr(client, "_data_home", lambda: home)
    logs = tmp_path_factory.mktemp("logs")
    monkeypatch.setattr(logging_utils, "log_directory", lambda: logs)
    return home


@pytest.fixture(scope="module")
def root():
    """One withdrawn Tk root per test module (skips without a display)."""
    root = tk_support.new_root()
    yield root
    tk_support.destroy(root)
