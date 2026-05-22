from pydantic import field_validator

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from settings.modules.CommonFieldValidators import check_is_float_convertible


class BlinkAlgoSettingsValidationModel(BaseValidationModel):
    gui_IBO: bool
    gui_LEAP_lid: bool
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


class BlinkAlgoSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = BlinkAlgoSettingsValidationModel

        self.gui_IBO = f"-IBO{widget_id}-"
        self.gui_LEAP_lid = f"-LEAPLID{widget_id}-"
        self.calibration_duration = f"-CALIBRATIONDURATION{widget_id}-"
        self.leap_lid_close_threshold_left = f"-LEAPLIDCLOSELEFT{widget_id}-"
        self.leap_lid_close_threshold_right = f"-LEAPLIDCLOSERIGHT{widget_id}-"
        self.leap_lid_widen_threshold_left = f"-LEAPLIDWIDENLEFT{widget_id}-"
        self.leap_lid_widen_threshold_right = f"-LEAPLIDWIDENRIGHT{widget_id}-"
        self.leap_lid_min_calibration_span = f"-LEAPLIDMINCALSPAN{widget_id}-"
        self.leap_calibration_duration = f"-LEAPCALIBRATION{widget_id}-"

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

        ttk.Entry(frame, textvariable=var, width=8).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(frame, text="-", width=2, command=lambda: bump(-1)).grid(
            row=0, column=1, sticky="w", padx=(4, 2)
        )
        ttk.Button(frame, text="+", width=2, command=lambda: bump(1)).grid(
            row=0, column=2, sticky="w", padx=(2, 0)
        )
        return frame

    def build(self, parent):
        checkbox_fields = [
            (self.gui_LEAP_lid, self.config.gui_LEAP_lid, "LEAP Lid Blink Algo"),
            (self.gui_IBO, self.config.gui_IBO, "Intensity Based Openness"),
        ]
        for idx, (key, default, label) in enumerate(checkbox_fields):
            var = tk.BooleanVar(value=default)
            self.tk_vars[key] = var
            ttk.Checkbutton(parent, text=label, variable=var).grid(
                row=0, column=idx, sticky="w", padx=8, pady=2
            )
        row = 1

        # Unified eyelid calibration duration controls both LEAP and non-LEAP duration values.
        eyelid_duration_var = tk.StringVar(value=str(self.config.calibration_duration))
        self.tk_vars[self.leap_calibration_duration] = eyelid_duration_var
        self.tk_vars[self.calibration_duration] = eyelid_duration_var
        ttk.Label(parent, text="Eyelid calibration duration (seconds)").grid(
            row=row, column=0, sticky="w", padx=8, pady=2
        )
        ttk.Entry(parent, textvariable=eyelid_duration_var, width=16).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )
        row += 1

        ttk.Label(parent, text="Left Lid Close Threshold").grid(
            row=row, column=0, sticky="w", padx=8, pady=2
        )
        leap_left_close_var = tk.StringVar(
            value=str(self.config.leap_lid_close_threshold_left)
        )
        self.tk_vars[self.leap_lid_close_threshold_left] = leap_left_close_var
        self._build_threshold_entry(parent, leap_left_close_var).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )

        ttk.Label(parent, text="Right Lid Close Threshold").grid(
            row=row, column=2, sticky="w", padx=8, pady=2
        )
        leap_right_close_var = tk.StringVar(
            value=str(self.config.leap_lid_close_threshold_right)
        )
        self.tk_vars[self.leap_lid_close_threshold_right] = leap_right_close_var
        self._build_threshold_entry(parent, leap_right_close_var).grid(
            row=row, column=3, sticky="w", padx=8, pady=2
        )
        row += 1

        ttk.Label(parent, text="Left Lid Widen Threshold").grid(
            row=row, column=0, sticky="w", padx=8, pady=2
        )
        leap_left_widen_var = tk.StringVar(
            value=str(self.config.leap_lid_widen_threshold_left)
        )
        self.tk_vars[self.leap_lid_widen_threshold_left] = leap_left_widen_var
        self._build_threshold_entry(parent, leap_left_widen_var).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )

        ttk.Label(parent, text="Right Lid Widen Threshold").grid(
            row=row, column=2, sticky="w", padx=8, pady=2
        )
        leap_right_widen_var = tk.StringVar(
            value=str(self.config.leap_lid_widen_threshold_right)
        )
        self.tk_vars[self.leap_lid_widen_threshold_right] = leap_right_widen_var
        self._build_threshold_entry(parent, leap_right_widen_var).grid(
            row=row, column=3, sticky="w", padx=8, pady=2
        )
        row += 1

        ttk.Label(parent, text="LEAP Lid Min Calibration Span").grid(
            row=row, column=0, sticky="w", padx=8, pady=2
        )
        leap_min_span_var = tk.StringVar(
            value=str(self.config.leap_lid_min_calibration_span)
        )
        self.tk_vars[self.leap_lid_min_calibration_span] = leap_min_span_var
        ttk.Entry(parent, textvariable=leap_min_span_var, width=12).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )
        # IBO Filter Sample Size and IBO Close Threshold fields removed — IBO
        # now derives its filter window from the Eyelid calibration duration
        # (× current FPS) and shares the Lid Close Threshold with LEAP Lid.
