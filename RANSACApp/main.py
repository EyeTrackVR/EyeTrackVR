from osc import VRChatOSC
from config import RansacConfig
from speech_engine import SpeechEngine
from ransac import Ransac
import queue
import threading
import cv2
import camera
import PySimpleGUI as sg

WINDOW_NAME = "RANSACApp"
CAMERA_ADDR_NAME = "CAMERAADDR"
THRESHOLD_SLIDER_NAME = "THREADHOLDSLIDER"
ROTATION_SLIDER_NAME = "ROTATIONSLIDER"

def main():
  # Get Configuration
  config: RansacConfig = RansacConfig.load()
  config.save()

  # Define the window's contents
  layout = [[sg.Text("Camera Address"), sg.InputText(config.capture_source, key=CAMERA_ADDR_NAME)],
            [sg.Text("Threshold"), sg.Slider(range=(0, 100), default_value=config.threshold, orientation = 'h', key=THRESHOLD_SLIDER_NAME)],
            [sg.Text("Rotation"), sg.Slider(range=(0, 360), default_value=config.rotation_angle, orientation = 'h', key=ROTATION_SLIDER_NAME)],
            [sg.Image(filename="", key="-IMAGE-")],
            ]

  # Create the window
  window = sg.Window('Window Title', layout)

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

  capture_queue = queue.Queue()

  image_queue: queue.Queue = queue.Queue()
  ransac = Ransac(config, cancellation_event, capture_queue, image_queue)
  ransac_thread = threading.Thread(target=ransac.run)
  ransac_thread.start()

  # Only start our camera AFTER we've brought up the RANSAC thread, otherwise we'll have no consumer
  camera_status_queue = queue.Queue()
  camera_0 = camera.Camera(config, 0, cancellation_event, camera_status_queue, capture_queue)
  camera_0_thread = threading.Thread(target=camera_0.run)
  camera_0_thread.start()

  # GUI Render loop

  while True:
    # If we're in ROI mode, show current video and allow markup.
    event, values = window.read(timeout=1)

    # If we're in either mode and someone hits q, quit immediately
    if event == "Exit" or event == sg.WIN_CLOSED:
      # cv2.destroyAllWindows()
      cancellation_event.set()
      osc_thread.join()
      ransac_thread.join()
#      t2s_engine.force_stop()
#      t2s_queue.put(None)
#      t2s_thread.join()
      print("Exiting RANSAC App")
      return

    if values[CAMERA_ADDR_NAME] != config.capture_source:
      try:
        # Try storing ints as ints, for those using wired cameras.
        config.capture_source = int(values[CAMERA_ADDR_NAME])
      except:
        config.capture_source = values[CAMERA_ADDR_NAME]
      config.save()

    if config.threshold != values[THRESHOLD_SLIDER_NAME]:
      config.threshold = values[THRESHOLD_SLIDER_NAME]
      config.save()

    if config.rotation_angle != values[ROTATION_SLIDER_NAME]:
      config.rotation_angle = values[ROTATION_SLIDER_NAME]
      config.save()

    # If we're in tracking mode, bring up the tracking thread, let it do all of its work, then
    # update ourselves whenever it pushes out an image into its buffer.
    try:
      maybe_image = image_queue.get(block = False)
      imgbytes = cv2.imencode(".ppm", maybe_image)[1].tobytes()
      window["-IMAGE-"].update(data=imgbytes)
      # cv2.imshow(WINDOW_NAME, maybe_image)
    except queue.Empty:
      pass


if __name__ == "__main__":
  main()