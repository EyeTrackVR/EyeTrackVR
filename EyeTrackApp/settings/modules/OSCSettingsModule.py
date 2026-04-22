from pydantic import model_validator

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk


class OSCValidationModel(BaseValidationModel):
    gui_osc_port: int
    gui_osc_address: str
    gui_ROSC: bool
    gui_osc_receiver_port: int
    gui_osc_recenter_address: str
    gui_osc_recalibrate_address: str
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
        self.gui_osc_address = f"-OSCADDRESS{widget_id}-"
        self.gui_osc_port = f"-OSCPORT{widget_id}-"
        self.gui_ROSC = f"-ROSC{widget_id}-"
        self.gui_osc_receiver_port = f"OSCRECEIVERPORT{widget_id}-"
        self.gui_osc_recenter_address = f"OSCRECENTERADDRESS{widget_id}-"
        self.gui_osc_recalibrate_address = f"OSCRECALIBRATEADDRESS{widget_id}-"
        self.gui_vrc_native = f"-VRCNATIVE{widget_id}-"
        self.gui_vrcft = f"-VRCFT{widget_id}-"
        self.gui_osc_vrcft_v1 = f"-OSCVRCFTV1{widget_id}-"
        self.gui_osc_vrcft_v2 = f"-OSCVRCFTV2{widget_id}-"
        self.gui_use_module = f"-OSCUSEMODULE{widget_id}-"

    def get_values_map(self) -> dict:
        values = super().get_values_map()
        vrcft_enabled = bool(values.get(self.gui_vrcft, False))
        if vrcft_enabled and values.get(self.gui_vrc_native):
            values[self.gui_vrc_native] = False
            self.tk_vars[self.gui_vrc_native].set(False)
        values[self.gui_use_module] = vrcft_enabled
        values[self.gui_osc_vrcft_v2] = vrcft_enabled
        values[self.gui_osc_vrcft_v1] = False
        return values

    def build(self, parent):
        row = 0
        toggle_items = [
            (self.gui_vrc_native, self.config.gui_vrc_native, "VRC Native"),
            (
                self.gui_vrcft,
                self.config.gui_use_module and self.config.gui_osc_vrcft_v2 and not self.config.gui_osc_vrcft_v1,
                "VRCFT",
            ),
            (self.gui_ROSC, self.config.gui_ROSC, "Receive"),
        ]
        for col, (key, default, label) in enumerate(toggle_items):
            var = tk.BooleanVar(value=default)
            self.tk_vars[key] = var
            ttk.Checkbutton(parent, text=label, variable=var).grid(row=row, column=col, sticky="w", padx=8, pady=2)
        row += 1

        # Hidden compatibility toggles still validated/saved through existing config fields.
        self.tk_vars[self.gui_use_module] = tk.BooleanVar(value=bool(self.config.gui_use_module))
        self.tk_vars[self.gui_osc_vrcft_v1] = tk.BooleanVar(value=bool(self.config.gui_osc_vrcft_v1))
        self.tk_vars[self.gui_osc_vrcft_v2] = tk.BooleanVar(value=bool(self.config.gui_osc_vrcft_v2))

        paired_fields = [
            (
                ("Address", self.gui_osc_address, self.config.gui_osc_address, 18),
                ("Port", self.gui_osc_port, self.config.gui_osc_port, 10),
            ),
            (
                ("Recenter Address", self.gui_osc_recenter_address, self.config.gui_osc_recenter_address, 16),
                ("Receiver Port", self.gui_osc_receiver_port, self.config.gui_osc_receiver_port, 10),
            ),
            (
                ("Recalibrate Address", self.gui_osc_recalibrate_address, self.config.gui_osc_recalibrate_address, 28),
                None,
            ),
        ]
        for left, right in paired_fields:
            ttk.Label(parent, text=left[0]).grid(row=row, column=0, sticky="w", padx=8, pady=2)
            left_var = tk.StringVar(value=str(left[2]))
            self.tk_vars[left[1]] = left_var
            ttk.Entry(parent, textvariable=left_var, width=left[3]).grid(row=row, column=1, sticky="w", padx=8, pady=2)

            if right is not None:
                ttk.Label(parent, text=right[0]).grid(row=row, column=2, sticky="w", padx=8, pady=2)
                right_var = tk.StringVar(value=str(right[2]))
                self.tk_vars[right[1]] = right_var
                ttk.Entry(parent, textvariable=right_var, width=right[3]).grid(row=row, column=3, sticky="w", padx=8, pady=2)
            row += 1
