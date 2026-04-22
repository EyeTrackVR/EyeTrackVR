from typing import Iterable

import tkinter as tk
from tkinter import ttk

from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
from settings.modules.CommonFieldValidators import check_is_ip_address, try_convert_to_float


class VRCFTSettingsModuleValidationModel(BaseValidationModel):
    gui_VRCFTModulePort: int
    gui_VRCFTModuleIPAddress: Annotated[str, AfterValidator(check_is_ip_address)]
    gui_ShouldEmulateEyeWiden: bool
    gui_ShouldEmulateEyeSquint: bool
    gui_ShouldEmulateEyebrows: bool
    gui_WidenThresholdV1_min: float
    gui_WidenThresholdV1_max: float
    gui_WidenThresholdV2_min: float
    gui_WidenThresholdV2_max: float
    gui_SqueezeThresholdV1_min: float
    gui_SqueezeThresholdV1_max: float
    gui_SqueezeThresholdV2_min: float
    gui_SqueezeThresholdV2_max: float
    gui_EyebrowThresholdRising: float
    gui_EyebrowThresholdLowering: float
    # this is a hack. I don't like it, but that's what I gotta do to make both, Pydantic and PySimpleGUI happy
    gui_OutputMultiplier: Annotated[float, AfterValidator(try_convert_to_float)]


class VRCFTSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = VRCFTSettingsModuleValidationModel
        self.gui_VRCFTModulePort = f"-VRCFTSETTINGSPORTNUMBER{widget_id}"
        self.gui_VRCFTModuleIPAddress = f"-VRCFTSETTINGSIPNUMBER{widget_id}"
        self.gui_ShouldEmulateEyeWiden = f"-VRCFTSETTINGSEMULATEWIDEN{widget_id}"
        self.gui_ShouldEmulateEyeSquint = f"-VRCFTSETTINGSEMULATEEYEWIDEN{widget_id}"
        self.gui_ShouldEmulateEyebrows = f"-VRCFTSETTINGSEMULATEEYEBROWS{widget_id}"
        self.gui_WidenThresholdV1_min = f"-VRCFTSETTINGSWIDENTHRESHOLDV1MIN{widget_id}"
        self.gui_WidenThresholdV1_max = f"-VRCFTSETTINGSWIDENTHRESHOLDV1MAX{widget_id}"
        self.gui_WidenThresholdV2_min = f"-VRCFTSETTINGSWIDENTHRESHOLDV2MIN{widget_id}"
        self.gui_WidenThresholdV2_max = f"-VRCFTSETTINGSWIDENTHRESHOLDV2MAX{widget_id}"
        self.gui_SqueezeThresholdV1_min = f"-VRCFTSETTINGSSQUEEZETHRESHOLDV1MIN{widget_id}"
        self.gui_SqueezeThresholdV1_max = f"-VRCFTSETTINGSSQUEEZETHRESHOLDV1MAX{widget_id}"
        self.gui_SqueezeThresholdV2_min = f"-VRCFTSETTINGSSQUEEZETHRESHOLDV2MIN{widget_id}"
        self.gui_SqueezeThresholdV2_max = f"-VRCFTSETTINGSSQUEEZETHRESHOLDV2MAX{widget_id}"
        self.gui_EyebrowThresholdRising = f"-VRCFTSETTINGSEYEBROWTHRESHOLDRISING{widget_id}"
        self.gui_EyebrowThresholdLowering = f"-VRCFTSETTINGSEYEBROWTHRESHOLDLOWERING{widget_id}"
        self.gui_OutputMultiplier = f"-VRCFTSETTINGSOUTPUTMULTIPLIER{widget_id}"

    def _add_slider_with_controls(self, parent, row, label, var, min_v, max_v, step=0.01):
        slider_length = 160
        value_label_var = tk.StringVar(value=f"{float(var.get()):.2f}")

        def _snap(value: float) -> float:
            return round(round(value / step) * step, 2)

        def sync(*_args):
            value_label_var.set(f"{_snap(float(var.get())):.2f}")

        def bump(delta):
            next_val = _snap(float(var.get()) + (delta * step))
            next_val = max(min_v, min(max_v, next_val))
            var.set(next_val)

        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        ttk.Scale(parent, from_=min_v, to=max_v, variable=var, orient="horizontal", length=slider_length).grid(
            row=row, column=1, sticky="w", padx=8, pady=2
        )
        ttk.Button(parent, text="-", width=2, command=lambda: bump(-1)).grid(row=row, column=2, sticky="w", padx=(4, 2), pady=2)
        ttk.Label(parent, textvariable=value_label_var, width=6, anchor="center").grid(row=row, column=3, sticky="w", padx=2, pady=2)
        ttk.Button(parent, text="+", width=2, command=lambda: bump(1)).grid(row=row, column=4, sticky="w", padx=(2, 8), pady=2)
        var.trace_add("write", sync)

    def build(self, parent) -> Iterable:
        row = 0
        for col, (key, default, label) in enumerate([
            (self.gui_ShouldEmulateEyeWiden, self.config.gui_ShouldEmulateEyeWiden, "Emulate Eye Widen"),
            (self.gui_ShouldEmulateEyeSquint, self.config.gui_ShouldEmulateEyeSquint, "Emulate Eye Squint"),
            (self.gui_ShouldEmulateEyebrows, self.config.gui_ShouldEmulateEyebrows, "Emulate Eyebrows"),
        ]):
            var = tk.BooleanVar(value=default)
            self.tk_vars[key] = var
            ttk.Checkbutton(parent, text=label, variable=var).grid(row=row, column=col, sticky="w", padx=8, pady=2)
        row += 1

        ttk.Label(parent, text="VRCFT Module listening IP").grid(row=row, column=0, sticky="w", padx=8, pady=2)
        ip_var = tk.StringVar(value=str(self.config.gui_VRCFTModuleIPAddress))
        self.tk_vars[self.gui_VRCFTModuleIPAddress] = ip_var
        ttk.Entry(parent, textvariable=ip_var, width=16).grid(row=row, column=1, sticky="w", padx=8, pady=2)

        ttk.Label(parent, text="VRCFT Module listening port").grid(row=row, column=2, sticky="w", padx=8, pady=2)
        port_var = tk.StringVar(value=str(self.config.gui_VRCFTModulePort))
        self.tk_vars[self.gui_VRCFTModulePort] = port_var
        ttk.Entry(parent, textvariable=port_var, width=10).grid(row=row, column=3, sticky="w", padx=8, pady=2)
        row += 1

        ttk.Label(parent, text="VRCFT Module output multiplier").grid(row=row, column=0, sticky="w", padx=8, pady=2)
        out_var = tk.StringVar(value=str(self.config.gui_OutputMultiplier))
        self.tk_vars[self.gui_OutputMultiplier] = out_var
        ttk.Entry(parent, textvariable=out_var, width=16).grid(row=row, column=1, sticky="w", padx=8, pady=2)
        row += 1

        slider_frame = ttk.Frame(parent)
        slider_frame.grid(row=row, column=0, columnspan=5, sticky="ew", padx=0, pady=(4, 0))
        row = 0

        slider_specs = [
            ("Widen V1 Min", self.gui_WidenThresholdV1_min, self.config.gui_WidenThresholdV1_min, 0, 1),
            ("Widen V1 Max", self.gui_WidenThresholdV1_max, self.config.gui_WidenThresholdV1_max, 0, 2),
            ("Widen V2 Min", self.gui_WidenThresholdV2_min, self.config.gui_WidenThresholdV2_min, 0, 2),
            ("Widen V2 Max", self.gui_WidenThresholdV2_max, self.config.gui_WidenThresholdV2_max, 0, 2),
            ("Squeeze V1 Min", self.gui_SqueezeThresholdV1_min, self.config.gui_SqueezeThresholdV1_min, 0, 1),
            ("Squeeze V1 Max", self.gui_SqueezeThresholdV1_max, self.config.gui_SqueezeThresholdV1_max, 0, 2),
            ("Squeeze V2 Min", self.gui_SqueezeThresholdV2_min, self.config.gui_SqueezeThresholdV2_min, 0, 1),
            ("Squeeze V2 Max", self.gui_SqueezeThresholdV2_max, self.config.gui_SqueezeThresholdV2_max, -2, 0),
            ("Eyebrow Rising", self.gui_EyebrowThresholdRising, self.config.gui_EyebrowThresholdRising, 0, 1),
            ("Eyebrow Lowering", self.gui_EyebrowThresholdLowering, self.config.gui_EyebrowThresholdLowering, 0, 2),
        ]
        for label, key, default, min_v, max_v in slider_specs:
            var = tk.DoubleVar(value=float(default))
            self.tk_vars[key] = var
            self._add_slider_with_controls(slider_frame, row, label, var, min_v, max_v, step=0.01)
            row += 1
