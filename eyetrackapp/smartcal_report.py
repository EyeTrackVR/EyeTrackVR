"""What a Smart Calib run did, in words, for the headset and the log.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

from eye import EyeId
from localization import tr
from next_smartcal import SMARTCAL_REJECTED
from utils.overlay_launch import headset_text


def _deg(value: float) -> str:
    return f"{value:.1f}"


def _eye_name(eye) -> str:
    return tr("smartcal.eye_left") if eye == EyeId.LEFT else tr("smartcal.eye_right")


def _status(result) -> str:
    if result.outcome != SMARTCAL_REJECTED:
        return tr(f"smartcal.{result.outcome}")
    return tr(
        f"smartcal.{result.reason or 'degenerate'}",
        used=result.dots_used,
        total=result.dots_total,
        error=_deg(result.fit_error or 0.0),
    )


def eye_report_lines(result) -> list:
    """The outcome, then the accuracy when there is one."""
    lines = [_status(result)]
    if result.heldout_mean is not None:
        lines.append(
            tr(
                "smartcal.accuracy",
                mean=_deg(result.heldout_mean),
                worst=_deg(result.heldout_worst),
                used=result.dots_used,
                total=result.dots_total,
            )
        )
    return lines


def headset_report(results) -> str:
    """The short report shown in the headset after the dots. Eyes with the
    same result (fused gaze) share one block."""
    blocks = [eye_report_lines(result) for result in results]
    if len(blocks) > 1 and any(block != blocks[0] for block in blocks):
        for block, result in zip(blocks, results):
            block[0] = f"{_eye_name(result.eye)}: {block[0]}"
    else:
        blocks = blocks[:1]
    return headset_text([line for block in blocks for line in block])


def log_report(results, finished: bool) -> str:
    return headset_report(results) if finished and results else tr("smartcal.stopped")
