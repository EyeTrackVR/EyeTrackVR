"""RANSAC3D tracker: failed fits, the ellipse axes it reports, pye3d
timestamps, what it draws on, and the per-eye blink statistics file
(location, legacy fallback, unwritable folder, percentile refresh)."""

import logging
import os
from types import SimpleNamespace

import cv2
import numpy as np

import ransac
from eye import EyeId
from utils import user_data


def _processor(eye_id, *, blink=True, detect=None):
    """An eye processor looking at a dark pupil ellipse at (40, 40) next to a
    second, differently shaped dark blob."""
    img = np.full((80, 80), 220, dtype=np.uint8)
    cv2.ellipse(img, (40, 40), (14, 8), 0, 0, 360, 0, -1)
    cv2.rectangle(img, (4, 4), (18, 34), 0, -1)
    if detect is None:

        def detect(*_):
            raise KeyError("x")

    return SimpleNamespace(
        eye_id=eye_id,
        rawx=40,
        rawy=40,
        radius=10,
        current_image_gray=img.copy(),
        current_image_gray_clean=img.copy(),
        settings=SimpleNamespace(gui_thresh_add=20, gui_RANSACBLINK=blink),
        failed=0,
        detector_3d=SimpleNamespace(update_and_detect=detect),
        last_projected_sphere={},
        current_frame_number=1,
        current_fps=60,
        ran_blink_check_for_file=True,
        blink_list=[],
    )


def _fit_at(monkeypatch, *ellipse):
    monkeypatch.setattr(ransac, "fit_rotated_ellipse_ransac", lambda data, rng: ellipse)


# ── tracking output ──────────────────────────────────────────────────────────


def test_failed_fit_keeps_previous_point_and_lets_the_next_tracker_run(monkeypatch):
    monkeypatch.setattr(ransac, "fit_rotated_ellipse_ransac", lambda data, rng: None)
    proc = _processor(EyeId.LEFT, blink=False)
    proc.rawx, proc.rawy = 33, 21

    cx, cy, *_ = ransac.RANSAC3D(proc, False)

    # (0, 0) here became a corner gaze for the frame.
    assert (cx, cy) == (33, 21)
    assert proc.failed == 1


def test_ransac_returns_ellipse_axes_and_loads_own_blink_file(monkeypatch):
    with open(ransac.ransac_blink_file_path(EyeId.LEFT), "w") as f:
        f.write("0.1\n0.2\n")
    with open(ransac.ransac_blink_file_path(EyeId.RIGHT), "w") as f:
        f.write("0.9\n")
    _fit_at(monkeypatch, 40.0, 40.0, 7.5, 4.25, 0.0)

    proc = _processor(EyeId.LEFT)
    *_, w, h = ransac.RANSAC3D(proc, False)

    assert (w, h) == (7.5, 4.25)
    assert proc.blink_list[:2] == [0.1, 0.2]
    assert 0.9 not in proc.blink_list


def test_pye3d_gets_the_capture_timestamp(monkeypatch):
    _fit_at(monkeypatch, 40.0, 40.0, 7.0, 4.0, 0.0)
    seen = []
    proc = _processor(EyeId.LEFT, blink=False, detect=lambda result, _img: seen.append(result["timestamp"]) or {})
    proc.current_fps = 0.0  # first frame: the fps average is not known yet
    proc.current_capture_ts = 12.5

    ransac.RANSAC3D(proc, False)

    assert seen == [12.5]


def test_ransac_leaves_the_clean_frame_unmodified(monkeypatch):
    """It draws only on the image it shows; the working frame it searched (in
    whole-frame mode, current_image_gray_clean itself) stays untouched."""
    sphere = {"center": (40.0, 40.0), "axes": (30.0, 30.0), "angle": 0.0}
    detected = {"ellipse": {"center": (42.0, 41.0)}, "projected_sphere": sphere, "diameter_3d": 3.0}
    proc = _processor(EyeId.RIGHT, blink=False, detect=lambda *_: detected)
    img = proc.current_image_gray.copy()
    clean = proc.current_image_gray_clean
    proc.ran_blink_check_for_file = False
    _fit_at(monkeypatch, 40.0, 40.0, 14.0, 8.0, 0.0)

    cx, cy, *_ = ransac.RANSAC3D(proc, False)

    assert (cx, cy) == (40.0, 40.0)
    assert np.array_equal(clean, img)  # nothing drawn onto the searched frame
    # The shown image is a copy of the working image with the eyeball outline on it.
    assert proc.current_image_gray is not clean
    assert not np.array_equal(proc.current_image_gray, img)


# ── blink statistics file ────────────────────────────────────────────────────


def test_blink_stats_are_saved_in_the_user_data_folder(isolated_user_data):
    proc = _processor(EyeId.RIGHT)
    proc.blink_list = [0.01] * 10000
    proc.ran_blink_check_for_file = False

    ransac.RANSAC3D(proc, False)

    saved = isolated_user_data / "RANSAC_BLINK_RIGHT.cfg"
    assert len(saved.read_text().splitlines()) == 10000
    assert not os.path.exists("RANSAC_BLINK_RIGHT.cfg")  # not the working directory


def test_unwritable_blink_stats_folder_does_not_stop_tracking(isolated_user_data, monkeypatch, caplog):
    monkeypatch.setattr(user_data, "_USER_DATA_DIR", str(isolated_user_data / "missing"))
    proc = _processor(EyeId.RIGHT)
    proc.blink_list = [0.01] * 10000
    proc.ran_blink_check_for_file = False

    with caplog.at_level(logging.WARNING, logger="ransac"):
        for _ in range(3):
            ransac.RANSAC3D(proc, False)

    assert sum("RANSAC blink" in r.getMessage() for r in caplog.records) == 1


def test_blink_stats_from_older_builds_are_still_loaded():
    # Builds before the user data folder wrote to the working directory.
    with open("RANSAC_BLINK_LEFT.cfg", "w") as f:
        f.write("0.3\n0.4\n")
    proc = _processor(EyeId.LEFT)

    ransac.RANSAC3D(proc, False)

    assert proc.blink_list[:2] == [0.3, 0.4]


def test_ransac_blink_percentile_computed_once_per_frame(count_calls):
    calls = count_calls(ransac.np, "percentile")
    proc = _processor(EyeId.RIGHT)
    ransac.RANSAC3D(proc, False)
    assert len(proc.blink_list) >= 2  # several contours were sampled...
    assert len(calls) == 1  # ...but the percentile ran once

    # Frozen list (calibration complete): no recomputation at all.
    proc.blink_list = [0.01] * 10001
    proc._ransac_blink_p92 = None
    ransac.RANSAC3D(proc, False)
    ransac.RANSAC3D(proc, False)
    assert len(calls) == 2


def test_blink_percentile_is_not_recomputed_every_frame(count_calls):
    calls = count_calls(ransac.np, "percentile")
    proc = _processor(EyeId.LEFT)
    proc.ran_blink_check_for_file = False
    proc.blink_list = [0.01] * 5000  # a large, still-growing window

    for _ in range(30):
        ransac.RANSAC3D(proc, False)

    assert len(calls) <= 4
