from consts import RANSAC_CALIBRATION_STEPS_START, RANSAC_CALIBRATION_STEPS_STOP
from utils.misc_utils import PlaySound, SND_FILENAME, SND_ASYNC, resource_path


def trigger_recenter(eyes):
    for eye in eyes:
        eye.settings.gui_recenter_eyes = True


def trigger_recalibration(eyes):
    for eye in eyes:
        eye.ransac.calibration_frame_counter = RANSAC_CALIBRATION_STEPS_START
        eye.ransac.ibo.clear_filter()
    PlaySound(resource_path("Audio/start.wav"), SND_FILENAME | SND_ASYNC)


def stop_calibration(eyes):
    for eye in eyes:
        eye.ransac.calibration_frame_counter = RANSAC_CALIBRATION_STEPS_STOP


def play_on_complete():
    PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)