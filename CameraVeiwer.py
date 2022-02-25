from threading import Thread
import cv2
import os, time

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
                (self.ret, self.frame) = self.capture.read()
       
    def show_frame(self):
        img = cv2.cvtColor(self.frame, cv2.COLOR_RGB2GRAY)
        img = cv2.resize(img, dsize=(config.X_RES, config.Y_RES))

        cv2.imshow('frame', img)
        cv2.waitKey(1)

if __name__ == '__main__':
    #src = 'http://192.168.0.202:81/stream'      
    #Format is http://{ip address}:81/stream
    src = input('enter ip of cam. (Format is http://{ip address}:81/stream) ')
    threaded_camera = ThreadedCamera(src)
    while True:
        try:
            threaded_camera.show_frame()
        except AttributeError:
            pass
