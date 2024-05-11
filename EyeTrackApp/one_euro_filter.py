# https://github.com/jaantollander/OneEuroFilter
# LICENSE: MIT

import numpy as np
from time import time

def smoothing_factor(t_e, cutoff):
    r = 2 * np.pi * cutoff * t_e
    return r / (r + 1)


def exponential_smoothing(a, x, x_prev):
    return a * x + (1 - a) * x_prev


class OneEuroFilter:
    def __init__(self, x0, dx0=0.0, min_cutoff=1.0, beta=0.0,
                 d_cutoff=1.0):
        """Initialize the one euro filter."""
        # The parameters.
        self.data_shape = x0.shape
        self.min_cutoff = np.full(x0.shape, min_cutoff)
        self.beta = np.full(x0.shape, beta)
        self.d_cutoff = np.full(x0.shape, d_cutoff)
        # Previous values.
        self.x_prev = x0
        self.dx_prev = np.full(x0.shape, dx0)
        self.t_prev = time()

    def __call__(self, x):
        """Compute the filtered signal."""
        assert x.shape == self.data_shape
        try:
            t = time()
            t_e = t - self.t_prev
            if t_e != 0.0: #occasionally when switching to HSF this becomes zero causing divide by zero errors crashing the filter.
                t_e = np.full(x.shape, t_e)

                # The filtered derivative of the signal.
                a_d = smoothing_factor(t_e, self.d_cutoff)
                dx = (x - self.x_prev) / t_e
                dx_hat = exponential_smoothing(a_d, dx, self.dx_prev)

                # The filtered signal.
                cutoff = self.min_cutoff + self.beta * np.abs(dx_hat)
                a = smoothing_factor(t_e, cutoff)
                x_hat = exponential_smoothing(a, x, self.x_prev)

                # Memorize the previous values.
                self.x_prev = x_hat
                self.dx_prev = dx_hat
                self.t_prev = t

                return x_hat
        except:
            print("\033[91m[ERROR] One Euro Filter Error. Is your system clock running properly?\033[0m")