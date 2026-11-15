# Copied from LEAPv2_Training/NEXT/src/smooth.py: the measurements behind it
# are in that folder (filter_study.py). Keep the two files in step.
"""Value-only temporal filter for the 12 NEXT outputs. numpy only.

The network is stateless, so three things are left to whoever consumes it:

  jitter   A still eye reads with frame noise. Inside a small band around the
           current estimate the filter is a slow low-pass.
  moves    A real move leaves that band and stays out, and the filter then
           follows the input at once. "Stays out" is a short time window, so a
           one-frame spike never triggers it.
  blinks   A closed or closing eye carries no gaze, and the network's gaze
           swings down through a blink on people it has not seen. The lid
           output moves in blinks and stays put in vertical saccades (measured
           in filter_study.py), so a fast lid drop freezes gaze and brow until
           the lid is back and still.

All thresholds are in output units and seconds, so behaviour does not depend
on the pass rate. Feed it the raw model outputs with any consistent gaze-Y sign.

    f = Smoother()
    out = f(time.perf_counter(), raw12, valid_left, valid_right)
"""

import math
from collections import deque
import numpy as np

BROW_L, LID_L, SQ_L, BROW_R, LID_R, SQ_R = 0, 1, 2, 3, 4, 5
GAZE, GAZE_L, GAZE_R = slice(6, 8), slice(8, 10), slice(10, 12)


class Snap:
    """Low-pass inside the noise band, follow outside it. Works on a vector, so
    a 2-D gaze move is judged by its length, not per axis."""

    def __init__(self, tau, d0, d1, persist_s=0.02, lead=0.0, follow_s=0.08, tau_fast=0.012):
        # persist_s spans two passes when two 60 fps cameras feed 120 passes a
        # second, so one camera's bad frame, seen in two passes, is not a move.
        self.tau, self.d0, self.d1, self.persist_s, self.lead = tau, d0, d1, persist_s, lead
        self.follow_s, self.tau_fast = follow_s, tau_fast
        self.s = None
        self.v = None
        self.hist = deque(maxlen=8)
        self.t_move = -1e9

    def reset(self):
        self.s = None
        self.hist.clear()

    def __call__(self, t, x, dt, trust=1.0):
        x = np.asarray(x, np.float64)
        if self.s is None:
            self.s = x.copy()
            self.v = np.zeros_like(x)
            self.hist.append((t, x))
            return self.s
        if trust <= 0:
            # Frozen: keep the state, forget pending samples and the drift rate.
            self.hist.clear()
            self.v[:] = 0
            return self.s
        # Smallest departure from the estimate over the persistence window: a
        # move counts only if every recent sample left the band the same way.
        # The window always reaches back to the previous sample, so one frame
        # is never enough, whatever the pass rate.
        e = x - self.s
        m = float(np.linalg.norm(e))
        seen = False
        last = self.hist[-1][0] if self.hist else None
        for tp, xp in self.hist:
            if t - tp <= self.persist_s + 1e-9 or (tp == last and t - tp <= 0.1):
                ep = xp - self.s
                seen = True
                m = min(m, float(np.linalg.norm(ep))) if float(ep @ e) > 0 else 0.0
        if not seen:
            m = min(m, self.d0)  # nothing to confirm against yet
        self.hist.append((t, x))
        u = min(max((m - self.d0) / (self.d1 - self.d0), 0.0), 1.0)
        u = u * u * (3 - 2 * u)
        a_slow = 1 - math.exp(-dt / self.tau)
        a = a_slow + (1 - a_slow) * u
        if u >= 1:
            self.t_move = t
        if t - self.t_move < self.follow_s:
            # A move lands inside the noise band; keep following until it has.
            a = max(a, 1 - math.exp(-dt / self.tau_fast))
        a *= trust
        prev = self.s
        # Slow drift (pursuit) is led by its own rate so the low-pass does not trail it.
        self.s = self.s + self.lead * self.v * dt * (1 - u) + a * (x - self.s - self.lead * self.v * dt * (1 - u))
        av = 1 - math.exp(-dt / 0.15)
        self.v = (1 - u) * (self.v + av * ((self.s - prev) / max(dt, 1e-4) - self.v))
        return self.s


class BlinkGate:
    """1 while an eye's gaze can be trusted, 0 through a blink or a closed eye."""

    def __init__(self, drop_rate=3.5, closed=0.18, back=0.7, still_rate=4.0, release_s=0.05, settle_s=0.2):
        # back: share of the open level the lid must regain. People often reopen
        # a little less wide than before, and gaze reads fine at that point.
        self.drop_rate, self.closed, self.back = drop_rate, closed, back
        self.still_rate, self.release_s, self.settle_s = still_rate, release_s, settle_s
        self.lid = self.ref = None
        self.held = False
        self.t_still = None
        self.t_held = None

    def __call__(self, t, lid, dt):
        if self.lid is None:
            self.lid = self.ref = lid
            return 1.0
        rate = (lid - self.lid) / max(dt, 1e-4)
        self.lid = lid
        if not self.held:
            if rate < -self.drop_rate or lid < self.closed:
                self.held, self.t_still, self.t_held = True, None, t
            else:
                self.ref += (1 - math.exp(-dt / 0.5)) * (lid - self.ref)  # the open level drifts slowly
                return 1.0
        # Held: wait for a lid that is open and no longer moving.
        if abs(rate) > self.still_rate or lid < self.closed:
            self.t_still = None
            return 0.0
        if self.t_still is None:
            self.t_still = t
        back = lid >= max(self.closed + 0.15, self.back * self.ref)
        if (back and t - self.t_still >= self.release_s) or t - self.t_still >= self.settle_s:
            # Second case: the lid settled somewhere new (a squint), not a blink.
            self.held = False
            self.ref = lid
            return 1.0
        return 0.0


GAZE_BAND = (0.12, 0.02, 0.06)  # slow time constant (s), noise band, follow band
GAZE_LEAD = 0.8


class Smoother:
    def __init__(
        self,
        gaze=GAZE_BAND,
        lid=(0.035, 0.03, 0.10),
        brow=(0.14, 0.04, 0.14),
        squeeze=(0.07, 0.04, 0.14),
        lead=GAZE_LEAD,
        blink_hold=True,
    ):
        self.f = {}
        for i in (LID_L, LID_R):
            self.f[i] = Snap(*lid)
        for i in (BROW_L, BROW_R):
            self.f[i] = Snap(*brow)
        for i in (SQ_L, SQ_R):
            self.f[i] = Snap(*squeeze)
        self.g = {k: Snap(*gaze, lead=lead) for k in ("both", "l", "r")}
        self.gate = [BlinkGate(), BlinkGate()]
        self.blink_hold = blink_hold
        self.t = None
        self.out = None
        self.trust = (1.0, 1.0)
        # One-eye passes read gaze from a weaker head that sits a little off
        # the two-eye one. off: its usual distance, learned while both eyes
        # are in. bump: what is left at the moment the eye set changes, faded
        # out, so losing or regaining a camera is not taken for an eye move.
        self.off = {"l": np.zeros(2), "r": np.zeros(2)}
        self.bump = np.zeros(2)
        self.src = None
        self.t_src = 0.0
        self.t_shut = [None, None]
        self.wink_s = 0.25
        self.dt = 1 / 60

    def __call__(self, t, raw, valid_l=True, valid_r=True):
        raw = np.asarray(raw, np.float64)
        if self.t is None:
            self.t = t - 1 / 60
        dt = min(max(t - self.t, 1e-4), 0.25)
        self.t = t
        self.dt = dt
        out = np.zeros(12) if self.out is None else self.out.copy()
        valid = (valid_l, valid_r)
        tr = [1.0, 1.0]
        for e, lid_i in enumerate((LID_L, LID_R)):
            if valid[e] and self.blink_hold:
                tr[e] = self.gate[e](t, raw[lid_i], dt)
        self.trust = tuple(tr)
        for e, (b, ld, s) in enumerate(((BROW_L, LID_L, SQ_L), (BROW_R, LID_R, SQ_R))):
            if not valid[e]:
                continue  # an absent eye keeps its last expression
            out[ld] = self.f[ld](t, raw[ld : ld + 1], dt)[0]
            out[s] = self.f[s](t, raw[s : s + 1], dt)[0]
            out[b] = self.f[b](t, raw[b : b + 1], dt, tr[e])[0]  # mid-blink frames read as brows-down
        # Fused gaze reads both eyes while both are open, and holds through a
        # blink. An eye that stays shut while the other is open is a wink: after
        # wink_s it counts as absent and gaze follows the open eye, so a wink or
        # a rested eye never freezes gaze.
        open_ = [valid[e] and tr[e] > 0 for e in range(2)]
        for e in range(2):
            if open_[e] or not valid[e]:
                self.t_shut[e] = None
            elif self.t_shut[e] is None:
                self.t_shut[e] = t
        gone = [not valid[e] or (self.t_shut[e] is not None and t - self.t_shut[e] > self.wink_s) for e in range(2)]
        src = (
            "both" if open_[0] and open_[1] else "l" if open_[0] and gone[1] else "r" if open_[1] and gone[0] else None
        )
        if src is None:
            if valid_l or valid_r:
                out[GAZE] = self.g["both"](t, raw[GAZE], dt, 0.0)
        else:
            if src == "both":
                x = raw[GAZE]
                k = 1 - math.exp(-dt / 1.0)
                self.off["l"] += k * (raw[GAZE] - raw[GAZE_L] - self.off["l"])
                self.off["r"] += k * (raw[GAZE] - raw[GAZE_R] - self.off["r"])
            else:
                x = raw[GAZE_L if src == "l" else GAZE_R] + self.off[src]
            # A short gap is bridged by the remaining eye's changes alone; a
            # long one slides onto that eye's own reading. Two eyes win back fast.
            if src == "both":
                self.bump = self.bump * math.exp(-dt / 0.08)
            elif t - self.t_src > 0.12:
                self.bump = self.bump * math.exp(-dt / 0.5)
            if self.src is not None and src != self.src and self.g["both"].s is not None:
                self.bump = self.g["both"].s - x
                self.t_src = t
            self.src = src
            out[GAZE] = self.g["both"](t, x + self.bump, dt)
        if valid_l:
            out[GAZE_L] = self.g["l"](t, raw[GAZE_L], dt, tr[0])
        if valid_r:
            out[GAZE_R] = self.g["r"](t, raw[GAZE_R], dt, tr[1])
        self.out = out
        return out.astype(np.float32)
