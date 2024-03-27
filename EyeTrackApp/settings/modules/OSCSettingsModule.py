from pydantic import model_validator

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg


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
        self.gui_osc_vrcft_v1 = f"-OSCVRCFTV1{widget_id}-"
        self.gui_osc_vrcft_v2 = f"-OSCVRCFTV2{widget_id}-"
        self.gui_use_module = f"-OSCUSEMODULE{widget_id}-"

    def get_layout(self):
        return [
            [
                sg.Text("OSC Settings:", background_color="#242224"),
            ],
            [
                sg.Checkbox(
                    "Use ETVR VRCFT Module",
                    default=self.config.gui_use_module,
                    key=self.gui_use_module,
                    background_color="#424042",
                    tooltip="Toggle output to VRCFT Module or just regular OSC port",
                ),
            ],
            [
                sg.Checkbox(
                    "VRC Native Eyetracking",
                    default=self.config.gui_vrc_native,
                    key=self.gui_vrc_native,
                    background_color="#424042",
                    tooltip="Toggle VRCFT output or VRC native",
                ),
                sg.Checkbox(
                    "VRCFT v1",
                    default=self.config.gui_osc_vrcft_v1,
                    key=self.gui_osc_vrcft_v1,
                    background_color="#424042",
                    tooltip="Toggle VRCFT's v1 Eyetracking format.",
                ),
                sg.Checkbox(
                    "VRCFT v2 (UE)",
                    default=self.config.gui_osc_vrcft_v2,
                    key=self.gui_osc_vrcft_v2,
                    background_color="#424042",
                    tooltip="Toggle VRCFT's v2 (UE) Eyetracking format.",
                ),
            ],
            [
                sg.Text("Address:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_osc_address,
                    key=self.gui_osc_address,
                    size=(0, 20),
                    tooltip="IP address we send OSC data to.",
                ),
                sg.Text("Port:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_osc_port,
                    key=self.gui_osc_port,
                    size=(0, 10),
                    tooltip="OSC port we send data to.",
                ),
            ],
            [
                sg.Text("Receive functions", background_color=BACKGROUND_COLOR),
                sg.Checkbox(
                    "",
                    default=self.config.gui_ROSC,
                    key=self.gui_ROSC,
                    background_color=BACKGROUND_COLOR,
                    size=(0, 10),
                    tooltip="Toggle OSC receive functions.",
                ),
            ],
            [
                sg.Text("Receiver Port:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_osc_receiver_port,
                    key=self.gui_osc_receiver_port,
                    size=(0, 10),
                    tooltip="Port we receive OSC data from (used to recalibrate or recenter app from within VRChat.",
                ),
                sg.Text("Recenter Address:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_osc_recenter_address,
                    key=self.gui_osc_recenter_address,
                    size=(0, 10),
                    tooltip="OSC Address used for recentering your eye.",
                ),
            ],
            [
                sg.Text("Recalibrate Address:", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_osc_recalibrate_address,
                    key=self.gui_osc_recalibrate_address,
                    size=(0, 10),
                    tooltip="OSC address we use for recalibrating your eye",
                ),
            ],
        ]
