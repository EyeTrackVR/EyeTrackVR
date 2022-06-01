from osc import VRChatOSC
from config import RansacConfig
from speech_engine import SpeechEngine
from ransac import Ransac
import queue
import threading
import cv2

WINDOW_NAME = "RANSACApp"

def main():
  # Get Configuration
  config = RansacConfig()
  config.load()

  # Set up basic cv2 window with our GUI
  def update_threshold(val: "int"):
      config.threshhold = val
  
  def update_rot(val: "int"):
      config.rotation_angle = val
  
  cv2.namedWindow(WINDOW_NAME)
  cv2.createTrackbar("Threshold", WINDOW_NAME, 0, 100, update_threshold)
  cv2.createTrackbar("Rotation", WINDOW_NAME, 0, 360, update_rot)

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

  ransac_queue = queue.Queue()
  image_queue = queue.Queue()
  ransac = Ransac(config, ransac_queue, image_queue)
  ransac_thread = threading.Thread(target=ransac.run)
  ransac_thread.start()


  # GUI Render loop

  while True:
    # If we're in ROI mode, show current video and allow markup.

    # If we're in tracking mode, bring up the tracking thread, let it do all of its work, then
    # update ourselves whenever it pushes out an image into its buffer.
    try:
      maybe_image = image_queue.get(block = False)
      cv2.imshow(WINDOW_NAME, maybe_image)
    except queue.Empty:
      pass

    # If we're in either mode and someone hits q, quit immediately
    if cv2.waitKey(10) & 0xFF == ord("q"):
      cv2.destroyAllWindows()
      osc_queue.put(None)
      osc_thread.join()
      ransac_queue.put(None)
      ransac_thread.join()
#      t2s_engine.force_stop()
#      t2s_queue.put(None)
#      t2s_thread.join()
      print("Exiting RANSAC App")
      return

if __name__ == "__main__":
  main()