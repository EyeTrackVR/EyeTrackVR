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
from typing import Tuple, Optional
import cv2
import numpy as np

# ------------------------- utility helpers ------------------------- #
def _rect_scale(rect: Tuple[int, int, int, int],
                ratio: float,
                keep_center: bool = True,
                square_outer: bool = False) -> Tuple[int, int, int, int]:
    """Scale rectangle by *ratio* (optionally keep centre fixed)."""
    x, y, w, h = rect
    if square_outer:
        w = h = int(max(w, h) * ratio)
    else:
        w = int(w * ratio)
        h = int(h * ratio)
    if keep_center:
        cx, cy = x + rect[2] // 2, y + rect[3] // 2
        x = int(cx - w / 2)
        y = int(cy - h / 2)
    return (x, y, w, h)

def _clip_rect(rect: Tuple[int, int, int, int],
               boundary: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    """Clip *rect* to *boundary* = (x, y, w, h)."""
    bx, by, bw, bh = boundary
    x, y, w, h = rect
    x = max(bx, x)
    y = max(by, y)
    w = min(x + w, bx + bw) - x
    h = min(y + h, by + bh) - y
    return (x, y, max(0, w), max(0, h))

def _get_block_integral(ii: np.ndarray,
                        rect: Tuple[int, int, int, int]) -> int:
    """Integral‑image sum over *rect*."""
    x, y, w, h = rect
    return (ii[y+h, x+w] - ii[y, x+w] - ii[y+h, x] + ii[y, x])

def _canny_pure(img: np.ndarray,
                low: int = 64,
                high_ratio: float = 2.0) -> np.ndarray:
    """Lightweight Canny wrapper (imitates canny_pure())."""
    img_blur = cv2.GaussianBlur(img, (3, 3), 0)
    return cv2.Canny(img_blur, low, int(low*high_ratio))

# --------------------------- main class ---------------------------- #
class PupilDetectorHaar:
    """
    Haar‑based coarse‑to‑fine pupil detector.

    Parameters
    ----------
    ratio_outer : float
        Scaling factor for Haar outer rectangle.
    kf : float
        Weighting term in response function f = µ_outer − kf*µ_inner.
    use_square_haar : bool
        If True, outer Haar window is square; else horizontal rectangle.
    use_init_rect : bool
        If True, provide an approximate pupil box in *init_rect*.
    init_rect : Tuple[int,int,int,int] | None
        Initial pupil location on the full‑resolution frame.
    target_resolution : Tuple[int,int]
        Image is down‑sampled so the longer side ~320 px by default.
    width_min / width_max / wh_step / xy_step
        Search‑grid parameters for Haar scanning.
    """

    # -------- initialisation -------- #
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

        # search‑grid params (may be auto‑tuned after first frame)
        self.width_min = width_min
        self.width_max = width_max
        self.wh_step = wh_step
        self.xy_step = xy_step

        # dynamic state
        self.frame_num = 0
        self.mu_inner = 50
        self.mu_outer = 200
        self.mu_inner0 = 50   # first frame stats
        self.mu_outer0 = 200

        # outputs (public)
        self.pupil_rect_coarse = (0, 0, 0, 0)
        self.outer_rect_coarse = (0, 0, 0, 0)
        self.max_response_coarse = -255
        self.center_coarse = (0.0, 0.0)

        self.pupil_rect_fine = (0, 0, 0, 0)
        self.center_fine = (0.0, 0.0)

        # private temp
        self._ratio_down = 1.0
        self._img_boundary = (0, 0, 0, 0)
        self._init_rect_down = (0, 0, 0, 0)

    # ---------------------------------------------------------------- #
    #                          PUBLIC API                              #
    # ---------------------------------------------------------------- #
    def detect(self, img_gray: np.ndarray) -> Tuple[Tuple[int,int,int,int], Tuple[float,float]]:
        """
        Run detector on a single *uint8* gray image.

        Returns
        -------
        pupil_rect_fine : (x,y,w,h)
        center_fine : (cx,cy)  -- both on full‑resolution image.
        """
        if img_gray.dtype != np.uint8:
            raise TypeError("img_gray must be uint8 [0,255]")

        self.frame_num += 1
        img_down = self._preprocess(img_gray)
        self._coarse_detection(img_down)
        self._fine_detection(img_down)
        self._postprocess()

        return self.pupil_rect_fine, self.center_fine

    # --------------- optional helper for visual debugging ------------ #
    def draw_debug(self, bgr: np.ndarray) -> None:
        """Draw rectangular outputs on *bgr* in‑place."""
        cv2.rectangle(bgr, self.pupil_rect_fine, (0, 255, 0), 1)
        cv2.rectangle(bgr, self.outer_rect_coarse, (255, 0, 0), 1)
        cx, cy = map(int, self.center_fine)
        cv2.drawMarker(bgr, (cx, cy), (0, 0, 255),
                       markerType=cv2.MARKER_CROSS, markerSize=10, thickness=1)

    # ---------------------------------------------------------------- #
    #                       INTERNAL STAGES                            #
    # ---------------------------------------------------------------- #
    def _preprocess(self, img_gray: np.ndarray) -> np.ndarray:
        # down‑sample to target size (longer side ≈ target_resolution[0])
        h, w = img_gray.shape
        self._ratio_down = max(w / self.target_resolution[0],
                               h / self.target_resolution[1], 1.0)
        new_w = int(round(w / self._ratio_down))
        new_h = int(round(h / self._ratio_down))
        img_down = cv2.resize(img_gray, (new_w, new_h),
                              interpolation=cv2.INTER_AREA)

        self._img_boundary = (0, 0, new_w, new_h)

        # optional high‑intensity suppression on first frame
        if self.use_init_rect and self.frame_num == 1:
            # Estimate µ_inner0 / µ_outer0 inside init box
            x, y, rw, rh = self.init_rect
            region = img_gray[y:y+rh, x:x+rw]
            self.mu_inner0 = np.percentile(region, 25)
            self.mu_outer0 = np.percentile(region, 75)

            # adjust kf like original code
            if self.mu_outer0 - self.mu_inner0 > 30:
                tau = self.mu_outer0
            else:
                tau = self.mu_inner0 + 30
            img_down = np.minimum(img_down, tau).astype(np.uint8)

        return img_down

    # ------------------------------------------------------------ #
    #                      COARSE DETECTION                        #
    # ------------------------------------------------------------ #
    def _initial_search_range(self, img_down: np.ndarray) -> Tuple[int,int,int,int]:
        """Compute ROI and width range for current frame (down‑sampled)."""
        h, w = img_down.shape
        margin = h // 10 // 2
        full = (margin, margin, w - 2*margin, h - 2*margin)

        if not self.use_init_rect:
            self.roi = full
            return

        # scale init_rect to down resolution
        self._init_rect_down = tuple(int(x / self._ratio_down) for x in self.init_rect)
        ix, iy, iw, ih = self._init_rect_down

        # grow ROI adaptively near borders (imitates C++ code)
        rx, ry, rw, rh = full
        enlarge = 35
        if ix < enlarge:                rx, rw = 0, w
        if iy < enlarge:                ry, rh = 0, h
        if ix+iw > w - enlarge:         rx, rw = 0, w
        if iy+ih > h - enlarge:         ry, rh = 0, h
        self.roi = (rx, ry, rw, rh)

        # width search band tuned by first frame
        self.width_min = max(int(iw*1.0), 24)
        self.width_max = min(int(iw*1.5), 120)

    def _coarse_detection(self, img_down: np.ndarray) -> None:
        self._initial_search_range(img_down)
        roi_x, roi_y, roi_w, roi_h = self.roi

        # build integral image (cv2 adds +1 row/col)
        ii = cv2.integral(img_down, sdepth=cv2.CV_32S)

        best_f = -255
        best_pupil = (0, 0, 0, 0)
        best_outer = (0, 0, 0, 0)
        best_mu_in, best_mu_out = 0, 0

        for width in range(self.width_min, self.width_max+1, self.wh_step):
            # height tied to width; rectangular pupils handled fine
            for height in range(width, width+1, self.wh_step):
                xmax = roi_x + roi_w - width
                ymax = roi_y + roi_h - height
                for x in range(roi_x, xmax+1, self.xy_step):
                    for y in range(roi_y, ymax+1, self.xy_step):
                        pupil = (x, y, width, height)
                        outer = _rect_scale(pupil, self.ratio_outer,
                                            keep_center=True,
                                            square_outer=self.use_square_haar)
                        outer = _clip_rect(outer, self._img_boundary)

                        mu_in, mu_out = 0.0, 0.0
                        mu_out = (_get_block_integral(ii, outer) -
                                  _get_block_integral(ii, pupil)) / \
                                 (outer[2]*outer[3] - width*height)
                        mu_in = _get_block_integral(ii, pupil) / (width*height)
                        f_val = mu_out - self.kf * mu_in
                        if f_val > best_f:
                            best_f = f_val
                            best_pupil = pupil
                            best_outer = outer
                            best_mu_in, best_mu_out = mu_in, mu_out

        self.pupil_rect_coarse = best_pupil
        self.outer_rect_coarse = best_outer
        self.max_response_coarse = best_f
        self.mu_inner, self.mu_outer = best_mu_in, best_mu_out

        px, py, pw, ph = best_pupil
        self.center_coarse = (px + pw / 2, py + ph / 2)

    # ------------------------------------------------------------ #
    #                      FINE DETECTION                          #
    # ------------------------------------------------------------ #
    def _fine_detection(self, img_down: np.ndarray) -> None:
        px, py, pw, ph = self.pupil_rect_coarse
        expand = 1.42
        exp_rect = _clip_rect(_rect_scale(self.pupil_rect_coarse, expand, True),
                              self._img_boundary)
        ex, ey, ew, eh = exp_rect
        patch = img_down[ey:ey+eh, ex:ex+ew]

        # threshold at µ_inner (same heuristic)
        _, bw = cv2.threshold(patch, int(self.mu_inner), 255,
                              cv2.THRESH_BINARY_INV)

        # dilate to merge gaps
        bw = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5)))

        # connected components
        n, labels, stats, centroids = cv2.connectedComponentsWithStats(bw)
        if n <= 1:
            # fall‑back: keep coarse rect
            self.pupil_rect_fine = tuple(int(v) for v in
                                         np.array(self.pupil_rect_coarse) *
                                         self._ratio_down)
            self.center_fine = tuple(v * self._ratio_down
                                     for v in self.center_coarse)
            return

        # discard tiny blobs (<4% of patch)
        areas = stats[1:, cv2.CC_STAT_AREA]
        mask = areas > 0.04 * bw.size
        if not np.any(mask):
            mask = areas.argmax()[None]  # keep largest if all tiny

        # choose component through image centre, else darkest centroid
        cx_local = patch.shape[1] // 2
        cy_local = patch.shape[0] // 2
        comp_idx = labels[cy_local, cx_local]
        if comp_idx == 0 or not mask[comp_idx-1]:
            # pick darkest of two largest blobs (C++ heuristic)
            dark = 255
            for idx in np.flatnonzero(mask) + 1:
                cx_i, cy_i = centroids[idx]
                val = patch[int(cy_i), int(cx_i)]
                if val < dark:
                    dark = val
                    comp_idx = idx

        # final bounding box in down‑scaled coords
        x, y, w, h = stats[comp_idx, cv2.CC_STAT_LEFT : cv2.CC_STAT_HEIGHT+1]
        x += ex
        y += ey
        self.pupil_rect_fine = (x, y, w, h)
        self.center_fine = (x + w / 2, y + h / 2)

    # ------------------------------------------------------------ #
    #                        UPSAMPLE BACK                         #
    # ------------------------------------------------------------ #
    def _postprocess(self) -> None:
        # scale coarse and fine rects + centres back to full resolution
        scale = self._ratio_down
        def _up(rect):
            return tuple(int(round(v*scale)) for v in rect)
        self.pupil_rect_coarse = _up(self.pupil_rect_coarse)
        self.outer_rect_coarse = _up(self.outer_rect_coarse)
        self.pupil_rect_fine = _up(self.pupil_rect_fine)

        self.center_coarse = tuple(v*scale for v in self.center_coarse)
        self.center_fine = tuple(v*scale for v in self.center_fine)
