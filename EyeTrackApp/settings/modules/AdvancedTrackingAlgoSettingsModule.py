from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk


class AdvancedTrackingAlgoSettingsValidationModel(BaseValidationModel):
    gui_HSF_radius_left: int
    gui_HSF_radius_right: int
    gui_legacy_ransac_thresh_left: int
    gui_legacy_ransac_thresh_right: int
    gui_skip_autoradius: bool
    gui_thresh_add: int
    gui_pupil_dilation: bool


class AdvancedTrackingAlgoSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = AdvancedTrackingAlgoSettingsValidationModel

        self.gui_skip_autoradius = f"-SKIPAUTORADIUS{widget_id}-"
        self.gui_thresh_add = f"-THRESHADD{widget_id}-"
        self.gui_HSF_radius_left = f"-HSFRADIUSLEFT{widget_id}-"
        self.gui_HSF_radius_right = f"-HSFRADIUSRIGHT{widget_id}-"

        self.gui_legacy_ransac_thresh_right = f"-THRESHRIGHT{widget_id}-"
        self.gui_legacy_ransac_thresh_left = f"-THRESHLEFT{widget_id}-"
        self.gui_pupil_dilation = f"-EBPD{widget_id}-"

    def _add_slider_with_controls(self, parent, row, label, var, min_v, max_v):
        slider_length = 160
        value_label_var = tk.StringVar(value=str(int(var.get())))

        def sync(*_args):
            value_label_var.set(str(int(round(float(var.get())))))

        def bump(delta):
            next_val = int(round(float(var.get()))) + delta
            next_val = max(min_v, min(max_v, next_val))
            var.set(next_val)

        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        ttk.Scale(parent, from_=min_v, to=max_v, variable=var, orient="horizontal", length=slider_length).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )
        ttk.Button(parent, text="-", width=2, command=lambda: bump(-1)).grid(row=row, column=2, sticky="w", padx=(4, 2), pady=2)
        ttk.Label(parent, textvariable=value_label_var, width=6, anchor="center").grid(row=row, column=3, sticky="w", padx=2, pady=2)
        ttk.Button(parent, text="+", width=2, command=lambda: bump(1)).grid(row=row, column=4, sticky="w", padx=(2, 8), pady=2)
        var.trace_add("write", sync)

    def build(self, parent):
        row = 0
        for key, default, label in [
            (self.gui_pupil_dilation, self.config.gui_pupil_dilation, "Ellipse Based Pupil Dilation"),
            (self.gui_skip_autoradius, self.config.gui_skip_autoradius, "HSF: Skip Auto Radius"),
        ]:
            var = tk.BooleanVar(value=default)
            self.tk_vars[key] = var
            ttk.Checkbutton(parent, text=label, variable=var).grid(row=row, column=0, sticky="w", padx=8, pady=2)
            row += 1

        slider_specs = [
            ("Left HSF Radius", self.gui_HSF_radius_left, self.config.gui_HSF_radius_left, 1, 50),
            ("Right HSF Radius", self.gui_HSF_radius_right, self.config.gui_HSF_radius_right, 1, 50),
            ("RANSAC Thresh Add", self.gui_thresh_add, self.config.gui_thresh_add, 1, 50),
            ("Right Eye Thresh", self.gui_legacy_ransac_thresh_right, self.config.gui_legacy_ransac_thresh_right, 1, 120),
            ("Left Eye Thresh", self.gui_legacy_ransac_thresh_left, self.config.gui_legacy_ransac_thresh_left, 1, 120),
        ]
        for label, key, default, min_v, max_v in slider_specs:
            var = tk.IntVar(value=int(default))
            self.tk_vars[key] = var
            self._add_slider_with_controls(parent, row, label, var, min_v, max_v)
            row += 1
