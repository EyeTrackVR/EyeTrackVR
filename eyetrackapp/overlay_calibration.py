"""Classic calibrations driven by the in-headset overlay: centre recenter,
3D points and the ellipse spiral, plus the live gaze preview.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import logging
import socket
import struct
import threading
import time

from calibration_state import var
from utils import gaze_preview
from utils.async_call import Async
from utils.misc_utils import PlaySound, SND_ASYNC, SND_FILENAME, resource_path
from utils.overlay_launch import OverlayExited, OverlaySession

logger = logging.getLogger(__name__)


@Async
def center_overlay_calibrate(self):
    if var.overlay_active:
        return
    var.overlay_active = True
    try:
        with OverlaySession("center") as overlay:
            overlay.recv()  # the overlay's only signal: the centre dot was shown
            overlay.finish()
    except (OSError, struct.error) as e:
        logger.warning(
            "Center-overlay calibration failed (%s). Make sure SteamVR is running.",
            e,
        )
    finally:
        self.settings.gui_recenter_eyes = False
        self.calibration_start_time = None
        var.overlay_active = False


@Async
def overlay_calibrate_3d(self):
    if var.overlay_active:
        return
    var.overlay_active = True
    try:
        with OverlaySession() as overlay:
            while var.overlay_active:
                message = struct.unpack("!l", overlay.recv())[0]
                self.settings.gui_recenter_eyes = False
                self.settings.grab_3d_point = True
                logger.debug("3D overlay calibration message: %s", message)
                if message == 9:
                    overlay.finish()
                    break
    except (OSError, struct.error) as e:
        logger.warning(
            "3D calibration overlay error (%s). Make sure SteamVR is running.",
            e,
        )
    finally:
        self.settings.gui_recenter_eyes = False
        var.overlay_active = False


_gaze_preview_stop = threading.Event()


def stop_gaze_preview() -> None:
    _gaze_preview_stop.set()


@Async
def gaze_preview_overlay(settings) -> None:
    """Show the output gaze live in the headset until stopped or the overlay
    is closed. The overlay signals 255 once it is up; samples go to it only
    from then on."""
    if var.overlay_active:
        return
    var.overlay_active = True
    _gaze_preview_stop.clear()
    gaze_preview.set_running(True)
    stream = gaze_preview.GazePreviewStream(settings)
    try:
        with OverlaySession("preview", timeout=30.0) as overlay:
            while struct.unpack(">i", overlay.recv(16)[:4])[0] != gaze_preview.SIG_READY:
                pass
            from localization import tr

            stream.send_text(tr("tracking.preview_panel"))
            gaze_preview.set_active(stream)
            # The overlay sends nothing more; it runs until stopped or closed.
            while not _gaze_preview_stop.wait(0.25):
                code = overlay.process.poll()
                if code is not None:
                    raise OverlayExited(f"calibration overlay exited with code {code}")
            gaze_preview.set_active(None)
            stream.quit()
            overlay.finish()
    except (OSError, struct.error) as e:
        logger.warning("Gaze preview overlay stopped (%s). Make sure SteamVR is running.", e)
    finally:
        gaze_preview.set_active(None)
        gaze_preview.set_running(False)
        stream.close()
        var.overlay_active = False


def _mark_next_classic_calibration_active(eye_processor) -> None:
    """Record whether the latest ellipse fit belongs to NEXT or a pixel tracker."""
    eye_processor.config.next_classic_calibration_active = bool(getattr(eye_processor, "_next_active", False))


# ── Overlay ellipse calibration (port 2112) ───────────────────────────────────
#
# The overlay animates the dot in a shrinking spiral and sends two signals:
#   int32(0) → start continuous per-frame sampling
#   int32(9) → stop sampling, fit and save the ellipse
#
# cal_osc accumulates raw cx/cy into CalibrationEllipse every frame while
# _ellipse_collect_active is set.  The std-deviation fit benefits from many
# uniformly distributed samples, so continuous collection is better than
# per-point IQR grabs.

# The overlay's opening orbit: anything shorter hasn't seen the full gaze range,
# so a fit from it is worse than the calibration it would replace.
ELLIPSE_PARTIAL_MIN_S = 9.0


@Async
def overlay_ellipse_calibrate(eye_processors: list, settings, baseconfig) -> None:
    """
    Launch the overlay in ellipse-calibration (spiral) mode and drive classic
    CalibrationEllipse per eye via continuous frame sampling.
    """
    if var.overlay_active:
        return
    var.overlay_active = True
    try:
        with OverlaySession("ellipse") as overlay:
            # Reset calibration samples so this run starts fresh
            for ep in eye_processors:
                ep.cal.xs = []
                ep.cal.ys = []
                ep.cal.fitted = False

            sampling_started = None
            while var.overlay_active:
                try:
                    data = overlay.recv()
                except (socket.timeout, OverlayExited) as e:
                    logger.warning("Overlay ellipse calibration ended early: %s", e)
                    # Save a partial fit if enough of the path was sampled before
                    # the overlay stopped. This handles the case where signal 0
                    # was received and the spiral ran but signal 9 never arrived.
                    _enough_sampled = (
                        sampling_started is not None and time.monotonic() - sampling_started >= ELLIPSE_PARTIAL_MIN_S
                    )
                    _saved_partial = False
                    for ep in eye_processors:
                        ep._ellipse_collect_active = False
                        if _enough_sampled and len(ep.cal.xs) >= 2:
                            evecs, axes = ep.cal.fit_ellipse()
                            if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
                                ep.config.calib_evecs = list(evecs.tolist() if hasattr(evecs, "tolist") else evecs)
                                ep.config.calib_axes = list(axes.tolist() if hasattr(axes, "tolist") else axes)
                                if ep.cal.center is not None:
                                    ep.config.calib_XOFF = float(ep.cal.center[0])
                                    ep.config.calib_YOFF = float(ep.cal.center[1])
                                _mark_next_classic_calibration_active(ep)
                                ep.baseconfig.save()
                                logger.info(
                                    "Ellipse cal: partial fit saved from %d samples (overlay stopped)",
                                    len(ep.cal.xs),
                                )
                                _saved_partial = True
                    if _saved_partial:
                        settings.calib_mode = "classic"
                        PlaySound(resource_path("assets/audio/completed.wav"), SND_FILENAME | SND_ASYNC)
                    break
                if not data or len(data) < 4:
                    continue

                signal = struct.unpack("!l", data)[0]

                if signal == 0:
                    # Start continuous per-frame sampling
                    logger.debug("Overlay ellipse calibration: sampling started")
                    sampling_started = time.monotonic()
                    for ep in eye_processors:
                        ep._ellipse_collect_active = True

                elif signal == 9:
                    # Stop sampling, fit, and save
                    for ep in eye_processors:
                        ep._ellipse_collect_active = False
                        evecs, axes = ep.cal.fit_ellipse()
                        if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
                            ep.config.calib_evecs = list(evecs.tolist() if hasattr(evecs, "tolist") else evecs)
                            ep.config.calib_axes = list(axes.tolist() if hasattr(axes, "tolist") else axes)
                            if ep.cal.center is not None:
                                ep.config.calib_XOFF = float(ep.cal.center[0])
                                ep.config.calib_YOFF = float(ep.cal.center[1])
                            _mark_next_classic_calibration_active(ep)
                            ep.baseconfig.save()
                            logger.info("Ellipse cal: fitted from %d samples", len(ep.cal.xs))
                    settings.calib_mode = "classic"
                    PlaySound(resource_path("assets/audio/completed.wav"), SND_FILENAME | SND_ASYNC)
                    overlay.finish()
                    break

    except (OSError, struct.error) as e:
        logger.warning("Ellipse overlay calibration error: %s", e)
    finally:
        # Always clear collect flag so cal_osc doesn't keep sampling
        for ep in eye_processors:
            ep._ellipse_collect_active = False
        var.overlay_active = False
