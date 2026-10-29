"""
Gaze output for foveated rendering tools on this PC.

Two transports, both on while "Foveated rendering gaze" is enabled:

* VRChat-style ``/tracking/eye/LeftRightPitchYaw`` (degrees, pitch positive
  down, yaw positive right) to UDP 9020, where PimaxMagic4All's "VRChat OSC"
  eye tracker listens. It only opens that port while a known gaze app holds
  its named mutex, so this sender holds ``Local\\eyetrackvr-osc-gaze``.
* The gaze shared memory block (osc/GazeSharedMemory.py,
  sdk/eyetrackvr_gaze.h): head-space direction per eye plus capture time,
  for EyeTrackVR's own OpenXR / SteamVR / streaming integrations.

Runs alongside whichever VRChat output mode is selected. Uses the same FOV
mapping as pyVRCFT's native endpoint so ±1 gaze lands on the calibrated FOV
edge rather than a fixed 45°. Gaze is EyeInfo.dfr_x / dfr_y: calibrated but
unfiltered, while VRChat keeps the smoothed x / y.
"""

import logging
import math
import sys

from eye import EyeId
from osc.GazeSharedMemory import (
    FLAG_GAZE_VALID,
    FLAG_OPENNESS_VALID,
    GazeEye,
    GazeSharedMemory,
    direction_from_pitch_yaw,
)
from osc.OSCMessage import OSCMessage
from osc.VRChatOSCSender import VRChatOSCSender
from pyvrcft.expressions import SingleEyeData, UnifiedTrackingData, native_pitch_yaw

logger = logging.getLogger(__name__)

FOVEATION_HOST = "127.0.0.1"
FOVEATION_PORT = 9020
FOVEATION_ADDRESS = "/tracking/eye/LeftRightPitchYaw"
FOVEATION_MUTEX = "Local\\eyetrackvr-osc-gaze"

# Below this openness the pupil fit is unreliable; hold that eye's last gaze
# instead of moving the foveal region to wherever a half-closed lid lands.
MIN_OPENNESS = 0.25


class _NamedMutex:
    """A Windows named mutex held only to signal "EyeTrackVR is publishing".
    No-op elsewhere: the consumers that check it are Windows-only."""

    def __init__(self, name: str):
        self.name = name
        self._handle = None

    def acquire(self) -> bool:
        if sys.platform != "win32" or self._handle is not None:
            return self._handle is not None
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            logger.warning("Foveation gaze: could not create mutex %s (error %d)", self.name, ctypes.get_last_error())
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle(self._handle)
        self._handle = None


def _finite(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


class FoveationGazeSender:
    def __init__(self):
        self.client = None
        self.data = UnifiedTrackingData()
        self.mutex = _NamedMutex(FOVEATION_MUTEX)
        self.shm = GazeSharedMemory()
        # Per-eye state for the shared memory block. GazeEye.flags also says
        # whether that eye has a usable gaze sample, so a closed or not-yet-seen
        # eye borrows the other eye's gaze on UDP instead of pulling to centre.
        self._eyes = {EyeId.LEFT: GazeEye(), EyeId.RIGHT: GazeEye()}
        self._sample_ns: int | None = None

    def start(self, config, client) -> None:
        """``client`` is a SafeOSCClient already pointed at FOVEATION_HOST:FOVEATION_PORT."""
        self.client = client
        self.data.gaze_yaw_max_deg = float(config.gui_gaze_yaw_max_deg)
        self.data.gaze_pitch_up_deg = float(config.gui_gaze_pitch_up_deg)
        self.data.gaze_pitch_down_deg = float(config.gui_gaze_pitch_down_deg)
        self.shm.fov = (self.data.gaze_yaw_max_deg, self.data.gaze_pitch_up_deg, self.data.gaze_pitch_down_deg)
        self.mutex.acquire()
        self.shm.open()
        logger.info("Foveation gaze sender started -> %s:%s", FOVEATION_HOST, FOVEATION_PORT)

    def stop(self) -> None:
        self.mutex.release()
        self.shm.close()
        if self.client is not None:
            self.client = None
            logger.info("Foveation gaze sender stopped")

    def _valid(self, eye_id) -> bool:
        return bool(self._eyes[eye_id].flags & FLAG_GAZE_VALID)

    def _update_eye(self, eye_id, eye: SingleEyeData, eye_info, openness: float) -> None:
        state = self._eyes[eye_id]
        state.openness = min(max(openness, 0.0), 1.0)
        state.flags = FLAG_OPENNESS_VALID
        # Unfiltered calibrated gaze: the foveal region should follow saccades at
        # once, so none of the smoothing VRChat gets. Filtered gaze only as a
        # fallback for a tracker without an unfiltered tap.
        x, y = _finite(getattr(eye_info, "dfr_x", None)), _finite(getattr(eye_info, "dfr_y", None))
        if x is None or y is None:
            x, y = _finite(eye_info.x), _finite(eye_info.y)
        if x is None or y is None or openness < MIN_OPENNESS:
            state.confidence = 0.0
            return
        eye.gaze = (x, y)
        state.direction = direction_from_pitch_yaw(*native_pitch_yaw(eye, self.data))
        state.confidence = 1.0
        state.flags |= FLAG_GAZE_VALID

    def output_osc_info(self, osc_message: OSCMessage, main_config, config) -> None:
        if self.client is None:
            return
        eye_id, eye_info = osc_message.data
        openness = _finite(eye_info.blink)
        if openness is None:
            return
        if config.osc_invert_eye_close:
            openness = 1.0 - openness

        left, right = self.data.eye.left, self.data.eye.right
        if VRChatOSCSender.get_is_single_eye(main_config.eye_display_id):
            self._update_eye(EyeId.LEFT, left, eye_info, openness)
            self._update_eye(EyeId.RIGHT, right, eye_info, openness)
        elif eye_id == EyeId.LEFT:
            self._update_eye(EyeId.LEFT, left, eye_info, openness)
        elif eye_id == EyeId.RIGHT:
            self._update_eye(EyeId.RIGHT, right, eye_info, openness)
        else:
            return

        capture_ts = _finite(getattr(eye_info, "capture_ts", None))
        if capture_ts is not None:
            self._sample_ns = int(capture_ts * 1e9)
        # Published even mid-blink: readers see the invalid flags right away.
        self.shm.publish(self._eyes[EyeId.LEFT], self._eyes[EyeId.RIGHT], self._sample_ns)

        left_ok, right_ok = self._valid(EyeId.LEFT), self._valid(EyeId.RIGHT)
        if not (left_ok or right_ok):
            # Blink or lost tracking: send nothing. PimaxMagic4All holds the
            # last gaze briefly, then falls back to fixed foveation.
            return
        lp, ly = native_pitch_yaw(left if left_ok else right, self.data)
        rp, ry = native_pitch_yaw(right if right_ok else left, self.data)
        self.client.send_message(FOVEATION_ADDRESS, [lp, ly, rp, ry])
