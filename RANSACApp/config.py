from dataclasses import dataclass
from typing import Union
from dacite import from_dict, Optional
import os.path
import json

@dataclass
class RansacConfig:
  threshold: "int" = 0
  rotation_angle: "int" = 0
  roi_window_x: "int" = 0
  roi_window_y: "int" = 0
  roi_window_w: "int" = 640
  roi_window_h: "int" = 480
  focal_length: "int" = 30
  capture_source: "Union[int, str, None]" = 2

  def load():
    if not os.path.exists("ransac_settings.json"):
      print("No settings file, using base settings")
      return RansacConfig()
    with open("ransac_settings.json", 'r') as settings_file:
      return from_dict(data_class = RansacConfig, data = json.load(settings_file))

  def save(self):
    with open("ransac_settings.json", 'w+') as settings_file:
      json.dump(self.__dict__, settings_file)