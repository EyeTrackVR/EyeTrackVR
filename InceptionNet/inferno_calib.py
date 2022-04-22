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


def main(m_type, m_name):
    with tf.Session() as sess:  # start a session

        # load best model
        model = load_model(sess, m_type, m_name)  # load the best model
        #cap = cv2.VideoCapture('http://192.168.0.202:81/stream')  # load the camera
        #cap = rotated = ndimage.rotate(capu, 45)
        #while cap.isOpened():

        with open("config.txt") as calibratefl:
            lines = calibratefl.readlines()
            vx = float(lines[0].strip())
            vy = float(lines[1].strip())
            vxl = float(lines[2].strip())
            vyl = float(lines[3].strip())
            rv = float(lines[4].strip())
            calibratefl.close()

        #cap = cv2.VideoCapture('http://192.168.0.202:81/stream')
        #ret, frame = cap.read()
        #frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        #try:
         #   frame1 = ndimage.rotate(frame, int(rv), reshape=True)
          #  frame1 = frame1[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
        
           # if frame1.shape[0] != 192:
            #    frame1 = rescale(frame1)
            
            #image = gray_normalizer(frame1)
            #image = change_channel(image, config["input_channel"])
            
          #  [p] = model.predict(sess, [image])
           #@ cv2.circle(frame1, (int(p[0]), int(p[1])), int(p[2]), (0, 0, 255), 2)
            #cv2.circle(frame1, (int(p[0]), int(p[1])), 1, (0, 0, 255), -1)
            #print(int(p[0]), int(p[1]), int(p[2]))  #int(p[2]) pupil pixel size (circ diamiter)
            #xt = int(p[0]) 
            #yt = int(p[1])
            #cap.release()
        #except:
         #   print('preoc error')  
            #try:
            #    xpercentage = (((xt - vc.xmin) * 100) / (vc.xmax - vc.xmin)) / 100 #TESTING NEEDED AM UNSURE IF VALUES NEED TO BE FLIPPED
                #   ypercentage = (((yt - vc.ymin) * 100) / (vc.ymax - vc.ymin)) / 100
            #if vc.cfc == 1 and vc.fc != 1:
            #if vc.cfc == 1:
               #00 try:
                    
                  #  with open("eyeconfig.cfg") as eyecalib:
                   #     lines = eyecalib.readlines()
                    #    calibcenterx = float(lines[0].strip())
                     #   calibcentery = float(lines[1].strip())
                      #  calibrightx = float(lines[2].strip())
                       # calibleftx = float(lines[3].strip())
                       # calibrighty = float(lines[4].strip())
                       # caliblefty = float(lines[5].strip())
                        #calibupx = float(lines[6].strip())
                        #calibupy = float(lines[7].strip())
                        
                        #vc.cfc = 1
                        #eyecalib.close()
                
                #except:
        while True:

            if vc.cc == 1:
                engine.say("a saved calibration file was not found.")
                engine.say("Calibration starting, 3. 2. 1. please look straight forward")
                engine.runAndWait()
                vc.cc = 2
                

            if vc.cc == 2:
                cap = cv2.VideoCapture('http://192.168.0.202:81/stream')
                ret, frame = cap.read()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                try:
                    frame1 = ndimage.rotate(frame, int(rv), reshape=True)
                    frame1 = frame1[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
                
                    if frame1.shape[0] != 192:
                        frame1 = rescale(frame1)
                    
                    image = gray_normalizer(frame1)
                    image = change_channel(image, config["input_channel"])
                    
                    [p] = model.predict(sess, [image])
                    cv2.circle(frame1, (int(p[0]), int(p[1])), int(p[2]), (0, 0, 255), 2)
                    cv2.circle(frame1, (int(p[0]), int(p[1])), 1, (0, 0, 255), -1)
                    #print(int(p[0]), int(p[1]), int(p[2]))  #int(p[2]) pupil pixel size (circ diamiter)
                    xt = int(p[0]) 
                    yt = int(p[1])
                    cap.release()
                    cv2.destroyAllWindows()
                except:
                    print('preoc error') 
                                    
                calibcenterx = xt
                calibcentery = yt
                print(xt, yt)
                engine.say("center calibration complete, please look right")
                engine.runAndWait()
                vc.cr = 1
                vc.cc = 3
                

            if vc.cr == 1:
                engine.say("Right calibration starting")
                engine.runAndWait()
                vc.cr = 2
                

            if vc.cr == 2:
                cap = cv2.VideoCapture('http://192.168.0.202:81/stream')
                ret, frame = cap.read()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                try:
                    frame1 = ndimage.rotate(frame, int(rv), reshape=True)
                    frame1 = frame1[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
                
                    if frame1.shape[0] != 192:
                        frame1 = rescale(frame1)
                    
                    image = gray_normalizer(frame1)
                    image = change_channel(image, config["input_channel"])
                    
                    [p] = model.predict(sess, [image])
                    cv2.circle(frame1, (int(p[0]), int(p[1])), int(p[2]), (0, 0, 255), 2)
                    cv2.circle(frame1, (int(p[0]), int(p[1])), 1, (0, 0, 255), -1)
                    #print(int(p[0]), int(p[1]), int(p[2]))  #int(p[2]) pupil pixel size (circ diamiter)
                    xt = int(p[0]) 
                    yt = int(p[1])
                    cap.release()
                    cv2.destroyAllWindows()
                except:
                    print('preoc error') 
                calibrightx = xt
                calibrighty = yt
                print(xt, yt)
                engine.say("Right calibration complete, please look left")
                engine.runAndWait()
                vc.cl = 1
                vc.cr = 3
                
            
            if vc.cl == 1:
                engine.say("left calibration starting")
                engine.runAndWait()
                vc.cl = 2
                
                

            if vc.cl == 2:
                cap = cv2.VideoCapture('http://192.168.0.202:81/stream')
                ret, frame = cap.read()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                try:
                    frame1 = ndimage.rotate(frame, int(rv), reshape=True)
                    frame1 = frame1[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
                
                    if frame1.shape[0] != 192:
                        frame1 = rescale(frame1)
                    
                    image = gray_normalizer(frame1)
                    image = change_channel(image, config["input_channel"])
                    
                    [p] = model.predict(sess, [image])
                    cv2.circle(frame1, (int(p[0]), int(p[1])), int(p[2]), (0, 0, 255), 2)
                    cv2.circle(frame1, (int(p[0]), int(p[1])), 1, (0, 0, 255), -1)
                    #print(int(p[0]), int(p[1]), int(p[2]))  #int(p[2]) pupil pixel size (circ diamiter)
                    xt = int(p[0]) 
                    yt = int(p[1])
                    cap.release()
                    cv2.destroyAllWindows()
                except:
                    print('preoc error') 
                calibleftx = xt
                caliblefty = yt
                print(xt, yt)
                engine.say("left calibration complete, please look up")
                engine.runAndWait()
                vc.cl = 3
                vc.cu = 1

            if vc.cu == 1:
                engine.say("up calibration starting")
                engine.runAndWait()
                vc.cu = 2
                

            if vc.cu == 2:
                cap = cv2.VideoCapture('http://192.168.0.202:81/stream')
                ret, frame = cap.read()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                try:
                    frame1 = ndimage.rotate(frame, int(rv), reshape=True)
                    frame1 = frame1[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
                
                    if frame1.shape[0] != 192:
                        frame1 = rescale(frame1)
                    
                    image = gray_normalizer(frame1)
                    image = change_channel(image, config["input_channel"])
                    
                    [p] = model.predict(sess, [image])
                    cv2.circle(frame1, (int(p[0]), int(p[1])), int(p[2]), (0, 0, 255), 2)
                    cv2.circle(frame1, (int(p[0]), int(p[1])), 1, (0, 0, 255), -1)
                    #print(int(p[0]), int(p[1]), int(p[2]))  #int(p[2]) pupil pixel size (circ diamiter)
                    xt = int(p[0]) 
                    yt = int(p[1])
                    cap.release()
                    cv2.destroyAllWindows()
                except:
                    print('preoc error') 
                calibupx = xt
                calibupy = yt
                print(xt, yt)
                engine.say("up calibration complete, please look down")
                engine.runAndWait()
                vc.cd = 1
                vc.cu = 3

            if vc.cd == 1:
                engine.say("down calibration starting")
                engine.runAndWait()
                vc.cd = 2
                

            if vc.cd == 2:
                cap = cv2.VideoCapture('http://192.168.0.202:81/stream')
                ret, frame = cap.read()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                try:
                    frame1 = ndimage.rotate(frame, int(rv), reshape=True)
                    frame1 = frame1[int(vxl): int(float(vy)), int(vyl): int(float(vx))]
                
                    if frame1.shape[0] != 192:
                        frame1 = rescale(frame1)
                    
                    image = gray_normalizer(frame1)
                    image = change_channel(image, config["input_channel"])
                   
                    
                    [p] = model.predict(sess, [image])
                    cv2.circle(frame1, (int(p[0]), int(p[1])), int(p[2]), (0, 0, 255), 2)
                    cv2.circle(frame1, (int(p[0]), int(p[1])), 1, (0, 0, 255), -1)
                    #print(int(p[0]), int(p[1]), int(p[2]))  #int(p[2]) pupil pixel size (circ diamiter)
                    xt = int(p[0]) 
                    yt = int(p[1])
                    cap.release()
                    cv2.destroyAllWindows()
                except:
                    print('preoc error') 
                calibdownx = xt
                calibdowny = yt
                print(xt, yt)
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





            
                # client.send_message("/avatar/parameters/RightEyeX", xper) #sends to vr chat needs to use calibration function
                #client.send_message("/avatar/parameters/LeftEyeX", xper)
                # client.send_message("/Avatar/LeftEyeY", ypercentage)
                #client.send_message("/Avatar/RightEyeY", ypercentage)
                #client.send_message("/avatar/parameters/EyesY", yper)
                #client.send_message("/avatar/parameters/RightEyeLid", 0)
                #client.send_message("/avatar/parameters/LeftEyeLid", 0)
                #print('X: ', xper, ' Y: ', yper)

            #except:
                #   print('[WARN] Calculation Error: Move Eye Around or Adjust Detection Threshold.')
            

            #xt = int(p[0]) 
            #yt = int(p[1])





#            cv2.imshow("frame", frame1)
 #           cv2.imshow("img", image)
       # except:
        #    print('sussyy e rawr')


       # if cv2.waitKey(1) & 0xFF == ord("q"):
            #break
        
        #    cv2.destroyAllWindows()


if __name__ == "__main__":
    model_name = "3A4Bh-Ref25"
    model_type = "INC"
    video_path = 0


   # with open("config.txt") as calibratefl:
    #    lines = calibratefl.readlines()
     #   rv = float(lines[4].strip())
      #  calibratefl.close()

        
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



    # initial a logger

    main(model_type, model_name)
