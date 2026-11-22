"""The Smart Calib report says what a calibration run did, in words."""

import math
from unittest.mock import Mock

import pytest

import localization
from eye import EyeId
from next_smartcal import (
    NEXT_SMARTCAL_DOTS,
    SMARTCAL_APPLIED,
    SMARTCAL_KEPT,
    SMARTCAL_NOT_BETTER,
    SmartCalEyeResult,
    _fit_next_smartcal,
    next_smartcal_dot_tangents,
)
from smartcal_report import headset_report, log_report
from tests.test_next_smartcal import SETTINGS, _model, _processor


@pytest.fixture(autouse=True)
def english():
    localization.init_localization("en")


def _applied(**changes):
    result = SmartCalEyeResult(
        eye=EyeId.LEFT,
        dots_total=11,
        outcome=SMARTCAL_APPLIED,
        dots_used=10,
        dropped=[(2, 9.4)],
        heldout_mean=1.84,
        heldout_worst=3.91,
        current_mean=3.12,
    )
    for name, value in changes.items():
        setattr(result, name, value)
    return result


def test_the_headset_shows_the_outcome_and_accuracy():
    assert headset_report([_applied()]).splitlines() == [
        "Calibration saved.",
        "Average error 1.8°, worst 3.9°, on 10 of 11 dots.",
    ]
    assert headset_report([_applied(outcome=SMARTCAL_KEPT)]).startswith("Kept your previous calibration")
    assert headset_report([_applied(outcome=SMARTCAL_NOT_BETTER)]).startswith("Calibration not saved: this run was less")


def test_a_failed_calibration_says_what_went_wrong():
    result = SmartCalEyeResult(eye=EyeId.LEFT, dots_total=11, reason="too_few_dots", dots_used=4)
    assert headset_report([result]) == (
        "Calibration failed: only 4 of 11 dots were tracked. "
        "Check that the cameras see your pupils when you look towards the edges."
    )
    inconsistent = SmartCalEyeResult(eye=EyeId.LEFT, dots_total=11, reason="inconsistent", fit_error=9.25)
    assert "(9.2° average)" in headset_report([inconsistent])
    assert log_report([], finished=False) == "Calibration stopped before it finished. Nothing was changed."


def test_eyes_share_a_block_unless_their_results_differ():
    assert headset_report([_applied(), _applied(eye=EyeId.RIGHT)]) == headset_report([_applied()])
    both = headset_report([_applied(), _applied(eye=EyeId.RIGHT, heldout_mean=2.5)])
    assert both.startswith("Left eye: Calibration saved.") and "\nRight eye: Calibration saved." in both


def test_headset_text_fits_the_overlay_in_bytes():
    localization.init_localization("ja")
    text = headset_report([_applied(), _applied(eye=EyeId.RIGHT, heldout_mean=2.5)])
    assert len(text.encode("utf-8")) <= 400


@pytest.mark.parametrize("locale", ["de", "es", "ja", "zh"])
def test_every_language_formats_the_report(locale):
    localization.init_localization(locale)
    for result in (_applied(), SmartCalEyeResult(eye=EyeId.RIGHT, dots_total=11, reason="no_spread")):
        assert "smartcal." not in headset_report([result, result])


def test_the_fit_reports_each_eye():
    tangents = next_smartcal_dot_tangents()
    raw = {dot: _model(*tangents[dot]) for dot in range(len(NEXT_SMARTCAL_DOTS))}
    raw[2] = (raw[2][0] + 0.35, raw[2][1] + 0.25)
    results = []
    assert _fit_next_smartcal([_processor(raw)], Mock(), SETTINGS, results=results)
    (result,) = results
    assert result.outcome == SMARTCAL_APPLIED
    assert [dot for dot, _ in result.dropped] == [2] and result.dots_used == len(NEXT_SMARTCAL_DOTS) - 1
    assert result.heldout_mean == pytest.approx(0.0, abs=1e-6)
    assert result.current_mean > 1.0
    assert not math.isnan(result.heldout_worst)
