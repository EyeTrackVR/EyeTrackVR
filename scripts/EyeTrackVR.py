import cv2
import numpy as np
import threading
import time 
import os

try:
    fy= open("camport.txt","r+")
    camport = fy.read().strip()
    fy.close
except:
    camport = 0
    cam = open('camport.txt', 'w+')
    cam.write('0')
    cam.close
    print('Error: Run Gui first and adjust camera port')
    time.sleep(1)
bl = False
cap = cv2.VideoCapture(int(camport))
width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
print(width, height)


def lefteye():
    x = 1 #defining variables for smoothing
    y = 1
    x1 = 1
    y1 = 1
    h = 1 #defines hight value so blink check doesnt error out
  
    def smooth(x, x1, y, y1):
        xsmooth = (x1 + x) / 2
        ysmooth = (y1 + y) / 2
        print('x filtered:', xsmooth, 'y filtered:', ysmooth, 'x raw:', x, 'y raw:', y)
        #print('x raw:', x, 'y raw:', y)
	    
	    
    while True: #loop for eye detection
        ret, frame = cap.read()
        if ret is False:
            break  

################################################ Reads values set in gui, needs rework to single config file
        try:
            fy= open("valueY.txt","r+")
            vy = fy.read().strip()
            fy.close
        except:
            vy = str(height)
            v= open("valueY.txt","w+")
            v.write(vy)
            v.close()
            print('WARNING: Run Gui first and adjust Value Y')
            #time.sleep(2)
################################################
        try:
            fx= open("valueX.txt","r+")
            vx = fx.read().strip()
            fx.close
        except:
            vx = str(width)
            fx= open("valueX.txt","w+")
            fx.write(vx)
            fx.close()
            print('WARNING: Run Gui first and adjust Value X')
            #time.sleep(2)
################################################
        try:
            vyll= open("valueYl.txt","r+")
            vyl = vyll.read().strip()
            vyll.close
        except:
            vyll= open("valueYl.txt","w+")
            vyll.write('1')
            vyll.close
            vyl = 1
            print('WARNING: Run Gui first and adjust Value Y L')
            time.sleep(1)
################################################
        try:
            vxll= open("valueXl.txt","r+")
            vxl = vxll.read().strip()
            vxll.close
        except:    
            vxl = 1
            vyll= open("valueXl.txt","w+")
            vyl = vyll.write('1')
            vyll.close
            print('Error: Run Gui first and adjust Value X L')
            time.sleep(1)
################################################
        try:
            thresh= open("thresh.txt","r+")
            threshr = thresh.read().strip()
            thresh.close
        except:
            thresh= open("thresh.txt","w+")
            threshr = thresh.write('19')
            thresh.close
            print('WARNING: Run Gui first and adjust threshold value')
            threshr = 19
            time.sleep(1)
            
            
################################################
       # try:
        try:  # trys at set size if it errors it will revert to working size/ doesnt do what was orrigionally planed, it kinda helps
            roi = frame[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        except:
            roi = frame[100: 300, 200: 316]
        try:
            x1 = x
            y1 = y   	
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
              
                smooth(x, x1, y, y1)
                #print('Left:   x:', x, 'y:', y, 'openess:', openes)
                #print('Right:  x:', x, 'y:', y, 'openess:', openes)
                
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
        except: 
            print('ERROR 1: Something went wrong trying to track your eye.')


    
print('###############> initailizing <###############')

cv2.destroyAllWindows()
if __name__ == '__main__':
    lefteye()
    #t1 = threading.Thread(target=lefteye)
    #t2 = threading.Thread(target=righteye)
    #t1.start()
    #t2.start()
    #t1.join()
    #t2.join()
    print('Running:')
