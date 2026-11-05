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
    falloff_latch = False
    single_eye = True
    left_enb = 0
    right_enb = 0
    eye_wait = 10
    left_calib = False
    right_calib = False
    completed_3d_calib = 0
