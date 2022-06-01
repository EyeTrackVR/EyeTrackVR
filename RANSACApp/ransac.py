import sys
sys.path.append("../RANSAC3d")
from config import RansacConfig
from pye3dcustom.detector_3d import CameraModel, Detector3D, DetectorMode
import queue
import numpy as np
import cv2

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

class Ransac:
  def __init__(self, config: "RansacConfig", msg_queue: "queue.Queue[None]", img_queue):
    self.config = config
    self.img_queue = img_queue
    self.msg_queue = msg_queue

    self.roicheck = 1

    self.xoff = 1
    self.yoff = 1
    self.eyeoffset = 300 # Keep large in order to recenter correctly
    self.eyeoffx = 1
    self.setoff = 1
    self.x = config.roi_window_x
    self.y = config.roi_window_y
    self.w = config.roi_window_w
    self.h = config.roi_window_h

    self.xmax = 69420
    self.xmin = -69420
    self.ymax = 69420
    self.ymin = -69420

    
  def run(self):
    cap = cv2.VideoCapture(2)  # change this to the video you want to test
    # Get an initial image to get our settings for this run
    ret, img = cap.read()
    frame_number = cap.get(cv2.CAP_PROP_POS_FRAMES)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    #print(cv2.selectROI("image", img, fromCenter=False, showCrosshair=True))

    # TODO Read focal length from config
    camera = CameraModel(focal_length=60, resolution=[self.w, self.h])
    detector_3d = Detector3D(camera=camera, long_term_mode=DetectorMode.blocking)
    while cap.isOpened():
      try: 
        self.msg_queue.get(block=False)
        print("Exiting RANSAC thread")
        return
      except queue.Empty:
        pass

      result_2d = {}
      result_2d_final = {}

      # Get our current frame
      try:
        ret, img = cap.read()
        img = img[int(self.y): int(self.y+self.h), int(self.x): int(float(self.x+self.w))]  
      except:
        img = imgo[int(self.y): int(self.y+self.h), int(self.x): int(float(self.x+self.w))]
        print('[SEVERE WARN] Frame Issue Detected.')
    
      frame_number = cap.get(cv2.CAP_PROP_POS_FRAMES)
      fps = cap.get(cv2.CAP_PROP_FPS)

      if not ret:
        print("Error fetching frame, bailing")
        return
      # image_stack = np.concatenate((img, cv2.cvtColor(image_gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR), cv2.cvtColor(backupthresh, cv2.COLOR_GRAY2BGR)), axis=1)
      image_stack = img
      self.img_queue.put(image_stack)
      # Initial image will be huge, resize by half.
      
