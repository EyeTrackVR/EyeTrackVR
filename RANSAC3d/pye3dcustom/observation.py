"""
(*)~---------------------------------------------------------------------------
Pupil - eye tracking platform
Copyright (C) 2012-2019 Pupil Labs

Distributed under the terms of the GNU
Lesser General Public License (LGPL v3.0).
See COPYING and COPYING.LESSER for license details.
---------------------------------------------------------------------------~(*)
"""
from abc import abstractmethod, abstractproperty
from collections import deque
from math import floor
from typing import Sequence, Optional

import numpy as np
from sortedcontainers import SortedList

from .camera import CameraModel
from .constants import _EYE_RADIUS_DEFAULT
from .geometry.primitives import Ellipse, Line
from .geometry.projections import project_line_into_image_plane, unproject_ellipse


class Observation(object):
    def __init__(
        self, ellipse: Ellipse, confidence: float, timestamp: float, focal_length: float
    ):
        self.ellipse = ellipse
        self.confidence_2d = confidence
        self.confidence = 0.0
        self.timestamp = timestamp

        self.circle_3d_pair = None
        self.gaze_3d_pair = None
        self.gaze_2d = None
        self.aux_2d = None
        self.aux_3d = None
        self.invalid = True

        circle_3d_pair = unproject_ellipse(ellipse, focal_length)
        if not circle_3d_pair:
            # unprojecting ellipse failed, invalid observation!
            return

        self.invalid = False
        self.confidence = self.confidence_2d
        self.circle_3d_pair = circle_3d_pair

        self.gaze_3d_pair = [
            Line(
                circle_3d_pair[i].center,
                circle_3d_pair[i].center + circle_3d_pair[i].normal,
            )
            for i in [0, 1]
        ]
        self.gaze_2d = project_line_into_image_plane(self.gaze_3d_pair[0], focal_length)
        self.gaze_2d_line = np.array([*self.gaze_2d.origin, *self.gaze_2d.direction])

        self.aux_2d = np.empty((2, 3))
        v = np.reshape(self.gaze_2d.direction, (2, 1))
        self.aux_2d[:, :2] = np.eye(2) - v @ v.T
        self.aux_2d[:, 2] = (np.eye(2) - v @ v.T) @ self.gaze_2d.origin

        self.aux_3d = np.empty((2, 3, 4))
        for i in range(2):
            Dierkes_line = self.get_Dierkes_line(i)
            v = np.reshape(Dierkes_line.direction, (3, 1))
            self.aux_3d[i, :3, :3] = np.eye(3) - v @ v.T
            self.aux_3d[i, :3, 3] = (np.eye(3) - v @ v.T) @ Dierkes_line.origin

    def get_Dierkes_line(self, i):
        origin = (
            self.circle_3d_pair[i].center
            - _EYE_RADIUS_DEFAULT * self.circle_3d_pair[i].normal
        )
        direction = self.circle_3d_pair[i].center
        return Line(origin, direction)


class ObservationStorage:
    @abstractmethod
    def add(self, observation: Observation):
        pass

    @abstractproperty
    def observations(self) -> Sequence[Observation]:
        pass

    @abstractmethod
    def clear(self):
        pass

    @abstractmethod
    def count(self) -> int:
        pass


class BasicStorage(ObservationStorage):
    def __init__(self):
        self._storage = []

    def add(self, observation: Observation):
        if observation.invalid:
            return
        self._storage.append(observation)

    @property
    def observations(self) -> Sequence[Observation]:
        return self._storage

    def clear(self):
        self._storage.clear()

    def count(self) -> int:
        return len(self._storage)


class BufferedObservationStorage(ObservationStorage):
    def __init__(self, confidence_threshold: float, buffer_length: int):
        self.confidence_threshold = confidence_threshold
        self._storage = deque(maxlen=buffer_length)

    def add(self, observation: Observation):
        if observation.invalid:
            return
        if observation.confidence < self.confidence_threshold:
            return

        self._storage.append(observation)

    @property
    def observations(self) -> Sequence[Observation]:
        return list(self._storage)

    def clear(self):
        self._storage.clear()

    def count(self) -> int:
        return len(self._storage)


class BinBufferedObservationStorage(ObservationStorage):
    def __init__(
        self,
        camera: CameraModel,
        confidence_threshold: float,
        n_bins_horizontal: int,
        bin_buffer_length: int,
        forget_min_observations: Optional[int] = None,
        forget_min_time: Optional[float] = None,
    ):
        self.camera = camera
        self.confidence_threshold = confidence_threshold
        self.bin_buffer_length = bin_buffer_length
        self.forget_min_observations = forget_min_observations
        self.forget_min_time = forget_min_time
        self.pixels_per_bin = self.camera.resolution[0] / n_bins_horizontal
        self.w = n_bins_horizontal
        self.h = int(round(self.camera.resolution[1] / self.pixels_per_bin))

        self._by_time = SortedList(key=lambda obs: obs.timestamp)
        self._by_bin = dict()

    def add(self, observation: Observation):
        if observation.invalid:
            return
        if observation.confidence < self.confidence_threshold:
            return

        idx = self._get_bin(observation)
        if idx < 0 or idx >= self.w * self.h:
            print(f"INDEX OUT OF BOUNDS: {idx}")
            return

        if idx not in self._by_bin:
            self._by_bin[idx] = SortedList(key=lambda obs: obs.timestamp)

        # add to both lookup structures
        _bin: SortedList = self._by_bin[idx]
        _bin.add(observation)
        self._by_time.add(observation)

        # manage within-bin forgetting
        while len(_bin) > self.bin_buffer_length:
            old = _bin.pop(0)
            self._by_time.remove(old)

        # manage across-bin forgetting
        if self.forget_min_observations is None or self.forget_min_time is None:
            return

        while self.count() > self.forget_min_observations:
            oldest_age = observation.timestamp - self._by_time[0].timestamp
            if oldest_age < self.forget_min_time:
                break

            # forget oldest entry
            old = self._by_time.pop(0)
            idx = self._get_bin(old)
            _bin = self._by_bin[idx]
            _bin.remove(old)
            # make sure to remove bin if empty for bin-counting to work
            if len(_bin) == 0:
                self._by_bin.pop(idx)

    @property
    def observations(self) -> Sequence[Observation]:
        return list(self._by_time)

    def clear(self):
        self._by_time.clear()
        self._by_bin.clear()

    def count(self) -> int:
        return len(self._by_time)

    def get_bin_counts(self) -> np.ndarray:
        dense_1d = np.zeros((self.w * self.h,))
        for idx, _bin in self._by_bin.items():
            dense_1d[idx] = len(_bin)
        return np.reshape(dense_1d, (self.w, self.h))

    def _get_bin(self, observation: Observation) -> int:
        x, y = (
            floor((ellipse_center + resolution / 2) / self.pixels_per_bin)
            for ellipse_center, resolution in zip(
                observation.ellipse.center, self.camera.resolution
            )
        )
        # convert to 1D bin index
        return x + y * self.h
