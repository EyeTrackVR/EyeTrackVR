from osc import VRChatOSC
from config import RansacConfig
from speech_engine import SpeechEngine
from ransac import Ransac
import queue
import threading
import cv2
import PySimpleGUI as sg

WINDOW_NAME = "RANSACApp"
THRESHOLD_SLIDER_NAME = "THREADHOLDSLIDER"
ROTATION_SLIDER_NAME = "ROTATIONSLIDER"

def main():
  # Get Configuration
  config: RansacConfig = RansacConfig.load()
  config.save()

  # Define the window's contents
  layout = [[sg.Text("Threshold"), sg.Slider(range=(0, 100), orientation = 'h', key=THRESHOLD_SLIDER_NAME)],
            [sg.Text("Rotation"), sg.Slider(range=(0, 360), orientation = 'h', key=ROTATION_SLIDER_NAME)],
            [sg.Image(filename="", key="-IMAGE-")],
            ]

  # Create the window
  window = sg.Window('Window Title', layout)


  # Spawn worker threads
  osc_queue: "queue.Queue[tuple[bool, int, int] | None]" = queue.Queue()
  osc = VRChatOSC(osc_queue)
  osc_thread = threading.Thread(target=osc.run)
  osc_thread.start()

#  t2s_queue: "queue.Queue[str | None]" = queue.Queue()
#  t2s_engine = SpeechEngine(t2s_queue)
#  t2s_thread = threading.Thread(target=t2s_engine.run)
#  t2s_thread.start()
#  t2s_queue.put("App Starting")

  ransac_queue: queue.Queue[None] = queue.Queue()
  image_queue: queue.Queue = queue.Queue()
  ransac = Ransac(config, ransac_queue, image_queue)
  ransac_thread = threading.Thread(target=ransac.run)
  ransac_thread.start()

  # GUI Render loop

  while True:
    # If we're in ROI mode, show current video and allow markup.
    event, values = window.read(timeout=1)

    # If we're in either mode and someone hits q, quit immediately
    if event == "Exit" or event == sg.WIN_CLOSED:
      # cv2.destroyAllWindows()
      osc_queue.put(None)
      osc_thread.join()
      ransac_queue.put(None)
      ransac_thread.join()
#      t2s_engine.force_stop()
#      t2s_queue.put(None)
#      t2s_thread.join()
      print("Exiting RANSAC App")
      return

    config.threshhold = values[THRESHOLD_SLIDER_NAME]
    config.rotation_angle = values[ROTATION_SLIDER_NAME]

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