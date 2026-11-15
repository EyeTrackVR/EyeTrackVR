import pytest

import localization


@pytest.fixture(autouse=True)
def english(monkeypatch):
    """The windows and service messages read their text from the language files; load English
    as the app does at startup, and put the previous catalogs back afterwards."""
    for name in ("_base_catalog", "_active_catalog", "_active_code", "_warned_keys"):
        monkeypatch.setattr(localization, name, getattr(localization, name))
    localization.init_localization("en")
