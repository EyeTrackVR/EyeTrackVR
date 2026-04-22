from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from settings.modules.CommonFieldValidators import check_is_float_convertible


class OneEuroFilterValidationModel(BaseValidationModel):
    gui_speed_coefficient: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_min_cutoff: Annotated[str, AfterValidator(check_is_float_convertible)]


class OneEuroSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.gui_speed_coefficient = f"-SPEEDCOEFFICIENT{widget_id}-"
        self.gui_min_cutoff = f"-MINCUTOFF{widget_id}-"
        self.validation_model = OneEuroFilterValidationModel

    def build(self, parent):
        ttk.Label(parent, text="Min Frequency Cutoff").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        min_cutoff = tk.StringVar(value=str(self.config.gui_min_cutoff))
        self.tk_vars[self.gui_min_cutoff] = min_cutoff
        ttk.Entry(parent, textvariable=min_cutoff, width=12).grid(row=0, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(parent, text="Speed Coefficient").grid(row=0, column=2, sticky="w", padx=8, pady=4)
        speed_coeff = tk.StringVar(value=str(self.config.gui_speed_coefficient))
        self.tk_vars[self.gui_speed_coefficient] = speed_coeff
        ttk.Entry(parent, textvariable=speed_coeff, width=12).grid(row=0, column=3, sticky="w", padx=8, pady=4)