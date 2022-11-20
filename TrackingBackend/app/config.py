import json
import os.path
from pydantic import BaseModel
from app.logger import get_logger
logger = get_logger()


class AlgorithmConfig(BaseModel):
    speed_coefficient: float = 0.9
    min_cutoff: float = 0.0004
    blob_fallback: bool = True
    blob_minsize: float = 10
    blob_maxsize: float = 25


class OSCConfig(BaseModel):
    address: str = "127.0.0.1"
    sync_blink: bool = False
    enable_sending: bool = True
    sending_port: int = 9000
    enable_receiving: bool = True
    receiver_port: int = 9001
    recenter_address: str = "/avatar/parameters/etvr_recenter"
    recalibrate_address: str = "/avatar/parameters/etvr_recalibrate"


class CameraConfig(BaseModel):
    capture_source: str = ""
    threshold: int = 50
    focal_length: int = 30
    rotation_angle: int = 0
    flip_x_axis: bool = False
    flip_y_axis: bool = False
    roi_x: int = 0
    roi_y: int = 0
    roi_w: int = 0
    roi_h: int = 0


class EyeTrackConfig(BaseModel):
    version: int = 2  # increment this if anything is added, removed or renamed
    log_level: str = "INFO"
    osc: OSCConfig = OSCConfig()
    right_eye: CameraConfig = CameraConfig()
    left_eye: CameraConfig = CameraConfig()
    algorithm: AlgorithmConfig = AlgorithmConfig()

    def save(self, file: str = "config.json") -> None:
        with open(file, "w+") as settings_file:
            json.dump(obj=self.dict(), fp=settings_file, indent=4)

    @staticmethod
    def load(file: str = "config.json"):
        try:
            if not os.path.exists(file):
                logger.info("No settings file found, using base settings")
                EyeTrackConfig().save()
                return EyeTrackConfig()
            with open(file, "r") as config_file:
                config = EyeTrackConfig(**json.load(config_file))
                if EyeTrackConfig().version != config.version:
                    logger.warning("Config version mismatch regenerating file")
                    config_file.close()  # close file so we don't get permission errors
                    os.remove(file)
                    EyeTrackConfig().save()
                    return EyeTrackConfig()
                else:
                    return config
        except json.JSONDecodeError:  # if this happens the config is most likely corrupt
            logger.error("Cannot open config file assuming it is corrupt, regenerating")
            os.remove(file)
            EyeTrackConfig().save()
            return EyeTrackConfig()

    def return_config(self) -> dict:
        return self.__dict__
