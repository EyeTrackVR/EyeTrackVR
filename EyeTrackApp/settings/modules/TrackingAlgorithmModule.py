from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from utils.tooltips import attach_tooltip


# Tooltip text keyed by the algorithm's internal name (the radio button value).
_ALGO_TIPS = {
    "leap": (
        "LEAP — neural-network pupil tracker. Best general-purpose choice; "
        "handles low contrast and partial occlusion well."
    ),
    "ahrac": (
        "AHRAC — adaptive HSF + RANSAC. Falls back to RANSAC when HSF can't "
        "lock on. Good middle ground."
    ),
    "daddy": (
        "DADDY — older neural-network tracker. Heavier than LEAP; usually no "
        "reason to pick this unless LEAP misbehaves on your camera."
    ),
    "ransac3d": (
        "RANSAC 3D — fits an ellipse to the pupil edge in 3D. Robust to "
        "lighting changes but slower than LEAP."
    ),
    "next": (
        "NEXT — end-to-end neural network tracker. Takes the raw camera frame "
        "and directly outputs gaze, eyebrow, eyelid, and squint."
    ),
    "ahsf": "AHSF — adaptive Haar surround feature. Fast classical tracker.",
    "hsrac": "HSRAC — Haar surround + RANSAC. Older HSF/RANSAC hybrid.",
    "hsf": "HSF — Haar surround feature. Classical, very fast, less robust.",
}

_TIP_MAX_SPEED = (
    "Maximum frames per second the tracker will process. Lower = less CPU, "
    "but jerkier motion. 60 Hz is comfortable for most setups."
)


class TrackingAlgorithmValidationModel(BaseValidationModel):
    gui_DADDY: bool
    gui_HSF: bool
    gui_HSRAC: bool
    gui_AHSF: bool
    gui_LEAP: bool
    gui_RANSAC3D: bool
    gui_AHRAC: bool
    gui_NEXT: bool
    gui_max_tracking_speed: int


class TrackingAlgorithmModule(BaseSettingsModule):
    _TRACKING_SPEED_MIN = 1
    _TRACKING_SPEED_MAX = 200

    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = TrackingAlgorithmValidationModel
        self.gui_DADDY = f"-DADDY{widget_id}-"
        self.gui_HSF = f"-HSF{widget_id}-"
        self.gui_HSRAC = f"-HSRAC{widget_id}-"
        self.gui_LEAP = f"-LEAP{widget_id}-"
        self.gui_AHSF = f"-AHSF{widget_id}-"
        self.gui_AHRAC = f"-gui_AHRAC{widget_id}-"
        self.gui_RANSAC3D = f"-RANSAC3D{widget_id}-"
        self.gui_NEXT = f"-NEXT{widget_id}-"
        self.gui_max_tracking_speed = f"-MAXTRACKSPEED{widget_id}-"

        self._basic_entries = [
            ("LEAP", "leap", self.gui_LEAP, "gui_LEAP"),
            ("AHRAC", "ahrac", self.gui_AHRAC, "gui_AHRAC"),
            ("DADDY", "daddy", self.gui_DADDY, "gui_DADDY"),
            ("RANSAC 3D", "ransac3d", self.gui_RANSAC3D, "gui_RANSAC3D"),
            ("NEXT (alpha)", "next", self.gui_NEXT, "gui_NEXT"),
        ]
        self._advanced_entries = [
            ("ASHSF", "ahsf", self.gui_AHSF, "gui_AHSF"),
            ("HSRAC", "hsrac", self.gui_HSRAC, "gui_HSRAC"),
            ("HSF", "hsf", self.gui_HSF, "gui_HSF"),
        ]
        self._algo_entries = self._basic_entries + self._advanced_entries

    def build(self, parent):
        selected = "leap"
        for _label, name, _key, config_field in self._algo_entries:
            if getattr(self.config, config_field, False):
                selected = name
                break
        self.selected_algo = tk.StringVar(value=selected)
        for _label, name, key, config_field in self._algo_entries:
            self.tk_vars[key] = tk.BooleanVar(
                value=bool(getattr(self.config, config_field, False))
            )
        # Radio buttons live in their own frame so their column widths are
        # independent of the slider row below (which would otherwise force
        # column 1 wide via the Scale widget, creating a gap between LEAP and AHRAC).
        radio_frame = ttk.Frame(parent)
        radio_frame.grid(row=0, column=0, columnspan=5, sticky="w")
        self._render_radio_grid(radio_frame, self._basic_entries, ncol=4)

        speed_var = tk.IntVar(
            value=int(getattr(self.config, "gui_max_tracking_speed", 60))
        )
        self.tk_vars[self.gui_max_tracking_speed] = speed_var
        self._add_slider_with_controls(
            parent,
            row=1,
            label="Max Tracking Speed (Hz)",
            var=speed_var,
            min_v=self._TRACKING_SPEED_MIN,
            max_v=self._TRACKING_SPEED_MAX,
        )

    def build_advanced(self, parent):
        ttk.Label(parent, text="Tracking Algorithm (advanced)").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 2)
        )
        self._render_radio_grid(
            parent, self._advanced_entries, ncol=3, row_offset=1
        )

    def _render_radio_grid(self, parent, entries, ncol, row_offset=0):
        rows_per_column = (len(entries) + ncol - 1) // ncol
        for idx, (label, name, _key, _config_field) in enumerate(entries):
            row = (idx % rows_per_column) + row_offset
            col = idx // rows_per_column
            rb = ttk.Radiobutton(
                parent, text=label, variable=self.selected_algo, value=name
            )
            rb.grid(row=row, column=col, sticky="w", padx=8, pady=2)
            tip = _ALGO_TIPS.get(name)
            if tip:
                attach_tooltip(rb, tip)

    def _add_slider_with_controls(self, parent, row, label, var, min_v, max_v):
        slider_length = 160
        value_label_var = tk.StringVar(value=str(int(var.get())))

        def sync(*_args):
            value_label_var.set(str(int(round(float(var.get())))))

        def bump(delta):
            next_val = int(round(float(var.get()))) + delta
            next_val = max(min_v, min(max_v, next_val))
            var.set(next_val)

        lbl = ttk.Label(parent, text=label)
        lbl.grid(row=row, column=0, sticky="w", padx=8, pady=2)
        attach_tooltip(lbl, _TIP_MAX_SPEED)
        ttk.Scale(
            parent,
            from_=min_v,
            to=max_v,
            variable=var,
            orient="horizontal",
            length=slider_length,
        ).grid(row=row, column=1, sticky="w", padx=8, pady=2)
        ttk.Button(parent, text="-", width=2, command=lambda: bump(-1)).grid(
            row=row, column=2, sticky="w", padx=(4, 2), pady=2
        )
        ttk.Label(parent, textvariable=value_label_var, width=6, anchor="center").grid(
            row=row, column=3, sticky="w", padx=2, pady=2
        )
        ttk.Button(parent, text="+", width=2, command=lambda: bump(1)).grid(
            row=row, column=4, sticky="w", padx=(2, 8), pady=2
        )
        var.trace_add("write", sync)

    def get_values_map(self) -> dict:
        values = super().get_values_map()
        selected = self.selected_algo.get()
        for _label, name, key, _config_field in self._algo_entries:
            values[key] = name == selected
            self.tk_vars[key].set(name == selected)
        return values
