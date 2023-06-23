import PySimpleGUI as sg

from config import EyeTrackSettingsConfig
from osc import EyeId
from queue import Queue
from threading import Event

class AlgoSettingsWidget:
    def __init__(self, widget_id: EyeId, main_config: EyeTrackSettingsConfig, osc_queue: Queue):

        self.gui_flip_x_axis_left = f"-FLIPXAXISLEFT{widget_id}-"
        self.gui_flip_x_axis_right = f"-FLIPXAXISRIGHT{widget_id}-"
        self.gui_flip_y_axis = f"-FLIPYAXIS{widget_id}-"
        self.gui_general_settings_layout = f"-GENERALSETTINGSLAYOUT{widget_id}-"
        self.gui_osc_address = f"-OSCADDRESS{widget_id}-"
        self.gui_osc_port = f"-OSCPORT{widget_id}-"
        self.gui_osc_receiver_port = f"OSCRECEIVERPORT{widget_id}-"
        self.gui_osc_recenter_address = f"OSCRECENTERADDRESS{widget_id}-"
        self.gui_osc_recalibrate_address = f"OSCRECALIBRATEADDRESS{widget_id}-"
        self.gui_BLOB = f"-BLOBFALLBACK{widget_id}-"
        self.gui_HSF = f"-HSF{widget_id}-"
        self.gui_DADDY = f"-DADDY{widget_id}-"
        self.gui_DADDYP = f"-DADDYP{widget_id}-"
        self.gui_MOMMYP = f"-MOMMYP{widget_id}-"
        self.gui_MOMMY = f"-MOMMY{widget_id}-"
        self.gui_RANSAC3D = f"-RANSAC3D{widget_id}-"
        self.gui_BLINK = f"-BLINK{widget_id}-"
        self.gui_IBO = f"-IBO{widget_id}-"
        self.gui_HSRAC = f"-HSRAC{widget_id}-"
        self.gui_HSF_radius = f"-HSFRADIUS{widget_id}-"
        self.gui_blob_maxsize = f"-BLOBMAXSIZE{widget_id}-"
        self.gui_blob_minsize = f"-BLOBMINSIZE{widget_id}-"
        self.gui_speed_coefficient = f"-SPEEDCOEFFICIENT{widget_id}-"
        self.gui_min_cutoff = f"-MINCUTOFF{widget_id}-"
        self.gui_eye_falloff = f"-EYEFALLOFF{widget_id}-"
        self.gui_skip_autoradius = f"-SKIPAUTORADIUS{widget_id}-"
        self.gui_HSRACP = f"-HSRACP{widget_id}-"
        self.gui_RANSAC3DP = f"-RANSAC3DP{widget_id}-"
        self.gui_HSFP = f"-HSFP{widget_id}-"
        self.gui_BLOBP = f"-BLOBP{widget_id}-"
        self.gui_thresh_add = f"-THRESHADD{widget_id}-"
        self.gui_ROSC = f"-ROSC{widget_id}-"
        self.gui_vrc_native = f"-VRCNATIVE{widget_id}-"
        self.gui_circular_crop_left = f"-CIRCLECROPLEFT{widget_id}-"
        self.gui_circular_crop_right = f"-CIRCLECROPRIGHT{widget_id}-"
        self.gui_update_check = f"-UPDATECHECK{widget_id}-"
        self.gui_threshold_slider = f"-BLOBTHRESHOLD{widget_id}-"
        self.gui_HSF_radius_left = f"-HSFRADIUSLEFT{widget_id}-"
        self.gui_HSF_radius_right = f"-HSFRADIUSRIGHT{widget_id}-"
        self.ibo_filter_samples = f"-IBOFILTERSAMPLE{widget_id}-"
        self.calibration_samples = f"-CALIBRATIONSAMPLES{widget_id}-"
        self.ibo_fully_close_eye_threshold = f"-CLOSETHRESH{widget_id}-"
        self.main_config = main_config
        self.config = main_config.settings
        self.osc_queue = osc_queue

        # Define the window's contents
        self.general_settings_layout = [


            [sg.Checkbox(
                    "",
                    default=self.config.gui_HSRAC,
                    key=self.gui_HSRAC,
                    background_color='#424042',
                    tooltip = "Our flagship algoritim, utilizing both HSF and RANSAC for best tracking quality and lighting resistance.",
                ),
                sg.Combo(['1','2','3','4'],
                default_value=self.config.gui_HSRACP,
                key=self.gui_HSRACP,
                background_color='#424042',
                text_color='white',
                button_arrow_color= "black",
                button_background_color = "#6f4ca1",
                tooltip = "Select the priority of eyetracking algorithims.",
                ),
                sg.Text("HSRAC", background_color='#424042'),
           # ],
           # [
                sg.Checkbox(
                    "",
                    default=self.config.gui_HSF,
                    key=self.gui_HSF,
                    background_color='#424042',
                    tooltip = "HSF Is a new, lower resolution tracking algorithim that provides excelent resilancy to lighting conditions and great speed.",
                ),
                sg.Combo(['1','2','3','4','5'],
                default_value=self.config.gui_HSFP,
                key=self.gui_HSFP,
                background_color='#424042',
                text_color='white',
                button_arrow_color= "black",
                button_background_color = "#6f4ca1",
                tooltip = "Select the priority of eyetracking algorithims.",
                ),
                sg.Text("Haar Surround Feature", background_color='#424042'),
            ],
            [sg.Checkbox(
                    "",
                    default=self.config.gui_DADDY,
                    key=self.gui_DADDY,
                    background_color='#424042',
                    tooltip = "DADDY Uses a Deep learning algorithm. This has a big CPU usage impact.",
                ),
                sg.Combo(['1','2','3','4','5'],
                default_value=self.config.gui_DADDYP,
                key=self.gui_DADDYP,
                background_color='#424042',
                text_color='white',
                button_arrow_color= "black",
                button_background_color = "#6f4ca1",
                tooltip = "Select the priority of eyetracking algorithims.",
                ),
                sg.Text("DADDY", background_color='#424042'),
         #   ],
         #   [
                sg.Checkbox(
                    "",
                    default=self.config.gui_RANSAC3D,
                    key=self.gui_RANSAC3D,
                    background_color='#424042',
                    tooltip = "RANSAC3D provides good tracking quality, however does not do well in bad lighting conditions.",
                ),
                sg.Combo(['1','2','3','4','5'],
                default_value=self.config.gui_RANSAC3DP,
                key=self.gui_RANSAC3DP,
                background_color='#424042',
                text_color='white',
                button_arrow_color= "black",
                button_background_color = "#6f4ca1",
                tooltip = "Select the priority of eyetracking algorithims.",
                ),
                sg.Text("RANSAC 3D", background_color='#424042'),
            ],
            [
                sg.Checkbox(
                    "",
                    default=self.config.gui_MOMMY,
                    key=self.gui_MOMMY,
                    background_color='#424042',
                    tooltip="MOMMY Uses a lightweight Deep learning algorithm.",
                ),
                    sg.Combo(['1', '2', '3', '4', '5'],
                             default_value=self.config.gui_MOMMYP,
                             key=self.gui_MOMMYP,
                             background_color='#424042',
                             text_color='white',
                             button_arrow_color="black",
                             button_background_color="#6f4ca1",
                             tooltip="Select the priority of eyetracking algorithims.",
                             ),
                    sg.Text("MOMMY", background_color='#424042'),

                sg.Checkbox(
                    "",
                    default=self.config.gui_BLOB,
                    key=self.gui_BLOB,
                    background_color='#424042',
                    tooltip = "Blob tracking is the oldest and worst tracking algorithm, it provides fast, though sometimes innaccurate tracking.",
                ),
                sg.Combo(['1','2','3','4','5'],
                default_value=self.config.gui_BLOBP,
                key=self.gui_BLOBP,
                background_color='#424042',
                text_color='white',
                button_arrow_color= "black",
                button_background_color = "#6f4ca1",
                tooltip = "Select the priority of eyetracking algorithims.",
                ),
                sg.Text("Blob", background_color='#424042'),
            ],
            [
            sg.Text("Blink Algo Settings:", background_color='#242224')
            ],
            [
                sg.Checkbox(
                    "Intensity Based Openness",
                    default=self.config.gui_IBO,
                    key=self.gui_IBO,
                    background_color='#424042',
                ),
                sg.Checkbox(
                    "Bianary Blink Algo",
                    default=self.config.gui_BLINK,
                    key=self.gui_BLINK,
                    background_color='#424042',
                ),

                
            ],
            [
                sg.Text("IBO Filter Sample Size", background_color='#424042'),
                sg.InputText(
                    self.config.ibo_filter_samples,
                    key=self.ibo_filter_samples,
                    size=(0,10),
                ),
                sg.Text("Calibration Samples", background_color='#424042'),
                sg.InputText(
                    self.config.calibration_samples,
                    key=self.calibration_samples,
                    size=(0,10),
                ),

                sg.Text("IBO Close Threshold", background_color='#424042'),
                sg.InputText(
                    self.config.ibo_fully_close_eye_threshold,
                    key=self.ibo_fully_close_eye_threshold,
                    size=(0,10),
                ),
            ],
                        [
                sg.Checkbox(
                    "Left Eye Circle crop",
                    default=self.config.gui_circular_crop_left,
                    key=self.gui_circular_crop_left,
                    background_color='#424042',
                ),
                sg.Checkbox(
                    "Right Eye Circle crop",
                    default=self.config.gui_circular_crop_right,
                    key=self.gui_circular_crop_right,
                    background_color='#424042',
                ),
            ],
            [
            sg.Text("Advanced Tracking Algorithim Settings:", background_color='#242224')
            ],
            [sg.Checkbox(
                    "HSF: Skip Auto Radius",
                    default=self.config.gui_skip_autoradius,
                    key=self.gui_skip_autoradius,
                    background_color='#424042',
                    tooltip = "To gain more control and possibly better tracking quality of HSF, please disable auto radius to enable manual adjustment.",
                ),
            ],
            [
                sg.Text("Left HSF Radius:", background_color='#424042'),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_HSF_radius_left,
                    orientation="h",
                    key=self.gui_HSF_radius_left,
                    background_color='#424042',
                    tooltip = "Adjusts the radius paramater for HSF. Only adjust if you are having tracking issues.",
                ),
            ],
            [
                sg.Text("Right HSF Radius:", background_color='#424042'),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_HSF_radius_right,
                    orientation="h",
                    key=self.gui_HSF_radius_right,
                    background_color='#424042',
                    tooltip="Adjusts the radius paramater for HSF. Only adjust if you are having tracking issues.",
                ),

            ],
            [sg.Text("RANSAC Thresh Add", background_color='#424042'),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_thresh_add,
                    orientation="h",
                    key=self.gui_thresh_add,
                    background_color='#424042',
                    tooltip = "Adjusts the ammount of threshold to add to RANSAC. Usefull for fine tuning your setup.",
                ),
          #  ],
           # [
                sg.Text("Blob Threshold", background_color='#424042'), #TODO make this for right and left eyes? I dont know how vital that is..
                sg.Slider(
                    range=(0, 110),
                    default_value=self.config.gui_threshold,
                    orientation="h",
                    key=self.gui_threshold_slider,
                    background_color='#424042',
                    tooltip = "Adjusts the threshold for blob tracking.",
                ),
            ],
            [sg.Text("Min Blob Size:", background_color='#424042'),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_blob_minsize,
                    orientation="h",
                    key=self.gui_blob_minsize,
                    background_color='#424042',
                    tooltip = "Minimun size a blob has to be for blob tracking.",
                ),
                
                sg.Text("Max Blob Size:", background_color='#424042'),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_blob_maxsize,
                    orientation="h",
                    key=self.gui_blob_maxsize,
                    background_color='#424042',
                    tooltip = "Maximum size a blob can be for blob tracking.",
                ),

   
            ],

        ]

        
        self.widget_layout = [
            [   
                sg.Text("Tracking Algorithm Order Settings:", background_color='#242224'),
            ],
            [
                sg.Column(self.general_settings_layout, key=self.gui_general_settings_layout, background_color='#424042' ),
            ],
        ]

        self.cancellation_event = Event() # Set the event until start is called, otherwise we can block if shutdown is called.
        self.cancellation_event.set()
        self.image_queue = Queue()


    def started(self):
        return not self.cancellation_event.is_set()

    def start(self):
        # If we're already running, bail
        if not self.cancellation_event.is_set():
            return
        self.cancellation_event.clear()

    def stop(self):
        # If we're not running yet, bail
        if self.cancellation_event.is_set():
            return
        self.cancellation_event.set()

    def render(self, window, event, values):
        # If anything has changed in our configuration settings, change/update those.
        changed = False

        if self.config.gui_HSFP != int(values[self.gui_HSFP]):
            self.config.gui_HSFP = int(values[self.gui_HSFP])
            changed = True

        if self.config.gui_HSF != values[self.gui_HSF]:
            self.config.gui_HSF = values[self.gui_HSF]
            changed = True

        if self.config.gui_DADDYP != int(values[self.gui_DADDYP]):
            self.config.gui_DADDYP = int(values[self.gui_DADDYP])
            changed = True

        if self.config.gui_DADDY != values[self.gui_DADDY]:
            self.config.gui_DADDY = values[self.gui_DADDY]
            changed = True
        
        if self.config.gui_RANSAC3DP != int(values[self.gui_RANSAC3DP]): #TODO check that priority order is unique/auto fix it.
            self.config.gui_RANSAC3DP = int(values[self.gui_RANSAC3DP])
            changed = True

        if self.config.gui_RANSAC3D != values[self.gui_RANSAC3D]:
            self.config.gui_RANSAC3D = values[self.gui_RANSAC3D]
            changed = True

        if self.config.gui_HSRACP != int(values[self.gui_HSRACP]):
            self.config.gui_HSRACP = int(values[self.gui_HSRACP])
            changed = True

        if self.config.gui_HSRAC != values[self.gui_HSRAC]:
            self.config.gui_HSRAC = values[self.gui_HSRAC]
            changed = True

        if self.config.gui_MOMMYP != int(values[self.gui_MOMMYP]):
            self.config.gui_MOMMYP = int(values[self.gui_MOMMYP])
            changed = True

        if self.config.gui_MOMMY != values[self.gui_MOMMY]:
            self.config.gui_MOMMY = values[self.gui_MOMMY]
            changed = True


        if self.config.gui_skip_autoradius != values[self.gui_skip_autoradius]:
            self.config.gui_skip_autoradius = values[self.gui_skip_autoradius]
            changed = True

        if self.config.gui_BLINK != values[self.gui_BLINK]:
            self.config.gui_BLINK = values[self.gui_BLINK]
            changed = True
        
        if self.config.gui_IBO != values[self.gui_IBO]:
            self.config.gui_IBO = values[self.gui_IBO]
            changed = True

        if self.config.gui_circular_crop_left != values[self.gui_circular_crop_left]:
            self.config.gui_circular_crop_left = values[self.gui_circular_crop_left]
            changed = True
        
        if self.config.gui_circular_crop_right != values[self.gui_circular_crop_right]:
            self.config.gui_circular_crop_right = values[self.gui_circular_crop_right]
            changed = True

        if self.config.gui_HSF_radius_left != int(values[self.gui_HSF_radius_left]):
            self.config.gui_HSF_radius_left = int(values[self.gui_HSF_radius_left])
            changed = True

        if self.config.gui_HSF_radius_right != int(values[self.gui_HSF_radius_right]):
            self.config.gui_HSF_radius_right = int(values[self.gui_HSF_radius_right])
            changed = True

        if self.config.gui_BLOB != values[self.gui_BLOB]:
            self.config.gui_BLOB = values[self.gui_BLOB]
            changed = True

        if self.config.gui_BLOBP != int(values[self.gui_BLOBP]):
            self.config.gui_BLOBP = int(values[self.gui_BLOBP])
            changed = True

        if self.config.gui_threshold != values[self.gui_threshold_slider]:
            self.config.gui_threshold = int(values[self.gui_threshold_slider])
            changed = True

        if self.config.gui_thresh_add != values[self.gui_thresh_add]:
            self.config.gui_thresh_add = int(values[self.gui_thresh_add])
            changed = True

        if self.config.gui_blob_maxsize != values[self.gui_blob_maxsize]:
            self.config.gui_blob_maxsize = values[self.gui_blob_maxsize]
            changed = True

        if self.config.ibo_filter_samples != int(values[self.ibo_filter_samples]):
            self.config.ibo_filter_samples = int(values[self.ibo_filter_samples])
            changed = True

        if self.config.ibo_fully_close_eye_threshold != float(values[self.ibo_fully_close_eye_threshold]):
            self.config.ibo_fully_close_eye_threshold = float(values[self.ibo_fully_close_eye_threshold])
            changed = True

        if self.config.calibration_samples != int(values[self.calibration_samples]):
            self.config.calibration_samples = int(values[self.calibration_samples])
            changed = True

        if changed:
            self.main_config.save()
            #print(self.main_config)
        self.osc_queue.put(EyeId.ALGOSETTINGS)
