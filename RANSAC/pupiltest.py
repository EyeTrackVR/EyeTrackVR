from tkinter import E
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from time import time
import sys
from pythonosc import udp_client
import torch

#model = torch.hub.load('ultralytics/yolov5', 'custom', path='best.pt',force_reload=True)
#model.conf = 0.25  # NMS confidence threshold
#model.iou = 0.45  # NMS IoU threshold
#model.agnostic = False  # NMS class-agnostic
#model.multi_label = False  # NMS multiple labels per box
#model.max_det = 1 # maximum number of detections per image
#model.amp = False  # Automatic Mixed Precision (AMP) inference

cx = 0.5
cy = 0.5

def vc():

    vc.lidmax = 1          
    vc.lidmin = 6969  #( ͡° ͜ʖ ͡°) yes i know im stupid



    vc.cfc = 1
    vc.cc = 1
    vc.cu = 0
    vc.cd = 0
    vc.cl = 0
    vc.cr = 0
    vc.fc = 0

    vc.el = 2
    vc.eyelidv = 1
    vc.src = '1'
vc()

OSCip="127.0.0.1" 
OSCport=9000 #VR Chat OSC port
client = udp_client.SimpleUDPClient(OSCip, OSCport)




def fit_rotated_ellipse_ransac(
    data, iter=90, sample_num=10, offset=80.0
):  # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower
    count_max = 0
    effective_sample = None

    for i in range(iter):
        sample = np.random.choice(len(data), sample_num, replace=False)

        xs = data[sample][:, 0].reshape(-1, 1)
        ys = data[sample][:, 1].reshape(-1, 1)

        J = np.mat(
            np.hstack((xs * ys, ys**2, xs, ys, np.ones_like(xs, dtype=np.float)))
        )
        Y = np.mat(-1 * xs**2)
        P = (J.T * J).I * J.T * Y

        # fitter a*x**2 + b*x*y + c*y**2 + d*x + e*y + f = 0
        a = 1.0
        b = P[0, 0]
        c = P[1, 0]
        d = P[2, 0]
        e = P[3, 0]
        f = P[4, 0]
        ellipse_model = (
            lambda x, y: a * x**2 + b * x * y + c * y**2 + d * x + e * y + f
        )

        # threshold
        ran_sample = np.array(
            [[x, y] for (x, y) in data if np.abs(ellipse_model(x, y)) < offset]
        )

        if len(ran_sample) > count_max:
            count_max = len(ran_sample)
            effective_sample = ran_sample

    return fit_rotated_ellipse(effective_sample)


def fit_rotated_ellipse(data):

    xs = data[:, 0].reshape(-1, 1)
    ys = data[:, 1].reshape(-1, 1)

    J = np.mat(np.hstack((xs * ys, ys**2, xs, ys, np.ones_like(xs, dtype=np.float))))
    Y = np.mat(-1 * xs**2)
    P = (J.T * J).I * J.T * Y

    a = 1.0
    b = P[0, 0]
    c = P[1, 0]
    d = P[2, 0]
    e = P[3, 0]
    f = P[4, 0]
    theta = 0.5 * np.arctan(b / (a - c))

    cx = (2 * c * d - b * e) / (b**2 - 4 * a * c)
    cy = (2 * a * e - b * d) / (b**2 - 4 * a * c)

    cu = a * cx**2 + b * cx * cy + c * cy**2 - f
    w = np.sqrt(
        cu
        / (
            a * np.cos(theta) ** 2
            + b * np.cos(theta) * np.sin(theta)
            + c * np.sin(theta) ** 2
        )
    )
    h = np.sqrt(
        cu
        / (
            a * np.sin(theta) ** 2
            - b * np.cos(theta) * np.sin(theta)
            + c * np.cos(theta) ** 2
        )
    )

    ellipse_model = lambda x, y: a * x**2 + b * x * y + c * y**2 + d * x + e * y + f

    error_sum = np.sum([ellipse_model(x, y) for x, y in data])
    print("fitting error = %.3f" % (error_sum))

    return (cx, cy, w, h, theta)


def increase_brightness(img, value):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    lim = 255 - value
    v[v > lim] = 255
    v[v <= lim] += value

    final_hsv = cv2.merge((h, s, v))
    img = cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR)
    return img


cap = cv2.VideoCapture("http://192.168.0.202:81/stream")  
#cap = cv2.VideoCapture("http://192.168.1.177:4747/video") 
# change this to the video you want to test
if cap.isOpened() == False:
    print("Error opening video stream or file")







while cap.isOpened():
        with open("config.txt") as calibratefl:
            lines = calibratefl.readlines()
            vx = float(lines[0].strip())
            vy = float(lines[1].strip())
            vxl = float(lines[2].strip())
            vyl = float(lines[3].strip())
            rv = float(lines[4].strip())
            calibratefl.close()

   # try:
        ret, img = cap.read()
        img = img[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        if ret == True:
            newImage2 = img.copy()
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            image_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, thresh = cv2.threshold(
                image_gray, 125, 255, cv2.THRESH_BINARY
            )  # this will need to be adjusted everytime hardwere is changed (brightness of IR, Camera postion, etc)
            
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
            image = 255 - closing
            contours, hierarchy = cv2.findContours(
                image, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE
            )
            hull = []
            for i in range(len(contours)):
                hull.append(cv2.convexHull(contours[i], False))
            try:
                cv2.drawContours(img, contours, -1, (255, 0, 0), 1)
                cnt = sorted(hull, key=cv2.contourArea)
                maxcnt = cnt[-1]
                ellipse = cv2.fitEllipse(maxcnt)
                cx, cy, w, h, theta = fit_rotated_ellipse_ransac(maxcnt.reshape(-1, 2))
                print(cx, cy)
                cv2.circle(newImage2, (int(cx), int(cy)), 2, (0, 0, 255), -1)
                cx1, cy1, w1, h1, theta1 = fit_rotated_ellipse(maxcnt.reshape(-1, 2))
                cv2.ellipse(
                    newImage2,
                    (int(cx), int(cy)),
                    (int(w), int(h)),
                    theta * 180.0 / np.pi,
                    0.0,
                    360.0,
                    (50, 250, 200),
                    1,
                )


            except:
                pass

            if vc.el == 2:
                print('here')
                vc.el = 5
                #results = model(img)  # inference
                #for box in results.xyxy[0]:   # box is a list of 4 numbers
                 #   if box[5]==0:       # if the confidence is 0, then skip       
                  #      xB = int(box[2])   # xB is the x coordinate of the bottom right corner
                   #     xA = int(box[0])   # xA is the x coordinate of the top left corner
                    #    yB = int(box[3])   # yB is the y coordinate of the bottom right corner
                     #   yA = int(box[1])   # yA is the y coordinate of the top left corner
                      #  cv2.rectangle(img, (xA, yA), (xB, yB), (0, 255, 0), 2) # draw a rectangle around the detected object
                        #cv2.circle(img, (int((xA+xB)/2), int((yA+yB)/2)), 2, (0, 0, 255), -1)
                #cv2.imshow('EYEMODEL',img)
                print('shown')
                
            
            vc.el = vc.el - 1

            print(vc.el)


            if vc.cfc == 1:
                try:
                    
                    with open("eyeconfig.cfg") as eyecalib:
                        lines = eyecalib.readlines()
                        calibcenterx = float(lines[0].strip())
                        calibcentery = float(lines[1].strip())
                        calibrightx = float(lines[2].strip())
                        calibleftx = float(lines[3].strip())
                        calibupy = float(lines[4].strip())
                        calibdowny = float(lines[5].strip())
                        eyecalib.close()
                        vc.cfc = 2
                
                except:
                    print('eror')
                    
                    sys.exit()

                #percentage = (((input - min) * 100) / (max - min)) / 100   only for reference because im dum and forget stuff
                
            

            
            xr = float((((cx - calibcenterx) * 100) / (calibrightx - calibcenterx)) / 100) 

            xl = float((((cx - calibcenterx) * 100) / (calibleftx - calibcenterx)) / 100) 



            yu = float((((cy - calibcentery) * 100) / (calibupy - calibcentery)) / 100)

            yd = float((((cy - calibcentery) * 100) / (calibdowny - calibcentery)) / 100)

            


            if xr > 0:
                if xr > 1:
                    xr = 1.0
                client.send_message("/avatar/parameters/RightEyeX", xr)
                client.send_message("/avatar/parameters/LeftEyeX", xr)

                print('XR', xr)
            if xl > 0:
                if xl > 1:
                    xl = 1.0
                client.send_message("/avatar/parameters/RightEyeX", -abs(xl))
                client.send_message("/avatar/parameters/LeftEyeX", -abs(xl))
                print('XL', xl)

            if yd > 0:
                if yd > 1:
                    yd = 1.0
                client.send_message("/avatar/parameters/EyesY", -abs(yd))
               # print('YD', yd)

            if yu > 0:
                if yu > 1:
                    yu = 1.0
            
                client.send_message("/avatar/parameters/EyesY", yu)
                #print('YU', yu)

            cv2.imshow("Ransac", newImage2)
            cv2.imshow("gray", image_gray)
            cv2.imshow("thresh", thresh)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    #except:
      #  print('error')