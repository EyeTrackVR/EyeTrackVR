from config import EyeTrackSettingsConfig
from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk


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
        ]

        row = 0
        for left, right in bool_pairs:
            for col, field in enumerate((left, right)):
                if field is None:
                    continue
                key, default, label = field
                var = tk.BooleanVar(value=default)
                self.tk_vars[key] = var
                ttk.Checkbutton(parent, text=label, variable=var).grid(
                    row=row, column=col, sticky="w", padx=8, pady=2
                )
            row += 1

        falloff_var = tk.BooleanVar(value=self.config.gui_outer_side_falloff)
        self.tk_vars[self.gui_outer_side_falloff] = falloff_var
        ttk.Checkbutton(parent, text="Outer Eye Falloff", variable=falloff_var).grid(
            row=row, column=0, sticky="w", padx=8, pady=2
        )
        diff_row = ttk.Frame(parent)
        diff_row.grid(row=row, column=1, sticky="w", padx=8, pady=2)
        ttk.Label(diff_row, text="Eye Difference Threshold").pack(
            side="left", padx=(0, 6)
        )
        diff_var = tk.StringVar(value=str(self.config.gui_eye_dominant_diff_thresh))
        self.tk_vars[self.gui_eye_dominant_diff_thresh] = diff_var
        ttk.Entry(diff_row, textvariable=diff_var, width=12).pack(side="left")
