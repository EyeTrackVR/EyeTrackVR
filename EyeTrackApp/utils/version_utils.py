"""Helpers for comparing EyeTrackApp release names."""

from __future__ import annotations

import re


_VERSION_RE = re.compile(
    r"(?:EyeTrackApp\s+)?v?(?P<version>\d+(?:\.\d+)+)"
    r"(?:[\s._-]*(?P<stage>alpha|beta|rc)[\s._-]*(?P<stage_number>\d+)?)?",
    re.IGNORECASE,
)
_STAGE_RANK = {"alpha": 0, "beta": 1, "rc": 2, None: 3}


def parse_app_version(value: str) -> tuple[tuple[int, ...], int, int] | None:
    """Parse release labels such as ``EyeTrackApp 0.3.0 BETA 8``.

    A final release sorts after alpha/beta/rc builds with the same numeric
    version. Extra numeric components (for example ``0.2.5.6``) are retained.
    """
    match = _VERSION_RE.search(str(value).strip())
    if match is None:
        return None
    numbers = tuple(int(part) for part in match.group("version").split("."))
    stage = match.group("stage")
    stage = stage.lower() if stage else None
    stage_number = int(match.group("stage_number") or 0)
    return numbers, _STAGE_RANK[stage], stage_number


def compare_app_versions(installed: str, available: str) -> int | None:
    """Return -1/0/1 when installed is older/equal/newer, or None if unknown."""
    current = parse_app_version(installed)
    latest = parse_app_version(available)
    if current is None or latest is None:
        return None

    current_numbers, current_stage, current_stage_number = current
    latest_numbers, latest_stage, latest_stage_number = latest
    width = max(len(current_numbers), len(latest_numbers))
    current_key = (
        current_numbers + (0,) * (width - len(current_numbers)),
        current_stage,
        current_stage_number,
    )
    latest_key = (
        latest_numbers + (0,) * (width - len(latest_numbers)),
        latest_stage,
        latest_stage_number,
    )
    return (current_key > latest_key) - (current_key < latest_key)
