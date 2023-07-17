import copy

import pydantic

from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.base_module import SettingsModule, ValidationBaseSettingsDataModel


class OSCValidationModel(ValidationBaseSettingsDataModel):
    osc_port: int
    osc_address: str
    osc_should_receive: bool
    osc_receive_port: int
    osc_recenter_address: str
    osc_recalibrate_address: str


class OSCSettingsModule(SettingsModule):
    def __init__(self, settings, widget_id, **kwargs):
        super().__init__(settings, widget_id, **kwargs)
        self.config = kwargs.get('config')
        self.gui_osc_address = f"-OSCADDRESS{widget_id}-"
        self.gui_osc_port = f"-OSCPORT{widget_id}-"
        self.gui_ROSC = f"-ROSC{widget_id}-"
        self.gui_osc_receiver_port = f"OSCRECEIVERPORT{widget_id}-"
        self.gui_osc_recenter_address = f"OSCRECENTERADDRESS{widget_id}-"
        self.gui_osc_recalibrate_address = f"OSCRECALIBRATEADDRESS{widget_id}-"

    def validate(self, values) -> dict[str, str]:
        try:
            # return only the changed values
            validated_model = OSCValidationModel(
                osc_port=values["gui_osc_port"],
                osc_address=values["gui_osc_address"],
                osc_should_receive=values["gui_ROSC"],
                osc_receive_port=values["gui_osc_receiver_port"],
                osc_recenter_address=values["gui_osc_recenter_address"],
                osc_recalibrate_address=values["gui_osc_recalibrate_address"],
            )
            return validated_model.dict()
        except pydantic.ValidationError as e:
            return e.errors()

    def get_layout(self):
        return [
            [
                sg.Text("OSC Settings:", background_color="#242224"),
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
