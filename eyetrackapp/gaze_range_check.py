"""Gaze range check: how far out the tracked gaze still lands on target.

Dots step outward from the centre along eight directions, out to near the
edge of what the headset shows. Once the gaze rests on each, the calibrated
NEXT gaze (the current Smart Calib fit applied to the raw model gaze, before
the output limits clip it) is compared with where the dot really is. A
direction counts as verified out to the last dot that the gaze hit closely
and steadily, with every dot before it passing too. Nothing is fitted or
saved.

Going past the configured gaze limits shows whether they could be wider, or
must be narrower than the headset allows. Wide headsets are where this
matters: the edges are where the model saturates and the lids hide the
pupil.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np

from calibration_state import var
from gaze_capture import OPEN_LID, GazeTrace
from next_eye_gaze import GAZE_MODE_FUSED, dominant_eye_from_settings, gaze_mode_from_settings
from next_smartcal import (
    CALIBRATION_COVERAGE,
    current_gaze_tangents,
    next_smartcal_dot_tangents,
    parse_overlay_gaze_range,
    show_dot_and_capture,
    start_when_ready,
)
from utils.async_call import Async
from utils.overlay_launch import (
    CMD_END_PASS,
    CMD_QUIT,
    CMD_TEXT,
    SIG_PASS_ENDED,
    SIG_READY,
    OverlaySession,
    OverlayStopped,
)

logger = logging.getLogger(__name__)

_DIAGONAL = math.sqrt(0.5)
# (name, normalised direction, the fractions of the range edge its dots sit at)
RAYS = (
    ("up", (0.0, 1.0), (0.25, 0.5, 0.75, 1.0)),
    ("down", (0.0, -1.0), (0.25, 0.5, 0.75, 1.0)),
    ("left", (-1.0, 0.0), (0.25, 0.5, 0.75, 1.0)),
    ("right", (1.0, 0.0), (0.25, 0.5, 0.75, 1.0)),
    ("up_left", (-_DIAGONAL, _DIAGONAL), (0.5, 0.75, 1.0)),
    ("up_right", (_DIAGONAL, _DIAGONAL), (0.5, 0.75, 1.0)),
    ("down_left", (-_DIAGONAL, -_DIAGONAL), (0.5, 0.75, 1.0)),
    ("down_right", (_DIAGONAL, -_DIAGONAL), (0.5, 0.75, 1.0)),
)
# Fewer open-eye samples than this and the dot counts as not tracked.
MIN_SAMPLES = 5
# A dot passes when the mean gaze lands close to it and scatters little
# around that mean, judged against how the same setup does near the centre:
# the median of the innermost dots (a quarter of the range out). Accuracy
# there differs a lot between a commercial insert and a hand-built rig, so a
# fixed limit would fail one everywhere and wave the other through. Within
# RATIO times the centre's error and jitter passes, never stricter than the
# floors, which allow for the noise of a well calibrated setup.
REFERENCE_LEVEL = 0.25
ERROR_RATIO = 2.0
JITTER_RATIO = 2.0
MIN_ERROR_DEG = 2.0
MIN_JITTER_DEG = 0.5
# Never looser than this, or a gaze that is off near the centre too (frozen
# tracking, a bad calibration) would pass everywhere.
MAX_ERROR_DEG = 5.0
MAX_JITTER_DEG = 1.5
# How long the result stays in the headset.
SUMMARY_S = 10.0
# The dots reach this fraction of the headset's binocular view, as Smart
# Calib's do.
COVERAGE = CALIBRATION_COVERAGE


def check_points():
    """Every dot of the check as (ray name, level, normalised x, y), one ray
    after another from the centre outward."""
    return [(name, level, dx * level, dy * level) for name, (dx, dy), levels in RAYS for level in levels]


def overlay_range_args() -> list:
    """Overlay flags that put the outermost dots near the edge of what both
    eyes can see on the headset, whatever the output limits. The overlay
    logs the range it used."""
    return [f"--coverage={COVERAGE:g}", "--max-deg=89", "--max-deg-up=89", "--max-deg-down=89"]


def mapping_of(ep) -> SimpleNamespace:
    """A copy of an eye's current gaze mapping, so clearing the calibration
    during a check cannot mix two mappings."""
    w, b = getattr(ep, "_next_smartcal_w", None), getattr(ep, "_next_smartcal_b", None)
    return SimpleNamespace(
        _next_smartcal_w=None if w is None else list(w),
        _next_smartcal_b=None if b is None else list(b),
        _next_smartcal_warp=getattr(ep, "_next_smartcal_warp", None),
    )


def scored_eyes(eye_processors: list, settings) -> list:
    """The eyes the check scores: those with a gaze fit. An eye without one
    reads the raw model gaze, which says nothing about the calibration. In
    the per-eye gaze modes both eyes share the dominant eye's fit and the
    other eye may really look elsewhere (see _fit_next_smartcal), so only the
    dominant eye is scored. Every eye when none has a fit."""
    fitted = [
        ep
        for ep in eye_processors
        if getattr(ep, "_next_smartcal_w", None) is not None and getattr(ep, "_next_smartcal_b", None) is not None
    ]
    if gaze_mode_from_settings(settings) != GAZE_MODE_FUSED:
        dominant = dominant_eye_from_settings(settings)
        fitted = [ep for ep in fitted if getattr(ep, "eye_id", None) == dominant] or fitted
    return fitted or list(eye_processors)


def gaze_samples(eye_processors_frames, settings, mappings=None, min_lids=None) -> list:
    """Per eye, (tan_x, tan_y, open) of each of its traced frames: where the
    eye's mapping (``mappings`` by processor id, else its current one) says
    it looked, before the output limits, and whether the eye was open and not
    blinking: its lid at least ``min_lids`` by processor id (GazeTrace.open_lid),
    else OPEN_LID."""
    eyes = []
    for ep, frames in eye_processors_frames:
        mapping = (mappings or {}).get(id(ep), ep)
        min_lid = (min_lids or {}).get(id(ep), OPEN_LID)
        eyes.append(
            [
                (*current_gaze_tangents(mapping, raw_x, raw_y, settings), lid >= min_lid)
                for _, raw_x, raw_y, lid, _ in frames
            ]
        )
    return eyes


def _unit(tan_x: float, tan_y: float) -> np.ndarray:
    direction = np.array([tan_x, tan_y, 1.0])
    return direction / np.linalg.norm(direction)


def score_point(samples, target) -> tuple:
    """(error, jitter) in degrees of the open-eye ``samples`` (tan_x, tan_y,
    open) against the ``target`` tangents, or None when too few.

    Error is the angle between the mean gaze direction and the target. Jitter
    is the angular spread of the gaze around its mean, from how much the mean
    of the unit directions shrinks below 1."""
    directions = [_unit(x, y) for x, y, is_open in samples if is_open]
    if len(directions) < MIN_SAMPLES:
        return None
    mean = np.mean(directions, axis=0)
    concentration = float(np.dot(mean, mean))
    jitter = math.degrees(math.asin(math.sqrt(min(1.0, max(0.0, 1.0 - concentration)))))
    cosine = float(np.dot(mean / np.linalg.norm(mean), _unit(*target)))
    error = math.degrees(math.acos(min(1.0, max(-1.0, cosine))))
    return error, jitter


def score_dot(eyes, target) -> tuple:
    """(error, jitter) in degrees of a dot from each eye's samples of it, or
    None when no eye tracked it. Each eye is scored on its own (score_point),
    so an offset between the eyes does not count as jitter, and the dot
    takes the largest error and the largest jitter among them."""
    scores = [scored for scored in (score_point(samples, target) for samples in eyes) if scored is not None]
    if not scores:
        return None
    return max(error for error, _ in scores), max(jitter for _, jitter in scores)


def _angle_deg(target) -> float:
    return math.degrees(math.atan(math.hypot(*target)))


@dataclass
class RayResult:
    """How far out one direction was verified, in degrees from straight
    ahead, against the farthest dot shown on it."""

    name: str
    verified_deg: float = 0.0
    shown_deg: float = 0.0
    points: list = field(default_factory=list)  # (level, angle, error, jitter) or (level, angle, None, None)


@dataclass
class RangeCheckResult:
    rays: list
    limits: tuple = (40.0, 15.0, 40.0)  # the output gaze limits: sideways, up, down
    tracked: bool = True  # any open-eye gaze arrived at all
    max_error_deg: float = MIN_ERROR_DEG  # the limits the dots were judged by
    max_jitter_deg: float = MIN_JITTER_DEG


def limits_from_centre(scores) -> tuple:
    """(max error, max jitter) in degrees for a pass, from the (error, jitter)
    of the innermost dots. The floors when none of them was tracked."""
    tracked = [score for score in scores if score is not None]
    if not tracked:
        return MIN_ERROR_DEG, MIN_JITTER_DEG
    error, jitter = np.median(np.asarray(tracked, dtype=np.float64), axis=0)
    return (
        min(MAX_ERROR_DEG, max(MIN_ERROR_DEG, ERROR_RATIO * float(error))),
        min(MAX_JITTER_DEG, max(MIN_JITTER_DEG, JITTER_RATIO * float(jitter))),
    )


def score(points, samples: dict, gaze_range, settings) -> RangeCheckResult:
    """Score every dot and verify each ray from the centre outward.
    ``samples`` holds each dot's gaze_samples."""
    tangents = next_smartcal_dot_tangents(gaze_range, [(nx, ny) for _, _, nx, ny in points])
    scores = [score_dot(samples.get(i, []), target) for i, target in enumerate(tangents)]
    max_error, max_jitter = limits_from_centre(
        [scores[i] for i, (_, level, _, _) in enumerate(points) if level == REFERENCE_LEVEL]
    )
    rays = {name: RayResult(name) for name, _, _ in RAYS}
    failed = set()
    for i, (name, level, _, _) in enumerate(points):
        ray = rays[name]
        angle = _angle_deg(tangents[i])
        ray.shown_deg = max(ray.shown_deg, angle)
        scored = scores[i]
        ray.points.append((level, angle, *(scored or (None, None))))
        passed = scored is not None and scored[0] <= max_error and scored[1] <= max_jitter
        if not passed:
            failed.add(name)
        elif name not in failed:
            ray.verified_deg = angle
    limits = tuple(
        float(getattr(settings, name, default))
        for name, default in (
            ("gui_gaze_yaw_max_deg", 40.0),
            ("gui_gaze_pitch_up_deg", 15.0),
            ("gui_gaze_pitch_down_deg", 40.0),
        )
    )
    return RangeCheckResult(
        rays=[rays[name] for name, _, _ in RAYS],
        limits=limits,
        tracked=any(is_open for eyes in samples.values() for eye in eyes for _, _, is_open in eye),
        max_error_deg=max_error,
        max_jitter_deg=max_jitter,
    )


def _log(result: RangeCheckResult) -> None:
    lines = []
    for ray in result.rays:
        for level, angle, error, jitter in ray.points:
            measured = "not tracked" if error is None else f"error {error:.1f} deg, jitter {jitter:.2f} deg"
            lines.append(f"  {ray.name:10s} {level:4.0%} ({angle:4.1f} deg): {measured}")
        lines.append(f"  {ray.name:10s} verified to {ray.verified_deg:.1f} of {ray.shown_deg:.1f} deg")
    logger.info(
        "Gaze range check (error <= %.1f deg, jitter <= %.2f deg, from the dots nearest the centre):\n%s",
        result.max_error_deg,
        result.max_jitter_deg,
        "\n".join(lines),
    )


def _checking() -> bool:
    return var.overlay_active


def _show_points(overlay, trace, points, settings, events: list) -> dict:
    """Show the check's dots once the user is ready and capture each at rest.
    Returns {point: gaze_samples of the scored eyes} for score."""
    from localization import tr

    overlay.wait_for(SIG_READY, _checking)
    overlay.send_text(CMD_TEXT, tr("range_check.follow"))
    start_when_ready(overlay, trace, events, _checking)
    mappings = {id(ep): mapping_of(ep) for ep in scored_eyes(trace.processors, settings)}
    captured = {}
    for i, (_, _, nx, ny) in enumerate(points):
        captured[i] = show_dot_and_capture(overlay, trace, events, i, (nx, ny), _checking)
    overlay.send(CMD_END_PASS)
    overlay.wait_for(SIG_PASS_ENDED, _checking)
    # Blinks are judged against each eye's usual lid over the whole run.
    min_lids = {id(ep): trace.open_lid(ep) for ep in trace.processors}
    return {
        i: gaze_samples([(ep, frames) for ep, frames in eyes if id(ep) in mappings], settings, mappings, min_lids)
        for i, eyes in captured.items()
    }


@Async
def gaze_range_check_overlay(eye_processors: list, settings) -> None:
    """Run the gaze range check in the headset and report the result."""
    from gaze_range_report import headset_report, log_report

    if var.overlay_active:
        return
    var.overlay_active = True
    points = check_points()
    result = None
    no_range = False
    trace = None
    try:
        with OverlaySession("interactive", *overlay_range_args()) as overlay:
            trace = GazeTrace(eye_processors)
            try:
                samples = _show_points(overlay, trace, points, settings, [])
                gaze_range = parse_overlay_gaze_range(overlay.log_text())
                if gaze_range is None:
                    # The dots go out to the edge of this headset's view, so
                    # their angles can't be assumed.
                    no_range = True
                    logger.warning("Gaze range check: the overlay did not report where it drew the dots.")
                else:
                    result = score(points, samples, gaze_range, settings)
                    _log(result)
                overlay.send_text(CMD_TEXT, headset_report(result, no_range))
                deadline = time.monotonic() + SUMMARY_S
                while time.monotonic() < deadline and overlay.process.poll() is None:
                    time.sleep(0.1)
            except OverlayStopped:
                logger.info("Gaze range check stopped.")
            overlay.send(CMD_QUIT)
            overlay.finish()
    except TimeoutError:
        logger.warning("Gaze range check timed out before completion.")
    except OSError as e:
        logger.warning("Gaze range check overlay error (%s). Make sure SteamVR is running.", e)
    finally:
        if trace is not None:
            trace.close()
        try:
            logger.info("Gaze range check report:\n%s", log_report(result, no_range))
        except Exception:
            logger.exception("Gaze range check: could not build the report")
        var.overlay_active = False
