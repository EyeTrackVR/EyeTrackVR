"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Algorithm App Implementations By: Prohurtz, qdot (GUI, Initial Implementations), PallasNeko (Optimizations), Summer (Algorithim Engineer)

Additional Contributors: [Assassin], Summer404NotFound, lorow, ZanzyTHEbar

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import logging
import sys
import os
import time
from collections import deque
from config import EyeTrackCameraConfig
from config import EyeTrackConfig
from config import EyeTrackSettingsConfig
from pye3d.camera import CameraModel
from pye3d.detector_3d import Detector3D, DetectorMode
import queue
from osc_calibrate_filter import *
from daddy import External_Run_DADDY
from leap import External_Run_LEAP
from next_model import External_Run_NEXT
from haar_surround_feature import External_Run_HSF
from ransac import *
from blink import *
from utils.img_utils import circle_crop
from eye import EyeId, EyeInfo, EyeInfoOrigin
from intensity_based_openness import *
from ellipse_based_pupil_dilation import *
from AHSF import *
from osc.OSCMessage import OSCMessageType, OSCMessage
from eyebrow import EyeBrow
from utils.calibration_elipse import *
from utils.runtime_state import set_value as _set_runtime_value
from utils.robust_calibration import RobustCalibrationSession, CalibrationPhase
from utils.bs_detector import BSDetector


os.environ["OMP_NUM_THREADS"] = "1"
sys.path.append(".")

logger = logging.getLogger(__name__)


def run_once(f):
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return f(*args, **kwargs)

    wrapper.has_run = False
    return wrapper


def remap_leap_lid_openness(raw: float, close_t: float, wide_t: float) -> float:
    """Remap LEAP lid openness (0 closed .. 1 open): snap closed at/below close_t; cap at 0.75 until wide_t; then map to 0.95 at fully open."""
    r = float(np.clip(raw, 0.0, 1.0))
    ct = float(np.clip(close_t, 0.0, 0.99))
    wt = float(np.clip(wide_t, 0.0, 1.0))
    if wt <= ct:
        wt = min(1.0, ct + 1e-3)
    if r <= ct:
        return 0.0
    if r >= 1.0:
        return 0.95
    if r >= wt:
        span = 1.0 - wt
        if span <= 1e-9:
            return 0.95
        t = (r - wt) / span
        return 0.75 + t * (0.95 - 0.75)
    span_mid = wt - ct
    if span_mid <= 1e-9:
        return 0.0
    t = (r - ct) / span_mid
    return float(t * 0.75)


def leap_lid_thresholds_for_eye(
    settings: "EyeTrackSettingsConfig", eye_id: EyeId
) -> tuple[float, float]:
    if eye_id == EyeId.LEFT:
        return (
            float(settings.leap_lid_close_threshold_left),
            float(settings.leap_lid_widen_threshold_left),
        )
    return (
        float(settings.leap_lid_close_threshold_right),
        float(settings.leap_lid_widen_threshold_right),
    )


class EyeProcessor:
    def __init__(
        self,
        config: "EyeTrackCameraConfig",
        settings: "EyeTrackSettingsConfig",
        baseconfig: "EyeTrackConfig",
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        capture_queue_incoming: "queue.Queue(maxsize=2)",
        image_queue_outgoing: "queue.Queue(maxsize=2)",
        eye_id,
        osc_queue: queue.Queue,
    ):
        self.config = config
        self.settings = settings
        self.eye_id = eye_id
        # Cross-thread communication management
        self.capture_queue_incoming = capture_queue_incoming
        self.image_queue_outgoing = image_queue_outgoing
        self.cancellation_event = cancellation_event
        self.capture_event = capture_event
        # When True, camera feeds roi_queue only; GUI paces capture_event, do not signal from this thread.
        self.suppress_auto_capture_signal = False
        self.eye_id = eye_id
        self.baseconfig = baseconfig
        self.osc_queue = osc_queue

        # Cross-algorithm state
        self.last_projected_sphere = None
        self.circle_crop_center_x = 20
        self.circle_crop_center_y = 20
        self.circle_crop_radius = 40

        # Image state
        self.previous_image = None
        self.current_image = None
        self.current_image_gray = None
        self.current_frame_number = None
        self.current_fps = None
        self.current_capture_ts: float | None = None
        # Tracking-output metrics. Both are time-windowed (last N seconds) so
        # the readout is stable and matches what the eye can perceive, not a
        # noisy single-frame number. output_fps = iterations / window; latency
        # = mean of per-frame (tracking_done_ts - capture_push_ts).
        self._metrics_window_s: float = 3.0
        self._tracking_tick_times: deque = deque()
        # Each entry: (sample_time, latency_ms_for_that_frame).
        self._tracking_latency_samples: deque = deque()
        self.output_fps: float = 0.0
        self.output_latency_ms: float = 0.0
        self.threshold_image = None
        self.thresh = None
        # Calibration Values
        # Keep large in order to recenter correctly
        self.calibration_start_time = None
        self.calibration_3d_frame_counter = None
        self.should_print_calibration_warning = True
        self.grab_3d_point = False
        self.xmax = -69420
        self.xmin = 69420
        self.ymax = -69420
        self.ymin = 69420
        self.blink_clear = False
        # Time-based warmup gates (previously frame counters tuned for a 50 fps
        # source). Frame-counter versions silently broke on high-fps cameras
        # (e.g. 120 fps cut the warmup in half) and low-fps files.
        self._circle_crop_warmup_s = 4.0  # was circle_crop_delay_frames = 200 @ 50 fps
        self._circle_crop_ready_at = time.perf_counter() + self._circle_crop_warmup_s
        self._recenter_delay_s = 0.2  # was recenter_delay_frames = 10 @ 50 fps
        self._recenter_armed_at = None  # perf_counter when recenter was requested
        # NEXT-model recenter: a fixed, in-memory gaze offset applied to the raw
        # NEXT output so the recenter button can zero it without calibration and
        # without persisting anything to disk.
        self._next_recenter_offset_x = 0.0
        self._next_recenter_offset_y = 0.0
        self._next_recenter_armed_at = None  # perf_counter when NEXT recenter was requested
        # NEXT Smart Calibration state.
        #   _next_smartcal_active_dot: index (0..10) of the overlay dot currently
        #     being held/sampled, or None when not calibrating.
        #   _next_smartcal_samples: {dot -> [(raw_gaze_x, raw_gaze_y), ...]}
        #     accumulated while that dot is held; medianed at fit time.
        #   _next_smartcal_w / _b: the fitted affine transform (loaded from
        #     config) applied to the raw model gaze each frame, or None.
        #   _next_smartcal_warp: the space the affine was fit in ("atanh" =
        #     un-saturate the model's tanh output first; None = legacy raw-space
        #     affine from older builds).
        self._next_smartcal_active_dot = None
        self._next_smartcal_dot_started = 0.0
        self._next_smartcal_samples = {}
        self._next_smartcal_w = (
            list(self.config.next_smartcal_w)
            if getattr(self.config, "next_smartcal_w", None) is not None
            else None
        )
        self._next_smartcal_b = (
            list(self.config.next_smartcal_b)
            if getattr(self.config, "next_smartcal_b", None) is not None
            else None
        )
        self._next_smartcal_warp = getattr(self.config, "next_smartcal_warp", None)
        # Validate transforms persisted by older builds (which saved fits with
        # no sanity checks): a degenerate transform pins the clipped gaze output
        # to the corners, which reads as "tracking completely broken". Ignore
        # and clear such transforms instead of applying them.
        if self._next_smartcal_w is not None and not next_smartcal_transform_is_sane(
            self._next_smartcal_w, self._next_smartcal_b, self._next_smartcal_warp
        ):
            logger.warning(
                "NEXT smart cal (eye %s): stored transform W=%s B=%s warp=%s is "
                "degenerate - ignoring it. Re-run NEXT Smart Calib to fit a new one.",
                self.eye_id, self._next_smartcal_w, self._next_smartcal_b,
                self._next_smartcal_warp,
            )
            self._next_smartcal_w = None
            self._next_smartcal_b = None
            self._next_smartcal_warp = None
            self.config.next_smartcal_w = None
            self.config.next_smartcal_b = None
            self.config.next_smartcal_warp = None
        self.previous_rotation = self.config.rotation_angle
        self.camera_model = None
        self.detector_3d = None
        self.hsf_runner = None
        self.daddy_runner = None
        self.leap_runner = None
        self.next_runner = None
        self.current_raw_frame: np.ndarray | None = None
        self.next_eyebrow: float = float("nan")
        self.ibo = IntensityBasedOpeness(self.eye_id)
        self.ebpd = EllipseBasedPupilDilation(self.eye_id)
        self.roi_include_set = {"rotation_angle", "roi_window_x", "roi_window_y"}
        self.failed = 0
        self.skip_blink_detect = False
        self._last_tracking_pull_mono: float = 0.0
        self.out_y = 0.0
        self.out_x = 0.0
        self.rawx = 0.0
        self.rawy = 0.0
        self.eyeopen = 0.9
        self.max_ints = []
        self.max_int = 0
        # Sentinel for "no minimum seen yet"; previously a magic 4e12 literal.
        self.min_int = float("inf")
        self.frames = 0
        # Preview output is for the GUI only; throttle to 60 Hz so trackers
        # running >60 fps don't waste cycles on cv2.resize / concatenate /
        # queue churn that the user can never see.
        self._preview_min_interval_s = 1.0 / 60.0
        self._preview_last_emit_ts = 0.0
        self.blinkvalue = False
        self.hsrac_enabled = False
        self.radius = 10
        self.past_blink = 0.7
        self.prev_x = None
        self.prev_y = 0.1
        self.prev_x_list = []
        self.prev_y_list = []
        self.blink_list = []
        self.ran_blink_check_for_file = True
        self.bd_blink = False
        self.current_algo = EyeInfoOrigin.HSRAC
        self.current_algorithm = EyeInfoOrigin.HSRAC
        self.pupil_width = 0.0
        self.pupil_height = 0.0
        self.avg_velocity = 0.0
        self.angle = 621
        self.ahsf_runner = None
        self.eyebrow_runner: EyeBrow | None = None
        self.cal = CalibrationEllipse()
        self.squeeze = 0.0
        self.ahsf_detector = PupilDetectorHaar()

        # Robust calibration pipeline
        self.robust_cal = RobustCalibrationSession()
        self.bs_detector = BSDetector()
        if getattr(config, "robust_calib_data", None):
            try:
                self.robust_cal = RobustCalibrationSession.from_dict(config.robust_calib_data)
            except Exception as _e:
                logger.warning("Failed to load robust calibration data: %s", _e)

        try:
            min_cutoff = float(self.settings.gui_min_cutoff)  # 0.0004
            beta = float(self.settings.gui_speed_coefficient)  # 0.9
        except (TypeError, ValueError):
            logger.warning("OneEuroFilter values must be a legal number.")
            min_cutoff = 0.0004
            beta = 0.9
        noisy_point = np.array([1, 1])
        self.one_euro_filter = OneEuroFilter(
            noisy_point, min_cutoff=min_cutoff, beta=beta
        )
        self._crop_geom_cache_key = None
        self._crop_matrix = None
        self._crop_fits_in_bounds = None
        # Built in run(); pre-set so ALGOSELECT can run safely before then.
        self._algorithm_slots: list = [None] * 8

    def _needs_gray_clean_copy(self) -> bool:
        s = self.settings
        if s.gui_BLINK or s.gui_LEAP or s.gui_LEAP_lid:
            return True
        if s.gui_HSRAC or s.gui_AHRAC or s.gui_RANSAC3D:
            return True
        # Robust calibration phases that sample the eye crop need the pre-algorithm frame.
        if getattr(self, "robust_cal", None) is not None:
            _phase = self.robust_cal.phase
            if _phase == CalibrationPhase.BLINK:
                return True
        return False

    # ── Robust calibration triggers ──────────────────────────────────────────

    def start_express_calibration(self) -> None:
        """Begin 5-point express calibration (automatic target advancement)."""
        self.robust_cal.start_express()

    def start_blink_calibration(self) -> None:
        """Begin 2-second closed-eye sclera threshold calibration."""
        self.robust_cal.start_blink()

    def start_pursuit_calibration(self) -> None:
        """Begin 10-second smooth-pursuit SVR training session."""
        self.robust_cal.start_pursuit()

    def _record_tracking_metrics(self):
        now = time.perf_counter()
        cutoff = now - self._metrics_window_s

        self._tracking_tick_times.append(now)
        while self._tracking_tick_times and self._tracking_tick_times[0] < cutoff:
            self._tracking_tick_times.popleft()
        if len(self._tracking_tick_times) >= 2:
            span = self._tracking_tick_times[-1] - self._tracking_tick_times[0]
            if span > 0:
                self.output_fps = (len(self._tracking_tick_times) - 1) / span

        if self.current_capture_ts is not None:
            latency_ms = (now - self.current_capture_ts) * 1000.0
            # Guard against absurd values from clock anomalies / first frame
            # after a long stall; keep them out of the moving average so the
            # readout isn't anchored to an outlier for the rest of the window.
            if 0.0 <= latency_ms < 10_000.0:
                self._tracking_latency_samples.append((now, latency_ms))
            while (
                self._tracking_latency_samples
                and self._tracking_latency_samples[0][0] < cutoff
            ):
                self._tracking_latency_samples.popleft()
            if self._tracking_latency_samples:
                self.output_latency_ms = sum(
                    s[1] for s in self._tracking_latency_samples
                ) / len(self._tracking_latency_samples)

    def output_images_and_update(self, threshold_image, output_information: EyeInfo):
        if self.image_queue_outgoing.qsize() > 0:
            return

        # Throttle preview emit to ~60 Hz independent of tracking rate. Two
        # cv2.resize calls + concatenate + queue put on a 120 fps tracker
        # was costing measurable time for a UI that can't render that fast.
        now = time.perf_counter()
        if now - self._preview_last_emit_ts < self._preview_min_interval_s:
            self.previous_image = self.current_image
            self.previous_rotation = self.config.rotation_angle
            return
        self._preview_last_emit_ts = now

        self.current_image_gray = cv2.resize(
            self.current_image_gray, (150, 150), interpolation=cv2.INTER_AREA
        )
        threshold_image = cv2.resize(
            threshold_image, (150, 150), interpolation=cv2.INTER_AREA
        )
        image_stack = np.concatenate((self.current_image_gray, threshold_image), axis=1)

        try:
            self.image_queue_outgoing.put_nowait((image_stack, output_information))
        except queue.Full:
            pass

        self.previous_image = self.current_image
        self.previous_rotation = self.config.rotation_angle

    def _maybe_apply_bigscreen_default_crop(self) -> None:
        """On the very first frame in bigscreen mode, default the ROI to this eye's half of the frame."""
        if self.settings.gui_setup_mode != "bigscreen":
            return
        if self.config.bigscreen_auto_crop_frame is not None:
            return
        h, w = self.current_image.shape[:2]
        half_w = w // 2
        if self.eye_id == EyeId.LEFT:
            self.config.roi_window_x = 0
            self.config.roi_window_y = 0
            self.config.roi_window_w = half_w
            self.config.roi_window_h = h
        else:
            self.config.roi_window_x = half_w
            self.config.roi_window_y = 0
            self.config.roi_window_w = w - half_w
            self.config.roi_window_h = h
        self.config.bigscreen_auto_crop_frame = [w, h]
        try:
            self.baseconfig.save()
        except Exception:
            pass

    def capture_crop_rotate_image(self):
        self.ibo.change_roi(
            {
                "rotation_angle": self.config.rotation_angle,
                "roi_window_x": self.config.roi_window_x,
                "roi_window_y": self.config.roi_window_y,
            }
        )
        roi_x = self.config.roi_window_x
        roi_y = self.config.roi_window_y
        roi_w = self.config.roi_window_w
        roi_h = self.config.roi_window_h

        img_h, img_w = self.current_image.shape[:2]

        try:
            # Apply rotation to cropped area. For any rotation area outside of the bounds of the image,
            # fill with avg color + 10.
            # fill with white (self.current_image_white) and average in-bounds color (self.current_image).
            normalized_rotation = float(self.config.rotation_angle) % 360.0
            no_rotation = (
                normalized_rotation < 1e-6 or 360.0 - normalized_rotation < 1e-6
            )
            integer_roi = all(
                float(v).is_integer() for v in (roi_x, roi_y, roi_w, roi_h)
            )
            if no_rotation and integer_roi:
                x0 = int(roi_x)
                y0 = int(roi_y)
                x1 = x0 + int(roi_w)
                y1 = y0 + int(roi_h)
                if 0 <= x0 and 0 <= y0 and x1 <= img_w and y1 <= img_h:
                    cropped = self.current_image[y0:y1, x0:x1].copy()
                    self.current_image_white = cropped
                    self.current_image = cropped
                    return True

            geom_key = (
                roi_x,
                roi_y,
                roi_w,
                roi_h,
                int(self.config.rotation_angle),
                img_w,
                img_h,
            )
            if self._crop_geom_cache_key != geom_key:
                crop_matrix = np.float32([[1, 0, -roi_x], [0, 1, -roi_y], [0, 0, 1]])
                img_center = (roi_w / 2, roi_h / 2)
                rotation_matrix = cv2.getRotationMatrix2D(
                    img_center, self.config.rotation_angle, 1
                )
                matrix = np.matmul(rotation_matrix, crop_matrix)
                inv_matrix = np.linalg.inv(np.vstack((matrix, [0, 0, 1])))[:-1]
                corners = np.matmul(
                    [[0, 0, 1], [roi_w, 0, 1], [0, roi_h, 1], [roi_w, roi_h, 1]],
                    np.transpose(inv_matrix),
                )
                fits_in_bounds = all(
                    0 <= x <= img_w and 0 <= y <= img_h for (x, y) in corners
                )
                self._crop_geom_cache_key = geom_key
                self._crop_matrix = matrix
                self._crop_fits_in_bounds = fits_in_bounds
            else:
                matrix = self._crop_matrix
                fits_in_bounds = self._crop_fits_in_bounds

            self.current_image_white = cv2.warpAffine(
                self.current_image,
                matrix,
                (roi_w, roi_h),
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            )

            if fits_in_bounds:
                # crop is entirely within original image bounds so average color and white are identical
                self.current_image = self.current_image_white
                return True

            # image does not fit in bounds, so warp, calculate average color of covered pixels, and apply that to the outside region.

            # warp image with alpha (use fresh BGR frame; do not mutate the alpha-warp input across calls)
            bgr = self.current_image
            alpha = np.full(bgr.shape[:2], 255, dtype=np.uint8)
            bgra = np.dstack((bgr, alpha))

            self.current_image = cv2.warpAffine(
                bgra,
                matrix,
                (roi_w, roi_h),
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0, 0),
            )

            avg_color_per_row = np.average(self.current_image, axis=0)
            avg_color = np.average(avg_color_per_row, axis=0)
            alpha_avg = float(avg_color[3])
            if alpha_avg < 1e-6:
                ar, ag, ab = 0.0, 0.0, 0.0
            else:
                avg_color_norm = avg_color[0:3] / alpha_avg
                ar, ag, ab = np.clip(avg_color_norm, 0.0, 1.0)

            rgb_ch = self.current_image[:, :, :3]
            inv_alpha_ch = 255 - self.current_image[:, :, 3]
            self.current_image = rgb_ch + np.stack(
                np.uint8([inv_alpha_ch * ar, inv_alpha_ch * ag, inv_alpha_ch * ab]),
                axis=-1,
            )

            return True
        except (cv2.error, ValueError, IndexError, AttributeError) as e:
            logger.debug("RGBA border blend failed: %s", e)

    def _ensure_pupil_axes_for_dilation(self) -> None:
        """EBPD expects ellipse axes in pixels; RANSAC3D sets pupil_width/height, other trackers only set radius."""
        if self.pupil_width > 1e-3 and self.pupil_height > 1e-3:
            return
        try:
            r = float(abs(self.radius))
        except (TypeError, ValueError):
            r = 0.0
        if r < 1.0:
            r = 10.0
        d = 2.0 * r
        self.pupil_width = d
        self.pupil_height = d

    def _enqueue_osc_message(self, osc_message: OSCMessage) -> None:
        try:
            self.osc_queue.put_nowait(osc_message)
            return
        except queue.Full:
            pass

        try:
            self.osc_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self.osc_queue.put_nowait(osc_message)
        except queue.Full:
            pass

    def _apply_circular_crop_if_enabled(self) -> None:
        circular_crop_enabled = (
            (self.eye_id == EyeId.LEFT and self.settings.gui_circular_crop_left)
            or (self.eye_id == EyeId.RIGHT and self.settings.gui_circular_crop_right)
        )
        if not circular_crop_enabled:
            return

        if time.perf_counter() < self._circle_crop_ready_at:
            return

        self.current_image_gray = circle_crop(
            self.current_image_gray,
            self.circle_crop_center_x,
            self.circle_crop_center_y,
            self.circle_crop_radius,
        )

    def _ibo_filter_samples(self) -> int:
        """IBO filter window size in frames, derived from the Eyelid
        Calibration Duration (seconds) at the current capture FPS. Previously
        a hand-tuned ``ibo_filter_samples`` field; folding it into the
        calibration duration eliminates a duplicated setting and makes the
        window track the actual frame rate (a 50 fps tune was silently too
        short at 120 fps and too long at 30 fps). 60 fps is used as a safe
        default before the first capture has set ``current_fps``."""
        fps = self.current_fps if self.current_fps and self.current_fps > 0 else 60.0
        seconds = max(1.0, float(self.settings.calibration_duration))
        return max(30, int(round(seconds * float(fps))))

    def UPDATE(self):
        self.current_algo = self.current_algorithm

        # NEXT produces its own eyelid openness (already remapped against the
        # close/widen thresholds in NEXTM). The image-intensity BLINK/IBO
        # estimators run on the eye-crop grayscale, which for NEXT is the full
        # uncropped frame; feeding that here would overwrite the model's
        # calibrated eyelid with garbage. Skip them for NEXT, mirroring the
        # existing `not gui_NEXT` guard on the LEAP-lid block below.
        if self.settings.gui_BLINK and not self.settings.gui_NEXT:
            self.eyeopen = BLINK(self)

        if (
            self.settings.gui_IBO and self.eyeopen != 0.0
            and not self.settings.gui_NEXT
        ):
            # TODO: Separate RANSAC blink state from the shared eye openness guard.
            self.eyeopen = self.ibo.intense(
                self.rawx,
                self.rawy,
                self.current_image_white,
                self._ibo_filter_samples(),
                self.settings.ibo_average_output_samples,
            )
            # Share the per-eye Lid Close Threshold with LEAP Lid, formerly a
            # separate ibo_fully_close_eye_threshold field, now consolidated.
            ibo_close_t, _ = leap_lid_thresholds_for_eye(self.settings, self.eye_id)
            if self.eyeopen < ibo_close_t:
                self.eyeopen = 0.0

            if self.bd_blink == True:
                logger.debug("Blink detected")

        if (
            self.settings.gui_LEAP_lid
            and self.eyeopen != 0.0
            and not self.settings.gui_LEAP
            and not self.settings.gui_NEXT
        ):
            (
                self.current_image_gray,
                self.rawx,
                self.rawy,
                self.eyeopen,
            ) = self.leap_runner.run(
                self.current_image_gray,
                self.current_image_gray_clean,
                self.calibration_start_time,
                self.settings.gui_use_gpu,
            )
            close_t, wide_t = leap_lid_thresholds_for_eye(self.settings, self.eye_id)
            self.eyeopen = remap_leap_lid_openness(self.eyeopen, close_t, wide_t)

        if (
            len(self.prev_y_list) >= 100
        ):
            self.prev_y_list.pop(0)
            self.prev_y_list.append(self.out_y)
        else:
            self.prev_y_list.append(self.out_y)

        blink_vec = min(abs(self.eyeopen - self.past_blink), 1)  # clamp to 1

        if blink_vec >= 0.18:
            # self.out_x = sum(self.prev_x_list) / len(self.prev_x_list)
            self.out_y = sum(self.prev_y_list) / len(self.prev_y_list)

        if self.settings.gui_pupil_dilation:
            self._ensure_pupil_axes_for_dilation()
            self.pupil_dilation = self.ebpd.intense(
                self.pupil_width,
                self.pupil_height,
                self.rawx,
                self.rawy,
                self.current_image_white,
                self._ibo_filter_samples(),
                self.settings.ibo_average_output_samples,
            )
        else:
            self.pupil_dilation = 0.5

        self.past_blink = self.eyeopen
        self.prev_x = self.out_x
        self.prev_y = self.out_y

        if self.eyebrow_runner is not None:
            _brow = self.eyebrow_runner.get_result()
        elif self.settings.gui_NEXT:
            _brow = self.next_eyebrow
        else:
            _brow = float("nan")
        self.output_images_and_update(
            self.thresh,
            EyeInfo(
                self.current_algo,
                self.out_x,
                self.out_y,
                self.pupil_dilation,
                self.eyeopen,
                self.avg_velocity,
                _brow,
                self.squeeze,
            ),
        )

        osc_message = OSCMessage(
            type=OSCMessageType.EYE_INFO,
            data=(
                self.eye_id,
                EyeInfo(
                    self.current_algo,
                    self.out_x,
                    self.out_y,
                    self.pupil_dilation,
                    self.eyeopen,
                    self.avg_velocity,
                    _brow,
                    self.squeeze,
                ),
            ),
        )
        self._enqueue_osc_message(osc_message)
        # TODO: Remove this reset after callers handle 0.0 openness explicitly.
        self.eyeopen = 0.8

    def BLINKM(self):
        self.eyeopen = BLINK(self)

    def LEAPM(self):
        self.thresh = self.current_image_gray.copy()
        (
            self.current_image_gray,
            self.rawx,
            self.rawy,
            eyeopen,
        ) = self.leap_runner.run(
            self.current_image_gray,
            self.current_image_gray_clean,
            self.calibration_start_time,
            self.settings.gui_use_gpu,
        )
        # Publish raw lid (pre-remap) so the settings UI visualizer can show
        # where the user's eye currently sits relative to the close/widen markers.
        _set_runtime_value(f"raw_lid_{int(self.eye_id)}", float(eyeopen))
        if self.settings.gui_LEAP_lid:
            close_t, wide_t = leap_lid_thresholds_for_eye(self.settings, self.eye_id)
            self.eyeopen = remap_leap_lid_openness(eyeopen, close_t, wide_t)
        self.thresh = self.current_image_gray.copy()
        self.out_x, self.out_y, self.avg_velocity = cal.cal_osc(
            self, self.rawx, self.rawy, self.angle
        )
        self.current_algorithm = EyeInfoOrigin.LEAP

    def DADDYM(self):
        self.thresh = self.current_image_gray.copy()
        self.rawx, self.rawy, self.radius = self.daddy_runner.run(
            self.current_image_gray
        )
        self.out_x, self.out_y, self.avg_velocity = cal.cal_osc(
            self, self.rawx, self.rawy, self.angle
        )
        self.current_algorithm = EyeInfoOrigin.DADDY

    def NEXTM(self):
        if self.current_raw_frame is None:
            return
        self.thresh = self.current_image_gray.copy()
        
        base_cutoff = float(self.settings.gui_min_cutoff)
        base_beta = float(self.settings.gui_speed_coefficient)

        # NEXT runs on the RAW camera frame (no ROI window, no rotation) to match
        # how the model was trained/exported (see infer.py's --roi handling). In
        # bigscreen mode one camera carries both eyes side-by-side, so feed this
        # eye's half; the LEFT/RIGHT split mirrors data_collection's bigscreen crop.
        next_frame = self.current_raw_frame
        if self.settings.gui_setup_mode == "bigscreen":
            mid = next_frame.shape[1] // 2
            next_frame = next_frame[:, :mid] if self.eye_id == EyeId.LEFT else next_frame[:, mid:]

        gaze_x, gaze_y, eyebrow, eyelid, squeeze = self.next_runner.run(
            next_frame, base_cutoff, base_beta
        )

        # Raw model gaze, before any flip. NEXT regresses gaze DIRECTION in
        # [-1, 1] (right/up positive), unlike pupil-pixel trackers, whose raw
        # output is an image coordinate. The calibration path below needs this
        # un-flipped copy (see the cal_osc call).
        model_gaze_x, model_gaze_y = gaze_x, gaze_y

        # Flip Y for output: the model regresses up-positive, but the app's
        # downstream/OSC convention is up-negative. model_gaze_y above stays
        # un-flipped so calibration keeps fitting against the raw model output.
        gaze_y = -gaze_y

        # ── NEXT Smart Calibration ────────────────────────────────────────────
        # While a dot is being held by the overlay, accumulate the raw model
        # gaze so the regression can be fit against the dot's known position.
        # Only within the capture window: the overlay holds each dot 0.5 s
        # after its signal, then the next dot appears and the user follows it;
        # sampling past the hold poisons this dot with the next dot's fixation.
        _sc_dot = self._next_smartcal_active_dot
        if _sc_dot is not None and (
            time.monotonic() - self._next_smartcal_dot_started
            <= NEXT_SMARTCAL_CAPTURE_WINDOW_S
        ):
            self._next_smartcal_samples.setdefault(_sc_dot, []).append(
                (model_gaze_x, model_gaze_y)
            )

        # Apply the fitted (warp + affine) transform (smart calib) to map raw
        # model gaze -> calibrated gaze. The arctanh warp un-saturates the
        # model's tanh output so the correction stays gentle instead of slamming
        # to the extremes. Skipped while the legacy ellipse-based
        # gui_NEXT_calibration is in use so the two paths never compound.
        if (
            self._next_smartcal_w is not None
            and self._next_smartcal_b is not None
            and not self.settings.gui_NEXT_calibration
        ):
            _cal_x, _cal_y = next_smartcal_apply(
                self._next_smartcal_w, self._next_smartcal_b,
                self._next_smartcal_warp, model_gaze_x, model_gaze_y,
            )
            # Keep the result in the model's native output range so a strong
            # transform can't push extreme values downstream to OSC.
            gaze_x = float(np.clip(_cal_x, -1.0, 1.0))
            gaze_y = float(np.clip(_cal_y, -1.0, 1.0))

        if self.eye_id == EyeId.RIGHT:
            if self.settings.gui_flip_x_axis_right:
                gaze_x = -gaze_x
        else:
            if self.settings.gui_flip_x_axis_left:
                gaze_x = -gaze_x
        if self.settings.gui_flip_y_axis:
            gaze_y = -gaze_y

        self.rawx = gaze_x
        self.rawy = gaze_y

        # Raw eyelid openness (pre-remap). Publish on the same runtime channel
        # LEAP uses so the settings-menu lid visualizer shows a live indicator
        # for NEXT too; this is what makes the close/widen markers tunable
        # against live tracking when NEXT calibration is enabled.
        eyeopen_raw = eyelid * max(0.0, 1.0 - squeeze)
        _set_runtime_value(f"raw_lid_{int(self.eye_id)}", float(eyeopen_raw))

        if self.settings.gui_NEXT_calibration:
            # cal_osc runs the classic ellipse calibration, which bakes in the
            # image-space -> gaze orientation flips (flip_x=True, -y) that
            # pupil-pixel trackers depend on, and then re-applies the user's
            # flip settings. NEXT's gaze is already correctly oriented, so we
            # feed the NEGATED raw model gaze: the negation cancels the ellipse's
            # baked flips (leaving orientation matching the non-calibration path),
            # while cal_osc still applies gui_flip_* exactly once. Passing
            # self.rawx/rawy here instead would invert both axes (the baked flip)
            # AND double-apply the gui flips (cancelling them).
            self.out_x, self.out_y, self.avg_velocity = cal.cal_osc(
                self, -model_gaze_x, -model_gaze_y, 0.0
            )
            close_t, wide_t = leap_lid_thresholds_for_eye(self.settings, self.eye_id)
            self.eyeopen = remap_leap_lid_openness(eyeopen_raw, close_t, wide_t)
        else:
            # Recenter (NEXT, no-save): when the recenter button is pressed,
            # capture the current raw gaze as a fixed offset and subtract it so
            # the output zeroes on the user's current gaze. Unlike calibration
            # recenter, this offset lives only in memory and is never saved.
            # gui_recenter_eyes is shared across both eye processors, so hold it
            # briefly (same 0.2s gate as the calibration path) to let both eyes
            # capture their offset before clearing the flag.
            if self.settings.gui_recenter_eyes:
                self._next_recenter_offset_x = gaze_x
                self._next_recenter_offset_y = gaze_y
                now = time.perf_counter()
                if self._next_recenter_armed_at is None:
                    self._next_recenter_armed_at = now
                elif now - self._next_recenter_armed_at >= self._recenter_delay_s:
                    self.settings.gui_recenter_eyes = False
                    self._next_recenter_armed_at = None
            else:
                self._next_recenter_armed_at = None

            gaze_x -= self._next_recenter_offset_x
            gaze_y -= self._next_recenter_offset_y

            dx = gaze_x - self.out_x
            dy = gaze_y - self.out_y
            self.avg_velocity = float(np.sqrt(dx * dx + dy * dy))
            self.out_x = gaze_x
            self.out_y = gaze_y
            self.eyeopen = eyeopen_raw

        # Snap to fully-closed: NEXT openness near zero is treated as a blink so
        # the eye reports a clean 0.0 instead of jittering just above closed.
        if self.eyeopen < 0.08:
            self.eyeopen = 0.0

        self.squeeze = squeeze
        self.next_eyebrow = eyebrow
        self._enqueue_osc_message(OSCMessage(
            type=OSCMessageType.EYEBROW_INFO,
            data=(self.eye_id, eyebrow),
        ))
        self.current_algorithm = EyeInfoOrigin.NEXT

    def AHRACM(self):
        self._apply_circular_crop_if_enabled()

        self.hsrac_enabled = True
        (
            self.current_image_gray,
            resize_img,
            self.rawx,
            self.rawy,
            self.radius,
        ) = self.ahsf_runner.detect_etvr(self.current_image_gray)
        self.current_image_gray_clean = resize_img.copy()

        self.thresh = resize_img
        (
            self.rawx,
            self.rawy,
            self.angle,
            self.thresh,
            ranblink,
            self.pupil_width,
            self.pupil_height,
        ) = RANSAC3D(self, True)
        if self.settings.gui_RANSACBLINK:  # might be redundant
            self.eyeopen = ranblink

        self.out_x, self.out_y, self.avg_velocity = cal.cal_osc(
            self, self.rawx, self.rawy, self.angle
        )
        self.current_algorithm = EyeInfoOrigin.HSRAC

    def HSRACM(self):
        self._apply_circular_crop_if_enabled()

        self.hsrac_enabled = True
        self.rawx, self.rawy, self.thresh, self.radius = self.hsf_runner.run(
            self.current_image_gray
        )
        (
            self.rawx,
            self.rawy,
            self.angle,
            self.thresh,
            ranblink,
            self.pupil_width,
            self.pupil_height,
        ) = RANSAC3D(self, True)
        if self.settings.gui_RANSACBLINK:  # might be redundant
            self.eyeopen = ranblink

        self.out_x, self.out_y, self.avg_velocity = cal.cal_osc(
            self, self.rawx, self.rawy, self.angle
        )
        self.current_algorithm = EyeInfoOrigin.HSRAC

    def HSFM(self):
        self._apply_circular_crop_if_enabled()
        # TODO: Reinitialize the HSF runner when the ROI resolution changes.
        self.rawx, self.rawy, self.thresh, self.radius = self.hsf_runner.run(
            self.current_image_gray
        )
        self.out_x, self.out_y, self.avg_velocity = cal.cal_osc(
            self, self.rawx, self.rawy, self.angle
        )
        self.current_algorithm = EyeInfoOrigin.HSF

    def RANSAC3DM(self):
        self._apply_circular_crop_if_enabled()
        self.hsrac_enabled = False
        (
            self.rawx,
            self.rawy,
            self.angle,
            self.thresh,
            ranblink,
            self.pupil_width,
            self.pupil_height,
        ) = RANSAC3D(self, True)
        if self.settings.gui_RANSACBLINK:
            self.eyeopen = ranblink
        self.out_x, self.out_y, self.avg_velocity = cal.cal_osc(
            self, self.rawx, self.rawy, self.angle
        )
        self.current_algorithm = EyeInfoOrigin.RANSAC

    def AHSFM(self):
        self._apply_circular_crop_if_enabled()
        (
            self.current_image_gray,
            resize_img,
            self.rawx,
            self.rawy,
            self.radius,
        ) = self.ahsf_runner.detect_etvr(self.current_image_gray)
        self.thresh = self.current_image_gray
        self.out_x, self.out_y, self.avg_velocity = cal.cal_osc(
            self, self.rawx, self.rawy, self.angle
        )
        self.current_algorithm = EyeInfoOrigin.HSF

    def ALGOSELECT(self):
        # Replaces an 8-way if/elif chain. Semantics preserved:
        # - Run the algorithm at slot self.failed (skipping None slots).
        # - The algorithm signals failure by incrementing self.failed, which
        #   causes the next non-None slot to run as a same-frame fallback.
        # - Success leaves self.failed unchanged (or sets it to 0).
        # - After walking past the last slot, wrap to 0.
        slots = self._algorithm_slots
        n = len(slots)
        for _ in range(n):
            if self.failed < 0 or self.failed >= n:
                self.failed = 0
            algo = slots[self.failed]
            if algo is None:
                self.failed += 1
                continue
            prev_failed = self.failed
            algo()
            if self.failed == prev_failed:
                # Algorithm did not advance: treat as success and stop.
                return
            # Algorithm advanced self.failed (failure): loop and try next slot.
        # Walked past the end without success: reset for next frame.
        self.failed = 0

    def _rebuild_algorithm_slots(self) -> None:
        """Rebuild _algorithm_slots from current settings. Called each frame so
        algo changes take effect immediately without a thread restart. Runner
        objects lazy-init on first use and are freed when their algo is disabled."""
        algorithm_slots: list = [None] * 8
        enabled_algorithms = []

        if self.settings.gui_AHRAC:
            if self.ahsf_runner is None:
                self.ahsf_runner = self.ahsf_detector
            enabled_algorithms.append(self.AHRACM)

        if self.settings.gui_AHSF:
            if self.ahsf_runner is None:
                self.ahsf_runner = self.ahsf_detector
            enabled_algorithms.append(self.AHSFM)

        if self.settings.gui_HSF:
            if self.hsf_runner is None:
                if self.eye_id in [EyeId.LEFT]:
                    self.hsf_runner = External_Run_HSF(
                        self.settings.gui_skip_autoradius,
                        self.settings.gui_HSF_radius_left,
                    )
                if self.eye_id in [EyeId.RIGHT]:
                    self.hsf_runner = External_Run_HSF(
                        self.settings.gui_skip_autoradius,
                        self.settings.gui_HSF_radius_right,
                    )
            enabled_algorithms.append(self.HSFM)
        else:
            if self.hsf_runner is not None:
                self.hsf_runner = None

        if self.settings.gui_HSRAC:
            if self.hsf_runner is None:
                if self.eye_id in [EyeId.LEFT]:
                    self.hsf_runner = External_Run_HSF(
                        self.settings.gui_skip_autoradius,
                        self.settings.gui_HSF_radius_left,
                    )
                if self.eye_id in [EyeId.RIGHT]:
                    self.hsf_runner = External_Run_HSF(
                        self.settings.gui_skip_autoradius,
                        self.settings.gui_HSF_radius_right,
                    )
            enabled_algorithms.append(self.HSRACM)
        else:
            if not self.settings.gui_HSF and self.hsf_runner is not None:
                self.hsf_runner = None

        if self.settings.gui_DADDY:
            if self.daddy_runner is None:
                self.daddy_runner = External_Run_DADDY()
            enabled_algorithms.append(self.DADDYM)
        else:
            if self.daddy_runner is not None:
                self.daddy_runner = None

        if self.settings.gui_NEXT:
            variant = getattr(self.settings, "gui_model_variant", "ETVR")
            # Reload if the selected model variant changed at runtime.
            if self.next_runner is not None and getattr(self.next_runner, "variant", None) != variant:
                self.next_runner = None
            if self.next_runner is None:
                self.next_runner = External_Run_NEXT(variant)
            enabled_algorithms.append(self.NEXTM)
        else:
            if self.next_runner is not None:
                self.next_runner = None

        if self.settings.gui_LEAP or self.settings.gui_LEAP_lid:
            if self.leap_runner is None:
                self.leap_runner = External_Run_LEAP(self.config, self.baseconfig)
            if self.settings.gui_LEAP:
                enabled_algorithms.append(self.LEAPM)
        else:
            if self.leap_runner is not None:
                self.leap_runner = None

        if self.settings.gui_RANSAC3D:
            enabled_algorithms.append(self.RANSAC3DM)

        for idx, algo in enumerate(enabled_algorithms[:8]):
            algorithm_slots[idx] = algo
        self._algorithm_slots = algorithm_slots

    def _run_eyebrow(self, raw_frame: np.ndarray) -> None:
        variant = getattr(self.settings, "gui_model_variant", "ETVR")
        # Reload if the selected model variant changed at runtime.
        if self.eyebrow_runner is not None and getattr(self.eyebrow_runner, "variant", None) != variant:
            self.eyebrow_runner.stop()
            self.eyebrow_runner = None
        if self.eyebrow_runner is None:
            try:
                self.eyebrow_runner = EyeBrow(variant)
            except Exception as e:
                logger.warning("EyeBrow init failed: %s", e)
                self.eyebrow_runner = None
                return
        if self.settings.gui_setup_mode == "bigscreen":
            mid = raw_frame.shape[1] // 2
            frame = raw_frame[:, :mid] if self.eye_id == EyeId.LEFT else raw_frame[:, mid:]
        else:
            frame = raw_frame
        self.eyebrow_runner.submit(frame)
        self._enqueue_osc_message(OSCMessage(
            type=OSCMessageType.EYEBROW_INFO,
            data=(self.eye_id, self.eyebrow_runner.get_result()),
        ))

    def run(self):
        # Reset HSF runner on each thread start so a fresh runner is built from
        # current settings rather than inheriting stale state from a prior run.
        self.hsf_runner = None

        while True:
            if self.cancellation_event.is_set():
                logger.info("Exiting tracking thread")
                return

            if self.config.roi_window_w <= 0 or self.config.roi_window_h <= 0:
                # At this point, we're waiting for the user to set up the ROI window in the GUI.
                if self.cancellation_event.wait(0.1):
                    return
                continue
            if (
                self.camera_model is None
                or self.detector_3d is None
                or self.camera_model.resolution
                != (
                    self.config.roi_window_w,
                    self.config.roi_window_h,
                )
            ):
                self.camera_model = CameraModel(
                    focal_length=self.config.focal_length,
                    resolution=(self.config.roi_window_w, self.config.roi_window_h),
                )
                self.detector_3d = Detector3D(
                    camera=self.camera_model, long_term_mode=DetectorMode.blocking
                )

            try:
                (
                    self.current_image,
                    self.current_frame_number,
                    self.current_fps,
                    self.current_capture_ts,
                ) = self.capture_queue_incoming.get(block=True, timeout=0.1)

                # [Limiter lag fix] We simply drain the queue to ensure we're processing the latest frame.
                try:
                    while True:
                        (
                            self.current_image,
                            self.current_frame_number,
                            self.current_fps,
                            self.current_capture_ts,
                        ) = self.capture_queue_incoming.get_nowait()
                except queue.Empty:
                    pass
            except queue.Empty:
                continue

            # Enforce tracking Hz limit
            max_hz = getattr(self.settings, "gui_max_tracking_speed", 0)
            if max_hz > 0:
                min_interval = 1.0 / max_hz
                now = time.perf_counter()
                elapsed = now - self._last_tracking_pull_mono
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                    # We slept, which means a fresher frame might have arrived. Drain the queue again.
                    try:
                        while True:
                            (
                                self.current_image,
                                self.current_frame_number,
                                self.current_fps,
                                self.current_capture_ts,
                            ) = self.capture_queue_incoming.get_nowait()
                    except queue.Empty:
                        pass
            self._last_tracking_pull_mono = time.perf_counter()

            raw_frame = self.current_image
            self.current_raw_frame = raw_frame

            self._maybe_apply_bigscreen_default_crop()

            if not self.capture_crop_rotate_image():
                continue

            if self.settings.gui_eyebrow:
                self._run_eyebrow(raw_frame)
            elif self.eyebrow_runner is not None:
                self.eyebrow_runner.stop()
                self.eyebrow_runner = None

            self.current_image_gray = cv2.cvtColor(
                self.current_image, cv2.COLOR_BGR2GRAY
            )
            if self._needs_gray_clean_copy():
                self.current_image_gray_clean = self.current_image_gray.copy()
            else:
                self.current_image_gray_clean = self.current_image_gray

            if self.cancellation_event.is_set():
                logger.info("Exiting tracking thread")
                return
            else:
                self._rebuild_algorithm_slots()
                self.ALGOSELECT()
                self.UPDATE()
                self._record_tracking_metrics()
