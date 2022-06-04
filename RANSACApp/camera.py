from time import sleep
from config import RansacConfig
from enum import Enum
import threading
import queue
import cv2


class CameraState(Enum):
  CONNECTED = 1
  DISCONNECTED = 2

class Camera:
  def __init__(self, config: RansacConfig, camera_index: int, cancellation_event: "threading.Event", camera_status_outgoing: "queue.Queue[CameraState]", camera_output_outgoing: "queue.Queue"):
    self.config = config
    self.camera_index = camera_index
    self.camera_address = config.capture_source
    self.camera_status_outgoing = camera_status_outgoing
    self.camera_output_outgoing = camera_output_outgoing
    self.cancellation_event = cancellation_event
    self.current_capture_source = config.capture_source
    self.capture_source: "cv2.VideoCapture" = cv2.VideoCapture(config.capture_source)

  def set_output_queue(self, camera_output_outgoing: "queue.Queue"):
    self.camera_output_outgoing = camera_output_outgoing

  def run(self):
    while True:
      if self.cancellation_event.is_set():
        print("Exiting capture thread")
        return

      # Since this keeps trying to reload based on config values, it'll hopefully connect as we're
      # updating it elsewhere in the GUI.
      if not self.capture_source.isOpened() or (self.config.capture_source != self.current_capture_source):
        print(f"Capture source {self.config.capture_source} not found, retrying in 500ms")
        sleep(0.5)
        self.current_capture_source = self.config.capture_source
        self.capture_source = cv2.VideoCapture(self.current_capture_source)
        continue

      try:
        ret, image = self.capture_source.read()
        if not ret:
          raise RuntimeError("Problem while getting frame")
        frame_number = self.capture_source.get(cv2.CAP_PROP_POS_FRAMES)
        fps = self.capture_source.get(cv2.CAP_PROP_FPS)
        self.camera_output_outgoing.put((image, frame_number, fps))
      except:
        print("Capture source problem, assuming camera disconnected, waiting for reconnect.")
        continue
