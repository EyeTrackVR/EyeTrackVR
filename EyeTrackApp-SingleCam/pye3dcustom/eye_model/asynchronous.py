"""
(*)~---------------------------------------------------------------------------
Pupil - eye tracking platform
Copyright (C) 2012-2019 Pupil Labs

Distributed under the terms of the GNU
Lesser General Public License (LGPL v3.0).
See COPYING and COPYING.LESSER for license details.
---------------------------------------------------------------------------~(*)
"""

import ctypes
import logging
import typing as T

import numpy as np

from ..constants import DEFAULT_SPHERE_CENTER
from .abstract import (
    TwoSphereModelAbstract,
    CameraModel,
    Circle,
    Observation,
    ObservationStorage,
    SphereCenterEstimates,
)
from .background_helper import BackgroundProcess, mp
from .base import TwoSphereModel

logger = logging.getLogger(__name__)


class TwoSphereModelAsync(TwoSphereModelAbstract):
    def __init__(
        self,
        camera: CameraModel,
        storage_cls: T.Type[ObservationStorage] = None,
        storage_kwargs: T.Dict = None,
    ):
        synced_sphere_center = mp.Array(ctypes.c_double, 3)
        synced_corrected_sphere_center = mp.Array(ctypes.c_double, 3)
        synced_projected_sphere_center = mp.Array(ctypes.c_double, 2)
        synced_observation_count = mp.Value(ctypes.c_long)
        synced_rms_residual = mp.Value(ctypes.c_double)
        is_estimation_ongoing_flag = mp.Event()

        self._frontend = _TwoSphereModelSyncedFrontend(
            synced_sphere_center,
            synced_corrected_sphere_center,
            synced_projected_sphere_center,
            synced_observation_count,
            synced_rms_residual,
            is_estimation_ongoing_flag,
            camera=camera,
        )
        self._backend_process = BackgroundProcess(
            function=self._process_relayed_commands,
            setup=self._setup_backend,
            setup_args=(
                synced_sphere_center,
                synced_corrected_sphere_center,
                synced_projected_sphere_center,
                synced_observation_count,
                synced_rms_residual,
                is_estimation_ongoing_flag,
            ),
            setup_kwargs=dict(
                camera=camera,
                storage_cls=storage_cls,
                storage_kwargs=storage_kwargs,
            ),
            cleanup=self._cleanup_backend,
            log_handlers=logging.getLogger().handlers,
        )

    @property
    def sphere_center(self) -> np.ndarray:
        return self._frontend.sphere_center

    @property
    def corrected_sphere_center(self) -> np.ndarray:
        return self._frontend.corrected_sphere_center

    @property
    def projected_sphere_center(self) -> np.ndarray:
        return self._frontend.projected_sphere_center

    @property
    def rms_residual(self) -> float:
        return self._frontend.rms_residual

    def relay_command(self, function_name: str, *args, **kwargs):
        self._backend_process.send(function_name, *args, **kwargs)

    @staticmethod
    def _process_relayed_commands(
        backend: "_TwoSphereModelSyncedBackend", function_name: str, *args, **kwargs
    ):
        function = getattr(backend, function_name)
        return function(*args, **kwargs)

    @staticmethod
    def _setup_backend(*args, **kwargs) -> "_TwoSphereModelSyncedBackend":
        logger = logging.getLogger(__name__)
        logger.debug(f"Setting up backend: {args}, {kwargs}")
        return _TwoSphereModelSyncedBackend(*args, **kwargs)

    @staticmethod
    def _cleanup_backend(backend: "_TwoSphereModelSyncedBackend"):
        backend.cleanup()
        logger = logging.getLogger(__name__)
        logger.debug(f"Backend cleaned")

    def add_observation(self, observation: Observation):
        self.relay_command("add_observation", observation)

    @property
    def n_observations(self) -> int:
        return self._frontend.n_observations

    def set_sphere_center(self, new_sphere_center: np.ndarray):
        raise NotImplementedError

    def estimate_sphere_center(
        self,
        from_2d: T.Optional[np.ndarray] = None,
        prior_3d: T.Optional[np.ndarray] = None,
        prior_strength: float = 0.0,
        calculate_rms_residual=False,
    ) -> SphereCenterEstimates:
        if not self._frontend._is_estimation_ongoing_flag.is_set():
            self.relay_command(
                "estimate_sphere_center",
                from_2d,
                prior_3d,
                prior_strength,
                calculate_rms_residual,
            )
            self._frontend._is_estimation_ongoing_flag.set()
        projected_sphere_center = self._frontend.projected_sphere_center
        sphere_center = self._frontend.sphere_center
        rms_residual = self._frontend.rms_residual
        return SphereCenterEstimates(
            projected_sphere_center, sphere_center, rms_residual
        )

    def estimate_sphere_center_2d(self) -> np.ndarray:
        raise NotImplementedError

    def estimate_sphere_center_3d(
        self,
        sphere_center_2d: np.ndarray,
        prior_3d: T.Optional[np.ndarray] = None,
        prior_strength: float = 0.0,
        calculate_rms_residual: bool = False,
    ) -> T.Tuple[np.array, T.Optional[float]]:
        raise NotImplementedError

    # GAZE PREDICTION
    def _extract_unproject_disambiguate(self, pupil_datum: T.Dict) -> Circle:
        return self._frontend._extract_unproject_disambiguate(pupil_datum)

    def _disambiguate_circle_3d_pair(
        self, circle_3d_pair: T.Tuple[Circle, Circle]
    ) -> Circle:
        return self._frontend._disambiguate_circle_3d_pair(circle_3d_pair)

    def predict_pupil_circle(
        self, observation: Observation, use_unprojection: bool = False
    ) -> Circle:
        return self._frontend.predict_pupil_circle(observation, use_unprojection)

    def apply_refraction_correction(self, pupil_circle: Circle) -> Circle:
        return self._frontend.apply_refraction_correction(pupil_circle)

    def cleanup(self):
        logger.debug("Cancelling backend process")
        self._backend_process.cancel()
        self._frontend.cleanup()

    def mean_observation_circularity(self) -> float:
        raise NotImplementedError


class _TwoSphereModelSyncedAbstract(TwoSphereModel):
    def __init__(
        self,
        synced_sphere_center: mp.Array,  # c_double_Array_3
        synced_corrected_sphere_center: mp.Array,  # c_double_Array_3
        synced_projected_sphere_center: mp.Array,  # c_double_Array_2
        synced_observation_count: mp.Value,  # c_long
        synced_rms_residual: mp.Value,  # c_double
        flag_is_estimation_ongoing: mp.Event,
        **kwargs,
    ):
        self._synced_sphere_center = synced_sphere_center
        self._synced_corrected_sphere_center = synced_corrected_sphere_center
        self._synced_projected_sphere_center = synced_projected_sphere_center
        self._synced_observation_count = synced_observation_count
        self._synced_rms_residual = synced_rms_residual
        self._is_estimation_ongoing_flag = flag_is_estimation_ongoing
        super().__init__(**kwargs)

    @property
    def sphere_center(self):
        with self._synced_sphere_center:
            return np.array(self._synced_sphere_center.get_obj())

    @sphere_center.setter
    def sphere_center(self, coordinates: np.array):
        raise NotImplementedError

    @property
    def corrected_sphere_center(self):
        with self._synced_corrected_sphere_center:
            return np.array(self._synced_corrected_sphere_center.get_obj())

    @corrected_sphere_center.setter
    def corrected_sphere_center(self, coordinates: np.array):
        raise NotImplementedError

    @property
    def projected_sphere_center(self):
        with self._synced_projected_sphere_center:
            return np.array(self._synced_projected_sphere_center.get_obj())

    @projected_sphere_center.setter
    def projected_sphere_center(self, coordinates: np.array):
        raise NotImplementedError

    def mean_observation_circularity(self) -> float:
        raise NotImplementedError

    @property
    def rms_residual(self) -> float:
        with self._synced_rms_residual:
            return self._synced_rms_residual.value

    @rms_residual.setter
    def rms_residual(self, residual: float):
        raise NotImplementedError


class _TwoSphereModelSyncedFrontend(_TwoSphereModelSyncedAbstract):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.storage  # There is no storage in the frontend

    def _set_default_model_params(self):
        with self._synced_sphere_center:
            self._synced_sphere_center[:] = DEFAULT_SPHERE_CENTER

        corrected_sphere_center = self.refractionizer.correct_sphere_center(
            np.asarray([[*self.sphere_center]])
        )[0]
        with self._synced_corrected_sphere_center:
            self._synced_corrected_sphere_center[:] = corrected_sphere_center

    @property
    def n_observations(self) -> int:
        return self._synced_observation_count.value


class _TwoSphereModelSyncedBackend(_TwoSphereModelSyncedAbstract):
    @property
    def sphere_center(self):
        return super().sphere_center

    @sphere_center.setter
    def sphere_center(self, coordinates: np.array):
        with self._synced_sphere_center:
            self._synced_sphere_center[:] = coordinates

    @property
    def corrected_sphere_center(self):
        return super().corrected_sphere_center

    @corrected_sphere_center.setter
    def corrected_sphere_center(self, coordinates: np.array):
        with self._synced_corrected_sphere_center:
            self._synced_corrected_sphere_center[:] = coordinates

    @property
    def projected_sphere_center(self):
        return super().projected_sphere_center

    @projected_sphere_center.setter
    def projected_sphere_center(self, coordinates: np.array):
        with self._synced_projected_sphere_center:
            self._synced_projected_sphere_center[:] = coordinates

    def add_observation(self, observation: Observation):
        super().add_observation(observation=observation)
        n_observations = super().n_observations
        with self._synced_observation_count:
            self._synced_observation_count.value = n_observations

    @property
    def n_observations(self) -> int:
        return self._synced_observation_count.value

    def estimate_sphere_center(self, *args, **kwargs):
        result = super().estimate_sphere_center(*args, **kwargs)
        self._is_estimation_ongoing_flag.clear()
        return result

    def estimate_sphere_center_2d(self) -> np.ndarray:
        estimated: np.ndarray = super().estimate_sphere_center_2d()
        self.projected_sphere_center = estimated
        return estimated

    @property
    def rms_residual(self) -> float:
        with self._synced_rms_residual:
            return self._synced_rms_residual.value

    @rms_residual.setter
    def rms_residual(self, residual: float):
        with self._synced_rms_residual:
            self._synced_rms_residual.value = residual
