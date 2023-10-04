from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import PySimpleGUI as sg


class AdvancedTrackingAlgoSettingsValidationModel(BaseValidationModel):
    gui_HSF_radius: int
    gui_HSF_radius_left: int
    gui_HSF_radius_right: int
    gui_blob_maxsize: int
    gui_blob_minsize: int
    gui_legacy_ransac_thresh_left: int
    gui_legacy_ransac_thresh_right: int
    gui_skip_autoradius: bool
    gui_thresh_add: int
    gui_threshold_slider: int
    gui_update_check: int


class GeneralSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, settings_base_class, **kwargs):
        super().__init__(config, widget_id, settings_base_class, **kwargs)
        self.validation_model = AdvancedTrackingAlgoSettingsValidationModel

        self.gui_HSF_radius = f"-HSFRADIUS{widget_id}-"
        self.gui_blob_maxsize = f"-BLOBMAXSIZE{widget_id}-"
        self.gui_blob_minsize = f"-BLOBMINSIZE{widget_id}-"
        self.gui_skip_autoradius = f"-SKIPAUTORADIUS{widget_id}-"
        self.gui_thresh_add = f"-THRESHADD{widget_id}-"
        self.gui_update_check = f"-UPDATECHECK{widget_id}-"
        self.gui_threshold_slider = f"-BLOBTHRESHOLD{widget_id}-"
        self.gui_HSF_radius_left = f"-HSFRADIUSLEFT{widget_id}-"
        self.gui_HSF_radius_right = f"-HSFRADIUSRIGHT{widget_id}-"

        self.gui_legacy_ransac_thresh_right = f"-THRESHRIGHT{widget_id}-"
        self.gui_legacy_ransac_thresh_left = f"-THRESHLEFT{widget_id}-"

    def get_layout(self):
        return [
            [
                sg.Checkbox(
                    "HSF: Skip Auto Radius",
                    default=self.config.gui_skip_autoradius,
                    key=self.gui_skip_autoradius,
                    background_color="#424042",
                    tooltip="To gain more control and possibly better tracking quality of HSF, please disable auto radius to enable manual adjustment.",
                ),
            ],
            [
                sg.Text("Left HSF Radius:", background_color="#424042"),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_HSF_radius_left,
                    orientation="h",
                    key=self.gui_HSF_radius_left,
                    background_color="#424042",
                    tooltip="Adjusts the radius parameter for HSF. Only adjust if you are having tracking issues.",
                ),
                sg.Text("Right HSF Radius:", background_color="#424042"),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_HSF_radius_right,
                    orientation="h",
                    key=self.gui_HSF_radius_right,
                    background_color="#424042",
                    tooltip="Adjusts the radius parameter for HSF. Only adjust if you are having tracking issues.",
                ),
            ],
            [
                sg.Text("RANSAC Thresh Add", background_color="#424042"),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_thresh_add,
                    orientation="h",
                    key=self.gui_thresh_add,
                    background_color="#424042",
                    tooltip="Adjusts the amount of threshold to add to RANSAC. Useful for fine tuning your setup.",
                ),
                sg.Text("Blob Threshold", background_color="#424042"),
                # TODO make this for right and left eyes? I dont know how vital that is..
                sg.Slider(
                    range=(0, 110),
                    default_value=self.config.gui_threshold,
                    orientation="h",
                    key=self.gui_threshold_slider,
                    background_color="#424042",
                    tooltip="Adjusts the threshold for blob tracking.",
                ),
            ],
            [
                sg.Text("Min Blob Size:", background_color="#424042"),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_blob_minsize,
                    orientation="h",
                    key=self.gui_blob_minsize,
                    background_color="#424042",
                    tooltip="Minimum size a blob has to be for blob tracking.",
                ),
                sg.Text("Max Blob Size:", background_color="#424042"),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_blob_maxsize,
                    orientation="h",
                    key=self.gui_blob_maxsize,
                    background_color="#424042",
                    tooltip="Maximum size a blob can be for blob tracking.",
                ),
            ],
            [
                sg.Text("Right Eye Thresh:", background_color="#424042"),
                sg.Slider(
                    range=(1, 120),
                    default_value=self.config.gui_legacy_ransac_thresh_right,
                    orientation="h",
                    key=self.gui_legacy_ransac_thresh_right,
                    background_color="#424042",
                    tooltip="Threshold for right eye, legacy RANSAC only",
                ),
                sg.Text("Left Eye Thresh:", background_color="#424042"),
                sg.Slider(
                    range=(1, 120),
                    default_value=self.config.gui_legacy_ransac_thresh_left,
                    orientation="h",
                    key=self.gui_legacy_ransac_thresh_left,
                    background_color="#424042",
                    tooltip="Threshold for left eye, legacy RANSAC only",
                ),
            ],
        ]
