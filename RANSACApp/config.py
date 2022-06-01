import json
import os.path

class RansacConfig:
  def __init__(self):
    self.threshhold = 0
    self.rotation_angle = 0
    self.roi_window_x = 0
    self.roi_window_y = 0
    self.roi_window_w = 640
    self.roi_window_h = 480

  def load(self):
    if not os.path.exists("ransac_settings.json"):
      print("No settings file, using base settings")
      return
    with open("ransac_settings.json", 'r') as settings_file:
      json.load(settings_file)

  def save(self):
    with open("ransac_settings.json", 'w+') as settings_file:
      json.dump(self.__dict__, settings_file)