import os


import cv2
import numpy as np
from sympy import N
import tensorflow.compat.v1 as tf

from config import config
from models import Inception
from utils import change_channel, gray_normalizer

import time
from pythonosc import udp_client
from scipy import ndimage
import sys


import pyttsx3

engine = pyttsx3.init()


tf.disable_v2_behavior()


def load_model(session, m_type, m_name):
    # load the weights based on best loss
    best_dir = "best_loss"

    # check model dir
    model_path = "models/" + m_name
    path = os.path.join(model_path, best_dir)
    if not os.path.exists(path):
        raise FileNotFoundError
    model = Inception(m_name, config)

    # load the best saved weights
    ckpt = tf.train.get_checkpoint_state(path)
    if ckpt and tf.train.checkpoint_exists(ckpt.model_checkpoint_path):
        model.restore(session, ckpt.model_checkpoint_path)

    else:
        raise ValueError("There is no best model with given model")

    return model


def rescale(image):
    """
    If the input video is other than network size, it will resize the input video
    :param image: a frame form input video
    :return: scaled down frame
    """
    scale_side = max(image.shape)
    # image width and height are equal to 192
    scale_value = config["input_width"] / scale_side

    # scale down or up the input image
    scaled_image = cv2.resize(image, dsize=None, fx=scale_value, fy=scale_value)

    # convert to numpy array
    scaled_image = np.asarray(scaled_image, dtype=np.uint8)

    # one of pad should be zero
    w_pad = int((config["input_width"] - scaled_image.shape[1]) / 2)
    h_pad = int((config["input_width"] - scaled_image.shape[0]) / 2)

    # create a new image with size of: (config["image_width"], config["image_height"])
    new_image = (
        np.ones((config["input_width"], config["input_height"]), dtype=np.uint8) * 250
    )

    # put the scaled image in the middle of new image
    new_image[
        h_pad : h_pad + scaled_image.shape[0], w_pad : w_pad + scaled_image.shape[1]
    ] = scaled_image

    return new_image


def writet(addressipn):
    addressips = addressipn.strip().lower()
    camadd = open("cam.txt","w+")
    camadd.write(str(addressips))
    print(addressips)
    camadd.close





#def eyelid(frame1):
 #   results = model1(frame1)  # inference
  #  for box in results.xyxy[0]:   # box is a list of 4 numbers
   #     if box[5]==0:       # if the confidence is 0, then skip       
    #        xB = int(box[2])   # xB is the x coordinate of the bottom right corner
    #        xA = int(box[0])   # xA is the x coordinate of the top left corner
    #        yB = int(box[3])   # yB is the y coordinate of the bottom right corner
    #        yA = int(box[1])   # yA is the y coordinate of the top left corner
     #       vc.eyelidv = yA - yB
      #      cv2.rectangle(frame1, (xA, yA), (xB, yB), (0, 255, 0), 2) # draw a rectangle around the detected object

      #      if vc.eyelidv > vc.lidmax:
      #          if vc.lidmax != 0:
       #             vc.lidmax = vc.eyelidv
       #     
        #    if vc.eyelidv < vc.lidmin:
         #       if vc.xmin != 0:
         #           vc.xmin = vc.eyelidv
            #cv2.circle(img, (int((xA+xB)/2), int((yA+yB)/2)), 2, (0, 0, 255), -1)
    #cv2.imshow('EYEMODEL',frame1)




def main(
    m_type,
    m_name,
):
    with tf.Session() as sess:  # start a session

        # load best model
        model = load_model(sess, m_type, m_name)  # load the best model
        cap = cv2.VideoCapture(vc.src)  # load the camera
        #cap = rotated = ndimage.rotate(capu, 45)
        while cap.isOpened():


            with open("config.txt") as calibratefl:
                lines = calibratefl.readlines()
                vx = float(lines[0].strip())
                vy = float(lines[1].strip())
                vxl = float(lines[2].strip())
                vyl = float(lines[3].strip())
                rv = float(lines[4].strip())
                calibratefl.close()


            ret, frame = cap.read()
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            try:
                frame1 = ndimage.rotate(frame, int(rv), reshape=True)
                frame1 = frame1[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
            
                if frame1.shape[0] != 192:
                    frame1 = rescale(frame1)
                
                image = gray_normalizer(frame1)
                image = change_channel(image, config["input_channel"])
                
            # vc.el - 1
            # if vc.el == 1:
                #    eyelid(frame1)
                #    vc.el = 3

                
                [p] = model.predict(sess, [image])
                cv2.circle(frame1, (int(p[0]), int(p[1])), int(p[2]), (0, 0, 255), 2)
                cv2.circle(frame1, (int(p[0]), int(p[1])), 1, (0, 0, 255), -1)
                #print(int(p[0]), int(p[1]), int(p[2]))  #int(p[2]) pupil pixel size (circ diamiter)



                xt = int(p[0]) 
                yt = int(p[1])

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
                        engine.say("A saved calibration file was not found. Please run the clibration program first.")
        
                        #will start the calibration program exe on release and close this one
                        engine.runAndWait()
                        sys.exit()

                #percentage = (((input - min) * 100) / (max - min)) / 100   only for reference because im dum and forget stuff
                
            


                xr = float((((xt - calibcenterx) * 100) / (calibrightx - calibcenterx)) / 100) 

                xl = float((((xt - calibcenterx) * 100) / (calibleftx - calibcenterx)) / 100) 



                yu = float((((yt - calibcentery) * 100) / (calibupy - calibcentery)) / 100)

                yd = float((((yt - calibcentery) * 100) / (calibdowny - calibcentery)) / 100)

                


                if xr > 0:
                    if xr > 1:
                        xr = 1.0
                    client.send_message("/avatar/parameters/RightEyeX", xr)
                    client.send_message("/avatar/parameters/LeftEyeX", xr)

                    #print('XR', xr)
                if xl > 0:
                    if xl > 1:
                        xl = 1.0
                    client.send_message("/avatar/parameters/RightEyeX", -abs(xl))
                    client.send_message("/avatar/parameters/LeftEyeX", -abs(xl))


                if yd > 0:
                    if yd > 1:
                        yd = 1.0
                    client.send_message("/avatar/parameters/EyesY", -abs(yd))

                if yu > 0:
                    if yu > 1:
                        yu = 1.0
                
                    client.send_message("/avatar/parameters/EyesY", yu)




                cv2.imshow("frame", frame1)
                cv2.imshow("img", image)
            except:
                print('[ERROR] Main Loop Error')


            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    model_name = "3A4Bh-Ref25"
    model_type = "INC"
    video_path = 0


   # with open("config.txt") as calibratefl:
    #    lines = calibratefl.readlines()
     #   rv = float(lines[4].strip())
      #  calibratefl.close()

        
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


    try:
        OSCip="127.0.0.1" 
        OSCport=9000 #VR Chat OSC port
        client = udp_client.SimpleUDPClient(OSCip, OSCport)
    except:
       print('[ERROR] Connection to VR Chat via OSC Failed')
            
    try:
        camadd= open("cam.txt","r+")
        vc.src = camadd.read().strip()
        camadd.close  
    except:
        addressipn = input('Enter IP Stream Address of Camera :>: ')
        writet(addressipn)
        vc.src = addressipn.strip().lower()
    

    # initial a logger

    main(model_type, model_name)


# 【=◈︿◈=】