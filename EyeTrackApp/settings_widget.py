import PySimpleGUI as sg
from config import EyeTrackConfig
from threading import Event, Thread
from eye_processor import EyeProcessor, InformationOrigin
from enum import Enum
from queue import Queue, Empty
from camera import Camera, CameraState
import cv2
from osc import EyeId

class SettingsWidget:
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig, osc_queue: Queue):

        self.gui_show_color_image = f"-SETTING1{widget_id}-"
        self.gui_camera_addr = f"-CAMERAADDR{widget_id}-"
        self.gui_threshold_slider = f"-THREADHOLDSLIDER{widget_id}-"

        self.gui_roi_button = f"-ROIMODE{widget_id}-"
        self.gui_roi_layout = f"-ROILAYOUT{widget_id}-"
        self.gui_roi_selection = f"-GRAPH{widget_id}-"
        self.gui_tracking_button = f"-TRACKINGMODE{widget_id}-"
        self.gui_save_tracking_button = f"-SAVETRACKINGBUTTON{widget_id}-"
        
        self.gui_tracking_image = f"-IMAGE{widget_id}-"
        self.gui_output_graph = f"-OUTPUTGRAPH{widget_id}-"
        self.gui_restart_calibration = f"-RESTARTCALIBRATION{widget_id}-"
        self.gui_recenter_eye = f"-RECENTEREYE{widget_id}-"
        self.gui_mode_readout = f"-APPMODE{widget_id}-"
        self.gui_show_color_image = f"-SHOWCOLORIMAGE{widget_id}-"
        self.gui_flip_x_axis = f"-FLIPXAXIS{widget_id}-"
        self.gui_flip_y_axis = f"-FLIPYAXIS{widget_id}-"
        self.gui_roi_message = f"-ROIMESSAGE{widget_id}-"
        self.gui_save_button = f"-SAVE{widget_id}-"

        self.gui_general_settings_layout = f"-GENERALSETTINGSLAYOUT{widget_id}-"
       # self.gui_algo_settings_layout = f"-ALGOSETTINGSLAYOUT{widget_id}-"
        
        self.gui_blob_fallback = f"-BLOBFALLBACK{widget_id}-"
        self.gui_speed_coefficient_slider = f"-SPEEDCOEFFICIENTSLIDER{widget_id}-"
        self.gui_min_cutoff_slider = f"-MINCUTOFFSLIDER{widget_id}-"
       # self.main_config = main_config
        #self.config = main_config.left_eye

        self.osc_queue = osc_queue
        # Define the window's contents
        self.general_settings_layout = [
           
           # [
          #      sg.Button("Recenter Eye", key=self.gui_recenter_eye, button_color = '#6f4ca1'),
                
           # ],
            [sg.Checkbox(
                    "Flip X axis",
                    default=False,
                    key=self.gui_flip_x_axis,
                    background_color='#424042',
                ),
            ],
            [sg.Checkbox(
                    "Flip Y axis",
                    default=False,
                    key=self.gui_flip_y_axis,
                    background_color='#424042',
                ),
            ],

            [
                sg.Text("Tracking algorithim toggles:", background_color='#424042'),
              #  sg.InputText(self.config.capture_source, key=self.gui_camera_addr),
            ],

            [sg.Checkbox(
                    "Blob Fallback",
                    default=True,
                    key=self.gui_blob_fallback,
                    background_color='#424042',
                ),
            ],
            [
                sg.Text("Filter paramaters:", background_color='#242224'),
                
              #  sg.InputText(self.config.capture_source, key=self.gui_camera_addr),
            ],
            [
                sg.Text("Min Frequency Cutoff", background_color='#424042'),
                sg.Slider(
                    range=(0, 10),
                    default_value=4,
                    orientation="h",
                    key=self.gui_min_cutoff_slider,
                    background_color='#424042'
                ),
            ],
            [
                sg.Text("Speed Coefficient", background_color='#424042'),
                sg.Slider(
                    range=(0, 20),
                    default_value=9,
                    orientation="h",
                    key=self.gui_speed_coefficient_slider,
                    background_color='#424042'
                ),
            ],


            #[sg.Image(filename="", key=self.gui_tracking_image)],
          #  [
            #    sg.Graph(
            #        (200, 200),
             #       (-100, 100),
             #       (100, -100),
             #       background_color="white",
             #       key=self.gui_output_graph,
              #      drag_submits=True,
              #      enable_events=True,
              #  ),
             #   sg.Text("Please set an Eye Cropping.", key=self.gui_roi_message, background_color='#424042', visible=False),
           # ],
        ]

        
        self.widget_layout = [
            [
                sg.Text("Settings", background_color='#242224'),
              #  sg.InputText(self.config.capture_source, key=self.gui_camera_addr),
            ],
            [
                sg.Column(self.general_settings_layout, key=self.gui_general_settings_layout, background_color='#424042' ),
                #sg.Column(self.algo_settings_layout, key=self.gui_algo_settings_layout, background_color='#424042' ),
               # sg.Column(self.roi_layout, key=self.gui_roi_layout, background_color='#424042', visible=False),
            ],
            
            [
                sg.Button(
                    "Save Settings", key=self.gui_save_button, button_color = '#6f4ca1'
                ),
            ],
        ]

        self.cancellation_event = Event()
        # Set the event until start is called, otherwise we can block if shutdown is called.
        self.cancellation_event.set()
       # self.capture_event = Event()
       # self.capture_queue = Queue()
       # self.roi_queue = Queue()

        self.image_queue = Queue()

       # self.ransac = EyeProcessor(
        #    self.config,
        #    self.cancellation_event,
        #    self.capture_event,
        #    self.capture_queue,
         #   self.image_queue,
       # )

       # self.camera_status_queue = Queue()
        #self.camera = Camera(
         #   self.config,
          #  0,
           # self.cancellation_event,
            #self.capture_event,
           # self.camera_status_queue,
            #self.capture_queue,
        #)


    def started(self):
        return not self.cancellation_event.is_set()

    def start(self):
        # If we're already running, bail
        if not self.cancellation_event.is_set():
            return
        self.cancellation_event.clear()
        #self.ransac_thread = Thread(target=self.ransac.run)
       # self.ransac_thread.start()
       # self.camera_thread = Thread(target=self.camera.run)
       # self.camera_thread.start()

    def stop(self):
        # If we're not running yet, bail
        if self.cancellation_event.is_set():
            return
        self.cancellation_event.set()
       # self.ransac_thread.join()
        #self.camera_thread.join()

    def render(self, window, event, values):
        changed = False
        # If anything has changed in our configuration settings, change/update those.
       # if (
        #    event == self.gui_save_tracking_button
        #    and values[self.gui_camera_addr] != self.config.capture_source
        #):
         #   print("New value: {}".format(values[self.gui_camera_addr]))
          #  try:
                # Try storing ints as ints, for those using wired cameras.
          # #     self.config.capture_source = int(values[self.gui_camera_addr])
          #  except ValueError:
           #     if values[self.gui_camera_addr] == "":
             #      self.config.capture_source = None
            #    else:
              #      self.config.capture_source = values[self.gui_camera_addr]
           # changed = True

        #if self.config.threshold != values[self.gui_threshold_slider]:
        #    self.config.threshold = int(values[self.gui_threshold_slider])
        #    changed = True

        #if self.config.rotation_angle != values[self.gui_rotation_slider]:
        #    self.config.rotation_angle = int(values[self.gui_rotation_slider])
         #   changed = True

        if self.config.show_color_image != values[self.gui_show_color_image]:
            self.config.show_color_image = values[self.gui_show_color_image]
            changed = True

        if changed:
            self.main_config.save()

       
      #  elif self.camera.camera_status == CameraState.CONNECTING:
        #    window[self.gui_mode_readout].update("Camera Connecting")
       # elif self.camera.camera_status == CameraState.DISCONNECTED:
        #    window[self.gui_mode_readout].update("CAMERA DISCONNECTED")
        #elif needs_roi_set:
        #    window[self.gui_mode_readout].update("Awaiting Eye Cropping Setting")
        #elif self.ransac.calibration_frame_counter != None:
        #    window[self.gui_mode_readout].update("Calibration")
       # else:
        #    window[self.gui_mode_readout].update("Tracking")

      #  if self.in_roi_mode:
        #    try:
         #       if self.roi_queue.empty():
          #          self.capture_event.set()
          #      maybe_image = self.roi_queue.get(block=False)
          #      imgbytes = cv2.imencode(".ppm", maybe_image[0])[1].tobytes()
          #      graph = window[self.gui_roi_selection]
          #      if self.figure:
           #         graph.delete_figure(self.figure)
                # INCREDIBLY IMPORTANT ERASE. Drawing images does NOT overwrite the buffer, the fucking
                # graph keeps every image fed in until you call this. Therefore we have to make sure we
                # erase before we redraw, otherwise we'll leak memory *very* quickly.
            #    graph.erase()
            #    graph.draw_image(data=imgbytes, location=(0, 0))
             #   if None not in (self.x0, self.y0, self.x1, self.y1):
             #       self.figure = graph.draw_rectangle(
             #           (self.x0, self.y0), (self.x1, self.y1), line_color="#6f4ca1"
             #       )
           # except Empty:
           #     pass
      #  else:
         #   if needs_roi_set:
          #      window[self.gui_roi_message].update(visible=True)
           #     window[self.gui_output_graph].update(visible=False)
           #     return
           # try:
           #     window[self.gui_roi_message].update(visible=False)
           #     window[self.gui_output_graph].update(visible=True)
        (maybe_image, eye_info) = self.image_queue.get(block=False)
            #    imgbytes = cv2.imencode(".ppm", maybe_image)[1].tobytes()
             #   window[self.gui_tracking_image].update(data=imgbytes)

                # Update the GUI
            #    graph = window[self.gui_output_graph]
             #   graph.erase()

                # Relay information to OSC
       # if eye_info.info_type != InformationOrigin.FAILURE:
        self.osc_queue.put((self.eye_id, eye_info))
        #self.osc_queue.put((EyeId.SETTINGS))
           # except Empty:
             #   return
