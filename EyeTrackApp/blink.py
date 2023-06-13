import numpy as np


def BLINK(self):
    if self.blink_clear:
        self.max_ints = []
        self.max_int = 0
        self.frames = 0

    intensity = np.sum(self.current_image_gray_clean)
    self.frames = self.frames + 1
    if len(str(intensity)) >= 8:  # filter abnormally high values
        print('filter, assume blink')
        intensity = self.max_int + 1

    if intensity > self.max_int:
        self.max_int = intensity
        if self.frames > 300:  # TODO: test this number more (make it a setting??)
            self.max_ints.append(self.max_int)
    if intensity < self.min_int:
        self.min_int = intensity

    if len(self.max_ints) > 1:
        if intensity > min(self.max_ints):
            blinkvalue = 0.0
        else:
            blinkvalue = 0.7
    try:
        return blinkvalue
    except:
        return 0.7
