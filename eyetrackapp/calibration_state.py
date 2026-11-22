"""State shared by the calibration code. Eye threads and the overlay
calibrations both read and write it.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""


class var:
    # Per-eye velocity state. Both eye threads call cal_osc concurrently, so
    # everything that's read across eyes (velocity, last-seen position) must
    # be stored per side; otherwise eye B's "delta from previous frame"
    # computation silently uses eye A's last position as the baseline.
    # Keyed by EyeId.LEFT / EyeId.RIGHT.
    past_xy: dict = {}
    last_t: dict = {}
    velocity_rolling: dict = {}
    kp_past: dict = {}
    kp_rolling: dict = {}
    r_eye_x = 0.0
    l_eye_x = 0.0
    left_y = 0.0
    right_y = 0.0
    l_eye_velocity = 0.0
    r_eye_velocity = 0.0
    l_keypoint_noise = 0.0
    r_keypoint_noise = 0.0
    l_eye_openness = 1.0
    r_eye_openness = 1.0
    overlay_active = False
    # The run that has the overlay and can be asked to stop: OVERLAY_RUN_*.
    # None when the overlay is free or the run that has it stops another way.
    overlay_run = None
    # Asks that run to stop. It stays the active one until its overlay is
    # gone, so this is not the same as overlay_active turning false.
    overlay_stop_requested = False
    falloff_latch = False
    single_eye = True
    left_enb = 0
    right_enb = 0
    eye_wait = 10
    left_calib = False
    right_calib = False
    completed_3d_calib = 0


OVERLAY_RUN_SMARTCAL = "smartcal"
OVERLAY_RUN_RANGE_CHECK = "range_check"


def begin_overlay_run(run: str) -> bool:
    """Take the overlay for ``run``. False when something else has it."""
    if var.overlay_active:
        return False
    var.overlay_active = True
    var.overlay_stop_requested = False
    var.overlay_run = run
    return True


def end_overlay_run() -> None:
    var.overlay_run = None
    var.overlay_stop_requested = False
    var.overlay_active = False


def request_overlay_stop() -> None:
    """Ask the run that has the overlay to stop (see var.overlay_run)."""
    if var.overlay_run is not None:
        var.overlay_stop_requested = True


def overlay_keep_going() -> bool:
    """False once the run that has the overlay was asked to stop."""
    return var.overlay_active and not var.overlay_stop_requested
