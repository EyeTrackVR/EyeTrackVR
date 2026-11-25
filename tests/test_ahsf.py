"""AHSF (ahsf.PupilDetectorHaar): finds a dark pupil on a bright eye, and the
fine refinement picks the largest small blob, never the background."""

import cv2
import numpy as np
import pytest

from ahsf import PupilDetectorHaar


@pytest.mark.parametrize("centre", [(60, 50), (130, 90), (40, 110)])
def test_finds_a_dark_pupil_wherever_it_is(centre):
    img = np.full((160, 200), 190, dtype=np.uint8)
    cv2.circle(img, centre, 14, 15, -1)
    original = img.copy()

    preview, working, x, y, radius = PupilDetectorHaar().detect_etvr(img)

    assert (x, y) == pytest.approx(centre, abs=1.0)
    assert 12 <= radius <= 20  # the 14 px pupil, not the whole frame
    assert np.array_equal(img, original)  # the camera frame is left as it was
    assert preview.shape == img.shape and not np.array_equal(preview, img)  # the preview shows the result


def test_rejects_a_frame_that_is_not_8_bit():
    with pytest.raises(TypeError):
        PupilDetectorHaar().detect(np.zeros((40, 40), dtype=np.float32))


def test_fine_detection_picks_largest_small_blob():
    img = np.full((60, 60), 200, dtype=np.uint8)
    # Both blobs stay under 4% of the patch after dilation and miss its centre,
    # so the refinement has to fall back to the biggest one (label 1 here).
    cv2.rectangle(img, (12, 12), (16, 16), 10, -1)
    cv2.rectangle(img, (44, 44), (46, 46), 10, -1)
    det = PupilDetectorHaar()
    det._img_boundary = (0, 0, 60, 60)
    det.pupil_rect_coarse = (5, 5, 50, 50)
    det.center_coarse = (30.0, 30.0)
    det.mu_inner = 50

    det._fine_detection_fast(img)

    x, y, w, h = det.pupil_rect_fine
    assert x <= 12 and y <= 12 and x + w >= 17 and y + h >= 17
    assert w < 20 and h < 20  # the blob, not the whole patch
