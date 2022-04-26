from tkinter import E
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from time import time
import pyttsx3

engine = pyttsx3.init()


    
def vc():

    vc.xmax = 1          
    vc.xmin = 6969  
    vc.ymax = 1
    vc.ymin = 6969 


    vc.cfc = 50
    vc.cc = 1
    vc.cu = 0
    vc.cd = 0
    vc.cl = 0
    vc.cr = 0
    vc.fc = 0
vc()

def savecalibvalues(calibcenterx, calibcentery, calibrightx, calibleftx, calibupy, calibdowny):
    with open('eyeconfig.cfg', 'w+') as cw:
        cw.write(str(calibcenterx))
        cw.write('\n')
        cw.write(str(calibcentery))
        cw.write('\n')
        cw.write(str(calibrightx))
        cw.write('\n')
        cw.write(str(calibleftx))
        cw.write('\n')
        cw.write(str(calibupy))
        cw.write('\n')
        cw.write(str(calibdowny))
        cw.close()

with open("config.txt") as calibratefl:
        lines = calibratefl.readlines()
        vx = float(lines[0].strip())
        vy = float(lines[1].strip())
        vxl = float(lines[2].strip())
        vyl = float(lines[3].strip())
        rv = float(lines[4].strip())
        calibratefl.close()



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


#cap = cv2.VideoCapture("http://192.168.0.202:81/stream")  # change this to the video you want to test
#if cap.isOpened() == False:
 #   print("Error opening video stream or file")



while True:

    if vc.cc == 1:
        engine.say("a saved calibration file was not found.")
        engine.say("Calibration starting, 3. 2. 1. please look straight forward")
        engine.runAndWait()
        vc.cc = 2
        

    if vc.cc == 2:
        cap = cv2.VideoCapture("http://192.168.0.202:81/stream")
        ret, img = cap.read()
        img = img[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        if ret == True:
            newImage2 = img.copy()
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            image_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, thresh = cv2.threshold(
                image_gray, 120, 255, cv2.THRESH_BINARY
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
            cv2.imshow("Ransac", newImage2)
            cv2.imshow("gray", image_gray)
            cv2.imshow("thresh", thresh)

            cap.release()
            cv2.destroyAllWindows()

                            
        calibcenterx = cx
        calibcentery = cy
        print(cx, cy)
        engine.say("center calibration complete, please look right")
        engine.runAndWait()
        vc.cr = 1
        vc.cc = 3
        

    if vc.cr == 1:
        engine.say("Right calibration starting")
        engine.runAndWait()
        vc.cr = 2
        

    if vc.cr == 2:
        cap = cv2.VideoCapture("http://192.168.0.202:81/stream")
        ret, img = cap.read()
        img = img[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        if ret == True:
            newImage2 = img.copy()
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            image_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, thresh = cv2.threshold(
                image_gray, 120, 255, cv2.THRESH_BINARY
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
            cv2.imshow("Ransac", newImage2)
            cv2.imshow("gray", image_gray)
            cv2.imshow("thresh", thresh)
                            
        calibrightx = cx
        calibrighty = cy
        print(cx, cy)
        cap.release()
        cv2.destroyAllWindows()
  
        engine.say("Right calibration complete, please look left")
        engine.runAndWait()
        vc.cl = 1
        vc.cr = 3
        
    
    if vc.cl == 1:
        engine.say("left calibration starting")
        engine.runAndWait()
        vc.cl = 2
        
        

    if vc.cl == 2:
        cap = cv2.VideoCapture("http://192.168.0.202:81/stream")
        ret, img = cap.read()
        img = img[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        if ret == True:
            newImage2 = img.copy()
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            image_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, thresh = cv2.threshold(
                image_gray, 120, 255, cv2.THRESH_BINARY
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
            cv2.imshow("Ransac", newImage2)
            cv2.imshow("gray", image_gray)
            cv2.imshow("thresh", thresh)
                            
        calibleftx = cx
        calibclefty = cy
        print(cx, cy)
        cap.release()
        cv2.destroyAllWindows()

        engine.say("left calibration complete, please look up")
        engine.runAndWait()
        vc.cl = 3
        vc.cu = 1

    if vc.cu == 1:
        engine.say("up calibration starting")
        engine.runAndWait()
        vc.cu = 2
        

    if vc.cu == 2:
        cap = cv2.VideoCapture("http://192.168.0.202:81/stream")
        ret, img = cap.read()
        img = img[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        if ret == True:
            newImage2 = img.copy()
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            image_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, thresh = cv2.threshold(
                image_gray, 120, 255, cv2.THRESH_BINARY
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
            cv2.imshow("Ransac", newImage2)
            cv2.imshow("gray", image_gray)
            cv2.imshow("thresh", thresh)
                            
        calibupx = cx
        calibupy = cy
        print(cx, cy)
        cap.release()
        cv2.destroyAllWindows()
  
        engine.say("up calibration complete, please look down")
        engine.runAndWait()
        vc.cd = 1
        vc.cu = 3

    if vc.cd == 1:
        engine.say("down calibration starting")
        engine.runAndWait()
        vc.cd = 2
        

    if vc.cd == 2:
        cap = cv2.VideoCapture("http://192.168.0.202:81/stream")
        ret, img = cap.read()
        img = img[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        if ret == True:
            newImage2 = img.copy()
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            image_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, thresh = cv2.threshold(
                image_gray, 120, 255, cv2.THRESH_BINARY
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
            cv2.imshow("Ransac", newImage2)
            cv2.imshow("gray", image_gray)
            cv2.imshow("thresh", thresh)
                            
        calibdownx = cx
        calibdowny = cy
        print(cx, cy)
        cap.release()
        cv2.destroyAllWindows()
  
        engine.say("calibration complete")
        engine.runAndWait()
        vc.cd = 3
    else:
        print('CALIBCOMPLETE')  
        savecalibvalues(calibcenterx, calibcentery, calibrightx, calibleftx, calibupy, calibdowny)
        vc.cfc = 2
        vc.fc = 1
        print('CALIBCOMPLETE22q2')  
        break
