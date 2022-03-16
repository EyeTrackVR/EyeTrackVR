import cv2
from threading import Thread
import time
import argparse


class config:
    X_RES = 128
    Y_RES = 128


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
        #xlist = []
        img = cv2.cvtColor(self.frame, cv2.COLOR_RGB2GRAY)
        img = cv2.resize(img, dsize=(config.X_RES, config.Y_RES))
        
        imgrgb = cv2.resize(self.frame, dsize=(config.X_RES, config.Y_RES))
        

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

        # trys at set size if it errors it will revert to working size/ doesnt do what was orrigionally planed, it kinda helps
        try:
            roi = img[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        except:
            print('roi invalid size')
    #    roi = img[100: 300, 200: 316]
        
        try:  	
            rows, cols, = roi.shape
            gray_roi = cv2.GaussianBlur(roi, (7, 7), 0)

            _, threshold = cv2.threshold(gray_roi, int(threshr), 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)
            #xlist.extend(int(x))
            #print(xlist)
            #print(x)
        except:
            print('no EYE')
        try:
            for cnt in contours:
                
                (x, y, w, h) = cv2.boundingRect(cnt)
                    

                
            
                #smooth(x, x1, y, y1)
                #print('Left:   x:', x, 'y:', y, 'openess:', 
                #'Right:  x:', x, 'y:', y,)
                if x > 0:
                    xlist.append(int(x))
                else:
                    print('x value too small to log')
               # print(xlist)
                if y > 0:
                    ylist.append(int(y))
                else:
                    print('Y value too small to log')

                cv2.line(threshold, (x + int(w/2), 0), (x + int(w/2), rows), (255, 0, 0), 1) #visualizes eyetracking on threshold
                cv2.line(threshold, (0, y + int(h/2)), (cols, y + int(h/2)), (255, 0, 0), 1)
                cv2.drawContours(threshold, [cnt], -1, (255, 0, 0), 3)
                cv2.rectangle(threshold, (x, y), (x + w, y + h), (255, 0, 0), 2)

                cv2.line(gray_roi, (x + int(w/2), 0), (x + int(w/2), rows), (255, 0, 0), 1) #visualizes eyetracking on greyscale 
                cv2.line(gray_roi, (0, y + int(h/2)), (cols, y + int(h/2)), (255, 0, 0), 1)
                cv2.drawContours(gray_roi, [cnt], -1, (255, 0, 0), 3)
                cv2.rectangle(gray_roi, (x, y), (x + w, y + h), (255, 0, 0), 2)
                break
            cv2.imshow("Threshold", threshold)
            #cv2.imshow("GreyScale", gray_roi)
            cv2.imshow("Roi", roi)

        except:
            print('no eye')
        
            
        
    
        #  key = cv2.waitKey(30)
    

        #cv2.imshow('color', imgrgb)
        cv2.imshow('frame', img)
        cv2.waitKey(1)
if __name__ == '__main__':
    #'http://192.168.0.202:81/stream'

    try:
        camadd= open("cam.txt","r+")
        src = camadd.read().strip()
        camadd.close
        
    except:
        print('Configure camera address in EyeTrack and make sure this program is in the same directory.')


    xlist = []
    ylist = []
    threaded_camera = ThreadedCamera(src)
    x = 1 #defining variables for smoothing
    y = 1
    x1 = 1
    y1 = 1
    h = 1 #defines hight value so blink check doesnt error out

    #def calibrate():
     #   print('CALIBRATION MODE')
      #  print('Please put on headset after properly cropping into your eye and verifying that it tracks properly.')
       # input('Press enter to contine :> ')
        #print('look forward')
        #threaded_camera.show_frame()


#def calibrate_center(x,y):
 #   print(x, y)
    

    while True:
        
        try:
            threaded_camera.show_frame()
        except AttributeError:
            pass
        except KeyboardInterrupt:

            maxx = max(xlist)
            print(maxx)

            maxy = max(ylist)
            print(maxy)

            minx = min(xlist)
            print(minx)

            miny = min(ylist)
            print(miny)
            #pass

            calibratedCenterx = (maxx + minx) / 2

            calibratedCentery = (maxy + miny) / 2

            calibratedLeft = minx

            calibratedRight = maxx

            calibratedUp = miny 

            calibratedDown = maxy

            print(calibratedCenterx, calibratedCentery)
            print(calibratedLeft)
            print(calibratedRight)
            print(calibratedUp)
            print(calibratedDown)


            with open('calibration.txt', 'w+') as cw:
                cw.write(str(calibratedLeft))
                cw.write('\n')
                cw.write(str(calibratedDown))
                cw.write('\n')
                cw.write(str(calibratedCenterx))
                cw.write('\n')
                cw.write(str(calibratedCentery))
                cw.write('\n')
                cw.write(str(calibratedRight))
                cw.write('\n')
                cw.write(str(calibratedUp))
                cw.write('\n')
                
                
                cw.close()





            #val = ((input - min) * 100) / (max - min)



            #calibratedleft = 













            break

