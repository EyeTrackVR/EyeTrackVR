from config import EyeTrackSettingsConfig
from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from utils.tooltips import attach_tooltip


# Map each gui field name → tooltip text. Centralised so the build loop below
# stays compact and the strings are easy to tweak.
_TIPS = {
    "gui_flip_x_axis_left": (
        "Mirror the left eye horizontally before reporting X position. "
        "Use when the left camera is mounted facing the user (most setups)."
    ),
    "gui_flip_x_axis_right": (
        "Mirror the right eye horizontally before reporting X position. "
        "Use when the right camera is mounted facing the user (most setups)."
    ),
    "gui_flip_y_axis": (
        "Mirror both eyes vertically. Use if your camera is rotated 180°."
    ),
    "gui_outer_side_falloff": (
        "When one eye drifts far from the other, mirror the cleaner eye's "
        "position. Hides tracking glitches on mismatched cameras. "
        "Recommended on."
    ),
    "gui_left_eye_dominant": (
        "Force the left eye to drive output when the two eyes disagree. "
        "Useful if your right camera is significantly less reliable."
    ),
    "gui_right_eye_dominant": (
        "Force the right eye to drive output when the two eyes disagree. "
        "Useful if your left camera is significantly less reliable."
    ),
    "gui_openvr_autostart": (
        "Start tracking when SteamVR starts and stop when it exits."
    ),
    "gui_use_gpu": (
        "Run the LEAP neural-network model on the GPU when available. "
        "Disable if you see crashes or driver issues."
    ),
    "gui_update_check": (
        "Check GitHub for a new ETVR release on startup."
    ),
    "gui_eye_dominant_diff_thresh": (
        "How far apart the two eyes' positions must be (normalised, 0–1) "
        "before Outer Eye Falloff kicks in. Lower = falloff triggers sooner."
    ),
    "gui_use_overlay_cal": (
        "Use the SteamVR overlay spiral to calibrate. When on, Start Calibration "
        "launches the in-headset dot spiral. When off, the classic on-screen "
        "calibration is used instead."
    ),
}


class GeneralSettingsValidationModel(BaseValidationModel):
    gui_flip_x_axis_left: bool
    gui_flip_x_axis_right: bool
    gui_flip_y_axis: bool
    gui_outer_side_falloff: bool
    gui_update_check: bool
    gui_right_eye_dominant: bool
    gui_left_eye_dominant: bool
    gui_eye_dominant_diff_thresh: float
    gui_openvr_autostart: bool
    gui_use_gpu: bool
    gui_show_et_debug: bool
    gui_use_overlay_cal: bool


class GeneralSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = GeneralSettingsValidationModel
        self.gui_flip_x_axis_left = f"-FLIPXAXISLEFT{widget_id}-"
        self.gui_flip_x_axis_right = f"-FLIPXAXISRIGHT{widget_id}-"
        self.gui_flip_y_axis = f"-FLIPYAXIS{widget_id}-"
        self.gui_outer_side_falloff = f"-EYEFALLOFF{widget_id}-"
        self.gui_eye_dominant_diff_thresh = f"-DIFFTHRESH{widget_id}-"
        self.gui_left_eye_dominant = f"-LEFTEYEDOMINANT{widget_id}-"
        self.gui_right_eye_dominant = f"-RIGHTEYEDOMINANT{widget_id}-"
        self.gui_update_check = f"-UPDATECHECK{widget_id}-"
        self.gui_openvr_autostart = f"-OPENVRAUTOSTART{widget_id}-"
        self.gui_use_gpu = f"-USEGPU{widget_id}-"
        self.gui_show_et_debug = f"-SHOWETDEBUG{widget_id}-"
        self.gui_use_overlay_cal = f"-USEOVERLAYCAL{widget_id}-"


    def build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        bool_pairs = [
            (
                (
                    self.gui_flip_x_axis_left,
                    self.config.gui_flip_x_axis_left,
                    "Flip Left Eye X Axis",
                ),
                (
                    self.gui_flip_x_axis_right,
                    self.config.gui_flip_x_axis_right,
                    "Flip Right Eye X Axis",
                ),
            ),
            (
                (
                    self.gui_left_eye_dominant,
                    self.config.gui_left_eye_dominant,
                    "Force Left Eye Dominant",
                ),
                (
                    self.gui_right_eye_dominant,
                    self.config.gui_right_eye_dominant,
                    "Force Right Eye Dominant",
                ),
            ),
            (
                (
                    self.gui_openvr_autostart,
                    self.config.gui_openvr_autostart,
                    "Start and Stop With SteamVR",
                ),
                (self.gui_use_gpu, self.config.gui_use_gpu, "Use GPU Acceleration"),
            ),
            (
                (self.gui_flip_y_axis, self.config.gui_flip_y_axis, "Flip Y Axis"),
                (
                    self.gui_update_check,
                    self.config.gui_update_check,
                    "Check For Updates",
                ),
            ),
            (
                (
                    self.gui_use_overlay_cal,
                    self.config.gui_use_overlay_cal,
                    "Use SteamVR Overlay for Calibration",
                ),
                None,
            ),
        ]

        # Map widget-key string → config attr so we can look up the tooltip.
        key_to_attr = {
            self.gui_flip_x_axis_left: "gui_flip_x_axis_left",
            self.gui_flip_x_axis_right: "gui_flip_x_axis_right",
            self.gui_flip_y_axis: "gui_flip_y_axis",
            self.gui_left_eye_dominant: "gui_left_eye_dominant",
            self.gui_right_eye_dominant: "gui_right_eye_dominant",
            self.gui_openvr_autostart: "gui_openvr_autostart",
            self.gui_use_gpu: "gui_use_gpu",
            self.gui_update_check: "gui_update_check",
            self.gui_use_overlay_cal: "gui_use_overlay_cal",
        }

        row = 0
        for left, right in bool_pairs:
            for col, field in enumerate((left, right)):
                if field is None:
                    continue
                key, default, label = field
                var = tk.BooleanVar(value=default)
                self.tk_vars[key] = var
                cb = ttk.Checkbutton(parent, text=label, variable=var)
                cb.grid(row=row, column=col, sticky="w", padx=8, pady=2)
                attr = key_to_attr.get(key)
                tip = _TIPS.get(attr) if attr else None
                if tip:
                    attach_tooltip(cb, tip)
            row += 1

        falloff_var = tk.BooleanVar(value=self.config.gui_outer_side_falloff)
        self.tk_vars[self.gui_outer_side_falloff] = falloff_var
        falloff_cb = ttk.Checkbutton(parent, text="Outer Eye Falloff", variable=falloff_var)
        falloff_cb.grid(row=row, column=0, sticky="w", padx=8, pady=2)
        attach_tooltip(falloff_cb, _TIPS["gui_outer_side_falloff"])
        diff_row = ttk.Frame(parent)
        diff_row.grid(row=row, column=1, sticky="w", padx=8, pady=2)
        diff_lbl = ttk.Label(diff_row, text="Eye Difference Threshold")
        diff_lbl.pack(side="left", padx=(0, 6))
        attach_tooltip(diff_lbl, _TIPS["gui_eye_dominant_diff_thresh"])
        diff_var = tk.StringVar(value=str(self.config.gui_eye_dominant_diff_thresh))
        self.tk_vars[self.gui_eye_dominant_diff_thresh] = diff_var
        ttk.Entry(diff_row, textvariable=diff_var, width=12).pack(side="left")

    def build_advanced(self, parent):
        debug_var = tk.BooleanVar(value=self.config.gui_show_et_debug)
        self.tk_vars[self.gui_show_et_debug] = debug_var
        cb = ttk.Checkbutton(parent, text="Show ET Debug in Tracking", variable=debug_var)
        cb.pack(side="left", padx=8, pady=2)
        attach_tooltip(
            cb,
            "Show the algorithm debug image (processed eye + threshold) in the tracking view. "
            "Off by default — the gaze dot and blink bar are always visible regardless.",
        )
