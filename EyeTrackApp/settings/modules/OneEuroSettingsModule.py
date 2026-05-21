"""Smoothing Intensity slider.

The OneEuroFilter has two knobs — ``min_cutoff`` (rest-cutoff in Hz) and
``beta`` (speed coefficient) — and the relationship between them and the
perceived smoothing is non-obvious to almost everyone. This module replaces
both raw entries with a single 0..100 slider; the underlying parameters are
derived from a tuned curve so the default (70) lands on the historical
defaults (min_cutoff=0.0004, beta=0.9), 0 is "almost no smoothing", and 100
is "very heavy smoothing".

The validation pipeline only owns the slider value. When the user moves the
slider we expand the change into the three fields (intensity + the two
derived values) so the rest of the codebase keeps reading
``gui_min_cutoff`` / ``gui_speed_coefficient`` directly.
"""

import math

from pydantic import Field
from typing_extensions import Annotated

from settings.modules.BaseModule import (
    BaseSettingsModule,
    BaseValidationModel,
    ValidationResult,
)
import tkinter as tk
from tkinter import ttk


# Curve endpoints picked so that intensity=70 hits the legacy defaults
# (min_cutoff=0.0004, beta=0.9) and the extremes still feel like meaningful
# choices rather than degenerate ones. min_cutoff is log-interpolated, beta
# linear — matches how each affects the filter perceptually.
_MIN_CUTOFF_LOG_MAX = math.log10(0.5)     # intensity=0
_MIN_CUTOFF_LOG_MIN = math.log10(0.00002)  # intensity=100
_BETA_MAX = 3.0                            # intensity=0
_BETA_MIN = 0.05                           # intensity=100


def _derive_one_euro_params(intensity: int) -> tuple[str, str]:
    """Map a 0..100 slider value to (min_cutoff, beta) as the strings that
    config / eye_processor expect."""
    t = max(0, min(100, int(intensity))) / 100.0
    log_cutoff = _MIN_CUTOFF_LOG_MAX + t * (_MIN_CUTOFF_LOG_MIN - _MIN_CUTOFF_LOG_MAX)
    min_cutoff = 10.0 ** log_cutoff
    beta = _BETA_MAX + t * (_BETA_MIN - _BETA_MAX)
    # Format to a stable precision so the validate() change-detection
    # compares as equal across saves (otherwise every move triggers a write).
    return f"{min_cutoff:.6f}", f"{beta:.4f}"


class OneEuroFilterValidationModel(BaseValidationModel):
    gui_smoothing_intensity: Annotated[int, Field(ge=0, le=100)]


class OneEuroSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.gui_smoothing_intensity = f"-SMOOTHINGINTENSITY{widget_id}-"
        # Reset-to-defaults walks ``getattr(module, key)`` for each entry
        # in get_key_for_panel_defaults(); the derived OneEuro fields need
        # *some* attribute so that lookup doesn't AttributeError. They aren't
        # backed by tk widgets — the slider drives them — but we still want
        # "Reset" to put them back to defaults.
        self.gui_min_cutoff = "__derived_one_euro_min_cutoff__"
        self.gui_speed_coefficient = "__derived_one_euro_beta__"
        self.validation_model = OneEuroFilterValidationModel
        self._value_label_var: tk.StringVar | None = None

    def get_key_for_panel_defaults(self):
        return (
            "gui_smoothing_intensity",
            "gui_min_cutoff",
            "gui_speed_coefficient",
        )

    def build(self, parent):
        intensity = tk.IntVar(value=int(self.config.gui_smoothing_intensity))
        # Keep tk_vars storing the integer so validate() sees an int directly
        # (the validation model expects an int and doing the conversion here
        # is cleaner than parsing strings later).
        self.tk_vars[self.gui_smoothing_intensity] = intensity

        min_v, max_v = 0, 100
        slider_length = 160
        value_label_var = tk.StringVar(value=str(intensity.get()))
        self._value_label_var = value_label_var

        def sync(*_args):
            value_label_var.set(str(int(round(float(intensity.get())))))

        def bump(delta):
            next_val = int(round(float(intensity.get()))) + delta
            next_val = max(min_v, min(max_v, next_val))
            intensity.set(next_val)

        ttk.Label(parent, text="Smoothing Intensity").grid(
            row=0, column=0, sticky="w", padx=8, pady=2
        )
        ttk.Scale(
            parent,
            from_=min_v,
            to=max_v,
            variable=intensity,
            orient="horizontal",
            length=slider_length,
        ).grid(row=0, column=1, sticky="w", padx=8, pady=2)
        ttk.Button(parent, text="-", width=2, command=lambda: bump(-1)).grid(
            row=0, column=2, sticky="w", padx=(4, 2), pady=2
        )
        ttk.Label(parent, textvariable=value_label_var, width=6, anchor="center").grid(
            row=0, column=3, sticky="w", padx=2, pady=2
        )
        ttk.Button(parent, text="+", width=2, command=lambda: bump(1)).grid(
            row=0, column=4, sticky="w", padx=(2, 8), pady=2
        )
        intensity.trace_add("write", sync)

    def validate(self, values, raise_exception=False):
        """Validate the slider value, then expand changes to also update the
        two derived OneEuroFilter parameters so downstream code keeps reading
        them as before."""
        result = super().validate(values, raise_exception=raise_exception)
        if result is None or result.changes is None or not result.changes:
            return result
        intensity = result.changes.get("gui_smoothing_intensity")
        if intensity is None:
            return result
        min_cutoff, beta = _derive_one_euro_params(intensity)
        derived = {}
        if self.config.gui_min_cutoff != min_cutoff:
            derived["gui_min_cutoff"] = min_cutoff
        if self.config.gui_speed_coefficient != beta:
            derived["gui_speed_coefficient"] = beta
        if derived:
            result.changes.update(derived)
        return result
