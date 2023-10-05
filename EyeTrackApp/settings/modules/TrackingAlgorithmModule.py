from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import PySimpleGUI as sg


class TrackingAlgorithmValidationModel(BaseValidationModel):
    gui_BLOB: bool
    gui_DADDY: bool
    gui_HSF: bool
    gui_HSRAC: bool
    gui_LEAP: bool
    gui_RANSAC3D: bool
    gui_legacy_ransac: bool

    gui_BLOBP: int
    gui_DADDYP: int
    gui_HSFP: int
    gui_HSRACP: int
    gui_LEAPP: int
    gui_RANSAC3DP: int


class TrackingAlgorithmModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.algo_count = ["1", "2", "3", "4", "5", "6"]
        self.validation_model = TrackingAlgorithmValidationModel
        self.gui_BLOB = f"-BLOBFALLBACK{widget_id}-"
        self.gui_DADDY = f"-DADDY{widget_id}-"
        self.gui_HSF = f"-HSF{widget_id}-"
        self.gui_HSRAC = f"-HSRAC{widget_id}-"
        self.gui_LEAP = f"-LEAP{widget_id}-"
        self.gui_RANSAC3D = f"-RANSAC3D{widget_id}-"
        self.gui_legacy_ransac = f"-LEGACYRANSACTHRESH{widget_id}-"

        self.gui_BLOBP = f"-BLOBP{widget_id}-"
        self.gui_DADDYP = f"-DADDYP{widget_id}-"
        self.gui_HSFP = f"-HSFP{widget_id}-"
        self.gui_HSRACP = f"-HSRACP{widget_id}-"
        self.gui_LEAPP = f"-LEAPP{widget_id}-"
        self.gui_RANSAC3DP = f"-RANSAC3DP{widget_id}-"


    # TODO custom validation, make a set of values, count if there's less than overall, if yeah we have a problem
    def get_layout(self):
        return [
            [
                sg.Text(
                    "Tracking Algorithm Order Settings:",
                    background_color="#242224",
                )
            ],
            [
                sg.Checkbox(
                    "",
                    default=self.config.gui_HSRAC,
                    key=self.gui_HSRAC,
                    background_color="#424042",
                    tooltip="Our flagship algorithm, utilizing both HSF and RANSAC for best tracking quality and lighting resistance.",
                ),
                sg.Combo(
                    self.algo_count,
                    default_value=self.config.gui_HSRACP,
                    key=self.gui_HSRACP,
                    background_color="#424042",
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithms.",
                ),
                sg.Text("HSRAC", background_color="#424042"),
                sg.Checkbox(
                    "",
                    default=self.config.gui_HSF,
                    key=self.gui_HSF,
                    background_color="#424042",
                    tooltip="HSF Is a new, lower resolution tracking algorithim that provides excelent resilancy to lighting conditions and great speed.",
                ),
                sg.Combo(
                    self.algo_count,
                    default_value=self.config.gui_HSFP,
                    key=self.gui_HSFP,
                    background_color="#424042",
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithims.",
                ),
                sg.Text("Haar Surround Feature", background_color="#424042"),
            ],
            [
                sg.Checkbox(
                    "",
                    default=self.config.gui_DADDY,
                    key=self.gui_DADDY,
                    background_color="#424042",
                    tooltip="DADDY Uses a Deep learning algorithm. This has a big CPU usage impact.",
                ),
                sg.Combo(
                    self.algo_count,
                    default_value=self.config.gui_DADDYP,
                    key=self.gui_DADDYP,
                    background_color="#424042",
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithms.",
                ),
                sg.Text("DADDY", background_color="#424042"),
                #   ],
                #   [
                sg.Checkbox(
                    "",
                    default=self.config.gui_RANSAC3D,
                    key=self.gui_RANSAC3D,
                    background_color="#424042",
                    tooltip="RANSAC3D provides good tracking quality, however does not do well in bad lighting conditions.",
                ),
                sg.Combo(
                    self.algo_count,
                    default_value=self.config.gui_RANSAC3DP,
                    key=self.gui_RANSAC3DP,
                    background_color="#424042",
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithms.",
                ),
                sg.Text("RANSAC 3D", background_color="#424042"),
                sg.Checkbox(
                    "Legacy RANSAC Thresh",
                    default=self.config.gui_legacy_ransac,
                    key=self.gui_legacy_ransac,
                    background_color="#424042",
                ),
            ],
            [
                sg.Checkbox(
                    "",
                    default=self.config.gui_LEAP,
                    key=self.gui_LEAP,
                    background_color="#424042",
                    tooltip="LEAP Uses a lightweight deep learning algorithm.",
                ),
                sg.Combo(
                    self.algo_count,
                    default_value=self.config.gui_LEAPP,
                    key=self.gui_LEAPP,
                    background_color="#424042",
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithms.",
                ),
                sg.Text("LEAP", background_color="#424042"),
                sg.Checkbox(
                    "",
                    default=self.config.gui_BLOB,
                    key=self.gui_BLOB,
                    background_color="#424042",
                    tooltip="Blob tracking is the oldest and worst tracking algorithm, it provides fast, though sometimes inaccurate tracking.",
                ),
                sg.Combo(
                    self.algo_count,
                    default_value=self.config.gui_BLOBP,
                    key=self.gui_BLOBP,
                    background_color="#424042",
                    text_color="white",
                    button_arrow_color="black",
                    button_background_color="#6f4ca1",
                    tooltip="Select the priority of eyetracking algorithms.",
                ),
                sg.Text("Blob", background_color="#424042"),
            ],
        ]
