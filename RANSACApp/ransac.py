import sys
sys.path.append("../RANSAC3d")
from config import RansacConfig
from pye3dcustom.detector_3d import CameraModel, Detector3D, DetectorMode
from typing import Union
import queue
import threading
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
  def __init__(self, config: "RansacConfig", cancellation_event: "threading.Event", capture_queue_incoming: "queue.Queue", image_queue_outgoing: "queue.Queue"):
    self.config = config
    self.capture_queue_incoming = capture_queue_incoming
    self.image_queue_outgoing = image_queue_outgoing
    self.cancellation_event = cancellation_event

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

    self.previous_image = None
    self.current_image = None
    self.current_frame_number = None
    self.current_fps = None
    self.threshold_image = None

    self.previous_rotation = self.config.rotation_angle
    self.current_rotation = self.config.rotation_angle

  def capture_crop_rotate_image(self):
    # Get our current frame
    try:
      # Get frame from capture source, crop to ROI
      self.current_image = self.current_image[int(self.y): int(self.y+self.h), int(self.x): int(float(self.x+self.w))]  
    except:
      # Failure to process frame, reuse previous frame.
      self.current_image = self.previous_image
      print('[ERROR] Frame capture issue detected.')

    # Apply rotation to cropped area. For any rotation area outside of the bounds of the image,
    # fill with white.
    rows, cols, _ = self.current_image.shape
    img_center = (cols / 2, rows / 2)
    rotation_matrix = cv2.getRotationMatrix2D(img_center, self.current_rotation, 1)
    self.current_image = cv2.warpAffine(self.current_image, rotation_matrix, (cols, rows),
                                        borderMode=cv2.BORDER_CONSTANT,
                                        borderValue=(255,255,255))
    return True

  def draw_output(self):
    pass

  def run(self):
    camera_model = CameraModel(focal_length=self.config.focal_length, resolution=[self.w, self.h])
    detector_3d = Detector3D(camera=camera_model, long_term_mode=DetectorMode.blocking)

    while True:
      # Check to make sure we haven't been requested to close
      if self.cancellation_event.is_set():
        print("Exiting RANSAC thread")
        return

      try: 
        # Wait a bit for images here. If we don't get one, just try again.
        (self.current_image, self.current_frame, self.current_fps) = self.capture_queue_incoming.get(block=True, timeout=0.1)
      except queue.Empty:
        print("No image available")
        continue

      if not self.capture_crop_rotate_image():
        continue

      # Convert the image to grayscale, and set up thresholding. Thresholds here are basically a
      # low-pass filter that will set any pixel < the threshold value to 0. Thresholding is user
      # configurable in this utility as we're dealing with variable lighting amounts/placement, as
      # well as camera positioning and lensing. Therefore everyone's cutoff may be different.
      #
      # The goal of thresholding settings is to make sure we can ONLY see the pupil. This is why we
      # crop the image earlier; it gives us less possible dark area to get confused about in the
      # next step.
      image_gray = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2GRAY)
      _, thresh = cv2.threshold(
          image_gray, int(self.config.threshold), 255, cv2.THRESH_BINARY
      )  

      # Set up morphological transforms, for smoothing and clearing the image we get out of the
      # thresholding operation. After this, we'd really like to just have a black blob in the middle
      # of a bunch of white area.
      kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
      opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
      closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
      image = 255 - closing

      # Now that the image is relatively clean, run contour finding in order to get us our pupil
      # boundaries in the 2D context. Ideally, we just get one border.
      contours, _ = cv2.findContours(
          image, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE
      )

      # Find the convex shape based on each contour, and sort the list of them from smallest to
      # largest area.
      convex_hulls = []
      for i in range(len(contours)):
          convex_hulls.append(cv2.convexHull(contours[i], False))
      
      # If we have no convex maidens, we have no pupil, and can't progress from here. Dump back to
      # using blob tracking.
      #
      # TODO Reimplement Prohurtz's blob tracking fallback
      if len(convex_hulls) == 0:
        # print("No contours found, eye not detected, continuing")
        # Draw our image and stack it for visual output
        cv2.drawContours(image_gray, contours, -1, (255, 0, 0), 1)

        image_stack = np.concatenate((self.current_image, cv2.cvtColor(image_gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)), axis=1)
        self.image_queue_outgoing.put(image_stack)
        self.previous_image = self.current_image
        continue

      # Find our largest hull, which we expect will probably be the ellipse that represents the 2d
      # area for the pupil, which we can use as the search area for the eye in general.
      largest_hull = sorted(convex_hulls, key=cv2.contourArea)[-1]

      # However eyes are annoyingly three dimensional, so we need to take this ellipse and turn it
      # into a curve patch on the surface of a sphere (the eye itself). If it's not a sphere, see your
      # ophthalmologist about possible issues with astigmatism.
      try:
        cx, cy, w, h, theta = fit_rotated_ellipse_ransac(largest_hull.reshape(-1, 2))
      except:
        # If we don't find anything, fall back to blob tracking.
        # print("No ellipse found, eye not detected, continuing")
        # Draw our image and stack it for visual output
        cv2.drawContours(image_gray, contours, -1, (255, 0, 0), 1)

        image_stack = np.concatenate((self.current_image, cv2.cvtColor(image_gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)), axis=1)
        self.image_queue_outgoing.put(image_stack)
        self.previous_image = self.current_image
        continue

      # Get axis and angle of the ellipse, using pupil labs 2d algos. The next bit of code ranges
      # from somewhat to completely magic, as most of it happens in native libraries (hence passing
      # via dicts).
      result_2d = {}
      result_2d_final = {}
      frame_number = self.capture_source.get(cv2.CAP_PROP_POS_FRAMES)
      fps = self.capture_source.get(cv2.CAP_PROP_FPS)

      result_2d["center"] = (cx, cy)
      result_2d["axes"] = (w, h) 
      result_2d["angle"] = theta * 180.0 / np.pi 
      result_2d_final["ellipse"] = result_2d
      result_2d_final["diameter"] = w 
      result_2d_final["location"] = (cx, cy)
      result_2d_final["confidence"] = 0.99
      result_2d_final["timestamp"] = self.current_frame_number / self.current_fps
      # Black magic happens here, but after this we have our reprojected pupil/eye, and all we had
      # to do was sell our soul to satan and/or C++.
      result_3d = detector_3d.update_and_detect(result_2d_final, image_gray)

      # Now we have our pupil
      ellipse_3d = result_3d["ellipse"]
      # And our eyeball that the pupil is on the surface of
      projected_sphere = result_3d["projected_sphere"]

      # Record our pupil center
      exm = ellipse_3d["center"][0]
      eym = ellipse_3d["center"][1]

      # So now we get the offset of the center of the eyeball
      xrl = (cx - projected_sphere["center"][0]) / projected_sphere["axes"][0]            
      eyey = (cy - projected_sphere["center"][1]) / projected_sphere["axes"][1]

      # TODO Reimplement Prohurtz's Center Calibration and Calculations

      # Pack our base info to send to VRChat
      output_tuple = (-abs(xrl) if xrl >= 0 else abs(xrl), 
                      -abs(eyey) if eyey >= 0 else abs(eyey), 
                      0)

      # print(output_tuple)

      # Draw our image and stack it for visual output
      cv2.drawContours(image_gray, contours, -1, (255, 0, 0), 1)

      # draw pupil
      try:
        cv2.ellipse(
            image_gray,
            tuple(int(v) for v in ellipse_3d["center"]),
            tuple(int(v) for v in ellipse_3d["axes"]),
            ellipse_3d["angle"],
            0,
            360,  # start/end angle for drawing
            (0, 255, 0),  # color (BGR): red
        )
      except Exception:
        # Sometimes we get bogus axes and trying to draw this throws. Ideally we should check for
        # validity beforehand, but for now just pass. It usually fixes itself on the next frame.
        pass
      # draw line from center of eyeball to center of pupil
      cv2.line(
          image_gray,
          tuple(int(v) for v in projected_sphere["center"]),
          tuple(int(v) for v in ellipse_3d["center"]),
          (0, 255, 0),  # color (BGR): red
      )

      # Shove a concatenated image out to the main GUI thread for rendering
      image_stack = np.concatenate((self.current_image, cv2.cvtColor(image_gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)), axis=1)
      self.image_queue_outgoing.put(image_stack)
      self.previous_image = self.current_image
      
