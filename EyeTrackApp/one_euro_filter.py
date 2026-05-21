# https://github.com/jaantollander/OneEuroFilter
# LICENSE: MIT

import numpy as np
from time import perf_counter


# Minimum dt the filter trusts: smaller deltas (system clock hiccups, two
# calls inside the same tick) would blow up the derivative term. We still
# advance t_prev so the *next* call sees a real dt instead of stalling.
_MIN_DT_S = 1e-9


def smoothing_factor(t_e, cutoff):
    r = 2 * np.pi * cutoff * t_e
    return r / (r + 1)


def exponential_smoothing(a, x, x_prev):
    return a * x + (1 - a) * x_prev


class OneEuroFilter:
    def __init__(self, x0, dx0=0.0, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        """Initialize the one euro filter."""
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

    def __call__(self, x):
        """Compute the filtered signal."""
        assert x.shape == self.data_shape
        try:
            t = perf_counter()
            t_e = t - self.t_prev
            # Always advance t_prev so a tiny dt doesn't permanently stall the
            # filter (used to skip the state update entirely on dt == 0).
            self.t_prev = t
            if t_e > _MIN_DT_S:
                t_e_arr = np.full(x.shape, t_e)

                # The filtered derivative of the signal.
                a_d = smoothing_factor(t_e_arr, self.d_cutoff)
                dx = (x - self.x_prev) / t_e_arr
                dx_hat = exponential_smoothing(a_d, dx, self.dx_prev)

                # The filtered signal.
                cutoff = self.min_cutoff + self.beta * np.abs(dx_hat)
                a = smoothing_factor(t_e_arr, cutoff)
                x_hat = exponential_smoothing(a, x, self.x_prev)

                self.x_prev = x_hat
                self.dx_prev = dx_hat
                return x_hat
            else:
                # Sub-nanosecond dt: pass-through but keep x_prev fresh so the
                # next real-dt call has a sane reference value.
                self.x_prev = x
                return x
        except (ValueError, FloatingPointError, ZeroDivisionError) as e:
            print(
                "\033[91m[ERROR] One Euro Filter Error: {}\033[0m".format(e)
            )
            return self.x_prev
