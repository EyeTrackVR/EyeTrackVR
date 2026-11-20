"""What a gaze range check found, in words.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

from localization import tr
from utils.overlay_launch import headset_text

_CARDINAL = ("up", "down", "left", "right")


def _sides(result, names) -> str:
    rays = {ray.name: ray for ray in result.rays}
    return ", ".join(
        tr(
            "range_check.side",
            direction=tr(f"range_check.{name}"),
            verified=f"{rays[name].verified_deg:.0f}",
            shown=f"{rays[name].shown_deg:.0f}",
        )
        for name in names
        if name in rays
    )


def headset_report(result) -> str:
    """What the check found, for the headset. ``result`` is None when the
    check did not finish."""
    if result is None:
        return tr("range_check.stopped")
    if not result.tracked:
        return tr("range_check.not_tracked")
    names = [ray.name for ray in result.rays]
    return headset_text(
        [
            tr("range_check.title"),
            tr("range_check.verified", error=f"{result.max_error_deg:.1f}"),
            _sides(result, [name for name in names if name in _CARDINAL]),
            _sides(result, [name for name in names if name not in _CARDINAL]),
        ]
    )


def log_report(result) -> str:
    """The headset report, and the output limits to compare it with."""
    if result is None or not result.tracked:
        return headset_report(result)
    yaw, up, down = result.limits
    return (
        headset_report(result) + "\n" + tr("range_check.limits", yaw=f"{yaw:.0f}", up=f"{up:.0f}", down=f"{down:.0f}")
    )
