'''
------------------------------------------------------------------------------------------------------                                                                                                    
                                                                                                    
                                               ,@@@@@@                                              
                                            @@@@@@@@@@@            @@@                              
                                          @@@@@@@@@@@@      @@@@@@@@@@@                             
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@                              
                                      @@@@@@@/         ,@@@@@@@@@@@@@                               
                                         /@@@@@@@@@@@@@@@  @@@@@@@@                                 
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@                                  
                                @@@@@@@@                @@@@@                                       
                              ,@@@                        @@@@&                                     
                                             @@@@@@.       @@@@                                     
                                   @@@     @@@@@@@@@/      @@@@@                                    
                                   ,@@@.     @@@@@@((@     @@@@(                                    
                                   //@@@        ,,  @@@@  @@@@@                                     
                                   @@@(                @@@@@@@                                      
                                   @@@  @          @@@@@@@@#                                        
                                       @@@@@@@@@@@@@@@@@                                            
                                      @@@@@@@@@@@@@(     

BLOB By: Prohurtz#0001 (Main App Developer)
Algorithm App Implimentations By: Prohurtz#0001, qdot (Inital App Creator)

Copyright (c) 2023 EyeTrackVR <3
------------------------------------------------------------------------------------------------------
'''  

import cv2
import numpy as np
from enum import IntEnum

class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3

def circle_crop(self):
    global cct
    print(cct)
    if cct == 0:
        try:
            ht, wd = self.current_image_gray.shape[:2]
            radius = int(float(self.lkg_projected_sphere["axes"][0]))
            self.xc = int(float(self.lkg_projected_sphere["center"][0]))
            self.yc = int(float(self.lkg_projected_sphere["center"][1]))
            if radius < 10: #minimum size
                radius = 10
            # draw filled circle in white on black background as mask
            mask = np.zeros((ht, wd), dtype=np.uint8)
            mask = cv2.circle(mask, (self.xc, self.yc), radius, 255, -1)
            # create white colored background
            color = np.full_like(self.current_image_gray, (255))
            # apply mask to image
            masked_img = cv2.bitwise_and(self.current_image_gray, self.current_image_gray, mask=mask)
            # apply inverse mask to colored image
            masked_color = cv2.bitwise_and(color, color, mask=255 - mask)
            # combine the two masked images
            self.current_image_gray = cv2.add(masked_img, masked_color)
            return self.current_image_gray
        except:
            return self.current_image_gray
            pass
    else:
        cct = cct - 1
        return self.current_image_gray
def BLOB(self):
        global cct
        # define circle
        if self.eye_id in [EyeId.LEFT] and self.settings.gui_circular_crop_left:
            self.current_image_gray = circle_crop(self)
        else:
            pass

        if self.eye_id in [EyeId.RIGHT] and self.settings.gui_circular_crop_right:
            self.current_image_gray = circle_crop(self)
        else:
            pass
        _, larger_threshold = cv2.threshold(self.current_image_gray, int(self.settings.gui_threshold), 255,
                                            cv2.THRESH_BINARY)

        try:
            # Try rebuilding our contours
            contours, _ = cv2.findContours(
                larger_threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )
            contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)
            
            # If we have no contours, we have nothing to blob track. Fail here.
            if len(contours) == 0:
                raise RuntimeError("No contours found for image")
        except:
            self.failed = self.failed + 1
            pass

        rows, cols = larger_threshold.shape

        for cnt in contours:
            (x, y, w, h) = cv2.boundingRect(cnt)

            # if our blob width/height are within boundaries, call that good.

            if not self.settings.gui_blob_minsize <= h <= self.settings.gui_blob_maxsize or not self.settings.gui_blob_minsize <= w <= self.settings.gui_blob_maxsize:
                continue
    
            cx = x + int(w / 2)
            cy = y + int(h / 2)

            cv2.drawContours(self.current_image_gray, [cnt], -1, (0, 0, 0), 3)
            cv2.rectangle(
                self.current_image_gray, (x, y), (x + w, y + h), (0, 0, 0), 2
            )

            #out_x, out_y = cal_osc(self, cx, cy) #filter and calibrate values

            print("S:KLJGHLDKIJGHLKS")
            self.failed = 0
            return cx, cy, larger_threshold
        print("S:KLJGHLDKIJGHLKS")
        self.failed = self.failed + 1
        return 0, 0, larger_threshold
        