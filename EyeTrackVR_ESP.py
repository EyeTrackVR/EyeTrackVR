from threading import Thread
import cv2
import os, time
import argparse
import time
from pythonosc import udp_client



#def smooth(x, x1, y, y1):
 #   xsmooth = (x1 + x) / 2
  #  ysmooth = (y1 + y) / 2
   # print('x filtered:', xsmooth, 'y filtered:', ysmooth, 'x raw:', x, 'y raw:', y)
    #print('x raw:', x, 'y raw:', y)

class config:
    X_RES = 128
    Y_RES = 128

def writet(addressipn):
    addressips = addressipn.strip().lower()
    camadd = open("cam.txt","w+")
    camadd.write(str(addressips))
    print(addressips)
    camadd.close


class ThreadedCamera(object):

    def __init__(self, src=0):
        self.capture = cv2.VideoCapture(src)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        # Start frame retrieval thread
        self.thread = Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()

    def update(self):
        while True:
            if self.capture.isOpened():
                (self.status, self.frame) = self.capture.read()
       
    def show_frame(self):

        img = cv2.cvtColor(self.frame, cv2.COLOR_RGB2GRAY)
        img = cv2.resize(img, dsize=(config.X_RES, config.Y_RES))
        
        imgrgb = cv2.resize(self.frame, dsize=(config.X_RES, config.Y_RES))
       
       ## \/ WILL BE COMBINED INTO ONE SINGLE FILE
        fy= open("valueY.txt","r+")
        vy = fy.read().strip()
        fy.close
    
        fx= open("valueX.txt","r+")
        vx = fx.read().strip()
        fx.close
    
        vyll= open("valueYl.txt","r+")
        vyl = vyll.read().strip()
        vyll.close

        vxll= open("valueXl.txt","r+")
        vxl = vxll.read().strip()
        vxll.close
        
        thresh= open("thresh.txt","r+")
        threshr = thresh.read().strip()
        thresh.close
       ## /\

        # trys at set size if it errors it will revert to working size/ doesnt do what was orrigionally planed, it kinda helps
        try:
            roi = img[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        except:
            print('[ERROR] Camera crop invalid size. Try making it larger.')
    
        
        try:  	
            rows, cols, = roi.shape
            gray_roi = cv2.GaussianBlur(roi, (7, 7), 0)

            _, threshold = cv2.threshold(gray_roi, int(threshr), 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)
        except:
            print('[INFO] No Eye Detected')
        try:
            for cnt in contours:
                
                (x, y, w, h) = cv2.boundingRect(cnt)
                    

                blink = False
                if h <= 25: #way to find if eye is closed and sets value (hopefully will train a model for correct openess detection) Help appriciated since I have no clue how to do ml models
                    blink = True 
            
            
                xpercentage = (((x - xmin) * 100) / (xmax - xmin)) / 100 #TESTING NEEDED AM UNSURE IF VALUES NEED TO BE FLIPPED
                ypercentage = (((y - ymin) * 100) / (ymax - ymin)) / 100
                
                


                if xpercentage >= 1: 
                    print('[WARN] X Value Exceedes Calibrated Value. Please Re Calibrate.')
                    xpercentage = 1
                if ypercentage >= 1: 
                    print('[WARN] X Value Exceedes Calibrated Value. Please Re Calibrate.')
                    ypercentage = 1
                

                print('X: ', xpercentage, ' Y: ', ypercentage)


                client.send_message("/Avatar/EyeRightX", xpercentage) #sends to vr chat needs to use calibration function
                client.send_message("/Avatar/EyeleftX", xpercentage)
                client.send_message("/Avatar/EyeY", ypercentage)
                client.send_message("/Avatar/Blink", blink)



                cv2.line(threshold, (x + int(w/2), 0), (x + int(w/2), rows), (255, 0, 0), 1) #visualizes eyetracking on threshold
                cv2.line(threshold, (0, y + int(h/2)), (cols, y + int(h/2)), (255, 0, 0), 1)
                cv2.drawContours(threshold, [cnt], -1, (255, 0, 0), 3)
                cv2.rectangle(threshold, (x, y), (x + w, y + h), (255, 0, 0), 2)

                cv2.line(gray_roi, (x + int(w/2), 0), (x + int(w/2), rows), (255, 0, 0), 1) #visualizes eyetracking on greyscale 
                cv2.line(gray_roi, (0, y + int(h/2)), (cols, y + int(h/2)), (255, 0, 0), 1)
                cv2.drawContours(gray_roi, [cnt], -1, (255, 0, 0), 3)
                cv2.rectangle(gray_roi, (x, y), (x + w, y + h), (255, 0, 0), 2)
                break

        except:
            print('[ERROR] Main Loop Failure.')

        cv2.imshow("Threshold", threshold)
        cv2.imshow("GreyScale", gray_roi)
        cv2.imshow("Roi", roi)

        cv2.imshow('color', imgrgb)
        cv2.imshow('frame', img)
        cv2.waitKey(1)
        
if __name__ == '__main__':
    #'http://192.168.0.202:81/stream'

 
    with open("calibration.txt") as calibratefl:
        
        lines=calibratefl.readlines()
        xmin = float(lines[0].strip())
        ymin = float(lines[1].strip())
        calibratedcenterx = float(lines[2].strip())
        calibratedcentery = float(lines[3].strip())
        xmax = float(lines[4].strip())
        ymax = float(lines[5].strip())


    try:
        
        OSCip="127.0.0.1" 
        OSCport=9000 #VR Chat OSC port
       
        client = udp_client.SimpleUDPClient(OSCip, OSCport)
    except:
        print('[ERROR] Connection to VR Chat via OSC Failed')
            

    try:
        camadd= open("cam.txt","r+")
        src = camadd.read().strip()
        camadd.close
        
    except:
        addressipn = input('Enter IP Stream Address of Camera :>: ')

        writet(addressipn)
        src = addressipn.strip().lower()
    

    threaded_camera = ThreadedCamera(src)
    x = 1 #defining variables for smoothing
    y = 1
    x1 = 1
    y1 = 1
    h = 1 #defines hight value so blink check doesnt error out

    while True:
        
        try:
            threaded_camera.show_frame()
        except AttributeError:
            pass