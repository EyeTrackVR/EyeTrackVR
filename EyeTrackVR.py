import cv2
import numpy as np
import threading
import time 
import os


fy= open("camport.txt","r+")
camport = fy.read().strip()
fy.close
bl = False
cap = cv2.VideoCapture(int(camport))


def lefteye():

    h = 1 #defines hight value so blink check doesnt error out
    while True: #loop for eye detection
        ret, frame = cap.read()
        if ret is False:
            break  

################################################ Reads values set in gui, needs rework to single config file
        fy= open("valueY.txt","r+")
        vy = fy.read().strip()
        fy.close
################################################
        fx= open("valueX.txt","r+")
        vx = fx.read().strip()
        fx.close
################################################
        vyll= open("valueYl.txt","r+")
        vyl = vyll.read().strip()
        vyll.close
################################################
        vxll= open("valueXl.txt","r+")
        vxl = vxll.read().strip()
        vxll.close
################################################
        thresh= open("thresh.txt","r+")
        threshr = thresh.read().strip()
        thresh.close
################################################
         
        try:  # trys at set size if it errors it will revert to working size/ doesnt do what was orrigionally planed, it kinda helps, entire thing will eventually go into try and except later 
            roi = frame[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        except:
            roi = frame[100: 300, 200: 316]
        

        rows, cols, _ = roi.shape
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray_roi = cv2.GaussianBlur(gray_roi, (7, 7), 0)

        _, threshold = cv2.threshold(gray_roi, int(threshr), 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)

        for cnt in contours:
            
            (x, y, w, h) = cv2.boundingRect(cnt)
                

            openes = 95
            if h <= 25: #way to find if eye is closed and sets value (hopefully will train tensorflow model for correct openess detection)
                openes = 0 

            print('Left:   x:', x, 'y:', y, 'openess:', openes)
            print('Right:  x:', x, 'y:', y, 'openess:', openes)
            
            cv2.line(threshold, (x + int(w/2), 0), (x + int(w/2), rows), (255, 0, 0), 1) #visualizes eyetracking on threshold
            cv2.line(threshold, (0, y + int(h/2)), (cols, y + int(h/2)), (255, 0, 0), 1)
            cv2.drawContours(threshold, [cnt], -1, (255, 0, 0), 3)
            cv2.rectangle(threshold, (x, y), (x + w, y + h), (255, 0, 0), 2)

            cv2.line(gray_roi, (x + int(w/2), 0), (x + int(w/2), rows), (255, 0, 0), 1) #visualizes eyetracking on greyscale 
            cv2.line(gray_roi, (0, y + int(h/2)), (cols, y + int(h/2)), (255, 0, 0), 1)
            cv2.drawContours(gray_roi, [cnt], -1, (255, 0, 0), 3)
            cv2.rectangle(gray_roi, (x, y), (x + w, y + h), (255, 0, 0), 2)
            break
       
        if h == 0: #basically useless lol
            print('no eye detected"')
            
        
            
        cv2.imshow("Threshold", threshold)
        cv2.imshow("GreyScale", gray_roi)
        #cv2.imshow("Roi", roi)
        key = cv2.waitKey(30)


print('###############> initailizing <###############')

cv2.destroyAllWindows()
if __name__ == '__main__':
    lefteye()

