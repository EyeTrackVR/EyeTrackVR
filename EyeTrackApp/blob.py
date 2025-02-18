"""
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

BLOB By: Prohurtz 
Algorithm App Implimentations By: Prohurtz, qdot (Inital App Creator)

Copyright (c) 2025 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import cv2


def BLOB(self):
    global cct
    # define circle
    _, larger_threshold = cv2.threshold(
        self.current_image_gray,
        int(self.settings.gui_threshold),
        255,
        cv2.THRESH_BINARY,
    )

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

        if (
            not self.settings.gui_blob_minsize <= h <= self.settings.gui_blob_maxsize
            or not self.settings.gui_blob_minsize <= w <= self.settings.gui_blob_maxsize
        ):
            continue

        cx = x + int(w / 2)
        cy = y + int(h / 2)

        cv2.drawContours(self.current_image_gray, [cnt], -1, (0, 0, 0), 3)
        cv2.rectangle(self.current_image_gray, (x, y), (x + w, y + h), (0, 0, 0), 2)

        # out_x, out_y = cal_osc(self, cx, cy) #filter and calibrate values

        self.failed = 0
        return cx, cy, larger_threshold

    self.failed = self.failed + 1
    return 0, 0, larger_threshold
