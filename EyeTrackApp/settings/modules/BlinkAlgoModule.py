from pydantic import field_validator

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from settings.modules.CommonFieldValidators import check_is_float_convertible
from utils.runtime_state import get_value as _get_runtime_value
from utils.tooltips import attach_tooltip
from eye_processor import remap_leap_lid_openness


# Centralised tooltip copy so the strings stay short here and easy to tweak.
_TIP_LEAP_LID = (
    "Use the LEAP neural-network model to detect eyelid openness. "
    "Recommended for most users. Disable only if LEAP misbehaves on your camera."
)
_TIP_IBO = (
    "Detect blinks by raw image intensity instead of LEAP. "
    "Fallback for cameras where LEAP under-performs (low light, occluded lashes)."
)
_TIP_BLINK_POINT = (
    "Below this raw lid value the eye is reported as fully closed (output = 0). "
    "Raise it to make blinks trigger easier; lower it if the app reports closed when your eye is open."
)
_TIP_WIDE_POINT = (
    "Above this raw lid value the eye starts mapping into the wide-open range (output > 0.75). "
    "Lower it to make wide-eye/surprise easier to trigger."
)
_TIP_REDO = (
    "Clear the stored eyelid calibration for both eyes and restart the sampling window. "
    "Use after changing camera position, IR brightness, or if blink detection drifted."
)
_TIP_CAL_DURATION = (
    "How many seconds to record your eyelid motion before locking in the open/closed bounds. "
    "Longer = more reliable but slower; blink several times during the window."
)
_TIP_MIN_SPAN = (
    "Calibration is rejected and restarted if your eye opened/closed by less than this amount "
    "during the sampling window. Catches the case where you forgot to blink."
)
_TIP_EYEBROW_V1 = (
    "Run the EyeBrowV1 neural-network model on each raw camera frame (pre-crop, pre-rotation) "
    "and send the result as a float [0–1] over OSC. "
    "Dual-eye: /avatar/parameters/v2/BrowExpressionLeft and BrowExpressionRight. "
    "Single-eye: /avatar/parameters/v2/BrowExpression. "
    "Requires Models/EyeBrowv1.onnx."
)


class BlinkAlgoSettingsValidationModel(BaseValidationModel):
    gui_IBO: bool
    gui_LEAP_lid: bool
    gui_eyebrow_v1: bool
    calibration_duration: int
    leap_lid_close_threshold_left: float
    leap_lid_close_threshold_right: float
    leap_lid_widen_threshold_left: float
    leap_lid_widen_threshold_right: float
    leap_lid_min_calibration_span: float
    leap_calibration_duration: int

    @field_validator(
        "leap_lid_close_threshold_left",
        "leap_lid_close_threshold_right",
        "leap_lid_widen_threshold_left",
        "leap_lid_widen_threshold_right",
        "leap_lid_min_calibration_span",
        mode="before",
    )
    @classmethod
    def _coerce_leap_lid_threshold(cls, v):
        if isinstance(v, str):
            float(check_is_float_convertible(v.strip()))
            return float(v.strip())
        return float(v)


# Canvas geometry for the threshold visualizer.
_VIZ_W = 280
_VIZ_H = 36
_VIZ_PAD = 4
# Draggable range — extends beyond the 0–1 output clip so thresholds can be
# pushed into the overshoot region when needed (e.g. forcing always-open).
_VIZ_RANGE_MIN = -0.3
_VIZ_RANGE_MAX = 1.3
# Min gap between close and widen so the remap range never collapses to 0.
_VIZ_MIN_GAP = 0.02
# EyeId int values used by eye_processor when publishing raw lid samples.
_EYE_ID_RIGHT = 0
_EYE_ID_LEFT = 1


class BlinkAlgoSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = BlinkAlgoSettingsValidationModel
        # The settings widget passes the full EyeTrackConfig as `settings`;
        # we need it to bump per-eye recalibration counters from the Redo button.
        self._main_config = kwargs.get("settings")

        self.gui_IBO = f"-IBO{widget_id}-"
        self.gui_LEAP_lid = f"-LEAPLID{widget_id}-"
        self.gui_eyebrow_v1 = f"-EYEBROWV1{widget_id}-"
        self.calibration_duration = f"-CALIBRATIONDURATION{widget_id}-"
        self.leap_lid_close_threshold_left = f"-LEAPLIDCLOSELEFT{widget_id}-"
        self.leap_lid_close_threshold_right = f"-LEAPLIDCLOSERIGHT{widget_id}-"
        self.leap_lid_widen_threshold_left = f"-LEAPLIDWIDENLEFT{widget_id}-"
        self.leap_lid_widen_threshold_right = f"-LEAPLIDWIDENRIGHT{widget_id}-"
        self.leap_lid_min_calibration_span = f"-LEAPLIDMINCALSPAN{widget_id}-"
        self.leap_calibration_duration = f"-LEAPCALIBRATION{widget_id}-"

        # Tracks the marker currently being dragged: (canvas, "close" | "widen").
        self._viz_drag = None
        # Per-canvas state polled by _tick_viz to redraw + update readouts.
        # Items: (canvas, eye_id, close_var, widen_var, readout_label).
        self._viz = []
        self._viz_after_id = None

    def _build_threshold_entry(self, parent, var, step=0.05):
        """Entry field with - / + bump buttons matching slider control styling."""
        frame = ttk.Frame(parent)

        def bump(delta):
            try:
                current = float(var.get())
            except (ValueError, TypeError):
                current = 0.0
            next_val = round(current + (delta * step), 2)
            var.set(f"{next_val:.2f}")

        ttk.Entry(frame, textvariable=var, width=6).grid(row=0, column=0, sticky="w")
        ttk.Button(frame, text="-", width=2, command=lambda: bump(-1)).grid(
            row=0, column=1, sticky="w", padx=(4, 2)
        )
        ttk.Button(frame, text="+", width=2, command=lambda: bump(1)).grid(
            row=0, column=2, sticky="w", padx=(2, 0)
        )
        return frame

    @staticmethod
    def _viz_x_to_value(x):
        span_px = (_VIZ_W - _VIZ_PAD) - _VIZ_PAD
        if span_px <= 0:
            return _VIZ_RANGE_MIN
        v = _VIZ_RANGE_MIN + (x - _VIZ_PAD) / span_px * (_VIZ_RANGE_MAX - _VIZ_RANGE_MIN)
        return max(_VIZ_RANGE_MIN, min(_VIZ_RANGE_MAX, v))

    @staticmethod
    def _viz_value_to_x(v):
        v = max(_VIZ_RANGE_MIN, min(_VIZ_RANGE_MAX, v))
        span_px = (_VIZ_W - _VIZ_PAD) - _VIZ_PAD
        return _VIZ_PAD + (v - _VIZ_RANGE_MIN) / (_VIZ_RANGE_MAX - _VIZ_RANGE_MIN) * span_px

    @staticmethod
    def _safe_float(var, default):
        try:
            return float(var.get())
        except (ValueError, TypeError, tk.TclError):
            return default

    def _build_viz_canvas(self, parent, eye_id, close_var, widen_var):
        """Compact horizontal bar showing close/widen markers + live raw lid.
        Markers are click-draggable — pressing near a marker grabs it; motion
        updates the underlying StringVar in real time. A polling tick (~12 Hz)
        keeps the live ▼ indicator and numeric readout fresh."""
        wrap = ttk.Frame(parent)
        canvas = tk.Canvas(
            wrap,
            width=_VIZ_W,
            height=_VIZ_H,
            highlightthickness=0,
            bd=0,
            bg="#1f1f1f",
            cursor="hand2",
        )
        canvas.grid(row=0, column=0, sticky="w")
        readout_frame = ttk.Frame(wrap)
        readout_frame.grid(row=0, column=1, sticky="w", padx=(6, 0))
        raw_readout = ttk.Label(readout_frame, text="raw: --", width=10, foreground="#bbbbbb")
        raw_readout.pack(anchor="w")
        adj_readout = ttk.Label(readout_frame, text="adj: --", width=10, foreground="#9999ff")
        adj_readout.pack(anchor="w")
        canvas.bind(
            "<ButtonPress-1>",
            lambda e: self._on_viz_press(e, canvas, close_var, widen_var),
        )
        canvas.bind(
            "<B1-Motion>",
            lambda e: self._on_viz_drag(e, canvas, close_var, widen_var),
        )
        canvas.bind(
            "<ButtonRelease-1>",
            lambda e: self._on_viz_release(canvas),
        )
        self._viz.append((canvas, eye_id, close_var, widen_var, raw_readout, adj_readout))
        return wrap

    def _redraw_viz(self, canvas, close_t, widen_t, raw):
        canvas.delete("all")
        h = _VIZ_H
        inner_left = _VIZ_PAD
        inner_right = _VIZ_W - _VIZ_PAD
        close_x = self._viz_value_to_x(close_t)
        widen_x = self._viz_value_to_x(widen_t)
        x_zero = self._viz_value_to_x(0.0)
        x_one = self._viz_value_to_x(1.0)
        bar_top = 4
        bar_bot = h - 12  # leave 12 px at bottom for "0" / "1" labels

        # Base zones (closed / neutral / wide) spanning the full bar width.
        canvas.create_rectangle(inner_left, bar_top, close_x, bar_bot, fill="#5a2a2a", outline="")
        canvas.create_rectangle(close_x, bar_top, widen_x, bar_bot, fill="#3a3a3a", outline="")
        canvas.create_rectangle(widen_x, bar_top, inner_right, bar_bot, fill="#2a5a2a", outline="")

        # Overshoot overlays — distinct dark tint over the regions outside 0–1.
        canvas.create_rectangle(inner_left, bar_top, x_zero, bar_bot, fill="#251a2e", outline="")
        canvas.create_rectangle(x_one, bar_top, inner_right, bar_bot, fill="#1a251a", outline="")

        # Boundary lines and labels at 0.0 and 1.0.
        for bx, lbl in ((x_zero, "0"), (x_one, "1")):
            canvas.create_line(bx, bar_top, bx, bar_bot + 2, fill="#aaaaaa", width=1)
            canvas.create_text(
                bx, bar_bot + 4, text=lbl, fill="#888888",
                font=("Segoe UI", 7), anchor="n",
            )

        # Threshold markers with grab-handle nubs — drawn on top of all zones.
        canvas.create_line(close_x, 1, close_x, bar_bot, fill="#ff8a8a", width=3)
        canvas.create_rectangle(close_x - 3, 0, close_x + 3, bar_top, fill="#ff8a8a", outline="")
        canvas.create_line(widen_x, 1, widen_x, bar_bot, fill="#8aff8a", width=3)
        canvas.create_rectangle(widen_x - 3, 0, widen_x + 3, bar_top, fill="#8aff8a", outline="")

        # Live raw lid indicator (yellow ▼ on top + thin vertical guide).
        if raw is not None:
            rx = self._viz_value_to_x(raw)
            canvas.create_polygon(rx - 4, 0, rx + 4, 0, rx, 7, fill="#ffd84a", outline="")
            canvas.create_line(rx, 6, rx, bar_bot, fill="#ffd84a", width=1)

    def _tick_viz(self):
        if not self._viz:
            return
        try:
            if not self._viz[0][0].winfo_exists():
                self._viz_after_id = None
                return
        except tk.TclError:
            self._viz_after_id = None
            return

        for canvas, eye_id, close_var, widen_var, raw_readout, adj_readout in self._viz:
            close_t = self._safe_float(close_var, 0.1)
            widen_t = self._safe_float(widen_var, 0.9)
            raw = _get_runtime_value(f"raw_lid_{eye_id}", None)
            self._redraw_viz(canvas, close_t, widen_t, raw)
            if raw is not None:
                adj = remap_leap_lid_openness(raw, close_t, widen_t)
                raw_readout.config(text=f"raw: {raw:.2f}")
                adj_readout.config(text=f"adj: {adj:.2f}")
            else:
                raw_readout.config(text="raw: --")
                adj_readout.config(text="adj: --")

        self._viz_after_id = self._viz[0][0].after(80, self._tick_viz)

    def _on_viz_press(self, event, canvas, close_var, widen_var):
        close_t = self._safe_float(close_var, 0.1)
        widen_t = self._safe_float(widen_var, 0.9)
        close_x = self._viz_value_to_x(close_t)
        widen_x = self._viz_value_to_x(widen_t)
        d_close = abs(event.x - close_x)
        d_widen = abs(event.x - widen_x)
        if d_close < d_widen or (d_close == d_widen and event.x <= (close_x + widen_x) / 2):
            self._viz_drag = (canvas, "close")
        else:
            self._viz_drag = (canvas, "widen")
        self._on_viz_drag(event, canvas, close_var, widen_var)

    def _on_viz_drag(self, event, canvas, close_var, widen_var):
        active = self._viz_drag
        if active is None or active[0] is not canvas:
            return
        v = self._viz_x_to_value(event.x)
        close_t = self._safe_float(close_var, 0.1)
        widen_t = self._safe_float(widen_var, 0.9)
        if active[1] == "close":
            v = max(_VIZ_RANGE_MIN, min(v, widen_t - _VIZ_MIN_GAP))
            close_var.set(f"{v:.2f}")
        else:
            v = min(_VIZ_RANGE_MAX, max(v, close_t + _VIZ_MIN_GAP))
            widen_var.set(f"{v:.2f}")

    def _on_viz_release(self, canvas):
        if self._viz_drag is not None and self._viz_drag[0] is canvas:
            self._viz_drag = None

    def _build_eye_column(self, parent, label, eye_id, close_var, widen_var):
        """One eye's column: heading + the two threshold rows + visualizer."""
        col = ttk.Frame(parent)
        ttk.Label(col, text=label, font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        blink_lbl = ttk.Label(col, text="Blink point")
        blink_lbl.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        attach_tooltip(blink_lbl, _TIP_BLINK_POINT)
        self._build_threshold_entry(col, close_var).grid(
            row=1, column=1, sticky="w", pady=2
        )
        wide_lbl = ttk.Label(col, text="Wide-eye point")
        wide_lbl.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=2)
        attach_tooltip(wide_lbl, _TIP_WIDE_POINT)
        self._build_threshold_entry(col, widen_var).grid(
            row=2, column=1, sticky="w", pady=2
        )
        self._build_viz_canvas(col, eye_id, close_var, widen_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        return col

    def build(self, parent):
        # Row 0: algorithm toggles.
        for idx, (key, default, label, tip) in enumerate(
            [
                (self.gui_LEAP_lid, self.config.gui_LEAP_lid, "LEAP Lid Blink Algo", _TIP_LEAP_LID),
                (self.gui_IBO, self.config.gui_IBO, "Intensity Based Openness", _TIP_IBO),
                (self.gui_eyebrow_v1, self.config.gui_eyebrow_v1, "EyeBrow v1", _TIP_EYEBROW_V1),
            ]
        ):
            var = tk.BooleanVar(value=default)
            self.tk_vars[key] = var
            cb = ttk.Checkbutton(parent, text=label, variable=var)
            cb.grid(row=0, column=idx, sticky="w", padx=8, pady=(2, 6))
            attach_tooltip(cb, tip)

        # Row 1: hint text — applies to both columns below.
        ttk.Label(
            parent,
            text="↑ Blink point = blinks trigger easier · ↓ Wide-eye point = wide-eye triggers easier",
            foreground="#888888",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))

        # Row 2: two per-eye columns separated by a vertical rule.
        left_close = tk.StringVar(value=f"{float(self.config.leap_lid_close_threshold_left):.2f}")
        left_widen = tk.StringVar(value=f"{float(self.config.leap_lid_widen_threshold_left):.2f}")
        right_close = tk.StringVar(value=f"{float(self.config.leap_lid_close_threshold_right):.2f}")
        right_widen = tk.StringVar(value=f"{float(self.config.leap_lid_widen_threshold_right):.2f}")
        self.tk_vars[self.leap_lid_close_threshold_left] = left_close
        self.tk_vars[self.leap_lid_widen_threshold_left] = left_widen
        self.tk_vars[self.leap_lid_close_threshold_right] = right_close
        self.tk_vars[self.leap_lid_widen_threshold_right] = right_widen

        def _live_float(cfg, field, var):
            def _cb(*_):
                try:
                    setattr(cfg, field, float(var.get()))
                except (ValueError, TypeError):
                    pass
            return _cb

        left_close.trace_add("write", _live_float(self.config, "leap_lid_close_threshold_left", left_close))
        left_widen.trace_add("write", _live_float(self.config, "leap_lid_widen_threshold_left", left_widen))
        right_close.trace_add("write", _live_float(self.config, "leap_lid_close_threshold_right", right_close))
        right_widen.trace_add("write", _live_float(self.config, "leap_lid_widen_threshold_right", right_widen))

        self._build_eye_column(
            parent, "Left Eye", _EYE_ID_LEFT, left_close, left_widen
        ).grid(row=2, column=0, sticky="nw", padx=(8, 12), pady=4)
        ttk.Separator(parent, orient="vertical").grid(
            row=2, column=1, sticky="ns", pady=4
        )
        self._build_eye_column(
            parent, "Right Eye", _EYE_ID_RIGHT, right_close, right_widen
        ).grid(row=2, column=2, sticky="nw", padx=(12, 8), pady=4)

        # Row 3: the Redo button lives where the calibration entries used to.
        # Calibration duration + min blink size now live under Advanced; the
        # tk vars are created here so they exist for the validation model
        # whether or not the user has expanded the Advanced section.
        self._eyelid_duration_var = tk.StringVar(
            value=str(self.config.calibration_duration)
        )
        self.tk_vars[self.leap_calibration_duration] = self._eyelid_duration_var
        self.tk_vars[self.calibration_duration] = self._eyelid_duration_var

        self._leap_min_span_var = tk.StringVar(
            value=str(self.config.leap_lid_min_calibration_span)
        )
        self.tk_vars[self.leap_lid_min_calibration_span] = self._leap_min_span_var

        cal_frame = ttk.Frame(parent)
        cal_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=(6, 2))
        self._redo_button = ttk.Button(
            cal_frame,
            text="Redo Eyelid Calib",
            command=self._on_redo_eyelid_calib,
        )
        self._redo_button.grid(row=0, column=0, sticky="w", pady=2)
        attach_tooltip(self._redo_button, _TIP_REDO)

        # Kick off polling now that all canvases exist.
        self._tick_viz()

    def build_advanced(self, parent):
        ttk.Label(parent, text="Eyelid calibration (advanced)").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 4)
        )
        cal_dur_lbl = ttk.Label(parent, text="Calibration duration (seconds)")
        cal_dur_lbl.grid(row=1, column=0, sticky="w", padx=8, pady=2)
        attach_tooltip(cal_dur_lbl, _TIP_CAL_DURATION)
        ttk.Entry(parent, textvariable=self._eyelid_duration_var, width=8).grid(
            row=1, column=1, sticky="w", pady=2
        )
        min_span_lbl = ttk.Label(parent, text="Min blink size during calibration")
        min_span_lbl.grid(row=2, column=0, sticky="w", padx=8, pady=2)
        attach_tooltip(min_span_lbl, _TIP_MIN_SPAN)
        ttk.Entry(parent, textvariable=self._leap_min_span_var, width=8).grid(
            row=2, column=1, sticky="w", pady=2
        )

    def _on_redo_eyelid_calib(self):
        """Bump every eye's recalibration sequence so LEAP_C resets its
        sampling window on the next frame. We bump all three (left/right/bsb2e)
        because the per-eye instance that's actually running depends on the
        current capture mode, and missing one would leave a stale calibration
        in place if the user switches modes later."""
        cfg = self._main_config
        if cfg is None:
            return
        bumped = False
        for attr in ("left_eye", "right_eye", "bsb2e"):
            eye = getattr(cfg, attr, None)
            if eye is None:
                continue
            current = int(getattr(eye, "leap_calib_request_seq", 0))
            eye.leap_calib_request_seq = current + 1
            eye.leap_calibrated = False
            eye.leap_calibration_percentile_90 = 0
            eye.leap_calibration_percentile_2 = 0
            bumped = True
        if bumped:
            try:
                cfg.save()
            except Exception:
                pass
            self._flash_redo_button()

    def _flash_redo_button(self):
        """Briefly swap the button label so the click registers visually."""
        btn = getattr(self, "_redo_button", None)
        if btn is None:
            return
        try:
            btn.config(text="Restarting…", state="disabled")
            btn.after(
                1200,
                lambda: btn.config(text="Redo Eyelid Calib", state="normal"),
            )
        except tk.TclError:
            pass
