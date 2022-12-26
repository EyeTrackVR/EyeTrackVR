import numpy as np

def BLINK(self): 

    intensity = np.sum(self.current_image_gray_clean)
    self.frames = self.frames + 1

    if intensity > self.max_int:
        self.max_int = intensity 
        if self.frames > 200: 
            self.max_ints.append(self.max_int)
    if intensity < self.min_int:
        self.min_int = intensity

    if len(self.max_ints) > 1:
        if intensity > min(self.max_ints):
            self.blinkvalue = True
        else:
            self.blinkvalue = False
   # print(self.blinkvalue, self.max_int, self.min_int, self.frames, intensity)