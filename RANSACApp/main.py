from osc import VRChatOSC
from config import RansacConfig
from speech_engine import SpeechEngine
from ransac import Ransac, InformationOrigin
import queue
import threading
import cv2
import camera
import PySimpleGUI as sg

WINDOW_NAME = "RANSACApp"
CAMERA_ADDR_NAME = "-CAMERAADDR-"
THRESHOLD_SLIDER_NAME = "-THREADHOLDSLIDER-"
ROTATION_SLIDER_NAME = "-ROTATIONSLIDER-"
SCALAR_SLIDER_NAME = "-EYESCALARSLIDER-"
ROI_BUTTON_NAME = "-ROIMODE-"
ROI_LAYOUT_NAME = "-ROILAYOUT-"
ROI_SELECTION_NAME = "-GRAPH-"
TRACKING_BUTTON_NAME = "-TRACKINGMODE-"
SAVE_TRACKING_BUTTON_NAME = "-SAVETRACKINGBUTTON-"
TRACKING_LAYOUT_NAME = "-TRACKINGLAYOUT-"
TRACKING_IMAGE_NAME = "-IMAGE-"
OUTPUT_GRAPH_NAME = "-OUTPUTGRAPH-"
RESTART_CALIBRATION_NAME = "-RESTARTCALIBRATION-"
RECENTER_EYE_NAME = "-RECENTEREYE-"
MODE_READOUT_NAME = "-APPMODE-"
SHOW_COLOR_IMAGE_NAME = "-SHOWCOLORIMAGE-"

def main():
  in_roi_mode = False

  # Get Configuration
  config: RansacConfig = RansacConfig.load()
  config.save()

  roi_layout = [
                [sg.Graph((640, 480), (0, 480), (640, 0), key=ROI_SELECTION_NAME,drag_submits=True, enable_events=True)]
               ]

  # Define the window's contents
  tracking_layout = [
                     [sg.Text("Threshold"), sg.Slider(range=(0, 100), default_value=config.threshold, orientation = 'h', key=THRESHOLD_SLIDER_NAME)],
                     [sg.Text("Rotation"), sg.Slider(range=(0, 360), default_value=config.rotation_angle, orientation = 'h', key=ROTATION_SLIDER_NAME)],
                     [sg.Text("Eye Position Scalar"), sg.Slider(range=(0, 5000), default_value=config.vrc_eye_position_scalar, orientation = 'h', key=SCALAR_SLIDER_NAME)],
                     [sg.Button("Restart Calibration", key=RESTART_CALIBRATION_NAME), sg.Button("Recenter Eye", key=RECENTER_EYE_NAME), sg.Checkbox('Show Color Image:', default=config.show_color_image, key=SHOW_COLOR_IMAGE_NAME)],
                     [sg.Text("Mode:"), sg.Text("Calibrating", key=MODE_READOUT_NAME)],
                     [sg.Image(filename="", key=TRACKING_IMAGE_NAME)],
                     [sg.Graph((200,200), (-100, 100), (100, -100), background_color='white', key=OUTPUT_GRAPH_NAME,drag_submits=True, enable_events=True)]
                     ]

  layout = [[[sg.Text("Camera Address"), sg.InputText(config.capture_source, key=CAMERA_ADDR_NAME), sg.Button("Save and Restart Tracking", key=SAVE_TRACKING_BUTTON_NAME)]],
            [sg.Button("Tracking Mode", key=TRACKING_BUTTON_NAME), sg.Button("ROI Mode", key=ROI_BUTTON_NAME)],
            [sg.Column(tracking_layout, key=TRACKING_LAYOUT_NAME), sg.Column(roi_layout, key=ROI_LAYOUT_NAME, visible=False)]]

  # Create the window
  window = sg.Window('Eye Tracking', layout)

  cancellation_event = threading.Event()

  # Check to see if we can connect to our video source first. If not, bring up camera finding
  # dialog.

  # Check to see if we have an ROI. If not, bring up ROI finder GUI.

  # Spawn worker threads
  osc_queue: "queue.Queue[tuple[bool, int, int]]" = queue.Queue()
  osc = VRChatOSC(cancellation_event, osc_queue)
  osc_thread = threading.Thread(target=osc.run)
  osc_thread.start()

#  t2s_queue: "queue.Queue[str | None]" = queue.Queue()
#  t2s_engine = SpeechEngine(t2s_queue)
#  t2s_thread = threading.Thread(target=t2s_engine.run)
#  t2s_thread.start()
#  t2s_queue.put("App Starting")

  capture_event = threading.Event()
  capture_queue = queue.Queue()
  roi_queue = queue.Queue()

  image_queue: queue.Queue = queue.Queue()
  ransac = Ransac(config, cancellation_event, capture_event, capture_queue, image_queue)
  ransac_thread = threading.Thread(target=ransac.run)
  ransac_thread.start()

  # Only start our camera AFTER we've brought up the RANSAC thread, otherwise we'll have no consumer
  camera_status_queue = queue.Queue()
  camera_0 = camera.Camera(config, 0, cancellation_event, capture_event, camera_status_queue, capture_queue)
  camera_0_thread = threading.Thread(target=camera_0.run)
  camera_0_thread.start()

  x0, y0 = None, None
  x1, y1 = None, None
  figure = None
  is_mouse_up = True

  # GUI Render loop

  while True:
    # First off, check for any events from the GUI
    event, values = window.read(timeout=1)

    # If we're in either mode and someone hits q, quit immediately
    if event == "Exit" or event == sg.WIN_CLOSED:
      cancellation_event.set()
      osc_thread.join()
      ransac_thread.join()
#      t2s_engine.force_stop()
#      t2s_queue.put(None)
#      t2s_thread.join()
      print("Exiting RANSAC App")
      return

    changed = False
    # If anything has changed in our configuration settings, change/update those.
    if event == SAVE_TRACKING_BUTTON_NAME and values[CAMERA_ADDR_NAME] != config.capture_source:
      try:
        # Try storing ints as ints, for those using wired cameras.
        config.capture_source = int(values[CAMERA_ADDR_NAME])
      except:
        config.capture_source = values[CAMERA_ADDR_NAME]
      changed = True

    if config.threshold != values[THRESHOLD_SLIDER_NAME]:
      config.threshold = int(values[THRESHOLD_SLIDER_NAME])
      changed = True

    if config.rotation_angle != values[ROTATION_SLIDER_NAME]:
      config.rotation_angle = int(values[ROTATION_SLIDER_NAME])
      changed = True

    if config.vrc_eye_position_scalar != values[SCALAR_SLIDER_NAME]:
      config.vrc_eye_position_scalar = int(values[SCALAR_SLIDER_NAME])
      changed = True

    if config.show_color_image != values[SHOW_COLOR_IMAGE_NAME]:
      config.show_color_image = values[SHOW_COLOR_IMAGE_NAME]
      changed = True

    if changed:
      config.save()

    if event == TRACKING_BUTTON_NAME:
      print("Moving to tracking mode")
      in_roi_mode = False
      camera_0.set_output_queue(capture_queue)
      window[ROI_LAYOUT_NAME].update(visible=False)
      window[TRACKING_LAYOUT_NAME].update(visible=True)
    elif event == ROI_BUTTON_NAME:
      print("move to roi mode")
      in_roi_mode = True
      camera_0.set_output_queue(roi_queue)
      window[ROI_LAYOUT_NAME].update(visible=True)
      window[TRACKING_LAYOUT_NAME].update(visible=False)
    elif event == '-GRAPH-+UP':
      # Event for mouse button up in ROI mode
      is_mouse_up = True
      if abs(x0-x1) != 0 and abs(y0-y1) != 0:
        config.roi_window_x = min([x0, x1])
        config.roi_window_y = min([y0, y1])
        config.roi_window_w = abs(x0-x1)
        config.roi_window_h = abs(y0-y1)
        config.save()
    elif event == '-GRAPH-':
      # Event for mouse button down or mouse drag in ROI mode
      if is_mouse_up:
        is_mouse_up = False
        x0, y0 = values['-GRAPH-']
      x1, y1 = values['-GRAPH-']
    elif event == RESTART_CALIBRATION_NAME:
      ransac.calibration_frame_counter = 300
    elif event == RECENTER_EYE_NAME:
      ransac.recenter_eye = True

    if ransac.calibration_frame_counter != None:
      window[MODE_READOUT_NAME].update("Calibration")
    else:
      window[MODE_READOUT_NAME].update("Tracking")

    if in_roi_mode:
      try:
        if roi_queue.empty():
          capture_event.set()
        maybe_image = roi_queue.get(block = False)
        imgbytes = cv2.imencode(".ppm", maybe_image[0])[1].tobytes()
        graph = window[ROI_SELECTION_NAME]
        if figure:
          graph.delete_figure(figure)
        # INCREDIBLY IMPORTANT ERASE. Drawing images does NOT overwrite the buffer, the fucking
        # graph keeps every image fed in until you call this. Therefore we have to make sure we
        # erase before we redraw, otherwise we'll leak memory *very* quickly.
        graph.erase()
        graph.draw_image(data=imgbytes, location=(0, 0))
        if None not in (x0, y0, x1, y1):
          figure = graph.draw_rectangle((x0, y0), (x1, y1), line_color='blue')
      except queue.Empty:
        pass
    else:
      try:
        (maybe_image, eye_info) = image_queue.get(block = False)
        imgbytes = cv2.imencode(".ppm", maybe_image)[1].tobytes()
        window[TRACKING_IMAGE_NAME].update(data=imgbytes)

        # Update the GUI
        graph = window[OUTPUT_GRAPH_NAME]
        graph.erase()

        if eye_info.info_type != InformationOrigin.FAILURE and not eye_info.blink:
          graph.update(background_color = 'white')
          graph.draw_circle((eye_info.x * -100, eye_info.y * -100), 25, fill_color='black',line_color='white')
        elif eye_info.blink:
          graph.update(background_color = 'blue')
        elif eye_info.info_type == InformationOrigin.FAILURE:
          graph.update(background_color = 'red')
        
        # Relay information to OSC
        if eye_info.info_type != InformationOrigin.FAILURE:
          osc_queue.put(eye_info)
      except queue.Empty:
        pass


if __name__ == "__main__":
  main()