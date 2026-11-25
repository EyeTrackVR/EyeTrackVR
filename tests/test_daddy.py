"""DADDY's heatmap decoding (daddy.get_final_preds): the landmark is read off
each heatmap to sub-pixel precision and scaled to the camera image."""

import numpy as np
import pytest

import daddy

# daddy.taylor solves its 2x2 system with np.matrix, which numpy discourages.
pytestmark = pytest.mark.filterwarnings("ignore:the matrix subclass:PendingDeprecationWarning")


def _heatmaps(*peaks, sigma=2.0):
    yy, xx = np.mgrid[0 : daddy.heatmap_size, 0 : daddy.heatmap_size]
    maps = [np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2)) for x, y in peaks]
    return np.array(maps, dtype=np.float64)[None]


@pytest.mark.parametrize("peak", [(20.3, 30.6), (10.0, 10.0), (35.7, 12.2)])
def test_landmarks_are_found_between_heatmap_pixels(peak):
    preds, maxvals = daddy.get_final_preds(_heatmaps(peak), 192)

    # Scaled from the 48 px heatmap to the 192 px image, within a tenth of a heatmap pixel.
    np.testing.assert_allclose(preds[0, 0] / 192 * daddy.heatmap_size, peak, atol=0.1)
    assert 0.9 < maxvals[0, 0, 0] <= 1.0


def test_each_landmark_has_its_own_heatmap_and_image_size_per_axis():
    preds, _ = daddy.get_final_preds(_heatmaps((12.0, 24.0), (36.0, 6.0)), np.array([160, 120]))
    np.testing.assert_allclose(preds[0], [[40.0, 60.0], [120.0, 15.0]], atol=0.5)


def test_an_empty_heatmap_reads_as_the_origin_not_a_random_pixel():
    coords, maxvals = daddy.get_max_preds(np.zeros((1, 2, daddy.heatmap_size, daddy.heatmap_size)))
    assert not coords.any() and not maxvals.any()
