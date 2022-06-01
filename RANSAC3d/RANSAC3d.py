from threading import Thread
import cv2
import numpy as np
from pye3dcustom.detector_3d import CameraModel, Detector3D, DetectorMode
from pythonosc import udp_client
import time
import os
from scipy import ndimage
import pyttsx3
import PIL
engine = pyttsx3.init()


OSCip="127.0.0.1" 
OSCport=9000 #VR Chat OSC port
client = udp_client.SimpleUDPClient(OSCip, OSCport)



def vc():
    vc.height = 1
    vc.width = 1
    vc.roicheck = 1

    vc.xoff = 1
    vc.yoff = 1
    vc.eyeoffset = 300 ################################################################################################################## INCREASEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE
    vc.eyeoffx = 1
    vc.setoff = 0
    vc.x = 1
    vc.y = 1
    vc.w = 1
    vc.h = 1

    vc.xmax = 69420
    vc.xmin = -69420
    vc.ymax = 69420
    vc.ymin = -69420

vc()




try:
    with open("camaddr.cfg", 'r') as camr:
        lines = camr.readlines()
        camaddrport = lines[0].strip()
    camr.close()


except:    
    camaddr = input('Camera Address or Port:> ')
    ipdetect = ".."

    if ipdetect in camaddr:
        camaddrport = f"http://{camaddr}:81/stream"
    else:
        camaddrport = camaddr

    with open('camaddr.cfg', 'w+') as cam:
        cam.write(str(camaddr))
    
try:
    with open("settings.cfg", 'r') as camr:
        lines = camr.readlines()
        thrsh = int(lines[0].strip())
        rv = int(lines[1].strip())

except:
    print('[ERROR] No Threshold or Rotation Set, Run GUI.')
    thrsh = input('Threshold:> ')
    rv = 0
    with open('settings.cfg', 'w+') as rf:
        rf.write(str(thrsh))
        rf.write('\n')
        rf.write(str(0))









try:
    with open("roi.cfg", 'r+') as roicnfg:
        lines = roicnfg.readlines()
        vc.x = float(lines[0].strip())
        vc.y = float(lines[1].strip())
        vc.w = float(lines[2].strip())
        vc.h = float(lines[3].strip())
        roicnfg.close()
except:
    print('[ERROR] No ROI Set.')
    cap = cv2.VideoCapture(camaddrport)
    ret, img = cap.read()
    img = ndimage.rotate(img, int(rv), reshape=True)
    roibb = cv2.selectROI("image", img, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()
    print('X', roibb[0])
    print('Y', roibb[1])
    print('Width', roibb[2])
    print('Height', roibb[3])
   
    with open('roi.cfg', 'w+') as rf:
        rf.write(str(roibb[0]))
        rf.write('\n')
        rf.write(str(roibb[1]))
        rf.write('\n')
        rf.write(str(roibb[2]))
        rf.write('\n')
        rf.write(str(roibb[3]))
    with open("roi.cfg", 'r+') as roicnfg:
        lines = roicnfg.readlines()
        vc.x = float(lines[0].strip())
        vc.y = float(lines[1].strip())
        vc.w = float(lines[2].strip())
        vc.h = float(lines[3].strip())
        roicnfg.close()

    try:
        cam = cv2.VideoCapture(camaddrport)
        print('[INFO] Press ESC when rotation is set.')
        while True:
            #time.sleep(0.1)############################################################## < REMOVE ####################################################
            ret_val, img = cam.read()
            with open("settings.cfg", 'r') as camr:
                lines = camr.readlines()
                thrsh = int(lines[0].strip())
                rv = int(lines[1].strip())
            img = img[int(vc.y): int(vc.y+vc.h), int(vc.x): int(float(vc.x+vc.w))]
            rows, cols, _ = img.shape
            img_center = (cols / 2, rows / 2)
            M = cv2.getRotationMatrix2D(img_center, rv, 1)
            img = cv2.warpAffine(img, M, (cols, rows),
                            borderMode=cv2.BORDER_CONSTANT,
                            borderValue=(255,255,255))
            #img = ndimage.rotate(img, int(rv), reshape=True)
            cv2.imshow('cam', img)
            if cv2.waitKey(1) == 27: 
                break  # esc to quit
        cv2.destroyAllWindows()
    except:
        print('[INFO] Rotation sucsessfully set')











try:
    with open("center_offset.cfg") as offr:
        lines = offr.readlines()
        vc.xoff = float(lines[0].strip())
        vc.yoff = float(lines[1].strip())

        offr.close()
except:
    print('[WARN] No eye offset has been detected.')
    engine.say("No eye offset has been detected please move your eye around and wait for audio prompt.")
        
    engine.runAndWait()
    vc.eyeoffset = 300
    vc.setoff = 1






def fit_rotated_ellipse_ransac(
    data, iter=80, sample_num=10, offset=80    # 80.0, 10, 80
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

        # thresh
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

    return (cx, cy, w, h, theta)




cap = cv2.VideoCapture(camaddrport)  # change this to the video you want to test
result_2d = {}
result_2d_final = {}

ret, img = cap.read()
frame_number = cap.get(cv2.CAP_PROP_POS_FRAMES)
fps = cap.get(cv2.CAP_PROP_FPS)
width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

        #print(cv2.selectROI("image", img, fromCenter=False, showCrosshair=True))
vc.width = vc.w
vc.height = vc.h

camera = CameraModel(focal_length=30, resolution=[vc.width,vc.height])

detector_3d = Detector3D(camera=camera, long_term_mode=DetectorMode.blocking)

if cap.isOpened() == False:
    print("Error opening video stream or file")
while cap.isOpened():



    try:
        rvo = rv
        with open("settings.cfg", 'r') as camr:
            lines = camr.readlines()
            thrsh = int(lines[0].strip())
            rv = int(lines[1].strip())
        if rv != rvo:
            print("[WARN] Rotation Detected. Center Calibration will start in a few seconds.")
            vc.eyeoffset = 300
    except:
        print('[WARN] Config Over-read Detected.')
    #try:
    try:
        ret, img = cap.read()
        img = img[int(vc.y): int(vc.y+vc.h), int(vc.x): int(float(vc.x+vc.w))]

        
    except:
        img = imgo[int(vc.y): int(vc.y+vc.h), int(vc.x): int(float(vc.x+vc.w))]
        print('[SEVERE WARN] Frame Issue Detected.')
#print(cv2.selectROI("image", img, fromCenter=False, showCrosshair=True))
    




    frame_number = cap.get(cv2.CAP_PROP_POS_FRAMES)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if ret == True:
        rows, cols, _ = img.shape
        img_center = (cols / 2, rows / 2)
        M = cv2.getRotationMatrix2D(img_center, rv, 1)
        img = cv2.warpAffine(img, M, (cols, rows),
                           borderMode=cv2.BORDER_CONSTANT,
                           borderValue=(255,255,255))
        newImage2 = img.copy()
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        image_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, backupthresh = cv2.threshold(
            image_gray, (int(thrsh) + 5) , 255, cv2.THRESH_BINARY
        )
        ret, thresh = cv2.threshold(
            image_gray, int(thrsh), 255, cv2.THRESH_BINARY
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
            #get axis and angle of ellipse pupil labs 2d  
            result_2d["center"] = (cx, cy)
            result_2d["axes"] = (w, h) 
            result_2d["angle"] = theta * 180.0 / np.pi 
            result_2d_final["ellipse"] = result_2d
            result_2d_final["diameter"] = w 
            result_2d_final["location"] = (cx, cy)
            result_2d_final["confidence"] = 0.99
            result_2d_final["timestamp"] = frame_number / fps
            result_3d = detector_3d.update_and_detect(result_2d_final, image_gray)
            ellipse_3d = result_3d["ellipse"]
            
            # draw pupil
            cv2.ellipse(
                image_gray,
                tuple(int(v) for v in ellipse_3d["center"]),
                tuple(int(v) for v in ellipse_3d["axes"]),
                ellipse_3d["angle"],
                0,
                360,  # start/end angle for drawing
                (0, 255, 0),  # color (BGR): red
            )
            projected_sphere = result_3d["projected_sphere"]
            
            # draw eyeball
            #image_gray1 = img
            cv2.ellipse(
                image_gray,
                tuple(int(v) for v in projected_sphere["center"]),
                tuple(int(v) for v in projected_sphere["axes"]),
                projected_sphere["angle"],
                0,
                360,  # start/end angle for drawing
                (0, 255, 0),  # color (BGR): red
            )
            
            # draw line from center of eyeball to center of pupil
            cv2.line(
                image_gray,
                tuple(int(v) for v in projected_sphere["center"]),
                tuple(int(v) for v in ellipse_3d["center"]),
                (0, 255, 0),  # color (BGR): red
            )

            exm = ellipse_3d["center"][0]
            eym = ellipse_3d["center"][1]

            xrl = (cx - projected_sphere["center"][0]) / projected_sphere["axes"][0]
            
            eyey = (cy - projected_sphere["center"][1]) / projected_sphere["axes"][1]

            if vc.eyeoffset == 1 and vc.setoff == 1:
                engine.say("Eye offset not found look straight forward")
                engine.runAndWait()
                time.sleep(3)



            if vc.eyeoffset == 0:
                vc.eyeoffset = vc.eyeoffset - 1
                vc.xoff = ellipse_3d["center"][0]
                vc.yoff = ellipse_3d["center"][1]


                with open('center_offset.cfg', 'w+') as rf:
                    rf.write(str(vc.xoff))
                    rf.write('\n')
                    rf.write(str(vc.yoff))
                engine.say("Eye offset has been set.")
                engine.runAndWait()
                
            else:
                if vc.eyeoffset > 0:


                    if exm > vc.xmax:
                        vc.xmax = exm
                    if exm < vc.xmin:
                        vc.xmin = exm

                    if eym > vc.ymax:
                        vc.ymax = eym
                    if eym < vc.xmin:
                        vc.ymin = eym
                    
           
                    vc.eyeoffset = vc.eyeoffset - 1
                



            xl = float((((cx - vc.xoff) * 100) / (vc.xmax - vc.xoff)) / 100) 

            xr = float((((cx - vc.xoff) * 100) / (vc.xmin - vc.xoff)) / 100) 


            yu = float((((cy - vc.yoff) * 100) / (vc.ymin - vc.yoff)) / 100)

            yd = float((((cy - vc.yoff) * 100) / (vc.ymax - vc.yoff)) / 100)



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






           # if xrl >= 0:
           #     client.send_message("/avatar/parameters/RightEyeX", -abs(xrl))
           #     client.send_message("/avatar/parameters/LeftEyeX", -abs(xrl))
          #  if xrl <= 0:
           #     client.send_message("/avatar/parameters/RightEyeX", abs(xrl))
           #     client.send_message("/avatar/parameters/LeftEyeX", abs(xrl))
            # client.send_message("/avatar/parameters/RightEyeX", abs(xrl - vc.eyeoffx))
                #client.send_message("/avatar/parameters/LeftEyeX", abs(xrl - vc.eyeoffx))

         #   if eyey >= 0:
          #      client.send_message("/avatar/parameters/EyesY", -abs(eyey))
          #      client.send_message("/avatar/parameters/EyesY", -abs(eyey))

         #   if eyey <= 0:
        #        client.send_message("/avatar/parameters/EyesY", abs(eyey))
         #       client.send_message("/avatar/parameters/EyesY", abs(eyey))

         #   client.send_message("/avatar/parameters/LeftEyeLid", float(1))
         #   client.send_message("/avatar/parameters/RightEyeLid", float(1))

       #     ellipse_3d["center"][0] x mid?
        #    ellipse_3d["center"][1] y mid




        except:
            try:
                contours, _ = cv2.findContours(backupthresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)
                rows, cols, _ = img.shape
                for cnt in contours:
                    
                    (x, y, w, h) = cv2.boundingRect(cnt)
                    xt = x + int(w/2) 
                    yt = y + int(h/2)
                    if h > 8 and w > 8 and h < 30 and w < 30:
                        

                        xrlb = (xt - projected_sphere["center"][0]) / projected_sphere["axes"][0]
                        eyeyb = (yt - projected_sphere["center"][1]) / projected_sphere["axes"][1]
                        print(xrlb, eyeyb)
                        cv2.line(image_gray, (x + int(w/2), 0), (x + int(w/2), rows), (255, 0, 0), 1) #visualizes eyetracking on thresh
                        cv2.line(image_gray, (0, y + int(h/2)), (cols, y + int(h/2)), (255, 0, 0), 1)
                        cv2.drawContours(image_gray, [cnt], -1, (255, 0, 0), 3)
                        cv2.rectangle(image_gray, (x, y), (x + w, y + h), (255, 0, 0), 2)

                        if xrlb >= 0:
                            client.send_message("/avatar/parameters/RightEyeX", -abs(xrl))
                            client.send_message("/avatar/parameters/LeftEyeX", -abs(xrl))
                        if eyeyb <= 0:
                            client.send_message("/avatar/parameters/RightEyeX", -abs(xrl))
                            client.send_message("/avatar/parameters/LeftEyeX", -abs(xrl))

                    else:
                        client.send_message("/avatar/parameters/LeftEyeLid", float(0))
                        client.send_message("/avatar/parameters/RightEyeLid", float(0))
                        print('[INFO] BLINK Detected.')

            except:
                print('[ERROR] Backup Tracking Failed.')
            #pass
        imgo = img

    cv2.imshow("Ransac", image_gray)
    cv2.imshow("Original", thresh)
    cv2.imshow("eye", img)
    cv2.imshow("backupthresh", backupthresh)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        cv2.destroyAllWindows()
        break
    #except:
            
       # print('E1')
