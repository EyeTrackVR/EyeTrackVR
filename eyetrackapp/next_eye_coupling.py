"""
NEXT left/right expression coupling.

A neutral face has nearly equal left and right eyelids and eyebrows, but the
model reads each eye separately, so one lid can wander on its own while the
user looks around (worst on people the model never trained on). The two
eyes are pulled to their mean while they disagree a little, and released to
their own values once they disagree clearly, so winks and one-sided brow
raises still come through. Each channel has a (sync_below, separate_above)
range on the L/R gap, set by one GUI "sync" slider (see sync_range):

    gap <= sync_below                    -> both read the mean
    sync_below < gap < separate_above    -> smoothstep blend (no snap)
    gap >= separate_above                -> each eye's own value

The weight releases instantly when the gap opens (a wink must not be delayed)
and re-engages over ENGAGE_TAU_S, which stops it flickering at the boundary.

Runs only on the shared Hybrid/stereo path, where one pass reads both eyes:
EyeProcessor._next_apply passes each pass through here in output space, after
Smart Calib's per-eye neutral anchors and the Manual Eyelid Tuning remap, and
before the closed-eye snap. The per-eye NEXT fallback and the classic trackers
have no paired reading to compare and are left alone.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import math
import threading

from eye import EyeId

# GUI sync sliders (gui_NEXT_lid_sync / gui_NEXT_brow_sync), 0..100:
# 0 = off, DEFAULT_SYNC = the chosen ranges (lid 0.12 / 0.30, brow
# 0.10 / 0.25), 100 = twice as wide. Gaps are in the values sent downstream
# (eyelid 0 closed .. 0.75 normal open; eyebrow 0..1 with 0.5 neutral).
SYNC_MAX = 100
DEFAULT_SYNC = 50
# sync_below at SYNC_MAX. Even there a full wink (gap ~0.75) and a full
# one-sided brow raise (gap 0.5) still come through.
LID_MAX_SYNC_BELOW = 0.24
BROW_MAX_SYNC_BELOW = 0.20
# separate_above / sync_below: the width of the smooth blend.
SEPARATE_RATIO = 2.5
# Time constant of the weight climbing back after the eyes reconverge.
ENGAGE_TAU_S = 0.25
# A pass with a missing (black-frame) eye has nothing to compare: the last
# coupling shift fades over this time instead of jumping away.
MISSING_TAU_S = 0.1
# Passes kept, so an eye served an older pass gets the values its peer got.
_CACHE_PASSES = 4


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 0.0 if x < edge0 else 1.0
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def sync_range(sync: float, max_sync_below: float) -> tuple[float, float]:
    """(sync_below, separate_above) for one 0..SYNC_MAX slider value; 0 = off."""
    strength = min(1.0, max(0.0, float(sync) / SYNC_MAX))
    sync_below = strength * max_sync_below
    return sync_below, sync_below * SEPARATE_RATIO


def lid_sync_range(sync: float) -> tuple[float, float]:
    return sync_range(sync, LID_MAX_SYNC_BELOW)


def brow_sync_range(sync: float) -> tuple[float, float]:
    return sync_range(sync, BROW_MAX_SYNC_BELOW)


def coupling_weight(gap: float, sync_below: float, separate_above: float) -> float:
    """Target weight for one left/right gap: 1 = both read the mean, 0 = each
    eye passes through. separate_above <= 0 disables the channel; equal ends
    switch hard at that gap."""
    if separate_above <= 0.0:
        return 0.0
    return 1.0 - smoothstep(sync_below, separate_above, abs(gap))


class _Channel:
    """Weight and shift state of one coupled channel (eyelid or eyebrow)."""

    def __init__(self):
        self.weight = 0.0
        self.half_gap = 0.0  # (right - left) / 2 of the last two-eye pass

    def step(self, left: float, right: float, both: bool, gap_range: tuple, dt: float):
        if both:
            target = coupling_weight(right - left, *gap_range)
            if target < self.weight:
                self.weight = target
            else:
                self.weight += (target - self.weight) * (1.0 - math.exp(-dt / ENGAGE_TAU_S))
            self.half_gap = 0.5 * (right - left)
        else:
            self.weight *= math.exp(-dt / MISSING_TAU_S)
        return self.apply(left, right)

    def apply(self, left: float, right: float):
        shift = self.weight * self.half_gap
        return left + shift, right - shift


class NextExpressionCoupler:
    """Couples one shared model's two eyes. Both eye threads call couple()
    for each pass they are served; the first one computes the pair and steps
    the weights, the second reuses it, so both eyes always get one consistent
    answer however the threads interleave.

    Each eye publishes its own lid/brow transform (Smart Calib anchors and lid
    remap: anything with openness(eyelid, squeeze) -> (calibrated, output) and
    brow(eyebrow)), so either thread can map both eyes of a pass."""

    def __init__(self):
        self._lock = threading.Lock()
        self._transforms = {EyeId.LEFT: None, EyeId.RIGHT: None}
        self._lid = _Channel()
        self._brow = _Channel()
        self._last_pass = None
        self._last_ts = None
        self._cache = {}

    def publish(self, eye_id, transform) -> None:
        with self._lock:
            self._transforms[eye_id] = transform

    def couple(self, eye_id, shared, lid_range: tuple, brow_range: tuple):
        """This eye's coupled (eyelid openness, eyebrow) for one shared pass, or
        None until both eyes have published a transform. Each range is
        (sync_below, separate_above) on the L/R gap."""
        with self._lock:
            pair = self._cache.get(shared.pass_id)
            if pair is None:
                pair = self._compute(shared, lid_range, brow_range)
                if pair is None:
                    return None
            return pair[eye_id]

    def peer_openness(self, eye_id, shared):
        """The other eye's lid output for one shared pass, before lid sync, or
        None until it has published a transform."""
        peer = EyeId.RIGHT if eye_id == EyeId.LEFT else EyeId.LEFT
        with self._lock:
            transform = self._transforms[peer]
        if transform is None or shared is None:
            return None
        base = 0 if peer == EyeId.LEFT else 3
        return transform.openness(float(shared.result[base + 1]), float(shared.result[base + 2]))[1]

    def _compute(self, shared, lid_range, brow_range):
        left_t, right_t = self._transforms[EyeId.LEFT], self._transforms[EyeId.RIGHT]
        if left_t is None or right_t is None:
            return None
        ebL, elidL, sqL, ebR, elidR, sqR = (float(v) for v in shared.result[:6])
        lid_l, lid_r = left_t.openness(elidL, sqL)[1], right_t.openness(elidR, sqR)[1]
        brow_l, brow_r = left_t.brow(ebL), right_t.brow(ebR)

        if self._last_pass is not None and shared.pass_id < self._last_pass:
            # Older than a pass already stepped and no longer cached: the
            # current weights still apply, but time must not run backwards.
            lid_l, lid_r = self._lid.apply(lid_l, lid_r)
            brow_l, brow_r = self._brow.apply(brow_l, brow_r)
        else:
            dt = 0.0 if self._last_ts is None else min(1.0, max(0.0, shared.ts - self._last_ts))
            self._last_pass, self._last_ts = shared.pass_id, shared.ts
            lid_l, lid_r = self._lid.step(lid_l, lid_r, shared.both_eyes, lid_range, dt)
            brow_l, brow_r = self._brow.step(brow_l, brow_r, shared.both_eyes, brow_range, dt)

        pair = {EyeId.LEFT: (lid_l, brow_l), EyeId.RIGHT: (lid_r, brow_r)}
        self._cache[shared.pass_id] = pair
        while len(self._cache) > _CACHE_PASSES:
            del self._cache[min(self._cache)]
        return pair
