import PySimpleGUI as sg
from config import EyeTrackSettingsConfig
from threading import Event, Thread
from eye_processor import EyeProcessor, InformationOrigin
from enum import Enum
from queue import Queue, Empty
from camera import Camera, CameraState
import cv2
from osc import EyeId

class SettingsWidget:
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
        self.gui_blob_fallback = f"-BLOBFALLBACK{widget_id}-"
        self.gui_blob_maxsize = f"-BLOBMAXSIZE{widget_id}-"
        self.gui_blob_minsize = f"-BLOBMINSIZE{widget_id}-"
        self.gui_speed_coefficient = f"-SPEEDCOEFFICIENT{widget_id}-"
        self.gui_min_cutoff = f"-MINCUTOFF{widget_id}-"
        self.gui_eye_falloff = f"-EYEFALLOFF{widget_id}-"
        self.gui_blink_sync = f"-BLINKSYNC{widget_id}-"
        self.main_config = main_config
        self.config = main_config.settings
        self.osc_queue = osc_queue

        # Define the window's contents
        self.general_settings_layout = [
           
            [
                sg.Checkbox(
                    "Flip Left Eye X Axis",
                    default=self.config.gui_flip_x_axis_left,
                    key=self.gui_flip_x_axis_left,
                    background_color='#424042',
                ),
                sg.Checkbox(
                    "Flip Right Eye X Axis",
                    default=self.config.gui_flip_x_axis_right,
                    key=self.gui_flip_x_axis_right,
                    background_color='#424042',
                ),

            ],
            [sg.Checkbox(
                    "Flip Y Axis",
                    default=self.config.gui_flip_y_axis,
                    key=self.gui_flip_y_axis,
                    background_color='#424042',
                ),
            ],
            [sg.Checkbox(
                    "Dual Eye Falloff",
                    default=self.config.gui_eye_falloff,
                    key=self.gui_eye_falloff,
                    background_color='#424042',
                ),
            ],
            [sg.Checkbox(
                    "Sync Blinks (disables winking)",
                    default=self.config.gui_blink_sync,
                    key=self.gui_blink_sync,
                    background_color='#424042',
                ),
            ],

            [
                sg.Text("Tracking Algorithim Settings:", background_color='#242224'),
            ],

            [sg.Checkbox(
                    "Blob Fallback",
                    default=self.config.gui_blob_fallback,
                    key=self.gui_blob_fallback,
                    background_color='#424042',
                ),
            ],
            [
                sg.Text("Min blob size:", background_color='#424042'),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_blob_minsize,
                    orientation="h",
                    key=self.gui_blob_minsize,
                    background_color='#424042'
                ),
                
                sg.Text("Max blob size:", background_color='#424042'),
                sg.Slider(
                    range=(1, 50),
                    default_value=self.config.gui_blob_maxsize,
                    orientation="h",
                    key=self.gui_blob_maxsize,
                    background_color='#424042'
                ),

   
            ],
            [
                sg.Text("Filter Paramaters:", background_color='#242224'),
            ],
            [
                
                sg.Text("Min Frequency Cutoff", background_color='#424042'),
                sg.InputText(self.config.gui_min_cutoff, key=self.gui_min_cutoff),
            ],
            [
                sg.Text("Speed Coefficient", background_color='#424042'),
                sg.InputText(self.config.gui_speed_coefficient, key=self.gui_speed_coefficient),
            ],
             [
                sg.Text("OSC Settings:", background_color='#242224'),
            ],
            [
                sg.Text("OSC Address:", background_color='#424042'),
                sg.InputText(self.config.gui_osc_address, key=self.gui_osc_address),
            ],
            [
                sg.Text("OSC Port:", background_color='#424042'),
                sg.InputText(self.config.gui_osc_port, key=self.gui_osc_port),
            ],
            [
                sg.Text("OSC Receiver Port:", background_color='#424042'),
                sg.InputText(self.config.gui_osc_receiver_port, key=self.gui_osc_receiver_port),
            ],
            [
                sg.Text("OSC Recenter Address:", background_color='#424042'),
                sg.InputText(self.config.gui_osc_recenter_address, key=self.gui_osc_recenter_address),
            ],
            [
                sg.Text("OSC Recalibrate Address:", background_color='#424042'),
                sg.InputText(self.config.gui_osc_recalibrate_address, key=self.gui_osc_recalibrate_address),
            ]

        ]

        
        self.widget_layout = [
            [   
                sg.Text("General Settings:", background_color='#242224'),
            ],
            [
                sg.Column(self.general_settings_layout, key=self.gui_general_settings_layout, background_color='#424042' ),
            ],
           # [
            #    sg.Button(
             #       "Save Settings", key=self.gui_save_button, button_color = '#6f4ca1'
              #  ),
            #],
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

        if self.config.gui_osc_port != values[self.gui_osc_port]:
            try: 
                int(values[self.gui_osc_port])
                if len(values[self.gui_osc_port]) <= 5:
                    self.config.gui_osc_port = int(values[self.gui_osc_port])
                    changed = True
                else:
                    print("[ERROR] OSC port value must be an integer 0-65535")
            except:
                print("[ERROR] OSC port value must be an integer 0-65535")

        if self.config.gui_osc_receiver_port != values[self.gui_osc_receiver_port]:
            try: 
                int(values[self.gui_osc_receiver_port])
                if len(values[self.gui_osc_receiver_port]) <= 5:
                    self.config.gui_osc_receiver_port = int(values[self.gui_osc_receiver_port])
                    changed = True
                else:
                    print("[ERROR] OSC receive port value must be an integer 0-65535")
            except:
                print("[ERROR] OSC receive port value must be an integer 0-65535")

        if self.config.gui_osc_address != values[self.gui_osc_address]:
            self.config.gui_osc_address = values[self.gui_osc_address]
            changed = True

        if self.config.gui_osc_recenter_address != values[self.gui_osc_recenter_address]:
            self.config.gui_osc_recenter_address = values[self.gui_osc_recenter_address]
            changed = True

        if self.config.gui_osc_recalibrate_address != values[self.gui_osc_recalibrate_address]:
            self.config.gui_osc_recalibrate_address = values[self.gui_osc_recalibrate_address]
            changed = True

        if self.config.gui_min_cutoff != values[self.gui_min_cutoff]:
            self.config.gui_min_cutoff = values[self.gui_min_cutoff]
            changed = True
            
        if self.config.gui_speed_coefficient != values[self.gui_speed_coefficient]:
            self.config.gui_speed_coefficient = values[self.gui_speed_coefficient]
            changed = True

        if self.config.gui_flip_x_axis_right != values[self.gui_flip_x_axis_right]:
            self.config.gui_flip_x_axis_right = values[self.gui_flip_x_axis_right]
            changed = True

        if self.config.gui_flip_x_axis_left != values[self.gui_flip_x_axis_left]:
            self.config.gui_flip_x_axis_left = values[self.gui_flip_x_axis_left]
            changed = True


        if self.config.gui_flip_y_axis != values[self.gui_flip_y_axis]:
            self.config.gui_flip_y_axis = values[self.gui_flip_y_axis]
            changed = True

        if self.config.gui_blob_fallback != values[self.gui_blob_fallback]:
            self.config.gui_blob_fallback = values[self.gui_blob_fallback]
            changed = True

        if self.config.gui_eye_falloff != values[self.gui_eye_falloff]:
            self.config.gui_eye_falloff = values[self.gui_eye_falloff]
            changed = True

        if self.config.gui_blink_sync != values[self.gui_blink_sync]:
            self.config.gui_blink_sync = values[self.gui_blink_sync]
            changed = True

        if self.config.gui_blob_maxsize != values[self.gui_blob_maxsize]:
            self.config.gui_blob_maxsize = values[self.gui_blob_maxsize]
            changed = True

        if changed:
            self.main_config.save()
            
        self.osc_queue.put((EyeId.SETTINGS))
