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
import numpy as np
from PIL import Image, ImageTk


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
        self.gui_mask_markup = f"-MARKUP{widget_id}-"
        self.gui_mask_lighten = f"-LIGHTEN{widget_id}-"

        self.last_eye_info = None
        self.osc_queue = osc_queue
        self.main_config = main_config
        self.eye_id = widget_id
        self.settings_config = main_config.settings
        self.configl = main_config.left_eye
        self.configr = main_config.right_eye
        self.settings = main_config.settings
        if self.eye_id == EyeId.RIGHT:
            self.config = main_config.right_eye
        elif self.eye_id == EyeId.LEFT:
            self.config = main_config.left_eye
        else:
            raise RuntimeError("\033[91m[WARN] Cannot have a camera widget represent both eyes!\033[0m")

        self.cancellation_event = Event()
        # Set the event until start is called, otherwise we can block if shutdown is called.
        self.cancellation_event.set()
        self.capture_event = Event()
        self.capture_queue = Queue(maxsize=2)
        self.roi_queue = Queue(maxsize=2)

        self.image_queue = Queue(maxsize=2)
        self.uses_shared_capture_event = False

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
        self.movavg_fps_queue = deque(maxlen=120)
        self.movavg_bps_queue = deque(maxlen=120)
        self._tracking_photo = None
        self._roi_photo = None
        self.frame = None
        self._config_save_after_id = None
        self._last_fps_readout = ""
        self._last_bps_readout = ""
        self._last_mode_readout = ""
        self._last_calibration_btn_text = None
        self._viz_item_ids = None
        self._roi_canvas_image_id = None
        self._roi_overlay_tag = "roi_overlay"
        self.camera_thread: Thread | None = None

    def build(self, parent, show_camera_controls=True):
        self.frame = ttk.Frame(parent)

        if show_camera_controls:
            top_row = ttk.Frame(self.frame)
            top_row.pack(fill="x", padx=8, pady=4)
            ttk.Label(top_row, text="Camera Address").pack(side="left")
            self.camera_addr_var = tk.StringVar(value=str(self.config.capture_source or ""))
            ttk.Entry(top_row, textvariable=self.camera_addr_var, width=36).pack(side="left", padx=8)
            ttk.Button(top_row, text="Save and Restart Tracking", command=self._save_tracking).pack(side="left", padx=8)

        mode_row = ttk.Frame(self.frame)
        mode_row.pack(fill="x", padx=8, pady=4)
        self._mode_tracking_btn = ttk.Button(mode_row, text="Tracking Mode", command=self._set_tracking_mode)
        self._mode_tracking_btn.pack(side="left", padx=4)
        self._mode_roi_btn = ttk.Button(mode_row, text="Cropping Mode", command=self._set_roi_mode)
        self._mode_roi_btn.pack(side="left", padx=4)
        self._sync_mode_tab_buttons()

        self.tracking_frame = ttk.Frame(self.frame)
        self.roi_frame = ttk.Frame(self.frame)
        self.tracking_frame.pack(fill="both", expand=True)

        tracking_controls = ttk.Frame(self.tracking_frame)
        tracking_controls.pack(fill="x", padx=8, pady=4)
        self._calibration_toggle_btn = ttk.Button(
            tracking_controls,
            text="Start Calibration",
            command=self._on_calibration_toggle,
        )
        self._calibration_toggle_btn.pack(side="left", padx=4)
        ttk.Button(tracking_controls, text="Recenter Eyes", command=self.recenter_eyes).pack(side="left", padx=4)

        status_row = ttk.Frame(self.tracking_frame)
        status_row.pack(fill="x", padx=8, pady=4)
        ttk.Label(status_row, text="Mode:").pack(side="left")
        self.mode_var = tk.StringVar(value="Calibrating")
        self.fps_var = tk.StringVar(value="")
        self.bps_var = tk.StringVar(value="")
        ttk.Label(status_row, textvariable=self.mode_var).pack(side="left", padx=4)
        ttk.Label(status_row, textvariable=self.fps_var).pack(side="left", padx=8)
        ttk.Label(status_row, textvariable=self.bps_var).pack(side="left", padx=8)

        # Source stack from processor is 300×150; compact display for dual-eye layout
        self._tracking_display_size = (300, 150)

        self._viz_pad = 8
        self._viz_gaze = 148
        self._viz_gaze_gap = 10
        self._viz_blink_w = 24
        self._viz_canvas_w = self._viz_pad * 2 + self._viz_gaze + self._viz_gaze_gap + self._viz_blink_w
        self._viz_canvas_h = self._viz_pad * 2 + self._viz_gaze

        self.tracking_image_widget = tk.Label(self.tracking_frame)
        self.tracking_image_widget.pack(padx=8, pady=4, anchor="w")

        graph_row = ttk.Frame(self.tracking_frame)
        graph_row.pack(fill="x", padx=8, pady=4)
        self.output_canvas = tk.Canvas(
            graph_row,
            width=self._viz_canvas_w,
            height=self._viz_canvas_h,
            bg="#1e1f23",
            highlightthickness=0,
        )
        self.output_canvas.pack(side="left")
        self.roi_message_var = tk.StringVar(value="Please set an Eye Cropping.")
        self.roi_message_label = ttk.Label(graph_row, textvariable=self.roi_message_var)
        self.roi_message_label.pack(side="left", padx=10)
        self.roi_message_label.pack_forget()

        roi_controls = ttk.Frame(self.roi_frame)
        roi_controls.pack(fill="x", padx=8, pady=4)
        ttk.Label(roi_controls, text="Rotation").pack(side="left")
        self.rotation_var = tk.IntVar(value=int(self.config.rotation_angle))
        ttk.Scale(roi_controls, from_=0, to=360, variable=self.rotation_var, orient="horizontal", length=160).pack(
            side="left", padx=8
        )
        self.rotation_readout_var = tk.StringVar(value=str(int(self.rotation_var.get())))

        def sync_rotation_readout(*_args):
            self.rotation_readout_var.set(str(int(round(float(self.rotation_var.get())))))

        def bump_rotation(delta):
            next_val = int(round(float(self.rotation_var.get()))) + delta
            next_val = max(0, min(360, next_val))
            self.rotation_var.set(next_val)

        ttk.Button(roi_controls, text="-", width=2, command=lambda: bump_rotation(-1)).pack(side="left", padx=(4, 2))
        ttk.Label(roi_controls, textvariable=self.rotation_readout_var, width=6, anchor="center").pack(side="left", padx=2)
        ttk.Button(roi_controls, text="+", width=2, command=lambda: bump_rotation(1)).pack(side="left", padx=(2, 8))
        self.rotation_var.trace_add("write", sync_rotation_readout)
        self.padding_var = tk.BooleanVar(value=bool(self.config.gui_rotation_ui_padding))
        ttk.Checkbutton(roi_controls, text="Camera Widget Padding", variable=self.padding_var).pack(side="left", padx=8)

        self.roi_canvas = tk.Canvas(self.roi_frame, width=640, height=480, bg="#424042", highlightthickness=0)
        self.roi_canvas.pack(padx=8, pady=4, anchor="w")
        self.roi_canvas.bind("<ButtonPress-1>", self._on_roi_mouse_down)
        self.roi_canvas.bind("<B1-Motion>", self._on_roi_mouse_drag)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_roi_mouse_up)
        self.roi_canvas.bind("<Motion>", self._on_roi_mouse_move)
        return self.frame

    def _sync_mode_tab_buttons(self) -> None:
        """Sun Valley accent on the active Tracking vs Cropping tab."""
        if self.in_roi_mode:
            self._mode_roi_btn.configure(style="Accent.TButton")
            self._mode_tracking_btn.configure(style="TButton")
        else:
            self._mode_tracking_btn.configure(style="Accent.TButton")
            self._mode_roi_btn.configure(style="TButton")

    def _tk_photo_from_bgr(self, image: np.ndarray, master: tk.Misc) -> ImageTk.PhotoImage | None:
        if image is None or image.size == 0 or image.shape[0] < 1 or image.shape[1] < 1:
            return None
        try:
            if image.ndim == 2:
                pil_img = Image.fromarray(image, mode="L").convert("RGB")
            elif image.ndim == 3 and image.shape[2] == 4:
                bgr = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
            elif image.ndim == 3 and image.shape[2] == 3:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
            else:
                return None
            return ImageTk.PhotoImage(pil_img, master=master)
        except (ValueError, TypeError, tk.TclError):
            return None

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
        tick = "#6d7285"
        dot = "#f4f2ff"
        ring_col = "#b49cff"
        c.configure(bg=bg)
        self._viz_item_ids = {
            "fail_bg": c.create_rectangle(0, 0, W, H, outline="", fill=fail_bg, tags="viz_fail"),
            "fail_txt": c.create_text(W // 2, H // 2, text="No track", fill=fail_fg, font=("Segoe UI", 9), tags="viz_fail"),
            "bg": c.create_rectangle(0, 0, W, H, outline="", fill=bg, tags="viz_main"),
            "panel": c.create_rectangle(0, 0, 0, 0, outline=panel_border, width=1, fill=panel, tags="viz_main"),
            "cross_v": c.create_line(0, 0, 0, 0, fill=cross, width=1, tags="viz_main"),
            "cross_h": c.create_line(0, 0, 0, 0, fill=cross, width=1, tags="viz_main"),
            "ring": c.create_oval(0, 0, 0, 0, outline=ring_col, width=2, fill="", tags="viz_main"),
            "dot": c.create_oval(0, 0, 0, 0, fill=dot, outline=dot, tags="viz_main"),
            "blink_track": c.create_rectangle(0, 0, 0, 0, outline=track_border, width=1, fill=track_fill, tags="viz_main"),
            "blink_bar": c.create_rectangle(0, 0, 0, 0, fill=blink_fill_col, outline="", tags="viz_main", state="hidden"),
            "tick_t": c.create_line(0, 0, 0, 0, fill=tick, width=1, tags="viz_main"),
            "tick_b": c.create_line(0, 0, 0, 0, fill=tick, width=1, tags="viz_main"),
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

        c.coords(ids["tick_t"], bx0 + bw // 2 - 4, by0 + inset, bx0 + bw // 2 + 4, by0 + inset)
        c.coords(ids["tick_b"], bx0 + bw // 2 - 4, by0 + bh - inset, bx0 + bw // 2 + 4, by0 + bh - inset)

    def _set_tracking_mode(self):
        print("\033[94m[INFO] Moving to tracking mode\033[0m")
        self.in_roi_mode = False
        self.ransac.suppress_auto_capture_signal = False
        self.camera.set_output_queue(self.capture_queue)
        self.roi_frame.pack_forget()
        self.tracking_frame.pack(fill="both", expand=True)
        self._sync_mode_tab_buttons()

    def _set_roi_mode(self):
        print("\033[94m[INFO] Move to roi mode\033[0m")
        self.in_roi_mode = True
        self.ransac.suppress_auto_capture_signal = True
        self.camera.set_output_queue(self.roi_queue)
        self.tracking_frame.pack_forget()
        self.roi_frame.pack(fill="both", expand=True)
        self._sync_mode_tab_buttons()

    def _save_tracking(self):
        value = self.camera_addr_var.get()
        if value == str(self.config.capture_source or ""):
            return
        try:
            new_source = int(value)
        except ValueError:
            if value == "":
                new_source = None
            elif len(value) > 5 and "http" not in value and ".mp4" not in value and "/dev" not in value:
                new_source = f"http://{value}/"
            else:
                new_source = value

        if new_source == self.config.capture_source:
            return

        print("\033[94m[INFO] New value: {}\033[0m".format(new_source))

        # Run the apply/restart off the Tk thread: update_eye_model_config notifies listeners
        # (including on_config_update, which stops/starts the camera), and stop() joins the
        # camera thread — which can block briefly on close/open. We don't want to freeze the GUI.
        def _apply():
            try:
                self.main_config.update_eye_model_config(
                    self.eye_id, {"capture_source": new_source}
                )
            except Exception as exc:
                print(f"\033[93m[WARN] Failed to apply new capture source: {exc}\033[0m")

        Thread(target=_apply, daemon=True, name=f"CameraSourceApply-{self.eye_id}").start()

    def _stop_calibration(self):
        self.ransac.calibration_start_time = None
        self._sync_calibration_toggle_button()

    def detach_shared_capture_event(self) -> None:
        if not self.uses_shared_capture_event:
            return
        ev = Event()
        self.capture_event = ev
        self.ransac.capture_event = ev
        self.uses_shared_capture_event = False

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

    def _on_roi_mouse_down(self, event):
        self.hover_pos = None
        self.is_mouse_up = False
        self.xy0 = np.array((event.x, event.y))
        self.xy1 = np.array((event.x, event.y))
        self._cartesian_to_polar()

    def _on_roi_mouse_drag(self, event):
        self.hover_pos = None
        self.xy1 = np.array((event.x, event.y))
        self._cartesian_to_polar()

    def _on_roi_mouse_up(self, event):
        self.is_mouse_up = True
        self.xy1 = np.array((event.x, event.y))
        if self.xy0 is None or self.clip_pos is None or self.clip_size is None:
            return
        self.xy0 = np.clip(self.xy0, self.clip_pos, self.clip_pos + self.clip_size)
        self.xy1 = np.clip(self.xy1, self.clip_pos, self.clip_pos + self.clip_size)
        self._cartesian_to_polar()
        if all(abs(self.xy0 - self.xy1) != 0):
            xy0, xy1 = self._polar_to_cartesian_at_angle(0)
            self.config.roi_window_x, self.config.roi_window_y = (np.minimum(xy0, xy1) - self.img_pos).tolist()
            self.config.roi_window_w, self.config.roi_window_h = (np.abs(xy0 - xy1)).tolist()
            self._schedule_main_config_save()

    def _on_roi_mouse_move(self, event):
        if not self.is_mouse_up:
            return
        self.hover_pos = np.array((event.x, event.y))
        if self.padded_size is not None and any(self.hover_pos > self.padded_size):
            self.hover_pos = None

    def _movavg_fps(self, next_fps):
        self.movavg_fps_queue.append(next_fps)
        fps = round(sum(self.movavg_fps_queue) / len(self.movavg_fps_queue))
        millisec = round((1 / fps if fps else 0) * 1000)
        return f"{fps} Fps {millisec} ms"

    def _movavg_bps(self, next_bps):
        self.movavg_bps_queue.append(next_bps)
        return f"{sum(self.movavg_bps_queue) / len(self.movavg_bps_queue) * 0.001 * 0.001 * 8:.3f} Mbps"

    def _cartesian_to_polar(self):
        if not (self.xy0 is None or self.xy1 is None):
            roi_center = (self.xy0 + self.xy1) / 2 - self.roi_image_center
            self.cr = np.linalg.norm(roi_center)
            self.ca = math.atan2(roi_center[Y], roi_center[X]) + math.radians(self.config.rotation_angle)
            self.roi_size = np.abs(self.xy1 - self.xy0)

    def _polar_to_cartesian_at_angle(self, rotation_angle_radians):
        if not (self.cr is None or self.ca is None or self.roi_size is None):
            ca = self.ca - rotation_angle_radians
            cx = math.cos(ca) * self.cr + self.roi_image_center[X]
            cy = math.sin(ca) * self.cr + self.roi_image_center[Y]
            roi_pos = np.array((int(cx), int(cy))) - self.roi_size // 2
            return (roi_pos, roi_pos + self.roi_size)
        else:
            return (None, None)

    def _polar_to_cartesian(self):
        if not (self.cr is None or self.ca is None or self.roi_size is None):
            (self.xy0), (self.xy1) = self._polar_to_cartesian_at_angle(math.radians(self.config.rotation_angle))

    def started(self):
        return not self.cancellation_event.is_set()

    def start(self, run_camera_thread: bool = True):
        # If we're already running, bail
        if not self.cancellation_event.is_set():
            return
        self.cancellation_event.clear()
        self.ransac_thread = Thread(target=self.ransac.run)
        self.ransac_thread.start()
        if run_camera_thread:
            self.camera_thread = Thread(target=self.camera.run)
            self.camera_thread.start()
        else:
            self.camera_thread = None

    def stop(self):
        # If we're not running yet, bail
        if self.cancellation_event.is_set():
            return
        self.detach_shared_capture_event()
        self.camera.set_extra_output_queues([])
        self.cancellation_event.set()
        self.ransac_thread.join()
        if self.camera_thread is not None:
            self.camera_thread.join()
            self.camera_thread = None

    def on_config_update(self, data):
        keys = set(data.keys())
        model_keys = set(self.config.model_fields.keys())
        # we only want to restart our stuff, if our stuff got updated
        # at the model level
        if model_keys.intersection(keys):
            self.stop()
            self.start()

    def recenter_eyes(self):
        self.settings.gui_recenter_eyes = True

    def recalibrate_eyes(self):
        self.ransac.calibration_start_time = time.time()
        self.ransac.ibo.clear_filter()
        PlaySound(resource_path("Audio/start.wav"), SND_FILENAME | SND_ASYNC)
        self._sync_calibration_toggle_button()

    def osc_recenter_eyes(self, osc_message: OSCMessage):
        if not isinstance(osc_message.data, bool):
            return  # just incase we get anything other than bool

        if osc_message.data:
            self.recenter_eyes()

    def osc_recalibrate_eyes(self, osc_message: OSCMessage):
        if not isinstance(osc_message.data, bool):
            return  # just incase we get anything other than bool

        if osc_message.data:
            self.recalibrate_eyes()

    def render_tick(self):
        changed = False

        if self.settings.gui_disable_gui == False:
            if self.config.rotation_angle != int(self.rotation_var.get()):
                self.config.rotation_angle = int(self.rotation_var.get())
                changed = True
                self.cartesian_needs_update = True

            if self.config.gui_rotation_ui_padding != bool(self.padding_var.get()):
                self.config.gui_rotation_ui_padding = bool(self.padding_var.get())
                changed = True
                self.cartesian_needs_update = True

            # if self.config.gui_circular_crop != values[self.gui_circular_crop]:
            #     self.config.gui_circular_crop = values[self.gui_circular_crop]
            #    changed = True

            if changed:
                self._schedule_main_config_save()

            needs_roi_set = self.config.roi_window_h <= 0 or self.config.roi_window_w <= 0

            mode_readout = ""
            fps_readout = ""
            bps_readout = ""
            if self.config.capture_source is None or self.config.capture_source == "":
                mode_readout = "Waiting for camera address"
                self.roi_message_label.pack_forget()
                self.output_canvas.pack_forget()
            elif self.camera.camera_status == CameraState.CONNECTING:
                mode_readout = "Camera Connecting"
            elif self.camera.camera_status == CameraState.DISCONNECTED:
                mode_readout = "Camera Reconnecting..."

            elif needs_roi_set:
                mode_readout = "Awaiting Eye Crop"
            elif self.ransac.calibration_start_time != None:
                mode_readout = "Calibration"
            else:
                mode_readout = "Tracking"
                fps_readout = self._movavg_fps(self.camera.fps)
                bps_readout = self._movavg_bps(self.camera.bps)

            if mode_readout != self._last_mode_readout:
                self._last_mode_readout = mode_readout
                self.mode_var.set(mode_readout)
            if fps_readout != self._last_fps_readout:
                self._last_fps_readout = fps_readout
                self.fps_var.set(fps_readout)
            if bps_readout != self._last_bps_readout:
                self._last_bps_readout = bps_readout
                self.bps_var.set(bps_readout)

            self._sync_calibration_toggle_button()

            #    if event == self.gui_mask_lighten:
            #       while True:
            #          try:
            #             maybe_image = self.roi_queue.get(block=False)
            #            imgbytes = cv2.imencode(".ppm", maybe_image[0])[1].tobytes()
            #           image = cv2.imdecode(
            #              np.frombuffer(imgbytes, np.uint8), cv2.IMREAD_COLOR
            #         )

            #        cv2.imshow("Image", image)
            #       cv2.waitKey(1)
            #      cv2.destroyAllWindows()
            #     print("lighen")
            # except Empty:
            #   pass
            # if event == self.gui_mask_markup:
            #    print("markup")

            if self.in_roi_mode:
                # Drain to latest frame: tracking thread does not consume capture_queue in ROI mode, but it was
                # still calling capture_event.set() every loop while capture_queue stayed empty — flooding this queue.
                maybe_image = None
                try:
                    while True:
                        try:
                            maybe_image = self.roi_queue.get(block=False)
                        except Empty:
                            break
                    if maybe_image:
                        image = maybe_image[0]

                        img_h, img_w, _ = image.shape

                        hyp = math.ceil((img_w**2 + img_h**2) ** 0.5)
                        rotation_matrix = cv2.getRotationMatrix2D(
                            ((img_w / 2), (img_h / 2)), self.config.rotation_angle, 1
                        )

                        # calculate position of all four corners of image

                        # calculate crop corner locations in original image space
                        x_coords, y_coords = np.matmul(
                            rotation_matrix,
                            np.transpose([[0, 0, 1], [img_w, 0, 1], [0, img_h, 1], [img_w, img_h, 1]]),
                        )

                        self.clip_size = np.array(
                            [math.ceil(max(x_coords) - min(x_coords)), math.ceil(max(y_coords) - min(y_coords))]
                        )
                        if self.config.gui_rotation_ui_padding:
                            self.padded_size = np.array([hyp, hyp])

                        else:
                            self.padded_size = self.clip_size

                        self.img_pos = ((self.padded_size - (img_w, img_h)) / 2).astype(np.int32)

                        self.clip_pos = ((self.padded_size - self.clip_size) / 2).astype(np.int32)

                        self.roi_image_center = self.padded_size / 2

                        # deferred to after roi_image_center is updated
                        if self.cartesian_needs_update:
                            self._polar_to_cartesian()
                            self.cartesian_needs_update = False

                        pad_matrix = np.float32([[1, 0, self.img_pos[X]], [0, 1, self.img_pos[Y]], [0, 0, 1]])
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

                        maybe_image = (image, *maybe_image[1:])

                        ps = tuple(int(x) for x in self.padded_size)
                        if getattr(self, "_last_roi_padded_size", None) != ps:
                            self.roi_canvas.delete("all")
                            self._roi_canvas_image_id = None
                            self._last_roi_padded_size = ps
                        else:
                            self.roi_canvas.delete(self._roi_overlay_tag)

                        photo = self._tk_photo_from_bgr(maybe_image[0], self.roi_canvas)
                        if photo is not None:
                            self._roi_photo = photo
                            if self._roi_canvas_image_id is None:
                                self._roi_canvas_image_id = self.roi_canvas.create_image(
                                    0, 0, image=self._roi_photo, anchor="nw"
                                )
                            else:
                                self.roi_canvas.itemconfigure(self._roi_canvas_image_id, image=self._roi_photo)

                        if self.xy0 is None or self.xy1 is None:
                            # roi_window rotates around roi center, we rotate around image center
                            # TODO: it would be nice if they were more consistent
                            roi_window_pos = (self.config.roi_window_x, self.config.roi_window_y)
                            roi_window_size = (self.config.roi_window_w, self.config.roi_window_h)
                            self.xy0 = roi_window_pos + self.img_pos
                            self.xy1 = self.xy0 + roi_window_size
                            self._cartesian_to_polar()
                            self.ca -= math.radians(self.config.rotation_angle)
                            self._polar_to_cartesian()

                        if self.xy0 is not None and self.xy1 is not None:
                            color = "#7f78ff" if self.is_mouse_up else "#000000"
                            self.roi_canvas.create_rectangle(
                                int(self.xy0[X]),
                                int(self.xy0[Y]),
                                int(self.xy1[X]),
                                int(self.xy1[Y]),
                                outline=color,
                                tags=self._roi_overlay_tag,
                            )
                        if self.is_mouse_up and self.hover_pos is not None:
                            self.roi_canvas.create_line(
                                int(self.hover_pos[X]),
                                0,
                                int(self.hover_pos[X]),
                                int(self.padded_size[Y]),
                                fill="#ffffff",
                                tags=self._roi_overlay_tag,
                            )
                            self.roi_canvas.create_line(
                                0,
                                int(self.hover_pos[Y]),
                                int(self.padded_size[X]),
                                int(self.hover_pos[Y]),
                                fill="#ffffff",
                                tags=self._roi_overlay_tag,
                            )
                finally:
                    # Pace the capture thread to the GUI tick; only the ROI branch should signal while in ROI mode.
                    self.capture_event.set()
            else:
                if needs_roi_set:
                    self.output_canvas.pack_forget()
                    self.roi_message_label.pack(side="left", padx=10)
                    return
                try:
                    self.roi_message_label.pack_forget()
                    if not self.output_canvas.winfo_ismapped():
                        self.output_canvas.pack(side="left")
                    (maybe_image, eye_info) = self.image_queue.get(block=False)

                    tw, th = self._tracking_display_size
                    disp = cv2.resize(maybe_image, (tw, th), interpolation=cv2.INTER_LINEAR)
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
                self.output_canvas.pack_forget()
                (maybe_image, eye_info) = self.image_queue.get(block=False)

            except Empty:
                pass