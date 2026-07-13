"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------

Lightweight localization (i18n) layer.

Design goals:
* **Drop-in languages.** Every language is a single ``lang/<code>.toml`` file.
  Adding one is purely a data change: copy ``_TEMPLATE.toml``, translate the
  values, drop it in ``lang/``, relaunch. No code edits, no registration.
* **English is the source of truth.** ``en.toml`` holds the canonical strings
  and is always loaded as the fallback base, so a translation that is missing a
  key (or is only partially filled in) simply shows English for that key rather
  than a blank or a crash.
* **Restart to apply.** The active language is chosen once at startup from the
  saved config. Changing it in the GUI persists the choice and prompts a
  restart; tkinter builds widget text once, so we don't try to re-text live.

Usage::

    from localization import tr, init_localization
    init_localization("es")          # once, before building the UI
    label = tr("settings.use_gpu")   # -> "Aceleración por GPU"
    status = tr("status.tracking_mode", mode="Dual")  # {mode} placeholder
"""
from __future__ import annotations

import logging
import os
import tomllib
from typing import Any

from utils.misc_utils import resource_path

logger = logging.getLogger(__name__)

# Locale code that is always available and used as the fallback base.
DEFAULT_LANGUAGE = "en"

_LANG_DIRNAME = "lang"

# Populated by init_localization(). ``_base`` is always English; ``_active`` is
# the selected language overlaid on top. Lookups check _active then _base.
_base_catalog: dict[str, Any] = {}
_active_catalog: dict[str, Any] = {}
_active_code: str = DEFAULT_LANGUAGE

# Keys we've already warned about, so a missing string logs once, not per frame.
_warned_keys: set[str] = set()


def _lang_dir() -> str:
    """Absolute path to the ``lang`` folder, valid in dev and frozen builds."""
    return resource_path(_LANG_DIRNAME)


def _load_toml(path: str) -> dict[str, Any]:
    """Parse one .toml file into a dict. Returns {} (and logs) on any error so a
    single broken language file can never take down the app."""
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.warning("Could not load language file %s: %s", path, e)
        return {}


def init_localization(lang_code: str | None) -> None:
    """Load the English base catalog plus the selected language.

    Call once at startup (after config load, before building the UI). Passing an
    unknown/None ``lang_code`` falls back to English. Safe to call again to
    switch the in-memory language, but note the GUI won't re-text until rebuilt.
    """
    global _base_catalog, _active_catalog, _active_code, _warned_keys

    lang_dir = _lang_dir()
    _base_catalog = _load_toml(os.path.join(lang_dir, f"{DEFAULT_LANGUAGE}.toml"))
    if not _base_catalog:
        logger.error("English catalog (%s.toml) missing or empty; UI text will "
                     "fall back to raw keys.", DEFAULT_LANGUAGE)

    code = (lang_code or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    if code == DEFAULT_LANGUAGE:
        _active_catalog = {}
    else:
        path = os.path.join(lang_dir, f"{code}.toml")
        if os.path.exists(path):
            _active_catalog = _load_toml(path)
        else:
            logger.warning("Language '%s' not found in %s; using English.", code, lang_dir)
            _active_catalog = {}
            code = DEFAULT_LANGUAGE

    _active_code = code
    _warned_keys = set()
    logger.info("Localization initialized: language=%s", _active_code)


def _lookup(catalog: dict[str, Any], key: str) -> str | None:
    """Resolve a dot-addressed key (``"settings.use_gpu"``) against a nested
    dict of TOML tables. Returns None if any segment is missing or the leaf is
    not a string."""
    node: Any = catalog
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def tr(key: str, **fmt: Any) -> str:
    """Translate ``key`` for the active language.

    Fallback chain: active language -> English -> the key itself (so a missing
    string is visible during development rather than silently blank). When
    keyword args are supplied they are applied with ``str.format`` so catalog
    entries can carry ``{placeholder}`` fields for dynamic strings.
    """
    value = _lookup(_active_catalog, key)
    if value is None:
        value = _lookup(_base_catalog, key)
    if value is None:
        if key not in _warned_keys:
            _warned_keys.add(key)
            logger.warning("Missing translation key: %s", key)
        value = key

    if fmt:
        try:
            return value.format(**fmt)
        except (KeyError, IndexError, ValueError):
            logger.warning("Bad format for translation key %s: %r", key, value)
            return value
    return value


def available_languages() -> list[dict[str, str]]:
    """Discover selectable languages by scanning ``lang/*.toml``.

    Files whose name starts with ``_`` (e.g. the template) are skipped. Each
    returned dict has ``code``, ``name`` (English name) and ``native_name``
    (shown in the dropdown). English is listed first, then the rest sorted by
    native name. A file missing a ``[meta]`` code is skipped with a warning.
    """
    lang_dir = _lang_dir()
    langs: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        entries = sorted(os.listdir(lang_dir))
    except OSError as e:
        logger.warning("Could not list language dir %s: %s", lang_dir, e)
        entries = []

    for fname in entries:
        if not fname.endswith(".toml") or fname.startswith("_"):
            continue
        data = _load_toml(os.path.join(lang_dir, fname))
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        code = str(meta.get("code") or os.path.splitext(fname)[0]).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        langs.append({
            "code": code,
            "name": str(meta.get("name") or code),
            "native_name": str(meta.get("native_name") or meta.get("name") or code),
        })

    # Guarantee English is present and first even if en.toml lacks [meta].
    if DEFAULT_LANGUAGE not in seen:
        langs.insert(0, {"code": DEFAULT_LANGUAGE, "name": "English", "native_name": "English"})

    langs.sort(key=lambda l: (l["code"] != DEFAULT_LANGUAGE, l["native_name"].lower()))
    return langs


def get_active_language() -> str:
    """Return the currently loaded language code."""
    return _active_code
