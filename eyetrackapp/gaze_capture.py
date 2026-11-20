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
import time

# Frames with the lids this closed are blinks, not gaze.
OPEN_LID = 0.3
# The gaze rests when, over the last SETTLE_S, it stays within RATIO times the
# steadiest scatter seen in this run, but never stricter than FLOOR (raw gaze
# units, about half a degree) and never looser than CEILING (about two
# degrees, far below a saccade). The ceiling matters before the run has seen
# a steady moment: then the steadiest scatter is still that of moving gaze.
SETTLE_S = 0.2
RATIO = 3.0
FLOOR = 0.01
CEILING = 0.05
# Fewer open-eye frames than this in a stretch say nothing about it.
MIN_FRAMES = 3
POLL_S = 0.01


def _scatter(frames) -> float:
    """Largest distance of the open-eye frames' raw gaze from their mean."""
    points = [(x, y) for _, x, y, lid, _ in frames if lid >= OPEN_LID]
    if len(points) < MIN_FRAMES:
        return math.inf
    mx = sum(x for x, _ in points) / len(points)
    my = sum(y for _, y in points) / len(points)
    return max(math.hypot(x - mx, y - my) for x, y in points)


class GazeTrace:
    """The raw gaze of the eye processors during one run."""

    def __init__(self, eye_processors: list):
        self.processors = list(eye_processors)
        self._steadiest = math.inf
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

    def scatter(self, start: float, end: float = math.inf) -> float:
        """The worst tracked eye's scatter between ``start`` and ``end``."""
        # An eye without enough frames says nothing, so a stalled camera
        # does not hold up the others.
        scatters = [s for s in (_scatter(frames) for _, frames in self.frames(start, end)) if math.isfinite(s)]
        return max(scatters, default=math.inf)

    def wait_until_resting(self, timeout: float, rest_s: float | None = None, keep_going=lambda: True) -> bool:
        """Wait until the gaze has rested for ``rest_s`` (SETTLE_S when None).
        False when it did not within ``timeout`` or ``keep_going()`` turned
        false.

        Every SETTLE_S stretch teaches the noise (the steadiest one so far),
        and the whole last ``rest_s`` must stay within RATIO times it. Any
        movement inside that window then fails it, even before the run has
        seen a steadier moment."""
        rest_s = SETTLE_S if rest_s is None else rest_s
        started = time.monotonic()
        while True:
            now = time.monotonic()
            if now - started >= SETTLE_S:
                self._steadiest = min(self._steadiest, self.scatter(now - SETTLE_S, now))
            if now - started >= rest_s and math.isfinite(self._steadiest):
                if self.scatter(now - rest_s, now) <= min(CEILING, max(FLOOR, RATIO * self._steadiest)):
                    return True
            if now - started >= timeout or not keep_going():
                return False
            time.sleep(POLL_S)

    def close(self) -> dict:
        """Stop tracing and hand back {eye id: frames}."""
        traces = {}
        for ep in self.processors:
            traces[getattr(ep, "eye_id", "?")] = ep._next_smartcal_trace or []
            ep._next_smartcal_trace = None
        return traces
