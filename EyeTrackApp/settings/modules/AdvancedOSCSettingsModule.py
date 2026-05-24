from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk


class AdvancedOSCValidationModel(BaseValidationModel):
    gui_osc_port: int
    gui_osc_address: str
    gui_osc_receiver_port: int
    gui_osc_recenter_address: str
    gui_osc_recalibrate_address: str


class AdvancedOSCSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = AdvancedOSCValidationModel
        self.gui_osc_address = f"-OSCADDRESS{widget_id}-"
        self.gui_osc_port = f"-OSCPORT{widget_id}-"
        self.gui_osc_receiver_port = f"OSCRECEIVERPORT{widget_id}-"
        self.gui_osc_recenter_address = f"OSCRECENTERADDRESS{widget_id}-"
        self.gui_osc_recalibrate_address = f"OSCRECALIBRATEADDRESS{widget_id}-"

    def build(self, parent):
        paired_fields = [
            (
                ("Address", self.gui_osc_address, self.config.gui_osc_address, 18),
                ("Port", self.gui_osc_port, self.config.gui_osc_port, 10),
            ),
            (
                (
                    "Recenter Address",
                    self.gui_osc_recenter_address,
                    self.config.gui_osc_recenter_address,
                    16,
                ),
                (
                    "Receiver Port",
                    self.gui_osc_receiver_port,
                    self.config.gui_osc_receiver_port,
                    10,
                ),
            ),
            (
                (
                    "Recalibrate Address",
                    self.gui_osc_recalibrate_address,
                    self.config.gui_osc_recalibrate_address,
                    28,
                ),
                None,
            ),
        ]
        for row, (left, right) in enumerate(paired_fields):
            ttk.Label(parent, text=left[0]).grid(
                row=row, column=0, sticky="w", padx=8, pady=2
            )
            left_var = tk.StringVar(value=str(left[2]))
            self.tk_vars[left[1]] = left_var
            ttk.Entry(parent, textvariable=left_var, width=left[3]).grid(
                row=row, column=1, sticky="w", padx=8, pady=2
            )
            if right is not None:
                ttk.Label(parent, text=right[0]).grid(
                    row=row, column=2, sticky="w", padx=8, pady=2
                )
                right_var = tk.StringVar(value=str(right[2]))
                self.tk_vars[right[1]] = right_var
                ttk.Entry(parent, textvariable=right_var, width=right[3]).grid(
                    row=row, column=3, sticky="w", padx=8, pady=2
                )
