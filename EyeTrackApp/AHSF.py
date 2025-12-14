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

Adaptive Haar Surround Feature: Summer
Algorithm App Implementations and Tweaks By: Prohurtz

Copyright (c) 2025 EyeTrackVR <3

LICENSE: Summer Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""
from __future__ import annotations
import cv2
import numpy as np
from typing import Tuple, Optional
import numba


@numba.njit(cache=True, fastmath=True)
def _get_integral_sum(ii: np.ndarray, x: int, y: int, w: int, h: int) -> float:
    return ii[y + h, x + w] - ii[y, x + w] - ii[y + h, x] + ii[y, x]


@numba.njit(cache=True, fastmath=True)
def _evaluate_single_position(ii: np.ndarray, x: int, y: int, width: int, height: int,
                              ratio_outer: float, kf: float, use_square: bool,
                              bx: int, by: int, bw: int, bh: int) -> Tuple[float, int, int, int, int, float, float]:
    if use_square:
        ow = oh = int(max(width, height) * ratio_outer)
    else:
        ow = int(width * ratio_outer)
        oh = int(height * ratio_outer)

    cx = x + width // 2
    cy = y + height // 2
    ox = int(cx - ow / 2)
    oy = int(cy - oh / 2)

    ox = max(bx, ox)
    oy = max(by, oy)
    ow = min(ox + ow, bx + bw) - ox
    oh = min(oy + oh, by + bh) - oy

    if ow <= 0 or oh <= 0:
        return -255.0, ox, oy, max(0, ow), max(0, oh), 0.0, 0.0

    inner_area = width * height
    outer_area = ow * oh - inner_area

    if outer_area <= 0:
        return -255.0, ox, oy, max(0, ow), max(0, oh), 0.0, 0.0

    inner_sum = _get_integral_sum(ii, x, y, width, height)
    outer_sum = _get_integral_sum(ii, ox, oy, ow, oh)

    mu_in = inner_sum / inner_area
    mu_out = (outer_sum - inner_sum) / outer_area

    f_val = mu_out - kf * mu_in

    return f_val, ox, oy, max(0, ow), max(0, oh), mu_in, mu_out


@numba.njit(cache=True)
def _coarse_search(ii: np.ndarray,
                   roi_x: int, roi_y: int, roi_w: int, roi_h: int,
                   width_min: int, width_max: int, wh_step: int, xy_step: int,
                   ratio_outer: float, kf: float, use_square: bool,
                   bx: int, by: int, bw: int, bh: int):
    best_f = -255
    best_pupil = (0, 0, 0, 0)
    best_outer = (0, 0, 0, 0)
    best_mu_in = best_mu_out = 0.0

    for width in range(width_min, width_max + 1, wh_step):
        height = width

        xmax = roi_x + roi_w - width
        ymax = roi_y + roi_h - height

        if xmax < roi_x or ymax < roi_y:
            continue

        for x in range(roi_x, xmax + 1, xy_step):
            for y in range(roi_y, ymax + 1, xy_step):
                f_val, ox, oy, ow, oh, mu_in, mu_out = _evaluate_single_position(
                    ii, x, y, width, height, ratio_outer, kf, use_square, bx, by, bw, bh)

                if f_val > best_f:
                    best_f = f_val
                    best_pupil = (x, y, width, height)
                    best_outer = (ox, oy, ow, oh)
                    best_mu_in = mu_in
                    best_mu_out = mu_out

    return best_f, best_pupil, best_outer, best_mu_in, best_mu_out


class PupilDetectorHaar:

    def __init__(self,
                 ratio_outer: float = 1.4,
                 kf: float = 1.5,
                 use_square_haar: bool = False,
                 use_init_rect: bool = False,
                 init_rect: Optional[Tuple[int, int, int, int]] = None,
                 target_resolution: Tuple[int, int] = (320, 240),
                 width_min: int = 31,
                 width_max: int = 120,
                 wh_step: int = 2,
                 xy_step: int = 2):

        self.ratio_outer = ratio_outer
        self.kf = kf
        self.use_square_haar = use_square_haar
        self.use_init_rect = use_init_rect
        self.init_rect = (0, 0, 0, 0) if init_rect is None else init_rect
        self.target_resolution = target_resolution

        self.width_min = width_min
        self.width_max = width_max
        self.wh_step = wh_step
        self.xy_step = xy_step

        self.frame_num = 0
        self.mu_inner = 50
        self.mu_outer = 200
        self.mu_inner0 = 50
        self.mu_outer0 = 200

        self.pupil_rect_coarse = (0, 0, 0, 0)
        self.outer_rect_coarse = (0, 0, 0, 0)
        self.max_response_coarse = -255
        self.center_coarse = (0.0, 0.0)

        self.pupil_rect_fine = (0, 0, 0, 0)
        self.center_fine = (0.0, 0.0)

        self._ratio_down = 1.0
        self._img_boundary = (0, 0, 0, 0)
        self._init_rect_down = (0, 0, 0, 0)

    def detect_etvr(self, img_gray) -> Tuple[np.ndarray, np.ndarray, float, float, float]:
        """
        Runs the full detection and returns a visualized image and ETVR-specific data.

        Args:
            img_gray: The input grayscale image (uint8).

        Returns:
            A tuple containing:
            - vis_img (np.ndarray): The original image with visualizations drawn on it (BGR).
            - resize_img (np.ndarray): The downscaled image used for processing.
            - rawx (float): The final X coordinate of the pupil center.
            - rawy (float): The final Y coordinate of the pupil center.
            - radius (float): The calculated average radius of the final pupil rectangle.
        """

        # 1. Run the main detection.
        # This populates all internal class attributes:
        # self.pupil_rect_fine, self.center_fine,
        # self.pupil_rect_coarse, self.outer_rect_coarse,
        # and self._ratio_down. It also increments self.frame_num.
        self.detect(img_gray)

        # 2. Get the downscaled image.
        # We call _preprocess again. This is slightly inefficient but
        # avoids refactoring detect(). It will correctly use the
        # self.frame_num that detect() just set.
        resize_img = img_gray

        # 3. Get the final data from class attributes
        rawx, rawy = self.center_fine
        px, py, pw, ph = self.pupil_rect_fine

        # Calculate an average radius from the fine rect's width and height
        radius = (pw + ph) / 4.0

        # 4. Create the visualization image
        # Convert the original grayscale image to BGR for color drawing
        vis_img = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)

        # Draw coarse pupil rect (Green)
        x, y, w, h = self.pupil_rect_coarse
        if w > 0 and h > 0:
            cv2.rectangle(vis_img, (x, y), (x + w, y + h), (0, 255, 0), 1)

        # Draw coarse outer rect (Yellow)
        x, y, w, h = self.outer_rect_coarse
        if w > 0 and h > 0:
            cv2.rectangle(vis_img, (x, y), (x + w, y + h), (0, 255, 255), 1)

        # Draw fine pupil rect (Red)
        x, y, w, h = self.pupil_rect_fine
        if w > 0 and h > 0:
            cv2.rectangle(vis_img, (x, y), (x + w, y + h), (0, 0, 255), 1)

        # Draw fine center (Red)
        cv2.circle(vis_img, (int(round(rawx)), int(round(rawy))), 3, (0, 0, 255), -1)

        vis_img = cv2.cvtColor(vis_img, cv2.COLOR_BGR2GRAY)
        # 5. Return the requested 5-tuple
        return vis_img, resize_img, rawx, rawy, radius

    def detect(self, img_gray: np.ndarray) -> Tuple[Tuple[int, int, int, int], Tuple[float, float]]:
        if img_gray.dtype != np.uint8:
            raise TypeError("img_gray must be uint8 [0,255]")

        self.frame_num += 1
        img_down = self._preprocess(img_gray)
        self._coarse_detection(img_down)
        self._fine_detection_fast(img_down)
        self._postprocess()

        return self.pupil_rect_fine, self.center_fine

    def _preprocess(self, img_gray: np.ndarray) -> np.ndarray:
        h, w = img_gray.shape
        self._ratio_down = max(w / self.target_resolution[0],
                               h / self.target_resolution[1], 1.0)
        new_w = int(round(w / self._ratio_down))
        new_h = int(round(h / self._ratio_down))

        img_down = cv2.resize(img_gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
        self._img_boundary = (0, 0, new_w, new_h)

        if self.use_init_rect and self.frame_num == 1:
            x, y, rw, rh = self.init_rect
            region = img_gray[y:y + rh, x:x + rw]
            self.mu_inner0 = np.percentile(region, 25)
            self.mu_outer0 = np.percentile(region, 75)

            if self.mu_outer0 - self.mu_inner0 > 30:
                tau = self.mu_outer0
            else:
                tau = self.mu_inner0 + 30
            img_down = np.minimum(img_down, tau).astype(np.uint8)

        return img_down

    def _initial_search_range(self, img_down: np.ndarray) -> Tuple[int, int, int, int]:
        h, w = img_down.shape
        margin = h // 10 // 2
        full = (margin, margin, w - 2 * margin, h - 2 * margin)

        if not self.use_init_rect:
            self.roi = full
            return

        self._init_rect_down = tuple(int(x / self._ratio_down) for x in self.init_rect)
        ix, iy, iw, ih = self._init_rect_down

        rx, ry, rw, rh = full
        enlarge = 35
        if ix < enlarge:                rx, rw = 0, w
        if iy < enlarge:                ry, rh = 0, h
        if ix + iw > w - enlarge:         rx, rw = 0, w
        if iy + ih > h - enlarge:         ry, rh = 0, h
        self.roi = (rx, ry, rw, rh)

        self.width_min = max(int(iw * 1.0), 24)
        self.width_max = min(int(iw * 1.5), 120)

    def _coarse_detection(self, img_down: np.ndarray) -> None:
        self._initial_search_range(img_down)
        roi_x, roi_y, roi_w, roi_h = self.roi

        # Build integral image
        ii = cv2.integral(img_down, sdepth=cv2.CV_32S)

        # Optimized search
        bx, by, bw, bh = self._img_boundary
        best_f, best_pupil, best_outer, best_mu_in, best_mu_out = _coarse_search(
            ii, roi_x, roi_y, roi_w, roi_h,
            self.width_min, self.width_max, self.wh_step, self.xy_step,
            self.ratio_outer, self.kf, self.use_square_haar,
            bx, by, bw, bh
        )

        self.pupil_rect_coarse = best_pupil
        self.outer_rect_coarse = best_outer
        self.max_response_coarse = best_f
        self.mu_inner = best_mu_in
        self.mu_outer = best_mu_out

        px, py, pw, ph = best_pupil
        self.center_coarse = (px + pw / 2, py + ph / 2)

    def _fine_detection_fast(self, img_down: np.ndarray) -> None:
        px, py, pw, ph = self.pupil_rect_coarse
        expand = 1.42

        cx, cy = px + pw // 2, py + ph // 2
        ew, eh = int(pw * expand), int(ph * expand)
        ex, ey = cx - ew // 2, cy - eh // 2

        # Clip to boundary
        bx, by, bw, bh = self._img_boundary
        ex = max(bx, ex)
        ey = max(by, ey)
        ew = min(ex + ew, bx + bw) - ex
        eh = min(ey + eh, by + bh) - ey

        if ew <= 0 or eh <= 0:
            self.pupil_rect_fine = self.pupil_rect_coarse
            self.center_fine = self.center_coarse
            return

        patch = img_down[ey:ey + eh, ex:ex + ew]

        _, bw = cv2.threshold(patch, int(self.mu_inner), 255, cv2.THRESH_BINARY_INV)
        bw = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

        n, labels, stats, centroids = cv2.connectedComponentsWithStats(bw)
        if n <= 1:
            self.pupil_rect_fine = self.pupil_rect_coarse
            self.center_fine = self.center_coarse
            return

        areas = stats[1:, cv2.CC_STAT_AREA]
        mask = areas > 0.04 * bw.size
        if not np.any(mask):
            mask = areas.argmax()[None]

        cx_local = patch.shape[1] // 2
        cy_local = patch.shape[0] // 2
        comp_idx = labels[cy_local, cx_local]
        if comp_idx == 0 or not mask[comp_idx - 1]:
            dark = 255
            for idx in np.flatnonzero(mask) + 1:
                cx_i, cy_i = centroids[idx]
                val = patch[int(cy_i), int(cx_i)]
                if val < dark:
                    dark = val
                    comp_idx = idx

        x, y, w, h = stats[comp_idx, cv2.CC_STAT_LEFT: cv2.CC_STAT_HEIGHT + 1]
        x += ex
        y += ey
        self.pupil_rect_fine = (x, y, w, h)
        self.center_fine = (x + w / 2, y + h / 2)

    def _postprocess(self) -> None:
        scale = self._ratio_down

        def _up(rect):
            return tuple(int(round(v * scale)) for v in rect)

        self.pupil_rect_coarse = _up(self.pupil_rect_coarse)
        self.outer_rect_coarse = _up(self.outer_rect_coarse)
        self.pupil_rect_fine = _up(self.pupil_rect_fine)

        self.center_coarse = tuple(v * scale for v in self.center_coarse)
        self.center_fine = tuple(v * scale for v in self.center_fine)