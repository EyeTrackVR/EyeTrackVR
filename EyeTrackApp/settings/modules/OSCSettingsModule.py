from pydantic import model_validator

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from utils.tooltips import attach_tooltip

from localization import tr


class OSCValidationModel(BaseValidationModel):
    gui_ROSC: bool
    gui_vrc_native: bool
    gui_osc_vrcft_v1: bool
    gui_osc_vrcft_v2: bool
    gui_pyvrcft: bool
    gui_use_module: bool

    @model_validator(mode="after")
    def check_osc_vrcft_versions(self):
        if self.gui_osc_vrcft_v1 and self.gui_osc_vrcft_v2:
            raise ValueError(tr("osc.err_one_vrcft_version"))
        return self

    @model_validator(mode="after")
    def check_osc_output_mode(self):
        exclusive = [
            self.gui_vrc_native,
            self.gui_osc_vrcft_v1,
            self.gui_osc_vrcft_v2,
            self.gui_pyvrcft,
        ]
        if sum(bool(x) for x in exclusive) > 1:
            raise ValueError(tr("osc.err_output_mode_conflict"))
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
        self.gui_pyvrcft = f"-OSCPYVRCFT{widget_id}-"
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
        values[self.gui_pyvrcft] = mode == "pyvrcft"
        return values

    def build(self, parent):
        if self.config.gui_pyvrcft:
            osc_out_initial = "pyvrcft"
        elif self.config.gui_vrc_native:
            osc_out_initial = "native"
        elif self.config.gui_osc_vrcft_v1:
            osc_out_initial = "vrcft_v1"
        else:
            osc_out_initial = "vrcft_v2"

        osc_bar = ttk.Frame(parent)
        osc_bar.grid(row=0, column=0, sticky="w", pady=2)
        mode_var = tk.StringVar(value=osc_out_initial)
        self.tk_vars[self.gui_osc_output_mode] = mode_var
        native_rb = ttk.Radiobutton(
            osc_bar, text=tr("osc.mode_native"), variable=mode_var, value="native"
        )
        native_rb.pack(side="left", padx=(8, 4))
        attach_tooltip(native_rb, tr("osc.mode_native_tip"))
        v2_rb = ttk.Radiobutton(
            osc_bar, text=tr("osc.mode_vrcft_v2"), variable=mode_var, value="vrcft_v2"
        )
        v2_rb.pack(side="left", padx=4)
        attach_tooltip(v2_rb, tr("osc.mode_vrcft_v2_tip"))
        # VRCFT v1 (legacy) is hidden from the GUI but kept in the backend:
        # get_values_map still maps a saved "vrcft_v1" mode, and
        # output_v1_params still runs, so existing v1 configs keep working.
        pyvrcft_rb = ttk.Radiobutton(
            osc_bar, text=tr("osc.mode_pyvrcft"), variable=mode_var, value="pyvrcft"
        )
        pyvrcft_rb.pack(side="left", padx=4)
        attach_tooltip(pyvrcft_rb, tr("osc.mode_pyvrcft_tip"))

        ros_var = tk.BooleanVar(value=bool(self.config.gui_ROSC))
        self.tk_vars[self.gui_ROSC] = ros_var
        receive_cb = ttk.Checkbutton(osc_bar, text=tr("osc.receive"), variable=ros_var)
        receive_cb.pack(side="left", padx=(24, 8))
        attach_tooltip(receive_cb, tr("osc.receive_tip"))
