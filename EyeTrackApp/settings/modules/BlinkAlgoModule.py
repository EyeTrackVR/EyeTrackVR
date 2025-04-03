from pydantic import AfterValidator
from typing_extensions import Annotated

from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import PySimpleGUI as sg

from settings.modules.CommonFieldValidators import check_is_float_convertible


class BlinkAlgoSettingsValidationModel(BaseValidationModel):
    gui_IBO: bool
    gui_RANSACBLINK: bool
    gui_BLINK: bool
    gui_LEAP_lid: bool
    ibo_filter_samples: int
    calibration_samples: int
    ibo_fully_close_eye_threshold: Annotated[str, AfterValidator(check_is_float_convertible)]
    gui_circular_crop_left: bool
    gui_circular_crop_right: bool
    leap_calibration_samples: int


class BlinkAlgoSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = BlinkAlgoSettingsValidationModel

        self.gui_IBO = f"-IBO{widget_id}-"
        self.gui_RANSACBLINK = f"-RANSACBLINK{widget_id}-"
        self.gui_BLINK = f"-BLINK{widget_id}-"
        self.gui_LEAP_lid = f"-LEAPLID{widget_id}-"
        self.ibo_filter_samples = f"-IBOFILTERSAMPLE{widget_id}-"
        self.calibration_samples = f"-CALIBRATIONSAMPLES{widget_id}-"
        self.ibo_fully_close_eye_threshold = f"-CLOSETHRESH{widget_id}-"
        self.gui_circular_crop_left = f"-CIRCLECROPLEFT{widget_id}-"
        self.gui_circular_crop_right = f"-CIRCLECROPRIGHT{widget_id}-"
        self.leap_calibration_samples = f"-LEAPCALIBRATION{widget_id}-"

    def get_layout(self):
        return [
            [sg.Text("Blink Algo Settings:", background_color="#242224")],
            [
                sg.Checkbox(
                    "Intensity Based Openness",
                    default=self.config.gui_IBO,
                    key=self.gui_IBO,
                    background_color="#424042",
                ),
                sg.Checkbox(
                    "RANSAC Quick Blink Algo",
                    default=self.config.gui_RANSACBLINK,
                    key=self.gui_RANSACBLINK,
                    background_color="#424042",
                ),
                sg.Checkbox(
                    "Binary Blink Algo",
                    default=self.config.gui_BLINK,
                    key=self.gui_BLINK,
                    background_color="#424042",
                ),
                sg.Checkbox(
                    "LEAP Lid",
                    default=self.config.gui_LEAP_lid,
                    key=self.gui_LEAP_lid,
                    background_color="#424042",
                ),
            ],
            [
                sg.Text("LEAP Calibration Samples", background_color="#424042"),
                sg.InputText(
                    self.config.leap_calibration_samples,
                    key=self.leap_calibration_samples,
                    size=(0, 10),
                ),
            ],
            [
                sg.Text("IBO Filter Sample Size", background_color="#424042"),
                sg.InputText(
                    self.config.ibo_filter_samples,
                    key=self.ibo_filter_samples,
                    size=(0, 10),
                ),
                sg.Text("Calibration Samples", background_color="#424042"),
                sg.InputText(
                    self.config.calibration_samples,
                    key=self.calibration_samples,
                    size=(0, 10),
                ),
                sg.Text("IBO Close Threshold", background_color="#424042"),
                sg.InputText(
                    self.config.ibo_fully_close_eye_threshold,
                    key=self.ibo_fully_close_eye_threshold,
                    size=(0, 10),
                ),
            ],
            [
                sg.Checkbox(
                    "Left Eye Circle crop",
                    default=self.config.gui_circular_crop_left,
                    key=self.gui_circular_crop_left,
                    background_color="#424042",
                ),
                sg.Checkbox(
                    "Right Eye Circle crop",
                    default=self.config.gui_circular_crop_right,
                    key=self.gui_circular_crop_right,
                    background_color="#424042",
                ),
            ],
        ]
