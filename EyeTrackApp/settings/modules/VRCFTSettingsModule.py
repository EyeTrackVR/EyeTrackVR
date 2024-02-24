from typing import Iterable

import PySimpleGUI as sg

from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
from settings.modules.CommonFieldValidators import check_is_float_convertible


class VRCFTSettingsModuleValidationModel(BaseValidationModel):
    gui_PortNumber: int
    gui_ShouldEmulateEyeWiden: bool
    gui_ShouldEmulateEyeSquint: bool
    gui_ShouldEmulateEyebrows: bool
    gui_WidenThresholdV1_min: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_WidenThresholdV1_max: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_WidenThresholdV2_min: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_WidenThresholdV2_max: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_SqueezeThresholdV1_min: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_SqueezeThresholdV1_max: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_SqueezeThresholdV2_min: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_SqueezeThresholdV2_max: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_EyebrowThresholdRising: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_EyebrowThresholdLowering: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_OutputMultiplier: Annotated[str, AfterValidator(check_is_float_convertible)]


class VRCFTSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.gui_PortNumber = f"-VRCFTSETTINGSPORTNUMBER{widget_id}"
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

    def get_layout(self) -> Iterable:
        return [
            [
                sg.Text("Emulation selection:", background_color="#242224"),
            ],
            [
                sg.Checkbox(
                    "Emulate Eye Widen",
                    default=self.config.gui_ShouldEmulateEyeWiden,
                    key=self.gui_ShouldEmulateEyeWiden,
                    background_color="#424042",
                ),
                sg.Checkbox(
                    "Emulate Eye Squint",
                    default=self.config.gui_ShouldEmulateEyeSquint,
                    key=self.gui_ShouldEmulateEyeSquint,
                    background_color="#424042",
                ),
                sg.Checkbox(
                    "Emulate Eyebrows",
                    default=self.config.gui_ShouldEmulateEyebrows,
                    key=self.gui_ShouldEmulateEyebrows,
                    background_color="#424042",
                ),
            ],
            [
                sg.Text("General Module Settings:", background_color="#242224"),
            ],
            [
                sg.Text("VRCFT Module listening port", background_color="#242224"),
                sg.InputText(
                    self.config.gui_PortNumber,
                    key=self.gui_PortNumber,
                    size=(0, 10),
                    tooltip="UDP port on which the module should listen.",
                ),
                sg.Text("VRCFT Module output multiplier", background_color="#242224"),
                sg.InputText(
                    self.config.gui_OutputMultiplier,
                    key=self.gui_OutputMultiplier,
                    size=(0, 10),
                    tooltip="Output multiplier adjusts the output by the given amount",
                ),
            ],
            [
                sg.Text("Eye Widen thresholds:", background_color="#424042"),
            ],
            [
                sg.Text("V1 Min:", background_color="#424042"),
                sg.Slider(
                    range=(0, 1),
                    resolution=0.01,
                    default_value=float(self.config.gui_WidenThresholdV1_min),
                    orientation="h",
                    key=self.gui_WidenThresholdV1_min,
                    background_color="#424042",
                    tooltip="Controls the point at which the emulation should start for v1 params, reacts to openness",
                ),
                sg.Text("V1 Max:", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.01,
                    default_value=float(self.config.gui_WidenThresholdV1_max),
                    orientation="h",
                    key=self.gui_WidenThresholdV1_max,
                    background_color="#424042",
                    tooltip="Controls the maximum range of widen emulation",
                ),
            ],
            [
                sg.Text("V2 Min:", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.01,
                    default_value=float(self.config.gui_WidenThresholdV2_min),
                    orientation="h",
                    key=self.gui_WidenThresholdV2_min,
                    background_color="#424042",
                    tooltip="Controls the point at which the emulation should start for v2 params, reacts to openness",
                ),
                sg.Text("V2 Max:", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.01,
                    default_value=float(self.config.gui_WidenThresholdV2_max),
                    orientation="h",
                    key=self.gui_WidenThresholdV2_max,
                    background_color="#424042",
                    tooltip="Controls the maximum range of widen emulation",
                ),
            ],
            [
                sg.Text("Eye Squeeze thresholds:", background_color="#424042"),
            ],
            [
                sg.Text("V1 Min:", background_color="#424042"),
                sg.Slider(
                    range=(0, 1),
                    resolution=0.01,
                    default_value=float(self.config.gui_SqueezeThresholdV1_min),
                    orientation="h",
                    key=self.gui_SqueezeThresholdV1_min,
                    background_color="#424042",
                    tooltip="Controls the point at which the emulation should start for v1 params, reacts to openness",
                ),
                sg.Text("V1 Max:", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.01,
                    default_value=float(self.config.gui_SqueezeThresholdV1_max),
                    orientation="h",
                    key=self.gui_SqueezeThresholdV1_max,
                    background_color="#424042",
                    tooltip="Controls the maximum range of squeeze emulation",
                ),
            ],
            [
                sg.Text("V2 Min:", background_color="#424042"),
                sg.Slider(
                    range=(0, 1),
                    resolution=0.01,
                    default_value=float(self.config.gui_SqueezeThresholdV2_min),
                    orientation="h",
                    key=self.gui_SqueezeThresholdV2_min,
                    background_color="#424042",
                    tooltip="Controls the point at which the emulation should start for v2 params, reacts to openness",
                ),
                sg.Text("V2 Max:", background_color="#424042"),
                sg.Slider(
                    range=(-2, 0),
                    resolution=0.01,
                    default_value=float(self.config.gui_SqueezeThresholdV2_max),
                    orientation="h",
                    key=self.gui_SqueezeThresholdV2_max,
                    background_color="#424042",
                    tooltip="Controls the maximum range of squeeze emulation",
                ),
            ],
            [
                sg.Text("Eyebrow emulation Thresholds:", background_color="#424042"),
            ],
            [
                sg.Text("Rising:", background_color="#424042"),
                sg.Slider(
                    range=(0, 1),
                    resolution=0.01,
                    default_value=float(self.config.gui_EyebrowThresholdRising),
                    orientation="h",
                    key=self.gui_EyebrowThresholdRising,
                    background_color="#424042",
                    tooltip="Controls the point at which the emulation should start, reacts to openness",
                ),
                sg.Text("Lowering:", background_color="#424042"),
                sg.Slider(
                    range=(0, 2),
                    resolution=0.01,
                    default_value=float(self.config.gui_EyebrowThresholdLowering),
                    orientation="h",
                    key=self.gui_EyebrowThresholdLowering,
                    background_color="#424042",
                    tooltip="Controls the maximum range of eyebrows emulation",
                ),
            ],
        ]
