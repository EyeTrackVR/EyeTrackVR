"""Following the raw NEXT gaze while the overlay shows dots: waiting until it
rests on a dot, and taking the frames to capture.

The eye threads append every frame to each processor's
``_next_smartcal_trace`` while a run is on (see next_processing). This reads
those lists as they grow.

When the gaze rests is judged against the setup's own noise, not a fixed
number. A run first learns how much the gaze scatters while the user looks at
a dot (the steadiest short stretch seen so far), and a stretch counts as
resting once it scatters by no more than RATIO times that. Cameras, models
and eyes differ a lot in that noise, and in how long a saccade and its
settling take.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

from __future__ import annotations

import math
import statistics
import time

# Frames with the lids below OPEN_FRACTION of the run's usual lid reading are
# blinks, not gaze. How high the raw lid of an open eye reads differs between
# users and cameras (Smart Calib takes a resting lid from 0.15 up), so a fixed
# level would call every frame of a low-reading eye a blink. Never above
# OPEN_LID, and never below MIN_OPEN_LID: a run with the eyes shut has no
# open-eye frames.
OPEN_LID = 0.3
OPEN_FRACTION = 0.5
MIN_OPEN_LID = 0.05
# The usual lid reading of a growing trace is taken again every this many
# frames.
LID_REFRESH_FRAMES = 30
# The gaze rests when, over the last SETTLE_S, it stays within RATIO times the
# steadiest scatter seen in this run, but never stricter than FLOOR (raw gaze
# units, about half a degree) and never looser than CEILING (about two
# degrees, far below a saccade). The ceiling matters before the run has seen
# a steady moment: then the steadiest scatter is still that of moving gaze.
SETTLE_S = 0.2
RATIO = 3.0
FLOOR = 0.01
CEILING = 0.05
# Scatter is how far from their middle SCATTER_PERCENT of a stretch's frames
# stay, not the single farthest one. On a clean camera the two agree: a gaze
# that moves through a stretch spreads all of its frames. On a noisy one the
# farthest frame of a resting gaze grows with every frame looked at, and a
# per-axis noise of 0.02 raw put it over CEILING in nearly every stretch, so
# the gaze never counted as resting on any dot.
SCATTER_PERCENT = 90.0
# A dot the gaze never rested on by that rule is still captured, from the
# steadiest stretch of its wait (GazeTrace.steadiest_stretch), unless even
# that scattered by more than this: then the gaze was moving, not noisy.
UNRESTED_CEILING = 0.15
# Fewer open-eye frames than this in a stretch say nothing about it.
MIN_FRAMES = 3
POLL_S = 0.01


def open_lid(lids) -> float:
    """The lid reading from which a frame counts as open-eyed, from the
    ``lids`` of a run. The eyes are open for most of a run, so the median is
    their usual open reading."""
    lids = list(lids)
    if not lids:
        return OPEN_LID
    return max(MIN_OPEN_LID, min(OPEN_LID, OPEN_FRACTION * statistics.median(lids)))


def _scatter(frames, min_lid: float = OPEN_LID) -> float:
    """The distance from their median that SCATTER_PERCENT of the open-eye
    frames' raw gaze stay within."""
    points = [(x, y) for _, x, y, lid, _ in frames if lid >= min_lid]
    if len(points) < MIN_FRAMES:
        return math.inf
    mx = statistics.median(x for x, _ in points)
    my = statistics.median(y for _, y in points)
    distances = sorted(math.hypot(x - mx, y - my) for x, y in points)
    at = (len(distances) - 1) * SCATTER_PERCENT / 100.0
    below = int(at)
    above = min(below + 1, len(distances) - 1)
    return distances[below] + (distances[above] - distances[below]) * (at - below)


class GazeTrace:
    """The raw gaze of the eye processors during one run."""

    def __init__(self, eye_processors: list):
        self.processors = list(eye_processors)
        self._steadiest = math.inf
        self._stretch = None  # (scatter, start, end): the steadiest of the last wait
        self._open_lids = {}  # processor id -> (frames it is from, open_lid)
        for ep in self.processors:
            ep._next_smartcal_trace = []

    def frames(self, start: float, end: float = math.inf) -> list:
        """[(processor, its frames between ``start`` and ``end``)] (monotonic)."""
        out = []
        for ep in self.processors:
            trace = ep._next_smartcal_trace or []
            # The eye threads append while this reads: copy the list first.
            out.append((ep, [frame for frame in list(trace) if start <= frame[0] <= end]))
        return out

    def open_lid(self, ep) -> float:
        """The lid reading from which this eye's frames count as open-eyed
        (see open_lid), from its trace so far."""
        trace = ep._next_smartcal_trace or []
        seen, level = self._open_lids.get(id(ep), (0, OPEN_LID))
        if trace and (not seen or len(trace) - seen >= LID_REFRESH_FRAMES):
            level = open_lid(frame[3] for frame in list(trace))
            self._open_lids[id(ep)] = (len(trace), level)
        return level

    def scatter(self, start: float, end: float = math.inf) -> float:
        """The worst tracked eye's scatter between ``start`` and ``end``."""
        # An eye without enough frames says nothing, so a stalled camera
        # does not hold up the others.
        scatters = (_scatter(frames, self.open_lid(ep)) for ep, frames in self.frames(start, end))
        return max((s for s in scatters if math.isfinite(s)), default=math.inf)

    def wait_until_resting(self, timeout: float, rest_s: float | None = None, keep_going=lambda: True) -> bool:
        """Wait until the gaze has rested for ``rest_s`` (SETTLE_S when None).
        False when it did not within ``timeout`` or ``keep_going()`` turned
        false.

        Every SETTLE_S stretch teaches the noise (the steadiest one so far),
        and the whole last ``rest_s`` must stay within RATIO times it. A gaze
        that moves through that window then fails it, even before the run has
        seen a steadier moment."""
        rest_s = SETTLE_S if rest_s is None else rest_s
        started = time.monotonic()
        self._stretch = None
        while True:
            now = time.monotonic()
            if now - started >= SETTLE_S:
                self._steadiest = min(self._steadiest, self.scatter(now - SETTLE_S, now))
            if now - started >= rest_s:
                scatter = self.scatter(now - rest_s, now)
                if math.isfinite(scatter) and (self._stretch is None or scatter < self._stretch[0]):
                    self._stretch = (scatter, now - rest_s, now)
                if math.isfinite(self._steadiest) and scatter <= min(CEILING, max(FLOOR, RATIO * self._steadiest)):
                    return True
            if now - started >= timeout or not keep_going():
                return False
            time.sleep(POLL_S)

    def steadiest_stretch(self):
        """(start, end) of the steadiest ``rest_s`` of the last
        wait_until_resting: the best there is of a dot the gaze did not rest
        on by the rule, as on a camera too noisy for it. None when even that
        was a moving gaze (see UNRESTED_CEILING) or nothing was tracked."""
        if self._stretch is None or self._stretch[0] > UNRESTED_CEILING:
            return None
        return self._stretch[1:]

    def close(self) -> dict:
        """Stop tracing and hand back {eye id: frames}."""
        traces = {}
        for ep in self.processors:
            traces[getattr(ep, "eye_id", "?")] = ep._next_smartcal_trace or []
            ep._next_smartcal_trace = None
        return traces
