import cv2
import numpy as np
import threading
from multiprocessing import Process,Queue,Pipe
cap = cv2.VideoCapture(3)
bl = False

import time

def lefteye():


    h = 1
    textl = 1
    while True:
        ret, frame = cap.read()
        if ret is False:
            break  


        fy= open("valueY.txt","r+")
        vy = fy.read().strip()
        fy.close
        
        ###########

        fx= open("valueX.txt","r+")
        vx = fx.read().strip()
        fx.close
    
    ################

        vyll= open("valueYl.txt","r+")
        vyl = vyll.read().strip()
        vyll.close
      
      #############
        vxll= open("valueXl.txt","r+")
        vxl = vxll.read().strip()
        vxll.close
##########################
        thresh= open("thresh.txt","r+")
        threshr = thresh.read().strip()
        thresh.close

  
        try:
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
            #print(x, y,)
            textl = str(x) + ' ' + str(y)
            
            cv2.drawContours(roi, [cnt], -1, (0, 0, 255), 3)
            cv2.rectangle(roi, (x, y), (x + w, y + h), (255, 0, 0), 2)
            if h <= 10:
                print('blink')
                textl = 'blink'
            if w >= 50:
                print('eyeclosed')
                textl = 'eyeclosed'
            eyeopeness1 = h * 2 * w
            print(eyeopeness1)
            cv2.putText(frame, textl, (200, 300), cv2.FONT_HERSHEY_DUPLEX, 0.9, (100, 58, 31), 1)
            cv2.line(roi, (x + int(w/2), 0), (x + int(w/2), rows), (100, 0, 255), 1)
            cv2.line(roi, (0, y + int(h/2)), (cols, y + int(h/2)), (0, 255, 0), 1)
            break
        if textl == 'blink':
            cv2.putText(frame, textl, (200, 300), cv2.FONT_HERSHEY_DUPLEX, 0.9, (100, 58, 31), 1)
        if textl == 'eyeclosed':
            cv2.putText(frame, textl, (200, 300), cv2.FONT_HERSHEY_DUPLEX, 0.9, (100, 58, 31), 1)
        if h == 0:
            print('no eye detected"')
            iii = 0
       
        
        cv2.imshow("Threshold", threshold)
        cv2.imshow("gray roi", gray_roi)
        cv2.imshow("Roi", roi)
        key = cv2.waitKey(30)
   
print('###############> initailizing threads <###############')
t1 = threading.Thread(target=lefteye)
#t2 = threading.Thread(target=valuy)
t1.start()
#t2.start()
t1.join()
#t2.join()
cv2.destroyAllWindows()
