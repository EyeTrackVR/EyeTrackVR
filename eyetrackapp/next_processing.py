"""EyeProcessor's NEXT path: runs the mono or shared model on a frame and
turns its output into calibrated gaze, eyelid and eyebrow values.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import logging
import time
from dataclasses import dataclass

import numpy as np

from config import DEFAULT_LID_CLOSE_THRESHOLD, DEFAULT_LID_WIDEN_THRESHOLD, EyeTrackSettingsConfig
from eye import EyeId, EyeInfoOrigin
from next_eye_coupling import brow_sync_range, lid_sync_range
from next_eye_gaze import (
    GAZE_MODE_DOMINANT,
    GAZE_MODE_FUSED,
    GAZE_MODE_INDEPENDENT,
    SquintYHold,
    dominant_eye_from_settings,
    gaze_mode_from_settings,
    select_eye_gaze,
)
from next_model import External_Run_NEXT, variant_from_settings
from next_smartcal import (
    NEXT_SMARTCAL_BROW_TARGET,
    NEXT_SMARTCAL_CAPTURE_WINDOW_S,
    NEXT_SMARTCAL_LID_TARGET,
    next_smartcal_apply,
    next_smartcal_neutral_apply,
)
from next_stereo_model import get_stereo_coordinator
from osc.osc_message import OSCMessage, OSCMessageType
from utils.runtime_state import set_value as _set_runtime_value

logger = logging.getLogger(__name__)


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


def leap_lid_thresholds_for_eye(settings: "EyeTrackSettingsConfig", eye_id: EyeId) -> tuple[float, float]:
    if eye_id == EyeId.LEFT:
        return (
            float(settings.leap_lid_close_threshold_left),
            float(settings.leap_lid_widen_threshold_left),
        )
    return (
        float(settings.leap_lid_close_threshold_right),
        float(settings.leap_lid_widen_threshold_right),
    )


def next_eyelid_tuning_active(settings: "EyeTrackSettingsConfig", eye_id: EyeId) -> bool:
    """True only after the user moves this eye away from NEXT's raw defaults."""
    close_t, widen_t = leap_lid_thresholds_for_eye(settings, eye_id)
    return abs(close_t - DEFAULT_LID_CLOSE_THRESHOLD) > 1e-9 or abs(widen_t - DEFAULT_LID_WIDEN_THRESHOLD) > 1e-9


@dataclass(frozen=True)
class NextExpressionTransform:
    """One eye's mapping from NEXT lid/brow output to the values it sends:
    Smart Calib's neutral anchors (None = not calibrated or turned off) and,
    once Manual Eyelid Tuning is moved off its defaults, the close/widen
    remap. Published to the eye coupler so the peer eye can map this eye too."""

    lid_neutral: float | None = None
    brow_neutral: float | None = None
    lid_thresholds: tuple[float, float] | None = None

    def openness(self, eyelid: float, squeeze: float) -> tuple[float, float]:
        """(calibrated, output) openness. Openness is the lid aperture scaled
        down by squeeze, so a forceful squint reads as more closed."""
        calibrated = next_smartcal_neutral_apply(
            eyelid * max(0.0, 1.0 - squeeze), self.lid_neutral, NEXT_SMARTCAL_LID_TARGET
        )
        if self.lid_thresholds is None:
            return calibrated, calibrated
        return calibrated, remap_leap_lid_openness(calibrated, *self.lid_thresholds)

    def brow(self, eyebrow: float) -> float:
        return next_smartcal_neutral_apply(eyebrow, self.brow_neutral, NEXT_SMARTCAL_BROW_TARGET)


class NextProcessingMixin:
    _next_squint_hold: SquintYHold | None = None  # state of gui_NEXT_squint_y_hold

    def NEXTM(self):
        """NEXT tracking with native single/dual-eye Hybrid inference.

        Hybrid keeps the shared session active even with one camera; missing
        or stale eyes use the trained black sentinel. Legacy variants switch
        between their separate mono and stereo builds. Inference never waits
        for the other camera (see next_stereo_model).

        All downstream handling (flips, smart-cal, recenter, lid remap, OSC) is
        shared by both paths via _next_apply()."""
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

        variant = variant_from_settings(self.settings)
        coord = get_stereo_coordinator(variant, self.settings.gui_use_gpu)
        if coord is not None:
            # The Frame's two cameras deliver each pair together.
            coord.paired = self.settings.gui_setup_mode == "frame"
            # Publish independently; Hybrid can infer immediately from this
            # eye alone, while legacy stereo still needs an active peer.
            coord.submit(self.eye_id, next_frame, self.current_capture_ts)
            if coord.supports_single_eye or coord.peer_active(self.eye_id):
                self._next_mode_changed(True)
                gaze_x, gaze_y, eyebrow, eyelid, squeeze = coord.run(self.eye_id, base_cutoff, base_beta)
                served = coord.served_pass(self.eye_id)
                raw_gaze = coord.raw_gaze()
                extra = {}
                # Per-eye gaze modes (strabismus / amblyopia, see next_eye_gaze):
                # swap in the Hybrid's monocular gaze of the same pass. Recenter
                # then references the dominant eye, so it can't zero a real
                # deviation the way a per-eye recenter would.
                mode = gaze_mode_from_settings(self.settings)
                eye_gaze = getattr(served, "eye_gaze", None)
                if mode != GAZE_MODE_FUSED and eye_gaze is not None:
                    dominant = dominant_eye_from_settings(self.settings)
                    gaze_x, gaze_y = select_eye_gaze(eye_gaze, self.eye_id, mode, dominant)
                    if served.raw_eye_gaze is not None:
                        raw_gaze = select_eye_gaze(served.raw_eye_gaze, self.eye_id, mode, dominant)
                    extra["recenter_gaze"] = select_eye_gaze(eye_gaze, dominant, GAZE_MODE_DOMINANT, dominant)
                self._next_apply(
                    gaze_x,
                    gaze_y,
                    eyebrow,
                    eyelid,
                    squeeze,
                    raw_gaze=raw_gaze,
                    shared=(coord.expression_coupler, served),
                    **extra,
                )
                return

        self._next_mode_changed(False)
        if self.next_runner is None:
            self.next_runner = External_Run_NEXT(variant, self.settings.gui_use_gpu, self.eye_id)
        gaze_x, gaze_y, eyebrow, eyelid, squeeze = self.next_runner.run(next_frame, base_cutoff, base_beta)
        self._next_apply(gaze_x, gaze_y, eyebrow, eyelid, squeeze, raw_gaze=self.next_runner.raw_gaze)

    def _next_mode_changed(self, stereo: bool) -> None:
        """Handle a mono/stereo handover: reset the incoming model's temporal
        history so it can't splice pre-handover frames into its motion stack,
        and log the switch once (not per frame)."""
        if self._next_stereo_engaged is stereo:
            return
        self._next_stereo_engaged = stereo
        self._next_squint_hold = None
        if not stereo and self.next_runner is not None:
            self.next_runner.reset_history()
        logger.info(
            "NEXT %s: %s model",
            "LEFT" if self.eye_id == EyeId.LEFT else "RIGHT",
            "shared Hybrid/stereo" if stereo else "per-eye",
        )

    def _next_dfr_gaze(self, raw_x: float, raw_y: float) -> tuple[float, float]:
        """Foveated-rendering gaze: the model's unfiltered gaze through the same
        Smart Calib transform, flips and recenter offset as the OSC gaze, with no
        median / One-Euro smoothing. Call after the recenter offset is updated."""
        x, y = self._next_calibrate_flip(raw_x, raw_y)
        return x - self._next_recenter_offset_x, y - self._next_recenter_offset_y

    def _next_calibrate_flip(self, raw_x: float, raw_y: float) -> tuple[float, float]:
        """A model-space gaze through this eye's Smart Calib transform and
        user flips, exactly as the OSC gaze gets them (before recenter)."""
        x, y = raw_x, raw_y
        if self._next_smartcal_w is not None and self._next_smartcal_b is not None:
            x, y = next_smartcal_apply(
                self._next_smartcal_w,
                self._next_smartcal_b,
                self._next_smartcal_warp,
                raw_x,
                raw_y,
            )
            # Same native-range bound as the OSC gaze: a strong transform must
            # not throw the foveal region off the display.
            x = float(np.clip(x, -1.0, 1.0))
            y = float(np.clip(y, -1.0, 1.0))
        if self.eye_id == EyeId.RIGHT:
            if self.settings.gui_flip_x_axis_right:
                x = -x
        elif self.settings.gui_flip_x_axis_left:
            x = -x
        if self.settings.gui_flip_y_axis:
            y = -y
        return x, y

    def _next_expression_transform(self) -> NextExpressionTransform:
        calibrate = self.settings.gui_NEXT_calib_lids_brows
        return NextExpressionTransform(
            lid_neutral=self._next_smartcal_lid_neutral if calibrate else None,
            brow_neutral=self._next_smartcal_brow_neutral if calibrate else None,
            lid_thresholds=(
                leap_lid_thresholds_for_eye(self.settings, self.eye_id)
                if next_eyelid_tuning_active(self.settings, self.eye_id)
                else None
            ),
        )

    def _next_couple_eyes(self, shared, transform, eyeopen, eyebrow):
        """Left/right eyelid and eyebrow sync (gui_NEXT_lid_sync / _brow_sync,
        see next_eye_coupling). Compared in output space, after each eye's Smart
        Calib anchor and lid remap: the anchors exist to take out per-eye
        neutral bias, so before them a static offset would eat the threshold
        and the mean would be re-split by the two anchors. Before the closed
        snap, so a coupled blink snaps on both eyes or neither."""
        coupler, served = shared
        coupler.publish(self.eye_id, transform)
        lid_range = lid_sync_range(getattr(self.settings, "gui_NEXT_lid_sync", 0))
        brow_range = brow_sync_range(getattr(self.settings, "gui_NEXT_brow_sync", 0))
        if served is None or (lid_range[1] <= 0.0 and brow_range[1] <= 0.0):
            return eyeopen, eyebrow
        coupled = coupler.couple(self.eye_id, served, lid_range, brow_range)
        return (eyeopen, eyebrow) if coupled is None else coupled

    def _next_squint_y(self, gaze_y, shared):
        """Optional hold on vertical gaze while the lids hide the pupil
        (gui_NEXT_squint_y_hold, see next_eye_gaze.SquintYHold). The shared gaze
        reads both eyes, so unless each eye has its own gaze it stays trusted
        while either eye is open: a wink must not freeze it."""
        if not getattr(self.settings, "gui_NEXT_squint_y_hold", False):
            self._next_squint_hold = None
            return gaze_y
        if self._next_squint_hold is None:
            self._next_squint_hold = SquintYHold()
        openness = self.eyeopen
        if shared is not None and gaze_mode_from_settings(self.settings) != GAZE_MODE_INDEPENDENT:
            peer = shared[0].peer_openness(self.eye_id, shared[1])
            if peer is not None:
                openness = max(openness, peer)
        return self._next_squint_hold.apply(gaze_y, openness, time.perf_counter())

    def _next_apply(self, gaze_x, gaze_y, eyebrow, eyelid, squeeze, raw_gaze=None, shared=None, recenter_gaze=None):
        """Shared NEXT post-processing for the mono and stereo model paths:
        user-configured flips, smart-calibration, recenter, eyelid remap, and
        the OSC enqueue. Inputs preserve the model's native axis orientation.
        ``raw_gaze`` is the same gaze before the runner's filtering; it becomes
        the foveated-rendering gaze (self.dfr_x / dfr_y). ``shared`` is the
        stereo path's (expression coupler, served pass), None on the per-eye
        fallback, which has no paired reading to couple against.
        ``recenter_gaze`` (per-eye gaze modes only) is the model-space gaze the
        recenter offset is taken from instead of this eye's own: the dominant
        eye's, so recentering keeps a real deviation between the eyes."""
        # Raw model gaze, before user-configured flips, in [-1, 1].
        model_gaze_x, model_gaze_y = gaze_x, gaze_y

        # Openness as the model reports it: lid aperture scaled down by squeeze,
        # so a forceful squint reads as more closed. This is the channel the
        # lid calibration and every downstream consumer work on.
        eyeopen_raw = eyelid * max(0.0, 1.0 - squeeze)

        # ── NEXT Smart Calibration ────────────────────────────────────────────
        # Capture and apply calibration in the model's native coordinate space;
        # NEXT does not impose an algorithm-specific Y-axis inversion.
        sc_gaze_x, sc_gaze_y = model_gaze_x, model_gaze_y

        # While a dot is being held by the overlay, accumulate the native gaze
        # so the regression can be fit against the dot's known position.
        # Only within the capture window: the overlay holds each dot 0.5 s
        # after its signal, then the next dot appears and the user follows it;
        # sampling past the hold poisons this dot with the next dot's fixation.
        _sc_dot = self._next_smartcal_active_dot
        if _sc_dot is not None and (
            time.monotonic() - self._next_smartcal_dot_started <= NEXT_SMARTCAL_CAPTURE_WINDOW_S
        ):
            # Lid and brow ride along in the same sample: the user holds a
            # neutral face for the whole sequence, so these are captures of
            # "eyes normally open, brow at rest" (pooled across dots at fit
            # time). Costs nothing extra and needs no second calibration pass.
            # Gaze is captured before the median and One-Euro filters. Their lag
            # would otherwise carry the previous dot's fixation into this short
            # window; the fit's per-dot median already rejects frame noise.
            cap_x, cap_y = raw_gaze if raw_gaze is not None else (sc_gaze_x, sc_gaze_y)
            self._next_smartcal_samples.setdefault(_sc_dot, []).append((cap_x, cap_y, eyeopen_raw, eyebrow))

        # Apply the fitted (warp + affine) transform (smart calib) to map raw
        # model gaze -> calibrated gaze. The arctanh warp un-saturates the
        # model's tanh output so the correction stays gentle instead of slamming
        # to the extremes. Smart Calib is NEXT's only calibration, so a fitted
        # transform always applies.
        if self._next_smartcal_w is not None and self._next_smartcal_b is not None:
            _cal_x, _cal_y = next_smartcal_apply(
                self._next_smartcal_w,
                self._next_smartcal_b,
                self._next_smartcal_warp,
                sc_gaze_x,
                sc_gaze_y,
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

        # Lid/brow smart calibration: re-anchor this user's neutral face onto
        # the target output values (normal-open lid, neutral brow), leaving
        # fully closed and fully open/raised where they are. Captured by the
        # same dot sequence as the gaze fit; a no-op until that has run. The
        # same transform then applies the Manual Eyelid Tuning remap, if any.
        transform = self._next_expression_transform()
        eyeopen_raw, eyeopen = transform.openness(eyelid, squeeze)
        eyebrow = transform.brow(eyebrow)

        # Eyelid openness before the close/widen remap. Publish on the same
        # runtime channel LEAP uses so the settings-menu lid visualizer shows a
        # live indicator for NEXT too; this is what makes the close/widen
        # markers tunable against live tracking when NEXT calibration is
        # enabled. Post lid-calibration, so the markers and the remap below all
        # read the same scale.
        _set_runtime_value(f"raw_lid_{int(self.eye_id)}", float(eyeopen_raw))

        # No classic ellipse path here: NEXT calibrates with Smart Calib only
        # (see eyetrackapp's _next_smartcal_selected), so cal_osc is never fed
        # by this tracker and the recenter path below always runs.

        # Recenter (NEXT, no-save): when the recenter button is pressed,
        # capture the current raw gaze as a fixed offset and subtract it so
        # the output zeroes on the user's current gaze. Unlike calibration
        # recenter, this offset lives only in memory and is never saved.
        # gui_recenter_eyes is shared across both eye processors, so hold it
        # briefly (same 0.2s gate as the calibration path) to let both eyes
        # capture their offset before clearing the flag.
        if self.settings.gui_recenter_eyes:
            if recenter_gaze is None:
                self._next_recenter_offset_x = gaze_x
                self._next_recenter_offset_y = gaze_y
            else:
                self._next_recenter_offset_x, self._next_recenter_offset_y = self._next_calibrate_flip(*recenter_gaze)
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

        if raw_gaze is not None:
            self.dfr_x, self.dfr_y = self._next_dfr_gaze(*raw_gaze)
        else:  # runner without a raw tap: fall back to the OSC gaze
            self.dfr_x, self.dfr_y = gaze_x, gaze_y

        # Fresh installs preserve the model's eyelid output (Smart Calib's
        # neutral anchor aside) until the user changes Manual Eyelid Tuning.
        self.eyeopen = eyeopen
        if shared is not None:
            self.eyeopen, eyebrow = self._next_couple_eyes(shared, transform, self.eyeopen, eyebrow)

        # Snap to fully-closed: NEXT openness near zero is treated as a blink so
        # the eye reports a clean 0.0 instead of jittering just above closed.
        if self.eyeopen < 0.08:
            self.eyeopen = 0.0

        gaze_y = self._next_squint_y(gaze_y, shared)

        dx = gaze_x - self.out_x
        dy = gaze_y - self.out_y
        self.avg_velocity = float(np.sqrt(dx * dx + dy * dy))
        self.out_x = gaze_x
        self.out_y = gaze_y

        self.squeeze = squeeze
        self.next_eyebrow = eyebrow
        self._enqueue_osc_message(
            OSCMessage(
                type=OSCMessageType.EYEBROW_INFO,
                data=(self.eye_id, eyebrow),
            )
        )
        self.current_algorithm = EyeInfoOrigin.NEXT
