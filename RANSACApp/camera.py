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
  def __init__(self, config: RansacConfig, camera_index: int, cancellation_event: "threading.Event", capture_event: "threading.Event", camera_status_outgoing: "queue.Queue[CameraState]", camera_output_outgoing: "queue.Queue"):
    self.config = config
    self.camera_index = camera_index
    self.camera_address = config.capture_source
    self.camera_status_outgoing = camera_status_outgoing
    self.camera_output_outgoing = camera_output_outgoing
    self.capture_event = capture_event
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

      # If things aren't open, retry until they are. Don't let read requests come in any earlier
      # than this, otherwise we can deadlock ourselves.
      if not self.capture_source.isOpened() or (self.config.capture_source != self.current_capture_source):
        print(f"Capture source {self.config.capture_source} not found, retrying in 500ms")
        sleep(0.5)
        self.current_capture_source = self.config.capture_source
        self.capture_source = cv2.VideoCapture(self.current_capture_source)
        continue

      # Assuming we can access our capture source, wait for another thread to request a capture.
      # Cycle every so often to see if our cancellation token has fired. This basically uses a
      # python event as a contextless, resettable one-shot channel.
      if not self.capture_event.wait(timeout=0.02):
        continue

      try:
        ret, image = self.capture_source.read()
        if not ret:
          self.capture_source.set(cv2.CAP_PROP_POS_FRAMES, 0)
          raise RuntimeError("Problem while getting frame")
        frame_number = self.capture_source.get(cv2.CAP_PROP_POS_FRAMES)
        fps = self.capture_source.get(cv2.CAP_PROP_FPS)
        # If there's backpressure, just yell. We really shouldn't have this unless we start getting
        # some sort of capture event conflict though.
        qsize = self.camera_output_outgoing.qsize()
        if qsize > 1:
          print(f"CAPTURE QUEUE BACKPRESSURE OF {qsize}. CHECK FOR CRASH OR TIMING ISSUES IN ALGORITHM.")
        self.camera_output_outgoing.put((image, frame_number, fps))
        self.capture_event.clear()
      except:
        # print("Capture source problem, assuming camera disconnected, waiting for reconnect.")
        continue
