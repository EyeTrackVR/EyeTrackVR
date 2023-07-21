import copy
from typing import Any

import pydantic

from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.base_module import SettingsModule, ValidationBaseSettingsDataModel


class OSCValidationModel(ValidationBaseSettingsDataModel):
    gui_osc_port: int
    gui_osc_address: str
    gui_ROSC: bool
    gui_osc_receiver_port: int
    gui_osc_recenter_address: str
    gui_osc_recalibrate_address: str


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

    def validate(self, values) -> (dict[str, Any], dict[str, str]):
        try:
            changes = {}
            validated_model = OSCValidationModel(
                gui_osc_port=values[self.gui_osc_port],
                gui_osc_address=values[self.gui_osc_address],
                gui_ROSC=values[self.gui_ROSC],
                gui_osc_receiver_port=values[self.gui_osc_receiver_port],
                gui_osc_recenter_address=values[self.gui_osc_recenter_address],
                gui_osc_recalibrate_address=values[self.gui_osc_recalibrate_address],
            )
            for field, value in validated_model.dict().items():
                if getattr(self.config, field) != value:
                    changes[field] = value
            return changes, {},
        except pydantic.ValidationError as e:
            return {}, e.errors()

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
