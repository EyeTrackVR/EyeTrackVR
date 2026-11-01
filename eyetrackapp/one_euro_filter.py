# https://github.com/jaantollander/OneEuroFilter
# LICENSE: MIT

import logging

import numpy as np
from time import perf_counter

logger = logging.getLogger(__name__)


# Minimum dt the filter trusts: smaller deltas (system clock hiccups, two
# calls inside the same tick) would blow up the derivative term. We still
# advance t_prev so the *next* call sees a real dt instead of stalling.
_MIN_DT_S = 1e-9
# Fixed-step mode replays at most this many steps after a stall.
_MAX_CATCHUP_STEPS = 32


def smoothing_factor(t_e, cutoff):
    r = 2 * np.pi * cutoff * t_e
    return r / (r + 1)


def exponential_smoothing(a, x, x_prev):
    return a * x + (1 - a) * x_prev


class OneEuroFilter:
    def __init__(self, x0, dx0=0.0, min_cutoff=1.0, beta=0.0, d_cutoff=1.0, step_s=None):
        """Initialize the one euro filter.

        step_s=None updates once per call with the real dt, so the response
        depends on the call rate: the derivative is taken against the filtered
        value, and more calls per second build the speed term up faster. A
        step_s advances the state in fixed steps of that length instead, so
        the response in time is the same at any call rate (see _fixed_step)."""
        # The parameters.
        self.data_shape = x0.shape
        self.min_cutoff = np.full(x0.shape, min_cutoff)
        self.beta = np.full(x0.shape, beta)
        self.d_cutoff = np.full(x0.shape, d_cutoff)
        # Previous values.
        self.x_prev = x0
        self.dx_prev = np.full(x0.shape, dx0)
        # perf_counter is monotonic; the previous time() implementation could
        # produce negative dt across NTP corrections and stall the filter.
        self.t_prev = perf_counter()
        self.step_s = step_s
        # Fixed-step mode: elapsed time not yet committed as a whole step.
        self._pending_s = 0.0

    def _step(self, x, t_e):
        """One filter update over t_e seconds. Returns (x_hat, dx_hat)."""
        t_e_arr = np.full(x.shape, t_e)

        # The filtered derivative of the signal.
        a_d = smoothing_factor(t_e_arr, self.d_cutoff)
        dx = (x - self.x_prev) / t_e_arr
        dx_hat = exponential_smoothing(a_d, dx, self.dx_prev)

        # The filtered signal.
        cutoff = self.min_cutoff + self.beta * np.abs(dx_hat)
        a = smoothing_factor(t_e_arr, cutoff)
        return exponential_smoothing(a, x, self.x_prev), dx_hat

    def _fixed_step(self, x, t_e):
        """Commit every whole step_s elapsed (holding the newest input), then
        return the state advanced by the leftover fraction without storing it.
        The committed state only ever sees step_s updates, so it is independent
        of the call rate, and the output still reflects this call's input."""
        self._pending_s += t_e
        steps = int(self._pending_s / self.step_s)
        if steps > _MAX_CATCHUP_STEPS:
            # Long stall (camera dropout, paused thread): don't replay it all.
            steps = _MAX_CATCHUP_STEPS
            self._pending_s = steps * self.step_s
        for _ in range(steps):
            self.x_prev, self.dx_prev = self._step(x, self.step_s)
        self._pending_s -= steps * self.step_s
        if self._pending_s > _MIN_DT_S:
            return self._step(x, self._pending_s)[0]
        return self.x_prev

    def __call__(self, x):
        """Compute the filtered signal."""
        assert x.shape == self.data_shape
        try:
            t = perf_counter()
            t_e = t - self.t_prev
            # Always advance t_prev so a tiny dt doesn't permanently stall the
            # filter (used to skip the state update entirely on dt == 0).
            self.t_prev = t
            if self.step_s is not None:
                return self._fixed_step(x, max(t_e, 0.0))
            if t_e > _MIN_DT_S:
                x_hat, dx_hat = self._step(x, t_e)
                self.x_prev = x_hat
                self.dx_prev = dx_hat
                return x_hat
            else:
                # Sub-nanosecond dt: pass-through but keep x_prev fresh so the
                # next real-dt call has a sane reference value.
                self.x_prev = x
                return x
        except (ValueError, FloatingPointError, ZeroDivisionError) as e:
            logger.error("One Euro Filter error: %s", e)
            return self.x_prev
