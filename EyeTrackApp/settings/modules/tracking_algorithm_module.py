from typing import Optional, Any

import pydantic

from settings.constants import BACKGROUND_COLOR
import PySimpleGUI as sg

from settings.modules.base_module import SettingsModule, BaseValidationModel


class TrackingAlgorithmsValidationModel(BaseValidationModel):
    gui_BLOB: bool
    gui_HSF: bool
    gui_DADDY: bool
    gui_RANSAC3D: bool
    gui_BLINK: bool
    gui_IBO: bool
    gui_HSRAC: bool

    gui_HSF_radius: int
    gui_blob_maxsize: int
    gui_blob_minsize: int
    gui_speed_coefficient: str  # GUI lib does not support doubles ;-;
    gui_min_cutoff: str  # or floats ;-;

    gui_skip_autoradius: int
    gui_DADDYP: int
    gui_HSRACP: int
    gui_RANSAC3DP: int
    gui_HSFP: int
    gui_BLOBP: int

    gui_thresh_add: int
    gui_circular_crop_left: bool
    gui_circular_crop_right: bool
    gui_threshold: int


class TrackingAlgorithmsModule(SettingsModule):
    def __init__(self, settings, widget_id, **kwargs):
        super().__init__(settings, widget_id, **kwargs)
        self.validation_model = TrackingAlgorithmsValidationModel
        self.config = kwargs.get("config")

        self.gui_BLOB = f"-BLOBFALLBACK{widget_id}-"
        self.gui_HSF = f"-HSF{widget_id}-"
        self.gui_DADDY = f"-DADDY{widget_id}-"
        self.gui_DADDYP = f"-DADDYP{widget_id}-"
        self.gui_RANSAC3D = f"-RANSAC3D{widget_id}-"
        self.gui_BLINK = f"-BLINK{widget_id}-"
        self.gui_IBO = f"-IBO{widget_id}-"
        self.gui_HSRAC = f"-HSRAC{widget_id}-"
        self.gui_HSF_radius = f"-HSFRADIUS{widget_id}-"
        self.gui_blob_maxsize = f"-BLOBMAXSIZE{widget_id}-"
        self.gui_blob_minsize = f"-BLOBMINSIZE{widget_id}-"
        self.gui_speed_coefficient = f"-SPEEDCOEFFICIENT{widget_id}-"
        self.gui_min_cutoff = f"-MINCUTOFF{widget_id}-"

        self.gui_skip_autoradius = f"-SKIPAUTORADIUS{widget_id}-"
        self.gui_HSRACP = f"-HSRACP{widget_id}-"
        self.gui_RANSAC3DP = f"-RANSAC3DP{widget_id}-"
        self.gui_HSFP = f"-HSFP{widget_id}-"
        self.gui_BLOBP = f"-BLOBP{widget_id}-"
        self.gui_thresh_add = f"-THRESHADD{widget_id}-"

        self.gui_circular_crop_left = f"-CIRCLECROPLEFT{widget_id}-"
        self.gui_circular_crop_right = f"-CIRCLECROPRIGHT{widget_id}-"
        self.gui_threshold = f"-BLOBTHRESHOLD{widget_id}-"


    def get_layout(self):
        return [
            *self.get_basic_layout(),
            *self.get_one_euro_filter_layout(),
        ]

    def get_basic_layout(self):
        return [
            [
                sg.Text("Tracking Algorithim Settings:", background_color="#242224"),
            ],
            [
                sg.Checkbox(
                    "",
                    default=self.config.gui_HSRAC,
                    key=self.gui_HSRAC,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Our flagship algoritim, utilizing both HSF and RANSAC for best tracking quality and lighting resistance.",
                ),
                sg.Combo(
                    ["1", "2", "3", "4"],
                    default_value=self.config.gui_HSRACP,
                    key=self.gui_HSRACP,
                    background_color=BACKGROUND_COLOR,
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithims.",
                ),
                sg.Text("HSRAC", background_color=BACKGROUND_COLOR),
                sg.Checkbox(
                    "",
                    default=self.config.gui_HSF,
                    key=self.gui_HSF,
                    background_color=BACKGROUND_COLOR,
                    tooltip="HSF Is a new, lower resolution tracking algorithim that provides excelent resilancy to lighting conditions and great speed.",
                ),
                sg.Combo(
                    ["1", "2", "3", "4", "5"],
                    default_value=self.config.gui_HSFP,
                    key=self.gui_HSFP,
                    background_color=BACKGROUND_COLOR,
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithims.",
                ),
                sg.Text("Haar Surround Feature", background_color=BACKGROUND_COLOR),
            ],
            [
                sg.Checkbox(
                    "",
                    default=self.config.gui_DADDY,
                    key=self.gui_DADDY,
                    background_color=BACKGROUND_COLOR,
                    tooltip="DADDY Uses a Deep learning algorithm. This has a big CPU usage impact.",
                ),
                sg.Combo(
                    ["1", "2", "3", "4", "5"],
                    default_value=self.config.gui_DADDYP,
                    key=self.gui_DADDYP,
                    background_color=BACKGROUND_COLOR,
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithims.",
                ),
                sg.Text("DADDY", background_color=BACKGROUND_COLOR),
                sg.Checkbox(
                    "",
                    default=self.config.gui_RANSAC3D,
                    key=self.gui_RANSAC3D,
                    background_color=BACKGROUND_COLOR,
                    tooltip="RANSAC3D provides good tracking quality, however does not do well in bad lighting conditions.",
                ),
                sg.Combo(
                    ["1", "2", "3", "4", "5"],
                    default_value=self.config.gui_RANSAC3DP,
                    key=self.gui_RANSAC3DP,
                    background_color=BACKGROUND_COLOR,
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithims.",
                ),
                sg.Text("RANSAC 3D", background_color=BACKGROUND_COLOR),
            ],
            [
                sg.Checkbox(
                    "",
                    default=self.config.gui_BLOB,
                    key=self.gui_BLOB,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Blob tracking is the oldest and worst tracking algorithm, it provides fast, though sometimes innaccurate tracking.",
                ),
                sg.Combo(
                    ["1", "2", "3", "4", "5"],
                    default_value=self.config.gui_BLOBP,
                    key=self.gui_BLOBP,
                    background_color=BACKGROUND_COLOR,
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithims.",
                ),
                sg.Text("Blob", background_color=BACKGROUND_COLOR),
            ],
            [
                sg.Checkbox(
                    "Intensity Based Openness",
                    default=self.config.gui_IBO,
                    key=self.gui_IBO,
                    background_color=BACKGROUND_COLOR,
                ),
                sg.Checkbox(
                    "Bianary Blink Algo",
                    default=self.config.gui_BLINK,
                    key=self.gui_BLINK,
                    background_color=BACKGROUND_COLOR,
                ),
            ],
            [
                sg.Checkbox(
                    "Left Eye Circle crop",
                    default=self.config.gui_circular_crop_left,
                    key=self.gui_circular_crop_left,
                    background_color=BACKGROUND_COLOR,
                ),
                sg.Checkbox(
                    "Right Eye Circle crop",
                    default=self.config.gui_circular_crop_right,
                    key=self.gui_circular_crop_right,
                    background_color=BACKGROUND_COLOR,
                ),
            ],
            [
                sg.Checkbox(
                    "HSF: Skip Auto Radius",
                    default=self.config.gui_skip_autoradius,
                    key=self.gui_skip_autoradius,
                    background_color=BACKGROUND_COLOR,
                    tooltip="To gain more control and possibly better tracking quality of HSF, please disable auto radius to enable manual adjustment.",
                ),
                sg.Text("HSF Radius:", background_color=BACKGROUND_COLOR),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_HSF_radius,
                    orientation="h",
                    key=self.gui_HSF_radius,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Adjusts the radius paramater for HSF. Only adjust if you are having tracking issues.",
                ),
            ],
            [
                sg.Text("RANSAC Thresh Add", background_color=BACKGROUND_COLOR),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_thresh_add,
                    orientation="h",
                    key=self.gui_thresh_add,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Adjusts the ammount of threshold to add to RANSAC. Usefull for fine tuning your setup.",
                ),
                #  ],
                # [
                sg.Text(
                    "Blob Threshold", background_color=BACKGROUND_COLOR
                ),  # TODO make this for right and left eyes? I dont know how vital that is..
                sg.Slider(
                    range=(0, 110),
                    default_value=self.config.gui_threshold,
                    orientation="h",
                    key=self.gui_threshold,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Adjusts the threshold for blob tracking.",
                ),
            ],
            [
                sg.Text("Min Blob Size:", background_color=BACKGROUND_COLOR),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_blob_minsize,
                    orientation="h",
                    key=self.gui_blob_minsize,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Minimun size a blob has to be for blob tracking.",
                ),
                sg.Text("Max Blob Size:", background_color=BACKGROUND_COLOR),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_blob_maxsize,
                    orientation="h",
                    key=self.gui_blob_maxsize,
                    background_color=BACKGROUND_COLOR,
                    tooltip="Maximum size a blob can be for blob tracking.",
                ),
            ],
        ]

    def get_one_euro_filter_layout(self):
        return [
            [
                sg.Text("One Euro Filter Paramaters:", background_color="#242224"),
            ],
            [
                sg.Text("Min Frequency Cutoff", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_min_cutoff,
                    key=self.gui_min_cutoff,
                    size=(0, 10),
                ),
                sg.Text("Speed Coefficient", background_color=BACKGROUND_COLOR),
                sg.InputText(
                    self.config.gui_speed_coefficient,
                    key=self.gui_speed_coefficient,
                    size=(0, 10),
                ),
            ],
        ]
