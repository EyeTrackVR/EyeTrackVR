from pydantic import AfterValidator, field_validator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from settings.modules.CommonFieldValidators import check_is_float_convertible


class BlinkAlgoSettingsValidationModel(BaseValidationModel):
    gui_IBO: bool
    gui_RANSACBLINK: bool
    gui_BLINK: bool
    gui_LEAP_lid: bool
    ibo_filter_samples: int
    calibration_duration: int
    ibo_fully_close_eye_threshold: Annotated[
        str, AfterValidator(check_is_float_convertible)
    ]
    leap_lid_close_threshold_left: float
    leap_lid_close_threshold_right: float
    leap_lid_widen_threshold_left: float
    leap_lid_widen_threshold_right: float
    gui_circular_crop_left: bool
    gui_circular_crop_right: bool
    leap_calibration_duration: int

    @field_validator(
        "leap_lid_close_threshold_left",
        "leap_lid_close_threshold_right",
        "leap_lid_widen_threshold_left",
        "leap_lid_widen_threshold_right",
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
        self.gui_RANSACBLINK = f"-RANSACBLINK{widget_id}-"
        self.gui_BLINK = f"-BLINK{widget_id}-"
        self.gui_LEAP_lid = f"-LEAPLID{widget_id}-"
        self.ibo_filter_samples = f"-IBOFILTERSAMPLE{widget_id}-"
        self.calibration_duration = f"-CALIBRATIONDURATION{widget_id}-"
        self.ibo_fully_close_eye_threshold = f"-CLOSETHRESH{widget_id}-"
        self.leap_lid_close_threshold_left = f"-LEAPLIDCLOSELEFT{widget_id}-"
        self.leap_lid_close_threshold_right = f"-LEAPLIDCLOSERIGHT{widget_id}-"
        self.leap_lid_widen_threshold_left = f"-LEAPLIDWIDENLEFT{widget_id}-"
        self.leap_lid_widen_threshold_right = f"-LEAPLIDWIDENRIGHT{widget_id}-"
        self.gui_circular_crop_left = f"-CIRCLECROPLEFT{widget_id}-"
        self.gui_circular_crop_right = f"-CIRCLECROPRIGHT{widget_id}-"
        self.leap_calibration_duration = f"-LEAPCALIBRATION{widget_id}-"

    def build(self, parent):
        checkbox_fields = [
            (self.gui_IBO, self.config.gui_IBO, "Intensity Based Openness"),
            (
                self.gui_RANSACBLINK,
                self.config.gui_RANSACBLINK,
                "RANSAC Quick Blink Algo",
            ),
            (self.gui_BLINK, self.config.gui_BLINK, "Binary Blink Algo"),
            (self.gui_LEAP_lid, self.config.gui_LEAP_lid, "LEAP Lid"),
            (
                self.gui_circular_crop_left,
                self.config.gui_circular_crop_left,
                "Left Eye Circle crop",
            ),
            (
                self.gui_circular_crop_right,
                self.config.gui_circular_crop_right,
                "Right Eye Circle crop",
            ),
        ]
        ncol = 3
        rows_per_column = (len(checkbox_fields) + ncol - 1) // ncol
        for idx, (key, default, label) in enumerate(checkbox_fields):
            row = idx % rows_per_column
            col = idx // rows_per_column
            var = tk.BooleanVar(value=default)
            self.tk_vars[key] = var
            ttk.Checkbutton(parent, text=label, variable=var).grid(
                row=row, column=col, sticky="w", padx=8, pady=2
            )
        row = rows_per_column

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

        ttk.Label(parent, text="Left LEAP Lid Close Threshold").grid(
            row=row, column=0, sticky="w", padx=8, pady=2
        )
        leap_left_close_var = tk.StringVar(
            value=str(self.config.leap_lid_close_threshold_left)
        )
        self.tk_vars[self.leap_lid_close_threshold_left] = leap_left_close_var
        ttk.Entry(parent, textvariable=leap_left_close_var, width=12).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )

        ttk.Label(parent, text="Right LEAP Lid Close Threshold").grid(
            row=row, column=2, sticky="w", padx=8, pady=2
        )
        leap_right_close_var = tk.StringVar(
            value=str(self.config.leap_lid_close_threshold_right)
        )
        self.tk_vars[self.leap_lid_close_threshold_right] = leap_right_close_var
        ttk.Entry(parent, textvariable=leap_right_close_var, width=12).grid(
            row=row, column=3, sticky="w", padx=8, pady=2
        )
        row += 1

        ttk.Label(parent, text="Left LEAP Lid Widen Threshold").grid(
            row=row, column=0, sticky="w", padx=8, pady=2
        )
        leap_left_widen_var = tk.StringVar(
            value=str(self.config.leap_lid_widen_threshold_left)
        )
        self.tk_vars[self.leap_lid_widen_threshold_left] = leap_left_widen_var
        ttk.Entry(parent, textvariable=leap_left_widen_var, width=12).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )

        ttk.Label(parent, text="Right LEAP Lid Widen Threshold").grid(
            row=row, column=2, sticky="w", padx=8, pady=2
        )
        leap_right_widen_var = tk.StringVar(
            value=str(self.config.leap_lid_widen_threshold_right)
        )
        self.tk_vars[self.leap_lid_widen_threshold_right] = leap_right_widen_var
        ttk.Entry(parent, textvariable=leap_right_widen_var, width=12).grid(
            row=row, column=3, sticky="w", padx=8, pady=2
        )
        row += 1

        ttk.Label(parent, text="IBO Filter Sample Size").grid(
            row=row, column=0, sticky="w", padx=8, pady=2
        )
        ibo_samples_var = tk.StringVar(value=str(self.config.ibo_filter_samples))
        self.tk_vars[self.ibo_filter_samples] = ibo_samples_var
        ttk.Entry(parent, textvariable=ibo_samples_var, width=12).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )

        ttk.Label(parent, text="IBO Close Threshold").grid(
            row=row, column=2, sticky="w", padx=8, pady=2
        )
        ibo_close_var = tk.StringVar(
            value=str(self.config.ibo_fully_close_eye_threshold)
        )
        self.tk_vars[self.ibo_fully_close_eye_threshold] = ibo_close_var
        ttk.Entry(parent, textvariable=ibo_close_var, width=12).grid(
            row=row, column=3, sticky="w", padx=8, pady=2
        )
