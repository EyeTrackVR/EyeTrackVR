"""Tracking output visualizer: gaze dot with pupil-dilation ring, blink bar and
eyebrow bar, drawn on a Tk canvas. Shared by the main tracking page and the
algorithm settings previews; sizes scale from one width."""
import tkinter as tk

import numpy as np

from eye import EyeInfo
from eye_processor import EyeInfoOrigin
from localization import tr


# Full-size width at 100% DPI; the main tracking page uses exactly this.
BASE_WIDTH = 200


def _layout(width, dpi_scale):
    unit = width / BASE_WIDTH
    pad, gap = max(3, round(8 * unit)), max(2, round(6 * unit))
    blink_w = brow_w = max(8, round(20 * unit))
    gaze = width - pad * 2 - gap * 2 - blink_w - brow_w
    return pad, gap, blink_w, brow_w, gaze


class OutputVisualizer:
    @staticmethod
    def height_for(width: int, dpi_scale: float = 1.0) -> int:
        pad, _gap, _blink, _brow, gaze = _layout(width, dpi_scale)
        return pad * 2 + gaze

    def __init__(self, parent, width: int, dpi_scale: float = 1.0):
        self.pad, self.gap, self.blink_w, self.brow_w, self.gaze = _layout(width, dpi_scale)
        self.width = width
        self.height = self.pad * 2 + self.gaze
        # Marker sizes (dot, ring, ticks) relative to the full-size view at this DPI,
        # so the main page is unchanged and smaller copies shrink in proportion.
        self.u = width / (BASE_WIDTH * dpi_scale)
        self._item_ids = None
        self.canvas = tk.Canvas(parent, width=self.width, height=self.height, bg="#1e1f23",
                                highlightthickness=0)

    def hide(self) -> None:
        """Hide all visualization items inside the canvas without unpacking the canvas."""
        self._ensure_items()
        c = self.canvas
        c.itemconfigure("viz_main", state="hidden")
        c.itemconfigure("viz_fail", state="hidden")

    def _ensure_items(self) -> None:
        if self._item_ids is not None:
            return
        c = self.canvas
        W, H = self.width, self.height
        fail_bg = "#3a2428"
        fail_fg = "#ff9aaa"
        bg = "#1e1f23"
        panel = "#2a2c33"
        panel_border = "#454859"
        cross = "#3d4049"
        track_fill = "#32353d"
        track_border = "#4a4e5c"
        blink_fill_col = "#c4a5ff"
        brow_fill_col = "#a5d6ff"
        tick = "#6d7285"
        dot = "#f4f2ff"
        ring_col = "#b49cff"
        c.configure(bg=bg)
        self._item_ids = {
            "fail_bg": c.create_rectangle(
                0, 0, W, H, outline="", fill=fail_bg, tags="viz_fail"
            ),
            "fail_txt": c.create_text(
                W // 2,
                H // 2,
                text=tr("camera.no_track"),
                fill=fail_fg,
                font=("Segoe UI", 9 if self.u >= 0.8 else 7),
                tags="viz_fail",
            ),
            "bg": c.create_rectangle(0, 0, W, H, outline="", fill=bg, tags="viz_main"),
            "panel": c.create_rectangle(
                0, 0, 0, 0, outline=panel_border, width=1, fill=panel, tags="viz_main"
            ),
            "cross_v": c.create_line(0, 0, 0, 0, fill=cross, width=1, tags="viz_main"),
            "cross_h": c.create_line(0, 0, 0, 0, fill=cross, width=1, tags="viz_main"),
            "ring": c.create_oval(
                0, 0, 0, 0, outline=ring_col, width=2, fill="", tags="viz_main"
            ),
            "dot": c.create_oval(0, 0, 0, 0, fill=dot, outline=dot, tags="viz_main"),
            "blink_track": c.create_rectangle(
                0,
                0,
                0,
                0,
                outline=track_border,
                width=1,
                fill=track_fill,
                tags="viz_main",
            ),
            "blink_bar": c.create_rectangle(
                0,
                0,
                0,
                0,
                fill=blink_fill_col,
                outline="",
                tags="viz_main",
                state="hidden",
            ),
            "tick_t": c.create_line(0, 0, 0, 0, fill=tick, width=1, tags="viz_main"),
            "tick_b": c.create_line(0, 0, 0, 0, fill=tick, width=1, tags="viz_main"),
            "brow_track": c.create_rectangle(
                0, 0, 0, 0, outline=track_border, width=1, fill=track_fill, tags="viz_main"
            ),
            "brow_bar": c.create_rectangle(
                0, 0, 0, 0, fill=brow_fill_col, outline="", tags="viz_main", state="hidden"
            ),
            "tick_brow_t": c.create_line(0, 0, 0, 0, fill=tick, width=1, tags="viz_main"),
            "tick_brow_b": c.create_line(0, 0, 0, 0, fill=tick, width=1, tags="viz_main"),
        }
        c.itemconfigure("viz_fail", state="hidden")

    def draw(self, eye_info: EyeInfo) -> None:
        """Dark-mode compact gaze dot + vertical blink bar (right)."""
        self._ensure_items()
        c = self.canvas
        ids = self._item_ids
        W, H = self.width, self.height
        pad = self.pad
        G = self.gaze
        gap = self.gap
        bw = self.blink_w
        ew = self.brow_w

        if eye_info.info_type == EyeInfoOrigin.FAILURE:
            c.itemconfigure("viz_main", state="hidden")
            c.coords(ids["fail_bg"], 0, 0, W, H)
            c.coords(ids["fail_txt"], W // 2, H // 2)
            c.itemconfigure("viz_fail", state="normal")
            return

        c.itemconfigure("viz_fail", state="hidden")
        c.itemconfigure("viz_main", state="normal")

        gx0, gy0 = pad, pad
        bx0 = gx0 + G + gap
        by0, bh = gy0, G

        c.coords(ids["bg"], 0, 0, W, H)
        c.coords(ids["panel"], gx0, gy0, gx0 + G, gy0 + G)

        gc_x = gx0 + G // 2
        gc_y = gy0 + G // 2
        u = self.u
        edge = round(5 * u)
        c.coords(ids["cross_v"], gc_x, gy0 + edge, gc_x, gy0 + G - edge)
        c.coords(ids["cross_h"], gx0 + edge, gc_y, gx0 + G - edge, gc_y)

        half = max(12.0 * u, (G / 2) - 10.0 * u)
        gaze_gain = 2.75
        if not np.isnan(eye_info.x) and not np.isnan(eye_info.y):
            cx = int(round(gc_x - float(eye_info.x) * half * gaze_gain))
            cy = int(round(gc_y - float(eye_info.y) * half * gaze_gain))
        else:
            cx, cy = gc_x, gc_y

        margin = max(3, round(7 * u))
        cx = int(np.clip(cx, gx0 + margin, gx0 + G - margin))
        cy = int(np.clip(cy, gy0 + margin, gy0 + G - margin))

        try:
            pd_raw = float(eye_info.pupil_dilation)
        except (TypeError, ValueError):
            pd_raw = float("nan")
        if np.isfinite(pd_raw):
            # EBPD / OSC use ~0..1; clamp for ring so the viz matches shipped dilation semantics.
            pd = float(np.clip(pd_raw, 0.0, 1.0))
        else:
            pd = 0.5
        r_ring = int(round((7 + pd * 34) * u))
        r_max = min(cx - gx0, gx0 + G - cx, cy - gy0, gy0 + G - cy) - 2
        r_ring = min(r_ring, max(round(8 * u), r_max))
        c.coords(ids["ring"], cx - r_ring, cy - r_ring, cx + r_ring, cy + r_ring)

        r = max(2, round(5 * u))
        c.coords(ids["dot"], cx - r, cy - r, cx + r, cy + r)

        inset = max(2, round(3 * u))
        t = max(2, round(4 * u))
        c.coords(ids["blink_track"], bx0, by0, bx0 + bw, by0 + bh)
        if not np.isnan(eye_info.blink):
            b = float(np.clip(eye_info.blink, 0.0, 1.0))
            inner_h = bh - inset * 2
            fill_h = max(2, int(round(b * inner_h)))
            y_top = by0 + bh - inset - fill_h
            y_bot = by0 + bh - inset
            c.coords(ids["blink_bar"], bx0 + inset, y_top, bx0 + bw - inset, y_bot)
            c.itemconfigure(ids["blink_bar"], state="normal")
        else:
            c.itemconfigure(ids["blink_bar"], state="hidden")

        c.coords(
            ids["tick_t"],
            bx0 + bw // 2 - t,
            by0 + inset,
            bx0 + bw // 2 + t,
            by0 + inset,
        )
        c.coords(
            ids["tick_b"],
            bx0 + bw // 2 - t,
            by0 + bh - inset,
            bx0 + bw // 2 + t,
            by0 + bh - inset,
        )

        ex0 = bx0 + bw + gap
        brow_val = float(np.clip(eye_info.eyebrow, 0.0, 1.0)) if not np.isnan(eye_info.eyebrow) else 0.5
        inner_h = bh - inset * 2
        fill_h = max(2, int(round(brow_val * inner_h)))
        y_top = by0 + bh - inset - fill_h
        y_bot = by0 + bh - inset
        c.coords(ids["brow_track"], ex0, by0, ex0 + ew, by0 + bh)
        c.coords(ids["brow_bar"], ex0 + inset, y_top, ex0 + ew - inset, y_bot)
        c.itemconfigure(ids["brow_bar"], state="normal")
        c.coords(ids["tick_brow_t"], ex0 + ew // 2 - t, by0 + inset, ex0 + ew // 2 + t, by0 + inset)
        c.coords(ids["tick_brow_b"], ex0 + ew // 2 - t, by0 + bh - inset, ex0 + ew // 2 + t, by0 + bh - inset)
