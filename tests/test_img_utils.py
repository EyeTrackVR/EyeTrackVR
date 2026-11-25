"""Image helpers (utils.img_utils): crops that run past the frame, the
circular crop, and the picture NEXT sees of each eye (its half of a Bigscreen
frame, turned upright in quarter turns)."""

import numpy as np
import pytest

from utils.img_utils import circle_crop, eye_frame, quarter_turn, safe_crop


def _numbered(h=4, w=6):
    return np.arange(h * w, dtype=np.uint8).reshape(h, w)


def test_safe_crop_clips_a_window_that_runs_past_the_frame():
    img = _numbered()
    out = safe_crop(img, 4, -2, 9, 2)
    np.testing.assert_array_equal(out, img[0:2, 4:6])
    out[0, 0] = 255
    assert img[0, 4] != 255  # a copy: drawing on the crop leaves the frame alone


def test_safe_crop_keepsize_returns_the_requested_size():
    out = safe_crop(_numbered(), 4, -2, 9, 2, keepsize=True)
    assert out.shape == (4, 5)


def test_circle_crop_fills_outside_the_circle_with_the_average():
    img = np.zeros((60, 60), dtype=np.uint8)
    img[:, 30:] = 200
    out = circle_crop(img, 30, 30, 12)
    assert out[30, 35] == 200 and out[30, 25] == 0  # inside: untouched
    corner = out[0, 0]
    assert out[59, 59] == corner and 90 <= corner <= 110  # outside: the frame's average


def test_circle_crop_keeps_a_minimum_radius():
    img = np.zeros((60, 60), dtype=np.uint8)
    img[30, 38] = 255  # 8 px from the centre
    assert circle_crop(img, 30, 30, 2)[30, 38] == 255


@pytest.mark.parametrize(
    "angle, turn",
    [(0, 0), (90, 90), (-90, 270), (135, 180), (269, 270), (359, 0), ("90", 90), (None, 0), ("x", 0), (1e400, 0)],
)
def test_quarter_turn_rounds_any_rotation(angle, turn):
    assert quarter_turn(angle) == turn


@pytest.mark.parametrize("left, half", [(True, slice(0, 3)), (False, slice(3, 6))])
def test_bigscreen_frames_are_split_between_the_eyes(left, half):
    frame = _numbered()
    np.testing.assert_array_equal(eye_frame(frame, "bigscreen", left, 0), frame[:, half])
    np.testing.assert_array_equal(eye_frame(frame, "standard", left, 0), frame)


def test_eye_frame_turns_counter_clockwise_like_the_classical_trackers():
    frame = _numbered()
    turned = eye_frame(frame, "standard", True, 90)
    assert turned.shape == (6, 4)
    assert turned[0, 0] == frame[0, -1]  # the top-right corner comes to the top left
    np.testing.assert_array_equal(eye_frame(frame, "standard", True, 180), frame[::-1, ::-1])
