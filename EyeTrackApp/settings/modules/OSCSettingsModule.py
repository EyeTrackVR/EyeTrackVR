from pydantic import model_validator

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk


class OSCValidationModel(BaseValidationModel):
    gui_ROSC: bool
    gui_vrc_native: bool
    gui_osc_vrcft_v1: bool
    gui_osc_vrcft_v2: bool
    gui_use_module: bool

    @model_validator(mode="after")
    def check_osc_vrcft_versions(self):
        if self.gui_osc_vrcft_v1 and self.gui_osc_vrcft_v2:
            raise ValueError("Only one version of VRCFT params can be turned on")
        return self

    @model_validator(mode="after")
    def check_osc_output_mode(self):
        if self.gui_vrc_native and any([self.gui_osc_vrcft_v1, self.gui_osc_vrcft_v2]):
            raise ValueError("Either VRCNative or VRCFT output can be active at a time")
        return self


class OSCSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = OSCValidationModel
        self.gui_ROSC = f"-ROSC{widget_id}-"
        self.gui_vrc_native = f"-VRCNATIVE{widget_id}-"
        self.gui_osc_output_mode = f"-OSCOUTMODE{widget_id}-"
        self.gui_osc_vrcft_v1 = f"-OSCVRCFTV1{widget_id}-"
        self.gui_osc_vrcft_v2 = f"-OSCVRCFTV2{widget_id}-"
        self.gui_use_module = f"-OSCUSEMODULE{widget_id}-"

    def get_values_map(self) -> dict:
        values = {}
        for key, var in self.tk_vars.items():
            if key == self.gui_osc_output_mode:
                continue
            values[key] = var.get()
        mode = self.tk_vars[self.gui_osc_output_mode].get()
        values[self.gui_vrc_native] = mode == "native"
        values[self.gui_use_module] = mode in ("vrcft_v1", "vrcft_v2")
        values[self.gui_osc_vrcft_v1] = mode == "vrcft_v1"
        values[self.gui_osc_vrcft_v2] = mode == "vrcft_v2"
        return values

    def build(self, parent):
        if self.config.gui_vrc_native:
            osc_out_initial = "native"
        elif self.config.gui_osc_vrcft_v1:
            osc_out_initial = "vrcft_v1"
        else:
            osc_out_initial = "vrcft_v2"

        osc_bar = ttk.Frame(parent)
        osc_bar.grid(row=0, column=0, sticky="w", pady=2)
        mode_var = tk.StringVar(value=osc_out_initial)
        self.tk_vars[self.gui_osc_output_mode] = mode_var
        ttk.Radiobutton(
            osc_bar, text="VRC Native", variable=mode_var, value="native"
        ).pack(side="left", padx=(8, 4))
        ttk.Radiobutton(
            osc_bar, text="VRCFT (v2)", variable=mode_var, value="vrcft_v2"
        ).pack(side="left", padx=4)
        ttk.Radiobutton(
            osc_bar, text="VRCFT (v1)", variable=mode_var, value="vrcft_v1"
        ).pack(side="left", padx=4)

        ros_var = tk.BooleanVar(value=bool(self.config.gui_ROSC))
        self.tk_vars[self.gui_ROSC] = ros_var
        ttk.Checkbutton(osc_bar, text="Receive", variable=ros_var).pack(
            side="left", padx=(24, 8)
        )
