"""RANSAC draws its overlay only on the image it shows; the working frame it
searched (in whole-frame mode, current_image_gray_clean itself) stays untouched."""

from types import SimpleNamespace

import cv2
import numpy as np

import ransac
from eye import EyeId


def test_ransac_leaves_the_clean_frame_unmodified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img = np.full((80, 80), 220, dtype=np.uint8)
    cv2.ellipse(img, (40, 40), (14, 8), 0, 0, 360, 0, -1)
    clean = img.copy()
    sphere = {"center": (40.0, 40.0), "axes": (30.0, 30.0), "angle": 0.0}
    proc = SimpleNamespace(
        eye_id=EyeId.RIGHT,
        rawx=40,
        rawy=40,
        radius=10,
        current_image_gray=img.copy(),
        current_image_gray_clean=clean,
        settings=SimpleNamespace(gui_thresh_add=20, gui_RANSACBLINK=False),
        failed=0,
        detector_3d=SimpleNamespace(
            update_and_detect=lambda *_: {
                "ellipse": {"center": (42.0, 41.0)},
                "projected_sphere": sphere,
                "diameter_3d": 3.0,
            }
        ),
        last_projected_sphere={},
        current_frame_number=1,
        current_fps=60,
        ran_blink_check_for_file=False,
        blink_list=[],
    )
    monkeypatch.setattr(ransac, "fit_rotated_ellipse_ransac", lambda data, rng: (40.0, 40.0, 14.0, 8.0, 0.0))

    cx, cy, *_ = ransac.RANSAC3D(proc, False)

    assert (cx, cy) == (40.0, 40.0)
    assert np.array_equal(clean, img)  # nothing drawn onto the searched frame
    # The shown image is a copy of the working image with the eyeball outline on it.
    assert proc.current_image_gray is not clean
    assert not np.array_equal(proc.current_image_gray, img)
