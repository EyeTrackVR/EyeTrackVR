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

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import logging
import tkinter as tk
from tkinter import ttk
from config import EyeTrackConfig
from collections import deque
from threading import Event, Thread
import math
import time
from eye import EyeId, EyeInfo
from eye_processor import EyeProcessor, EyeInfoOrigin
from queue import Queue, Empty
from camera import Camera, CameraState
import cv2
from osc.OSCMessage import OSCMessageType, OSCMessage
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC, resource_path
from utils.img_utils import tk_photo_from_rgb
from localization import tr
import numpy as np

logger = logging.getLogger(__name__)


# for clarity when indexing
X = 0
Y = 1


class CameraWidget:
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig, osc_queue: Queue):
        self.gui_camera_addr = f"-CAMERAADDR{widget_id}-"
        self.gui_rotation_slider = f"-ROTATIONSLIDER{widget_id}-"
        self.gui_rotation_ui_padding = f"-ROTATIONUIPADDING{widget_id}-"
        self.gui_roi_button = f"-ROIMODE{widget_id}-"
        self.gui_roi_layout = f"-ROILAYOUT{widget_id}-"
        self.gui_roi_selection = f"-GRAPH{widget_id}-"
        self.gui_tracking_button = f"-TRACKINGMODE{widget_id}-"
        self.gui_save_tracking_button = f"-SAVETRACKINGBUTTON{widget_id}-"
        self.gui_tracking_layout = f"-TRACKINGLAYOUT{widget_id}-"
        self.gui_tracking_image = f"-IMAGE{widget_id}-"
        self.gui_tracking_fps = f"-TRACKINGFPS{widget_id}-"
        self.gui_tracking_bps = f"-TRACKINGBPS{widget_id}-"
        self.gui_output_graph = f"-OUTPUTGRAPH{widget_id}-"
        self.gui_restart_calibration = f"-RESTARTCALIBRATION{widget_id}-"
        self.gui_stop_calibration = f"-STOPCALIBRATION{widget_id}-"
        self.gui_recenter_eyes = f"-RECENTEREYES{widget_id}-"
        self.gui_mode_readout = f"-APPMODE{widget_id}-"
        self.gui_roi_message = f"-ROIMESSAGE{widget_id}-"
        self.last_eye_info = None
        self.osc_queue = osc_queue
        self.main_config = main_config
        self.eye_id = widget_id
        self.settings_config = main_config.settings
        self.settings = main_config.settings
        if self.eye_id == EyeId.RIGHT:
            self.config = main_config.right_eye
        elif self.eye_id == EyeId.LEFT:
            self.config = main_config.left_eye
        else:
            raise RuntimeError(
                "\033[91m[WARN] Cannot have a camera widget represent both eyes!\033[0m"
            )

        self.cancellation_event = Event()
        # Set the event until start is called, otherwise we can block if shutdown is called.
        self.cancellation_event.set()
        self.capture_event = Event()
        self.capture_queue = Queue(maxsize=2)
        self.roi_queue = Queue(maxsize=2)

        self.image_queue = Queue(maxsize=2)
        self.uses_shared_capture_event = False
        # When sharing a capture thread (Bigscreen / dual-eye on one source),
        # this widget's own ``self.camera`` never runs; its camera_status
        # stays at CONNECTING and the readout would lie. Track the upstream
        # camera here so the mode readout can read its real status.
        self._shared_capture_source: "Camera | None" = None

        self.ransac = EyeProcessor(
            self.config,
            self.settings_config,
            main_config,
            self.cancellation_event,
            self.capture_event,
            self.capture_queue,
            self.image_queue,
            self.eye_id,
            self.osc_queue,
        )

        self.camera_status_queue = Queue()
        self.camera = Camera(
            self.config,
            self.settings,
            0,
            self.cancellation_event,
            self.capture_event,
            self.camera_status_queue,
            self.capture_queue,
        )

        self.hover = None

        # cartesian co-ordinates in widget space are used during selection
        self.xy0 = None
        self.xy1 = None
        self.cartesian_needs_update = False
        # polar co-ordinates from the image center are the canonical representation
        self.cr, self.ca = None, None
        self.roi_size = None
        self.clip_size = None
        self.clip_pos = None
        self.padded_size = [244, 244]
        self.img_pos = None
        self.roi_image_center = None

        self.is_mouse_up = True
        self.hover_pos = None
        self.in_roi_mode = False
        self._tracking_photo = None
        self._roi_photo = None
        self.frame = None
        self._config_save_after_id = None
        self._last_fps_readout = ""
        self._last_latency_readout = ""
        self._last_mode_readout = ""
        self._last_calibration_btn_text = None
        self._viz_item_ids = None
        self._roi_canvas_image_id = None
        self._roi_overlay_tag = "roi_overlay"
        # Display scale used to fit the (warped/padded) ROI image into a
        # compact preview canvas. xy0/xy1 are kept in IMAGE coordinates; we
        # multiply by this when drawing on the canvas and divide by it when
        # translating mouse events back to image space. 1.0 = native.
        # Sized so both eyes can sit side-by-side in cropping mode without
        # overflowing typical window widths; it roughly matches the tracking
        # preview's longest side.
        self._roi_display_scale = 1.0
        self._ROI_CANVAS_MAX_DIM = 320
        self._dpi_scale = 1.0
        self._debug_image_visible = None  # None = uninitialized; True/False tracks current pack state
        self._preview_dim = 200
        self._eye_preview_photo = None
        # 'new' while drawing a fresh box; a handle id ('tl','tr','bl','br','t','b','l','r') while resizing
        self._drag_handle = "new"
        self._resize_anchor = None   # fixed corner (np.array) for corner drags
        self._resize_edge_state = None  # (x0,x1,y_fixed) or (y0,y1,x_fixed) for edge drags
        self.camera_thread: Thread | None = None
        self.tracking_thread: Thread | None = None

    def build(self, parent, show_camera_controls=True, dpi_scale=1.0):
        self._dpi_scale = dpi_scale
        self.frame = ttk.Frame(parent)

        if show_camera_controls:
            top_row = ttk.Frame(self.frame)
            top_row.pack(fill="x", padx=8, pady=4)
            ttk.Label(top_row, text=tr("camera.address")).pack(side="left")
            initial_source = self.config.capture_source
            self.camera_addr_var = tk.StringVar(
                value="" if initial_source is None or initial_source == "" else str(initial_source)
            )
            ttk.Entry(top_row, textvariable=self.camera_addr_var, width=36).pack(
                side="left", padx=8
            )
            ttk.Button(
                top_row, text=tr("camera.save_restart"), command=self._save_tracking
            ).pack(side="left", padx=8)

        # Tracking/Cropping mode buttons are now global (one pair in
        # eyetrackapp.py drives both eyes together) instead of per-eye.

        self.tracking_frame = ttk.Frame(self.frame)
        self.roi_frame = ttk.Frame(self.frame)
        self.tracking_frame.pack(fill="both", expand=True)

        # Per-eye Start Calibration / Recenter buttons used to live here; they're
        # now a single global pair in eyetrackapp.py (below the tracking row) so
        # both eyes calibrate together. _calibration_toggle_btn stays unset and
        # _sync_calibration_toggle_button() no-ops via its getattr guard.

        status_row = ttk.Frame(self.tracking_frame)
        status_row.pack(fill="x", padx=4, pady=2)
        self.mode_var = tk.StringVar(value=tr("camera.status_calibrating"))
        self.fps_var = tk.StringVar(value="")
        self.latency_var = tk.StringVar(value="")
        # Layout: [mode  tracking_fps  latency_ms                     ]
        # fps reports tracker output rate (includes camera + algo cost); latency
        # is end-to-end frame-in → tracking-out, both moving-averaged in
        # eye_processor. Widths sized for the worst-case readouts:
        #   fps     - "120 Fps"     (7 chars)
        #   latency - "999 ms lat"  (10 chars)
        ttk.Label(status_row, textvariable=self.mode_var, anchor="w").pack(side="left")
        ttk.Label(status_row, textvariable=self.fps_var, width=8, anchor="w").pack(
            side="left", padx=(4, 0)
        )
        ttk.Label(status_row, textvariable=self.latency_var, width=11, anchor="w").pack(
            side="left", padx=(4, 0)
        )

        # Source stack from processor is 300×150; compact display for dual-eye layout
        self._tracking_display_size = (round(380 * dpi_scale), round(190 * dpi_scale))
        self._preview_dim = round(200 * dpi_scale)

        self._viz_pad = round(8 * dpi_scale)
        self._viz_gaze_gap = round(6 * dpi_scale)
        self._viz_blink_w = round(20 * dpi_scale)
        self._viz_brow_w = round(20 * dpi_scale)
        # Both bars fit inside _preview_dim: pad + gaze + gap + blink + gap + brow + pad
        self._viz_canvas_w = self._preview_dim
        self._viz_gaze = (
            self._viz_canvas_w
            - self._viz_pad * 2
            - self._viz_gaze_gap * 2
            - self._viz_blink_w
            - self._viz_brow_w
        )
        self._viz_canvas_h = self._viz_pad * 2 + self._viz_gaze
        tw, th = self._tracking_display_size
        self._ROI_CANVAS_MAX_DIM = tw - round(16 * dpi_scale)

        # Reserve the final slot size up-front so the layout doesn't jitter when the first
        # frame arrives (Label would otherwise start at 0x0 and suddenly grow to 300x150,
        # shifting every widget below it, visible as "the right eye moves around at launch").
        self._tracking_image_holder = tk.Frame(
            self.tracking_frame,
            width=tw,
            height=th,
            bg="#1e1f23",
            highlightthickness=0,
            bd=0,
        )
        # Not packed here: render_tick packs it only when Show ET Debug is enabled.
        self._tracking_image_holder.pack_propagate(False)
        self.tracking_image_widget = tk.Label(
            self._tracking_image_holder,
            bg="#1e1f23",
            bd=0,
            highlightthickness=0,
        )
        self.tracking_image_widget.pack(fill="both", expand=True)

        # Small always-visible eye preview (left half of the image stack = processed eye image).
        _dim = self._preview_dim
        self._eye_preview_holder = tk.Frame(
            self.tracking_frame,
            width=_dim,
            height=_dim,
            bg="#1e1f23",
            highlightthickness=0,
            bd=0,
        )
        self._eye_preview_holder.pack(padx=4, pady=2, anchor="w")
        self._eye_preview_holder.pack_propagate(False)
        self._eye_preview_widget = tk.Label(
            self._eye_preview_holder,
            bg="#1e1f23",
            bd=0,
            highlightthickness=0,
        )
        self._eye_preview_widget.pack(fill="both", expand=True)

        # Keep the viz row at a fixed height regardless of whether the canvas, the ROI
        # placeholder message, or nothing is visible. pack_propagate(False) means children
        # can't resize the row, so showing/hiding them no longer reflows the layout.
        graph_row = ttk.Frame(self.tracking_frame, height=self._viz_canvas_h)
        graph_row.pack(fill="x", padx=4, pady=2)
        graph_row.pack_propagate(False)
        self._graph_row = graph_row
        self.output_canvas = tk.Canvas(
            graph_row,
            width=self._viz_canvas_w,
            height=self._viz_canvas_h,
            bg="#1e1f23",
            highlightthickness=0,
        )
        self.output_canvas.pack(side="left")
        self.roi_message_var = tk.StringVar(value=tr("camera.roi_prompt"))
        self.roi_message_label = ttk.Label(graph_row, textvariable=self.roi_message_var)
        # roi_message_label is packed/unpacked dynamically in render_tick; the fixed-height
        # parent absorbs the change so nothing downstream moves.

        roi_controls = ttk.Frame(self.roi_frame)
        roi_controls.pack(fill="x", padx=8, pady=4)
        ttk.Label(roi_controls, text=tr("camera.rotation")).pack(side="left")
        self.rotation_var = tk.IntVar(value=int(self.config.rotation_angle))
        ttk.Scale(
            roi_controls,
            from_=0,
            to=360,
            variable=self.rotation_var,
            orient="horizontal",
            length=round(160 * dpi_scale),
        ).pack(side="left", padx=8)
        self.rotation_readout_var = tk.StringVar(
            value=str(int(self.rotation_var.get()))
        )

        def sync_rotation_readout(*_args):
            self.rotation_readout_var.set(
                str(int(round(float(self.rotation_var.get()))))
            )

        def bump_rotation(delta):
            next_val = int(round(float(self.rotation_var.get()))) + delta
            next_val = max(0, min(360, next_val))
            self.rotation_var.set(next_val)

        ttk.Button(
            roi_controls, text="-", width=2, command=lambda: bump_rotation(-1)
        ).pack(side="left", padx=(4, 2))
        ttk.Label(
            roi_controls,
            textvariable=self.rotation_readout_var,
            width=6,
            anchor="center",
        ).pack(side="left", padx=2)
        ttk.Button(
            roi_controls, text="+", width=2, command=lambda: bump_rotation(1)
        ).pack(side="left", padx=(2, 8))
        self.rotation_var.trace_add("write", sync_rotation_readout)
        self.padding_var = tk.BooleanVar(
            value=bool(self.config.gui_rotation_ui_padding)
        )
        roi_padding_row = ttk.Frame(self.roi_frame)
        roi_padding_row.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Checkbutton(
            roi_padding_row,
            text=tr("camera.widget_padding"),
            variable=self.padding_var,
        ).pack(side="left")

        # Canvas auto-resizes to the scaled padded_size in render_tick once
        # the first frame arrives. Initial size is a small placeholder ~2x
        # tracking preview so the tab doesn't open with a huge empty box.
        self.roi_canvas = tk.Canvas(
            self.roi_frame, width=self._ROI_CANVAS_MAX_DIM, height=self._ROI_CANVAS_MAX_DIM // 2, bg="#424042", highlightthickness=0
        )
        self.roi_canvas.pack(padx=8, pady=4, anchor="w")
        self.roi_canvas.bind("<ButtonPress-1>", self._on_roi_mouse_down)
        self.roi_canvas.bind("<B1-Motion>", self._on_roi_mouse_drag)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_roi_mouse_up)
        self.roi_canvas.bind("<Motion>", self._on_roi_mouse_move)

        # Create viz items up-front and hide them so the canvas shows as a clean dark
        # rectangle at launch (same as its final "waiting for first frame" look), rather
        # than briefly exposing unfilled primitives when items are first created mid-run.
        self._hide_output_viz()
        return self.frame

    def _sync_mode_tab_buttons(self) -> None:
        """No-op: mode buttons moved to a global pair in eyetrackapp.py."""
        return

    def _tk_photo_from_bgr(self, image: np.ndarray, master: tk.Misc):
        if image is None or image.size == 0 or image.shape[0] < 1 or image.shape[1] < 1:
            return None
        try:
            if image.ndim == 2:
                rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            elif image.ndim == 3 and image.shape[2] == 4:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
            elif image.ndim == 3 and image.shape[2] == 3:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                return None
            return tk_photo_from_rgb(rgb, master)
        except (ValueError, TypeError, tk.TclError):
            return None

    def _hide_output_viz(self) -> None:
        """Hide all visualization items inside the canvas without unpacking the canvas."""
        self._ensure_output_viz_canvas_items()
        c = self.output_canvas
        c.itemconfigure("viz_main", state="hidden")
        c.itemconfigure("viz_fail", state="hidden")

    def _ensure_output_viz_canvas_items(self) -> None:
        if self._viz_item_ids is not None:
            return
        c = self.output_canvas
        W, H = self._viz_canvas_w, self._viz_canvas_h
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
        self._viz_item_ids = {
            "fail_bg": c.create_rectangle(
                0, 0, W, H, outline="", fill=fail_bg, tags="viz_fail"
            ),
            "fail_txt": c.create_text(
                W // 2,
                H // 2,
                text=tr("camera.no_track"),
                fill=fail_fg,
                font=("Segoe UI", 9),
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

    def _draw_output_visualization(self, eye_info: EyeInfo) -> None:
        """Dark-mode compact gaze dot + vertical blink bar (right)."""
        self._ensure_output_viz_canvas_items()
        c = self.output_canvas
        ids = self._viz_item_ids
        W, H = self._viz_canvas_w, self._viz_canvas_h
        pad = self._viz_pad
        G = self._viz_gaze
        gap = self._viz_gaze_gap
        bw = self._viz_blink_w
        ew = self._viz_brow_w

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
        c.coords(ids["cross_v"], gc_x, gy0 + 5, gc_x, gy0 + G - 5)
        c.coords(ids["cross_h"], gx0 + 5, gc_y, gx0 + G - 5, gc_y)

        half = max(12.0, (G / 2) - 10.0)
        gaze_gain = 2.75
        if not np.isnan(eye_info.x) and not np.isnan(eye_info.y):
            cx = int(round(gc_x - float(eye_info.x) * half * gaze_gain))
            cy = int(round(gc_y - float(eye_info.y) * half * gaze_gain))
        else:
            cx, cy = gc_x, gc_y

        margin = 7
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
        r_ring = int(round(7 + pd * 34))
        r_max = min(cx - gx0, gx0 + G - cx, cy - gy0, gy0 + G - cy) - 2
        r_ring = min(r_ring, max(8, r_max))
        c.coords(ids["ring"], cx - r_ring, cy - r_ring, cx + r_ring, cy + r_ring)

        r = 5
        c.coords(ids["dot"], cx - r, cy - r, cx + r, cy + r)

        inset = 3
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
            bx0 + bw // 2 - 4,
            by0 + inset,
            bx0 + bw // 2 + 4,
            by0 + inset,
        )
        c.coords(
            ids["tick_b"],
            bx0 + bw // 2 - 4,
            by0 + bh - inset,
            bx0 + bw // 2 + 4,
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
        c.coords(ids["tick_brow_t"], ex0 + ew // 2 - 4, by0 + inset, ex0 + ew // 2 + 4, by0 + inset)
        c.coords(ids["tick_brow_b"], ex0 + ew // 2 - 4, by0 + bh - inset, ex0 + ew // 2 + 4, by0 + bh - inset)

    def _effective_camera(self) -> "Camera":
        """The camera that actually produces frames for this widget.
        In bigscreen the secondary eye reuses the primary eye's camera;
        its own ``self.camera`` never runs (apply_camera_inputs sets
        ``run_camera_thread=False``)."""
        if self.uses_shared_capture_event and self._shared_capture_source is not None:
            return self._shared_capture_source
        return self.camera

    def _set_roi_tap(self, enabled: bool) -> None:
        """Add (or remove) this widget's roi_queue to the *effective* camera's
        extra output queues. ROI mode is now a TAP, not a reroute: the
        tracker's capture_queue keeps being fed throughout, so exiting ROI
        mode doesn't need to wake or unblock anything; the tracker has been
        running continuously. This eliminates the "one eye frozen after exit"
        race the rerouting version had.

        Preserves any pre-existing extras (e.g. the secondary eye's
        capture_queue in bigscreen), so toggling crop mode for one eye
        doesn't disturb the other eye's frame flow.
        """
        cam = self._effective_camera()
        current = list(cam._extra_output_queues)
        # Remove our roi_queue first so toggling is idempotent.
        current = [q for q in current if q is not self.roi_queue]
        if enabled:
            current.append(self.roi_queue)
        cam.set_extra_output_queues(current)

    def _set_tracking_mode(self):
        logger.info("Moving to tracking mode")
        self._set_roi_tap(False)
        self._drain_queue(self.roi_queue)
        self.in_roi_mode = False
        self.roi_frame.pack_forget()
        self.tracking_frame.pack(fill="both", expand=True)
        self._sync_mode_tab_buttons()

    def _set_roi_mode(self):
        logger.info("Moving to ROI mode")
        self._set_roi_tap(True)
        self.in_roi_mode = True
        self.tracking_frame.pack_forget()
        self.roi_frame.pack(fill="both", expand=True)
        self._sync_mode_tab_buttons()

    @staticmethod
    def _drain_queue(q: "Queue") -> None:
        try:
            while True:
                q.get_nowait()
        except Empty:
            pass

    def _save_tracking(self):
        value = self.camera_addr_var.get()
        # Render the current source identically to the initial-value population above so the
        # "no change" comparison handles UVC index 0 (which is falsy in Python) correctly.
        current_source = self.config.capture_source
        current_str = (
            "" if current_source is None or current_source == "" else str(current_source)
        )
        if value == current_str:
            return
        try:
            new_source = int(value)
        except ValueError:
            lower_value = value.lower()
            if value == "":
                new_source = None
            elif (
                len(value) > 5
                and "://" not in value
                and not value.startswith(("COM", "/dev", "uvc:"))
                and not lower_value.endswith((".mp4", ".avi", ".mkv", ".mov"))
            ):
                new_source = f"http://{value}/"
            else:
                new_source = value

        if new_source == self.config.capture_source:
            return

        logger.info("New capture source value: %s", new_source)

        # Run the apply/restart off the Tk thread: update_eye_model_config notifies listeners
        # (including on_config_update, which stops/starts the camera), and stop() joins the
        # camera thread, which can block briefly on close/open. We don't want to freeze the GUI.
        def _apply():
            try:
                self.main_config.update_eye_model_config(
                    self.eye_id, {"capture_source": new_source}
                )
            except Exception as exc:
                logger.warning("Failed to apply new capture source: %s", exc)

        Thread(
            target=_apply, daemon=True, name=f"CameraSourceApply-{self.eye_id}"
        ).start()

    def _stop_calibration(self):
        self.ransac.calibration_start_time = None
        self._sync_calibration_toggle_button()

    def _effective_camera_status(self):
        if self.uses_shared_capture_event and self._shared_capture_source is not None:
            return self._shared_capture_source.camera_status
        return self.camera.camera_status

    def detach_shared_capture_event(self) -> None:
        if not self.uses_shared_capture_event:
            return
        ev = Event()
        self.capture_event = ev
        self.ransac.capture_event = ev
        self.uses_shared_capture_event = False
        self._shared_capture_source = None

    def _schedule_main_config_save(self) -> None:
        if self.frame is None:
            return
        top = self.frame.winfo_toplevel()
        if self._config_save_after_id is not None:
            try:
                top.after_cancel(self._config_save_after_id)
            except tk.TclError:
                pass

        def _flush():
            self._config_save_after_id = None
            self.main_config.save()

        self._config_save_after_id = top.after(450, _flush)

    def _sync_calibration_toggle_button(self) -> None:
        btn = getattr(self, "_calibration_toggle_btn", None)
        if btn is None:
            return
        if self.ransac.calibration_start_time is not None:
            text = "Stop Calibration"
        else:
            text = "Start Calibration"
        if text != self._last_calibration_btn_text:
            self._last_calibration_btn_text = text
            btn.configure(text=text)

    def _on_calibration_toggle(self) -> None:
        if self.ransac.calibration_start_time is not None:
            self._stop_calibration()
        else:
            self.recalibrate_eyes()

    def _event_to_image_xy(self, event) -> np.ndarray:
        """Convert a canvas-space Tk event to image-space coordinates. xy0/xy1
        are stored in image space so the existing rotation / clip / config-save
        math is invariant to the display scale."""
        s = self._roi_display_scale or 1.0
        return np.array((event.x / s, event.y / s))

    def _get_bbox_image(self):
        """Normalized (x0,y0,x1,y1) of the crop box in image coords, or None."""
        if self.xy0 is None or self.xy1 is None:
            return None
        return (
            min(self.xy0[X], self.xy1[X]),
            min(self.xy0[Y], self.xy1[Y]),
            max(self.xy0[X], self.xy1[X]),
            max(self.xy0[Y], self.xy1[Y]),
        )

    def _get_handle_at(self, cx, cy):
        """Return the handle id under canvas point (cx,cy), or None for empty canvas."""
        bbox = self._get_bbox_image()
        if bbox is None:
            return None
        s = self._roi_display_scale or 1.0
        tol = round(self._dpi_scale * 10)
        x0, y0, x1, y1 = (v * s for v in bbox)
        def near(ax, ay):
            return abs(cx - ax) <= tol and abs(cy - ay) <= tol
        if near(x0, y0): return "tl"
        if near(x1, y0): return "tr"
        if near(x0, y1): return "bl"
        if near(x1, y1): return "br"
        if abs(cy - y0) <= tol and x0 - tol <= cx <= x1 + tol: return "t"
        if abs(cy - y1) <= tol and x0 - tol <= cx <= x1 + tol: return "b"
        if abs(cx - x0) <= tol and y0 - tol <= cy <= y1 + tol: return "l"
        if abs(cx - x1) <= tol and y0 - tol <= cy <= y1 + tol: return "r"
        return None

    def _on_roi_mouse_down(self, event):
        self.hover_pos = None
        self.is_mouse_up = False
        handle = self._get_handle_at(event.x, event.y)
        if handle is not None:
            self._drag_handle = handle
            bbox = self._get_bbox_image()
            x0, y0, x1, y1 = bbox
            if handle == "tl":
                self._resize_anchor = np.array([x1, y1])
            elif handle == "tr":
                self._resize_anchor = np.array([x0, y1])
            elif handle == "bl":
                self._resize_anchor = np.array([x1, y0])
            elif handle == "br":
                self._resize_anchor = np.array([x0, y0])
            elif handle == "t":
                self._resize_edge_state = (x0, x1, y1)
            elif handle == "b":
                self._resize_edge_state = (x0, x1, y0)
            elif handle == "l":
                self._resize_edge_state = (y0, y1, x1)
            elif handle == "r":
                self._resize_edge_state = (y0, y1, x0)
        else:
            self._drag_handle = "new"
            self._resize_anchor = None
            self._resize_edge_state = None
            self.xy0 = self._event_to_image_xy(event)
            self.xy1 = self.xy0.copy()
            self._cartesian_to_polar()

    def _on_roi_mouse_drag(self, event):
        self.hover_pos = None
        pos = self._event_to_image_xy(event)
        h = self._drag_handle
        if h == "new":
            self.xy1 = pos
        elif h in ("tl", "tr", "bl", "br"):
            self.xy0 = self._resize_anchor.copy()
            self.xy1 = pos
        elif h == "t":
            a0, a1, y_fixed = self._resize_edge_state
            self.xy0 = np.array([a0, pos[Y]])
            self.xy1 = np.array([a1, y_fixed])
        elif h == "b":
            a0, a1, y_fixed = self._resize_edge_state
            self.xy0 = np.array([a0, y_fixed])
            self.xy1 = np.array([a1, pos[Y]])
        elif h == "l":
            a0, a1, x_fixed = self._resize_edge_state
            self.xy0 = np.array([pos[X], a0])
            self.xy1 = np.array([x_fixed, a1])
        elif h == "r":
            a0, a1, x_fixed = self._resize_edge_state
            self.xy0 = np.array([x_fixed, a0])
            self.xy1 = np.array([pos[X], a1])
        self._cartesian_to_polar()

    def _save_roi(self):
        """Clip xy0/xy1 to valid image area and persist to config."""
        if self.xy0 is None or self.clip_pos is None or self.clip_size is None:
            return
        self.xy0 = np.clip(self.xy0, self.clip_pos, self.clip_pos + self.clip_size)
        self.xy1 = np.clip(self.xy1, self.clip_pos, self.clip_pos + self.clip_size)
        self._cartesian_to_polar()
        if all(abs(self.xy0 - self.xy1) != 0):
            xy0, xy1 = self._polar_to_cartesian_at_angle(0)
            # Cast to int: cv2.warpAffine needs integer (w,h); floats raise and
            # are swallowed by the broad except, freezing the preview.
            roi_xy = (np.minimum(xy0, xy1) - self.img_pos).astype(int).tolist()
            roi_wh = np.abs(xy0 - xy1).astype(int).tolist()
            self.config.roi_window_x, self.config.roi_window_y = roi_xy
            self.config.roi_window_w, self.config.roi_window_h = roi_wh
            self._schedule_main_config_save()

    def _on_roi_mouse_up(self, event):
        self.is_mouse_up = True
        if self._drag_handle == "new":
            self.xy1 = self._event_to_image_xy(event)
        self._save_roi()

    def _on_roi_mouse_move(self, event):
        if not self.is_mouse_up:
            return
        self.hover_pos = self._event_to_image_xy(event)
        if self.padded_size is not None and any(self.hover_pos > self.padded_size):
            self.hover_pos = None
        handle = self._get_handle_at(event.x, event.y)
        cursors = {
            "tl": "top_left_corner", "tr": "top_right_corner",
            "bl": "bottom_left_corner", "br": "bottom_right_corner",
            "t": "sb_v_double_arrow", "b": "sb_v_double_arrow",
            "l": "sb_h_double_arrow", "r": "sb_h_double_arrow",
        }
        self.roi_canvas.configure(cursor=cursors.get(handle, "crosshair"))

    def clear_crop(self):
        """Reset the crop box for this eye."""
        self.xy0 = None
        self.xy1 = None
        self.cr = None
        self.ca = None
        self.roi_size = None
        self.config.roi_window_x = 0
        self.config.roi_window_y = 0
        self.config.roi_window_w = 0
        self.config.roi_window_h = 0
        self._schedule_main_config_save()

    def _format_fps(self, fps):
        return f"{round(fps)} Fps"

    def _format_latency(self, latency_ms):
        # Tracking pipeline can be sub-ms when algos are light, so show one
        # decimal under 10ms and round above; that keeps the readout honest.
        if latency_ms < 10.0:
            return f"{latency_ms:.1f} ms lat"
        return f"{latency_ms:.0f} ms lat"

    def _cartesian_to_polar(self):
        # roi_image_center is None until the first ROI-mode frame populates it
        # in render_tick. In bigscreen mode the right eye widget can stay None
        # past the first user click (shared-camera roi_queue ordering), so a
        # drag in that window used to crash with `float - NoneType`. Defer the
        # conversion to the next event with a valid center.
        if self.xy0 is None or self.xy1 is None or self.roi_image_center is None:
            return
        roi_center = (self.xy0 + self.xy1) / 2 - self.roi_image_center
        self.cr = np.linalg.norm(roi_center)
        self.ca = math.atan2(roi_center[Y], roi_center[X]) + math.radians(
            self.config.rotation_angle
        )
        self.roi_size = np.abs(self.xy1 - self.xy0)

    def _polar_to_cartesian_at_angle(self, rotation_angle_radians):
        if (
            self.cr is None
            or self.ca is None
            or self.roi_size is None
            or self.roi_image_center is None
        ):
            return (None, None)
        ca = self.ca - rotation_angle_radians
        cx = math.cos(ca) * self.cr + self.roi_image_center[X]
        cy = math.sin(ca) * self.cr + self.roi_image_center[Y]
        roi_pos = np.array((int(cx), int(cy))) - self.roi_size // 2
        return (roi_pos, roi_pos + self.roi_size)

    def _polar_to_cartesian(self):
        if not (self.cr is None or self.ca is None or self.roi_size is None):
            (self.xy0), (self.xy1) = self._polar_to_cartesian_at_angle(
                math.radians(self.config.rotation_angle)
            )

    def started(self):
        return not self.cancellation_event.is_set()

    def start(self, run_camera_thread: bool = True):
        # If we're already running, bail
        if not self.cancellation_event.is_set():
            return
        self.cancellation_event.clear()
        self.tracking_thread = Thread(target=self.ransac.run)
        self.tracking_thread.start()
        if run_camera_thread:
            self.camera_thread = Thread(target=self.camera.run)
            self.camera_thread.start()
        else:
            self.camera_thread = None

    def request_stop(self):
        """Signal camera/tracking workers without waiting for native I/O.

        Network VideoCapture calls cannot be interrupted reliably on every
        OpenCV/FFmpeg build.  Keeping signalling separate lets application
        shutdown cancel both eyes before it waits for either one.
        """
        self.detach_shared_capture_event()
        self.camera.set_extra_output_queues([])
        self.cancellation_event.set()
        # Wake processors that may be waiting for the next captured frame.
        self.capture_event.set()

    def stop(self, join_timeout: float = 5.0, warn_if_alive: bool = True):
        self.request_stop()
        deadline = time.monotonic() + max(0.0, join_timeout)
        if self.tracking_thread is not None:
            self.tracking_thread.join(
                timeout=max(0.0, deadline - time.monotonic())
            )
            if warn_if_alive and self.tracking_thread.is_alive():
                logger.warning("Tracking thread (%s) did not exit within timeout", self.eye_id)
            self.tracking_thread = None
        if self.camera_thread is not None:
            self.camera_thread.join(
                timeout=max(0.0, deadline - time.monotonic())
            )
            if warn_if_alive and self.camera_thread.is_alive():
                logger.warning("Camera thread (%s) did not exit within timeout", self.eye_id)
            self.camera_thread = None

    def on_config_update(self, data):
        keys = set(data.keys())
        model_keys = set(self.config.model_fields.keys())
        # Restart only when this eye's camera config changed.
        if model_keys.intersection(keys):
            self.stop()
            self.start()

    def recenter_eyes(self):
        self.settings.gui_recenter_eyes = True

    def recalibrate_eyes(self):
        self.ransac.cal.xs = []
        self.ransac.cal.ys = []
        self.ransac.cal.fitted = False
        self.ransac.calibration_start_time = time.time()
        self.ransac.ibo.clear_filter()
        PlaySound(resource_path("Audio/start.wav"), SND_FILENAME | SND_ASYNC)
        self._sync_calibration_toggle_button()

    def osc_recenter_eyes(self, osc_message: OSCMessage):
        if not isinstance(osc_message.data, bool):
            return  # just incase we get anything other than bool

        if osc_message.data:
            self.recenter_eyes()

    def render_tick(self):
        changed = False

        # The capture thread rebound our uvc:name@address source to a fresh device
        # address (camera replugged into a different USB port) and rewrote
        # config.capture_source in place. Persist it to disk here (on the GUI
        # thread, debounced, and only once frames are confirmed flowing) so the
        # rebind survives restarts without the user re-selecting anything.
        if (
            getattr(self.camera, "uvc_rebind_pending", False)
            and self.camera.camera_status == CameraState.CONNECTED
        ):
            self.camera.uvc_rebind_pending = False
            addr_var = getattr(self, "camera_addr_var", None)
            new_source = self.config.capture_source
            if addr_var is not None and new_source:
                addr_var.set(str(new_source))
            self._schedule_main_config_save()
            logger.info(
                "Persisted auto-rebound capture source for %s: %s",
                self.eye_id, new_source,
            )

        if self.settings.gui_disable_gui == False:
            if self.config.rotation_angle != int(self.rotation_var.get()):
                self.config.rotation_angle = int(self.rotation_var.get())
                changed = True
                self.cartesian_needs_update = True

            if self.config.gui_rotation_ui_padding != bool(self.padding_var.get()):
                self.config.gui_rotation_ui_padding = bool(self.padding_var.get())
                changed = True
                self.cartesian_needs_update = True

            if changed:
                self._schedule_main_config_save()

            needs_roi_set = (
                self.config.roi_window_h <= 0 or self.config.roi_window_w <= 0
            )

            mode_readout = ""
            fps_readout = ""
            latency_readout = ""
            if self.config.capture_source is None or self.config.capture_source == "":
                mode_readout = tr("camera.status_no_camera")
                self.roi_message_label.pack_forget()
                # Don't pack_forget the canvas: the fixed-height graph_row absorbs size
                # changes but the canvas would still briefly vanish and reappear, which
                # reads as "the widget is moving" when it's not. Hide its viz contents
                # instead so the area stays reserved and visually stable.
                self._hide_output_viz()
            elif self._effective_camera_status() == CameraState.CONNECTING:
                mode_readout = tr("camera.status_connecting")
            elif self._effective_camera_status() == CameraState.DISCONNECTED:
                mode_readout = tr("camera.status_reconnecting")
            elif needs_roi_set:
                mode_readout = tr("camera.status_awaiting_crop")
            elif self.ransac.calibration_start_time != None:
                mode_readout = tr("camera.status_calibration")
            else:
                mode_readout = tr("camera.status_tracking")
                fps_readout = self._format_fps(self.ransac.output_fps)
                latency_readout = self._format_latency(self.ransac.output_latency_ms)

            if mode_readout != self._last_mode_readout:
                self._last_mode_readout = mode_readout
                self.mode_var.set(mode_readout)
            if fps_readout != self._last_fps_readout:
                self._last_fps_readout = fps_readout
                self.fps_var.set(fps_readout)
            if latency_readout != self._last_latency_readout:
                self._last_latency_readout = latency_readout
                self.latency_var.set(latency_readout)

            self._sync_calibration_toggle_button()

            if self.in_roi_mode:
                # Drain to latest frame: tracking thread does not consume capture_queue in ROI mode, but it was
                # still calling capture_event.set() every loop while capture_queue stayed empty, flooding this queue.
                # Single try/except cuts ~one Empty-throw per drained frame vs. the nested form.
                maybe_image = None
                try:
                    while True:
                        maybe_image = self.roi_queue.get_nowait()
                except Empty:
                    pass
                try:
                    if maybe_image:
                        image = maybe_image[0]

                        img_h, img_w, _ = image.shape

                        hyp = math.ceil((img_w**2 + img_h**2) ** 0.5)
                        rotation_matrix = cv2.getRotationMatrix2D(
                            ((img_w / 2), (img_h / 2)), self.config.rotation_angle, 1
                        )

                        x_coords, y_coords = np.matmul(
                            rotation_matrix,
                            np.transpose(
                                [
                                    [0, 0, 1],
                                    [img_w, 0, 1],
                                    [0, img_h, 1],
                                    [img_w, img_h, 1],
                                ]
                            ),
                        )

                        self.clip_size = np.array(
                            [
                                math.ceil(max(x_coords) - min(x_coords)),
                                math.ceil(max(y_coords) - min(y_coords)),
                            ]
                        )
                        if self.config.gui_rotation_ui_padding:
                            self.padded_size = np.array([hyp, hyp])

                        else:
                            self.padded_size = self.clip_size

                        self.img_pos = ((self.padded_size - (img_w, img_h)) / 2).astype(
                            np.int32
                        )

                        self.clip_pos = (
                            (self.padded_size - self.clip_size) / 2
                        ).astype(np.int32)

                        self.roi_image_center = self.padded_size / 2

                        # deferred to after roi_image_center is updated
                        if self.cartesian_needs_update:
                            self._polar_to_cartesian()
                            self.cartesian_needs_update = False

                        pad_matrix = np.float32(
                            [
                                [1, 0, self.img_pos[X]],
                                [0, 1, self.img_pos[Y]],
                                [0, 0, 1],
                            ]
                        )
                        rotation_matrix_padded = cv2.getRotationMatrix2D(
                            self.roi_image_center, self.config.rotation_angle, 1
                        )
                        matrix = np.matmul(rotation_matrix_padded, pad_matrix)

                        image = cv2.warpAffine(
                            image,
                            matrix,
                            self.padded_size,
                            borderMode=cv2.BORDER_CONSTANT,
                            borderValue=(128, 128, 128),
                        )

                        # Fit the (possibly large) warped image into the compact
                        # ROI canvas. Scale uniformly so longest side == cap,
                        # upscaling small cameras to fill the preview area.
                        # xy0/xy1 stay in image coords; only displayed pixels scale.
                        ps_img = tuple(int(x) for x in self.padded_size)
                        max_dim = max(ps_img) if max(ps_img) > 0 else 1
                        scale = self._ROI_CANVAS_MAX_DIM / max_dim
                        canvas_size = (
                            max(1, int(round(ps_img[0] * scale))),
                            max(1, int(round(ps_img[1] * scale))),
                        )
                        if scale != 1.0:
                            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                            image = cv2.resize(image, canvas_size, interpolation=interp)
                        self._roi_display_scale = scale

                        maybe_image = (image, *maybe_image[1:])

                        if getattr(self, "_last_roi_padded_size", None) != canvas_size:
                            self.roi_canvas.delete("all")
                            self._roi_canvas_image_id = None
                            self._last_roi_padded_size = canvas_size
                            self.roi_canvas.configure(
                                width=canvas_size[0], height=canvas_size[1]
                            )
                        else:
                            self.roi_canvas.delete(self._roi_overlay_tag)

                        photo = self._tk_photo_from_bgr(maybe_image[0], self.roi_canvas)
                        if photo is not None:
                            self._roi_photo = photo
                            if self._roi_canvas_image_id is None:
                                self._roi_canvas_image_id = (
                                    self.roi_canvas.create_image(
                                        0, 0, image=self._roi_photo, anchor="nw"
                                    )
                                )
                            else:
                                self.roi_canvas.itemconfigure(
                                    self._roi_canvas_image_id, image=self._roi_photo
                                )

                        if self.xy0 is None or self.xy1 is None:
                            # roi_window rotates around roi center, we rotate around image center
                            roi_window_pos = (
                                self.config.roi_window_x,
                                self.config.roi_window_y,
                            )
                            roi_window_size = (
                                self.config.roi_window_w,
                                self.config.roi_window_h,
                            )
                            self.xy0 = roi_window_pos + self.img_pos
                            self.xy1 = self.xy0 + roi_window_size
                            self._cartesian_to_polar()
                            self.ca -= math.radians(self.config.rotation_angle)
                            self._polar_to_cartesian()

                        # xy0/xy1/hover_pos are in image coords; multiply by
                        # _roi_display_scale to land on canvas pixels.
                        s = self._roi_display_scale
                        if self.xy0 is not None and self.xy1 is not None:
                            bx0 = int(min(self.xy0[X], self.xy1[X]) * s)
                            by0 = int(min(self.xy0[Y], self.xy1[Y]) * s)
                            bx1 = int(max(self.xy0[X], self.xy1[X]) * s)
                            by1 = int(max(self.xy0[Y], self.xy1[Y]) * s)
                            self.roi_canvas.create_rectangle(
                                bx0, by0, bx1, by1,
                                outline="#7f78ff",
                                tags=self._roi_overlay_tag,
                            )
                            # draw resize handles at corners and edge midpoints
                            hr = max(3, round(4 * self._dpi_scale))
                            mx, my = (bx0 + bx1) // 2, (by0 + by1) // 2
                            for hx, hy in [
                                (bx0, by0), (bx1, by0), (bx0, by1), (bx1, by1),
                                (mx, by0), (mx, by1), (bx0, my), (bx1, my),
                            ]:
                                self.roi_canvas.create_rectangle(
                                    hx - hr, hy - hr, hx + hr, hy + hr,
                                    outline="#ffffff", fill="#7f78ff",
                                    tags=self._roi_overlay_tag,
                                )
                        if self.is_mouse_up and self.hover_pos is not None:
                            hx = int(self.hover_pos[X] * s)
                            hy = int(self.hover_pos[Y] * s)
                            self.roi_canvas.create_line(
                                hx, 0, hx, canvas_size[1],
                                fill="#ffffff",
                                tags=self._roi_overlay_tag,
                            )
                            self.roi_canvas.create_line(
                                0, hy, canvas_size[0], hy,
                                fill="#ffffff",
                                tags=self._roi_overlay_tag,
                            )
                finally:
                    # Pace the capture thread to the GUI tick; only the ROI branch should signal while in ROI mode.
                    self.capture_event.set()
            else:
                if needs_roi_set:
                    # Keep the canvas mapped (fixed-height row, no layout shift). Hide its
                    # viz contents and show the hint label next to it.
                    self._hide_output_viz()
                    if not self.roi_message_label.winfo_ismapped():
                        self.roi_message_label.pack(side="left", padx=10)
                    return
                try:
                    self.roi_message_label.pack_forget()
                    (maybe_image, eye_info) = self.image_queue.get(block=False)

                    # Always update the small eye preview (left half = processed eye image).
                    _dim = self._preview_dim
                    _eye_img = maybe_image[:, :maybe_image.shape[1] // 2] if maybe_image.ndim == 2 else maybe_image
                    _interp = cv2.INTER_AREA if _eye_img.shape[0] > _dim else cv2.INTER_LINEAR
                    _preview = cv2.resize(_eye_img, (_dim, _dim), interpolation=_interp)
                    _preview_photo = self._tk_photo_from_bgr(_preview, self._eye_preview_widget)
                    if _preview_photo is not None:
                        self._eye_preview_photo = _preview_photo
                        self._eye_preview_widget.configure(image=self._eye_preview_photo)

                    # Full debug image, shown only when the setting is on.
                    debug_on = bool(self.settings_config.gui_show_et_debug)
                    if self._debug_image_visible != debug_on:
                        self._debug_image_visible = debug_on
                        if debug_on:
                            self._tracking_image_holder.pack(
                                padx=4, pady=2, anchor="w", before=self._graph_row
                            )
                        else:
                            self._tracking_image_holder.pack_forget()

                    if debug_on:
                        tw, th = self._tracking_display_size
                        if maybe_image.shape[1] == tw and maybe_image.shape[0] == th:
                            disp = maybe_image
                        else:
                            disp = cv2.resize(
                                maybe_image, (tw, th), interpolation=cv2.INTER_LINEAR
                            )
                        photo = self._tk_photo_from_bgr(disp, self.tracking_image_widget)
                        if photo is not None:
                            self._tracking_photo = photo
                            self.tracking_image_widget.configure(image=self._tracking_photo)

                    self._draw_output_visualization(eye_info)

                except Empty:
                    pass

        else:

            def back(*args):
                pass

            try:
                self.roi_message_label.pack_forget()
                self._hide_output_viz()
                (maybe_image, eye_info) = self.image_queue.get(block=False)

            except Empty:
                pass
