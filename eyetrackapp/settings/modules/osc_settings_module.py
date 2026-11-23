from pydantic import model_validator

from settings.modules.base_module import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from utils.tooltips import attach_tooltip

from localization import tr


class OSCValidationModel(BaseValidationModel):
    gui_ROSC: bool
    gui_osc_oscquery: bool
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
        self.gui_osc_oscquery = f"-OSCQUERY{widget_id}-"
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

    @staticmethod
    def _output_mode_from(settings) -> str:
        if settings.gui_pyvrcft:
            return "pyvrcft"
        if settings.gui_vrc_native:
            return "native"
        if settings.gui_osc_vrcft_v1:
            return "vrcft_v1"
        return "vrcft_v2"

    def apply_external_changes(self, data: dict) -> None:
        super().apply_external_changes(data)
        mode_fields = ("gui_pyvrcft", "gui_vrc_native", "gui_osc_vrcft_v1", "gui_osc_vrcft_v2", "gui_use_module")
        mode_var = self.tk_vars.get(self.gui_osc_output_mode)
        if mode_var is not None and any(field in data for field in mode_fields):
            mode_var.set(self._output_mode_from(self.config))

    def reset_to_defaults(self, defaults):
        mode_var = self.tk_vars.get(self.gui_osc_output_mode)
        if mode_var is not None:
            mode_var.set(self._output_mode_from(defaults))

    def build(self, parent):
        osc_out_initial = self._output_mode_from(self.config)

        osc_bar = ttk.Frame(parent)
        osc_bar.grid(row=0, column=0, sticky="w", pady=2)
        mode_var = tk.StringVar(value=osc_out_initial)
        self.tk_vars[self.gui_osc_output_mode] = mode_var
        # pyVRCFT here; VRC Native and VRCFT v2 are the same choice, under
        # Advanced (build_advanced). VRCFT v1 (legacy) is hidden from the GUI but
        # kept in the backend: get_values_map still maps a saved "vrcft_v1" mode,
        # and output_v1_params still runs, so existing v1 configs keep working.
        pyvrcft_rb = ttk.Radiobutton(osc_bar, text=tr("osc.mode_pyvrcft"), variable=mode_var, value="pyvrcft")
        pyvrcft_rb.pack(side="left", padx=(8, 4))
        attach_tooltip(pyvrcft_rb, tr("osc.mode_pyvrcft_tip"))

        ros_var = tk.BooleanVar(value=bool(self.config.gui_ROSC))
        self.tk_vars[self.gui_ROSC] = ros_var
        receive_cb = ttk.Checkbutton(osc_bar, text=tr("osc.receive"), variable=ros_var)
        receive_cb.pack(side="left", padx=(24, 8))
        attach_tooltip(receive_cb, tr("osc.receive_tip"))

    def build_advanced(self, parent):
        """The other output modes: one choice with pyVRCFT (same variable)."""
        mode_var = self.tk_vars[self.gui_osc_output_mode]
        row = ttk.Frame(parent)
        row.grid(row=0, column=0, sticky="w", padx=8, pady=2)
        ttk.Label(row, text=tr("osc.other_outputs")).pack(side="left", padx=(0, 8))
        native_rb = ttk.Radiobutton(row, text=tr("osc.mode_native"), variable=mode_var, value="native")
        native_rb.pack(side="left", padx=4)
        attach_tooltip(native_rb, tr("osc.mode_native_tip"))
        v2_rb = ttk.Radiobutton(row, text=tr("osc.mode_vrcft_v2"), variable=mode_var, value="vrcft_v2")
        v2_rb.pack(side="left", padx=4)
        attach_tooltip(v2_rb, tr("osc.mode_vrcft_v2_tip"))

        # On by default; off to receive on the fixed Receiver Port (Advanced OSC).
        oscquery_var = tk.BooleanVar(value=bool(getattr(self.config, "gui_osc_oscquery", True)))
        self.tk_vars[self.gui_osc_oscquery] = oscquery_var
        oscquery_cb = ttk.Checkbutton(parent, text=tr("osc.oscquery"), variable=oscquery_var)
        oscquery_cb.grid(row=1, column=0, sticky="w", padx=8, pady=2)
        attach_tooltip(oscquery_cb, tr("osc.oscquery_tip"))
