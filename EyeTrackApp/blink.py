import numpy as np

from consts import RANSAC_CALIBRATION_STEPS_START


def BLINK(self): 
    max_poll_points = 300

    if self.blink_clear == True:
        print('Clearing the Binary Blink stats')
        self.max_ints = []
        self.max_int = 0
        self.min_int = 4000000000000
        self.frames = 0

    intensity = np.sum(self.current_image_gray_clean)
    if self.calibration_frame_counter == RANSAC_CALIBRATION_STEPS_START:
        self.filterlist = []

    if len(self.filterlist) < max_poll_points:
        self.filterlist.append(intensity)
    else:
        self.filterlist.pop(0)
        self.filterlist.append(intensity)

    # we're clamping the outlier intensity measurements to the min/max thresholds
    if intensity >= np.percentile(self.filterlist, 99):
        intensity = max(self.filterlist)
    if intensity <= np.percentile(self.filterlist, 1):
        intensity = min(self.filterlist)

    # TODO this doesn't really work correctly, debug it some more
    self.frames += 1
    if intensity > self.max_int:
        self.max_int = intensity
        if self.frames > 300:
            if len(self.max_ints) > 300:
                self.max_ints.pop(0)
                self.max_ints.append(self.max_int)
            else:
                self.max_ints.append(self.max_int)
    if intensity < self.min_int:
        self.min_int = intensity

    if (len(self.max_ints)) and intensity > min(self.max_ints):
        return 0.0

    return 0.7
