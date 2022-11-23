from operator import truth
from dataclasses import dataclass
import sys
import asyncio

sys.path.append(".")
from config import EyeTrackCameraConfig
from config import EyeTrackSettingsConfig
from pye3d.camera import CameraModel
from pye3d.detector_3d import Detector3D, DetectorMode
import queue
import threading
import numpy as np
import cv2
from enum import Enum
from one_euro_filter import OneEuroFilter
if sys.platform.startswith("win"):
    from winsound import PlaySound, SND_FILENAME, SND_ASYNC


class InformationOrigin(Enum):
    RANSAC = 1
    BLOB = 2
    FAILURE = 3


@dataclass
class EyeInformation:
    info_type: InformationOrigin
    x: float
    y: float
    pupil_dialation: int
    blink: bool


lowb = np.array(0)


def run_once(f):
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return f(*args, **kwargs)

    wrapper.has_run = False
    return wrapper


async def delayed_setting_change(setting, value):
    await asyncio.sleep(5)
    setting = value
    if sys.platform.startswith("win"):
        PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)


def fit_rotated_ellipse_ransac(
    data, iter=5, sample_num=10, offset=80  # 80.0, 10, 80
):  # before changing these values, please read up on the ransac algorithm
    # However if you want to change any value just know that higher iterations will make processing frames slower
    count_max = 0
    effective_sample = None

    # TODO This iteration is extremely slow.
    #
    # Either we need to keep the iteration number low, or we need to keep a worker pool specifically
    # for handling this calculation. It's parallelizable, so just throwing something like joblib at
    # it would be fine.
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
            a * np.cos(theta)**2
            + b * np.cos(theta) * np.sin(theta)
            + c * np.sin(theta)**2
        )
    )
    h = np.sqrt(
        cu
        / (
            a * np.sin(theta)**2
            - b * np.cos(theta) * np.sin(theta)
            + c * np.cos(theta)**2
        )
    )

    ellipse_model = lambda x, y: a * x**2 + b * x * y + c * y**2 + d * x + e * y + f

    error_sum = np.sum([ellipse_model(x, y) for x, y in data])

    return (cx, cy, w, h, theta)


class EyeProcessor:
    def __init__(
        self,
        config: "EyeTrackCameraConfig",
        settings: "EyeTrackSettingsConfig",
        cancellation_event: "threading.Event",
        capture_event: "threading.Event",
        capture_queue_incoming: "queue.Queue",
        image_queue_outgoing: "queue.Queue",
        eye_id,
    ):
        self.config = config
        self.settings = settings

        # Cross-thread communication management
        self.capture_queue_incoming = capture_queue_incoming
        self.image_queue_outgoing = image_queue_outgoing
        self.cancellation_event = cancellation_event
        self.capture_event = capture_event
        self.eye_id = eye_id

        # Cross algo state
        self.lkg_projected_sphere = None
        self.xc = None
        self.yc = None

        # Image state
        self.previous_image = None
        self.current_image = None
        self.current_image_gray = None
        self.current_frame_number = None
        self.current_fps = None
        self.threshold_image = None

        # Calibration Values
        self.xoff = 1
        self.yoff = 1
        # Keep large in order to recenter correctly
        self.calibration_frame_counter = None
        self.eyeoffx = 1

        self.xmax = -69420
        self.xmin = 69420
        self.ymax = -69420
        self.ymin = 69420
        self.cct = 300
        self.cccs = False
        self.ts = 10
        self.previous_rotation = self.config.rotation_angle
        self.calibration_frame_counter

        try:
            min_cutoff = float(self.settings.gui_min_cutoff)  # 0.0004
            beta = float(self.settings.gui_speed_coefficient)  # 0.9
        except:
            print('[WARN] OneEuroFilter values must be a legal number.')
            min_cutoff = 0.0004
            beta = 0.9
        noisy_point = np.array([1, 1])
        self.one_euro_filter = OneEuroFilter(
            noisy_point,
            min_cutoff=min_cutoff,
            beta=beta
        )

    def output_images_and_update(self, threshold_image, output_information: EyeInformation):
        image_stack = np.concatenate(
            (
                cv2.cvtColor(self.current_image_gray, cv2.COLOR_GRAY2BGR),
                cv2.cvtColor(threshold_image, cv2.COLOR_GRAY2BGR),
            ),
            axis=1,
        )
        self.image_queue_outgoing.put((image_stack, output_information))
        self.previous_image = self.current_image
        self.previous_rotation = self.config.rotation_angle

    def capture_crop_rotate_image(self):
        # Get our current frame
        try:
            # Get frame from capture source, crop to ROI
            self.current_image = self.current_image[
                int(self.config.roi_window_y): int(
                    self.config.roi_window_y + self.config.roi_window_h
                ),
                int(self.config.roi_window_x): int(
                    self.config.roi_window_x + self.config.roi_window_w
                ),
            ]
        except:
            # Failure to process frame, reuse previous frame.
            self.current_image = self.previous_image
            print("[ERROR] Frame capture issue detected.")

        # Apply rotation to cropped area. For any rotation area outside of the bounds of the image,
        # fill with white.
        rows, cols, _ = self.current_image.shape
        img_center = (cols / 2, rows / 2)
        rotation_matrix = cv2.getRotationMatrix2D(
            img_center, self.config.rotation_angle, 1
        )
        self.current_image = cv2.warpAffine(
            self.current_image,
            rotation_matrix,
            (cols, rows),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
        return True

    def blob_tracking_fallback(self):
        # define circle
        if self.config.gui_circular_crop:
            if self.cct == 0:
                try:
                    ht, wd = self.current_image_gray.shape[:2]

                    radius = int(float(self.lkg_projected_sphere["axes"][0]))

                    # draw filled circle in white on black background as mask
                    mask = np.zeros((ht, wd), dtype=np.uint8)
                    mask = cv2.circle(mask, (self.xc, self.yc), radius, 255, -1)
                    # create white colored background
                    color = np.full_like(self.current_image_gray, (255))
                    # apply mask to image
                    masked_img = cv2.bitwise_and(self.current_image_gray, self.current_image_gray, mask=mask)
                    # apply inverse mask to colored image
                    masked_color = cv2.bitwise_and(color, color, mask=255 - mask)
                    # combine the two masked images
                    self.current_image_gray = cv2.add(masked_img, masked_color)
                except:
                    pass
            else:
                self.cct = self.cct - 1
        _, larger_threshold = cv2.threshold(self.current_image_gray, int(self.config.threshold + 12), 255, cv2.THRESH_BINARY)
        # Blob tracking requires that we have a vague idea of where the eye may be at the moment. This
        # means we need to have had at least one successful runthrough of the Pupil Labs algorithm in
        # order to have a projected sphere.
        if self.lkg_projected_sphere == None:
            self.output_images_and_update(
                larger_threshold, EyeInformation(InformationOrigin.FAILURE, 0, 0, 0, False)
            )
            return

        try:
            # Try rebuilding our contours
            contours, _ = cv2.findContours(
                larger_threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )
            contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)
            # If we have no contours, we have nothing to blob track. Fail here.
            if len(contours) == 0:
                raise RuntimeError("No contours found for image")
        except:
            self.output_images_and_update(
                larger_threshold, EyeInformation(InformationOrigin.FAILURE, 0, 0, 0, False)
            )
            return

        rows, cols = larger_threshold.shape
        for cnt in contours:
            (x, y, w, h) = cv2.boundingRect(cnt)

            # if our blob width/height are within suitable (yet arbitrary) boundaries, call that good.
            #
            # TODO This should be scaled based on camera resolution.

            if not self.settings.gui_blob_minsize <= h <= self.settings.gui_blob_maxsize or not self.settings.gui_blob_minsize <= w <= self.settings.gui_blob_maxsize:
                continue

            cx = x + int(w / 2)

            cy = y + int(h / 2)

            xrlb = (cx - self.lkg_projected_sphere["center"][0]) / self.lkg_projected_sphere["axes"][0]
            eyeyb = (cy - self.lkg_projected_sphere["center"][1]) / self.lkg_projected_sphere["axes"][1]
            cv2.line(
                self.current_image_gray,
                (x + int(w / 2), 0),
                (x + int(w / 2), rows),
                (255, 0, 0),
                1,
            )  # visualizes eyetracking on thresh
            cv2.line(
                self.current_image_gray,
                (0, y + int(h / 2)),
                (cols, y + int(h / 2)),
                (255, 0, 0),
                1,
            )
            cv2.drawContours(self.current_image_gray, [cnt], -1, (255, 0, 0), 3)
            cv2.rectangle(
                self.current_image_gray, (x, y), (x + w, y + h), (255, 0, 0), 2
            )

            if self.calibration_frame_counter == 0:
                self.calibration_frame_counter = None
                self.xoff = cx
                self.yoff = cy
                if sys.platform.startswith("win"):
                    PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)
            elif self.calibration_frame_counter != None:
                self.settings.gui_recenter_eyes = False
                if cx > self.xmax:
                    self.xmax = cx
                if cx < self.xmin:
                    self.xmin = cx
                if cy > self.ymax:
                    self.ymax = cy
                if cy < self.ymin:
                    self.ymin = cy
                self.calibration_frame_counter -= 1
            if self.settings.gui_recenter_eyes == True:
                self.xoff = cx
                self.yoff = cy
                if self.ts == 0:
                    self.settings.gui_recenter_eyes = False
                    if sys.platform.startswith("win"):
                        PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)
                else:
                    self.ts = self.ts - 1
            else:
                self.ts = 10

            xl = float(
                (cx - self.xoff) / (self.xmax - self.xoff)
            )
            xr = float(
                (cx - self.xoff) / (self.xmin - self.xoff)
            )
            yu = float(
                (cy - self.yoff) / (self.ymin - self.yoff)
            )
            yd = float(
                (cy - self.yoff) / (self.ymax - self.yoff)
            )

            out_x = 0
            out_y = 0
            if self.settings.gui_flip_y_axis:  # check config on flipped values settings and apply accordingly
                if yd > 0:
                    out_y = max(0.0, min(1.0, yd))
                if yu > 0:
                    out_y = -abs(max(0.0, min(1.0, yu)))
            else:
                if yd > 0:
                    out_y = -abs(max(0.0, min(1.0, yd)))
                if yu > 0:
                    out_y = max(0.0, min(1.0, yu))

            if self.settings.gui_flip_x_axis_right:
                if xr > 0:
                    out_x = -abs(max(0.0, min(1.0, xr)))
                if xl > 0:
                    out_x = max(0.0, min(1.0, xl))
            else:
                if xr > 0:
                    out_x = max(0.0, min(1.0, xr))
                if xl > 0:
                    out_x = -abs(max(0.0, min(1.0, xl)))

            try:
                noisy_point = np.array([out_x, out_y])  # fliter our values with a One Euro Filter
                point_hat = self.one_euro_filter(noisy_point)
                out_x = point_hat[0]
                out_y = point_hat[1]
            except:
                pass

            self.output_images_and_update(
                larger_threshold,
                EyeInformation(InformationOrigin.BLOB, out_x, out_y, 0, False),
            )
            return
        self.output_images_and_update(
            larger_threshold, EyeInformation(InformationOrigin.BLOB, 0, 0, 0, True)
        )
        print("[INFO] BLINK Detected.")

    def run(self):
        camera_model = None
        detector_3d = None
        out_pupil_dialation = 1

        if self.eye_id == "EyeId.RIGHT":
            flipx = self.settings.gui_flip_x_axis_right
        else:
            flipx = self.settings.gui_flip_x_axis_left

        while True:
            # Check to make sure we haven't been requested to close
            if self.cancellation_event.is_set():
                print("Exiting RANSAC thread")
                return

            if self.config.roi_window_w <= 0 or self.config.roi_window_h <= 0:
                # At this point, we're waiting for the user to set up the ROI window in the GUI.
                # Sleep a bit while we wait.
                if self.cancellation_event.wait(0.1):
                    return
                continue

            # If our ROI configuration has changed, reset our model and detector
            if (camera_model is None
                or detector_3d is None
                or camera_model.resolution != (
                    self.config.roi_window_w,
                    self.config.roi_window_h,
                )
            ):
                camera_model = CameraModel(
                    focal_length=self.config.focal_length,
                    resolution=(self.config.roi_window_w, self.config.roi_window_h),
                )
                detector_3d = Detector3D(
                    camera=camera_model, long_term_mode=DetectorMode.blocking
                )

            try:
                if self.capture_queue_incoming.empty():
                    self.capture_event.set()
                # Wait a bit for images here. If we don't get one, just try again.
                (
                    self.current_image,
                    self.current_frame_number,
                    self.current_fps,
                ) = self.capture_queue_incoming.get(block=True, timeout=0.2)
            except queue.Empty:
                # print("No image available")
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
            self.current_image_gray = cv2.cvtColor(
                self.current_image, cv2.COLOR_BGR2GRAY
            )

            if self.config.gui_circular_crop == True:
                if self.cct == 0:
                    try:
                        ht, wd = self.current_image_gray.shape[:2]
                        radius = int(float(self.lkg_projected_sphere["axes"][0]))
                        self.xc = int(float(self.lkg_projected_sphere["center"][0]))
                        self.yc = int(float(self.lkg_projected_sphere["center"][1]))
                        # draw filled circle in white on black background as mask
                        mask = np.zeros((ht, wd), dtype=np.uint8)
                        mask = cv2.circle(mask, (self.xc, self.yc), radius, 255, -1)
                        # create white colored background
                        color = np.full_like(self.current_image_gray, (255))
                        # apply mask to image
                        masked_img = cv2.bitwise_and(self.current_image_gray, self.current_image_gray, mask=mask)
                        # apply inverse mask to colored image
                        masked_color = cv2.bitwise_and(color, color, mask=255 - mask)
                        # combine the two masked images
                        self.current_image_gray = cv2.add(masked_img, masked_color)
                    except:
                        pass
                else:
                    self.cct = self.cct - 1
            else:
                self.cct = 300

            _, thresh = cv2.threshold(
                self.current_image_gray,
                int(self.config.threshold),
                255,
                cv2.THRESH_BINARY,
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
            contours, _ = cv2.findContours(image, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

            # Find the convex shape based on each contour, and sort the list of them from smallest to
            # largest area.
            convex_hulls = []
            for i in range(len(contours)):
                convex_hulls.append(cv2.convexHull(contours[i], False))

            # If we have no convex maidens, we have no pupil, and can't progress from here. Dump back to
            # using blob tracking.
            if len(convex_hulls) == 0:
                if self.settings.gui_blob_fallback:
                    self.blob_tracking_fallback()
                else:
                    print("[INFO] Blob fallback disabled. Assuming blink.")
                    self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, 0, 0, 0, True))
                continue

            # Find our largest hull, which we expect will probably be the ellipse that represents the 2d
            # area for the pupil, which we can use as the search area for the eye in general.
            largest_hull = sorted(convex_hulls, key=cv2.contourArea)[-1]

            # However eyes are annoyingly three dimensional, so we need to take this ellipse and turn it
            # into a curve patch on the surface of a sphere (the eye itself). If it's not a sphere, see your
            # ophthalmologist about possible issues with astigmatism.
            try:
                cx, cy, w, h, theta = fit_rotated_ellipse_ransac(
                    largest_hull.reshape(-1, 2)
                )
            except:
                if self.settings.gui_blob_fallback:
                    self.blob_tracking_fallback()
                else:
                    print("[INFO] Blob fallback disabled. Assuming blink.")
                    self.output_images_and_update(thresh, EyeInformation(InformationOrigin.RANSAC, 0, 0, 0, True))
                continue

            # Get axis and angle of the ellipse, using pupil labs 2d algos. The next bit of code ranges
            # from somewhat to completely magic, as most of it happens in native libraries (hence passing
            # via dicts).
            result_2d = {}
            result_2d_final = {}

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
            result_3d = detector_3d.update_and_detect(
                result_2d_final, self.current_image_gray
            )

            # Now we have our pupil
            ellipse_3d = result_3d["ellipse"]
            # And our eyeball that the pupil is on the surface of
            self.lkg_projected_sphere = result_3d["projected_sphere"]

            # Record our pupil center
            exm = ellipse_3d["center"][0]
            eym = ellipse_3d["center"][1]

            d = result_3d["diameter_3d"]

            if self.calibration_frame_counter == 0:
                self.calibration_frame_counter = None
                self.xoff = cx
                self.yoff = cy
                if sys.platform.startswith("win"):
                    PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)
            elif self.calibration_frame_counter != None:  # TODO reset calibration values on button press
                if exm > self.xmax:
                    self.xmax = exm
                if exm < self.xmin:
                    self.xmin = exm
                if eym > self.ymax:
                    self.ymax = eym
                if eym < self.ymin:
                    self.ymin = eym
                self.calibration_frame_counter -= 1
            if self.settings.gui_recenter_eyes:
                self.xoff = cx
                self.yoff = cy
                if self.ts == 0:
                    self.settings.gui_recenter_eyes = False
                    if sys.platform.startswith("win"):
                        PlaySound('Audio/compleated.wav', SND_FILENAME | SND_ASYNC)
                else:
                    self.ts = self.ts - 1
            else:
                self.ts = 20

            xl = float(
                (cx - self.xoff) / (self.xmax - self.xoff)
            )
            xr = float(
                (cx - self.xoff) / (self.xmin - self.xoff)
            )
            yu = float(
                (cy - self.yoff) / (self.ymin - self.yoff)
            )
            yd = float(
                (cy - self.yoff) / (self.ymax - self.yoff)
            )

            out_x = 0
            out_y = 0

            if self.settings.gui_flip_y_axis:
                if yd > 0:
                    out_y = max(0.0, min(1.0, yd))
                if yu > 0:
                    out_y = -abs(max(0.0, min(1.0, yu)))
            else:
                if yd > 0:
                    out_y = -abs(max(0.0, min(1.0, yd)))
                if yu > 0:
                    out_y = max(0.0, min(1.0, yu))

            if flipx:
                if xr > 0:
                    out_x = -abs(max(0.0, min(1.0, xr)))
                if xl > 0:
                    out_x = max(0.0, min(1.0, xl))
            else:
                if xr > 0:
                    out_x = max(0.0, min(1.0, xr))
                if xl > 0:
                    out_x = -abs(max(0.0, min(1.0, xl)))

            try:
                noisy_point = np.array([out_x, out_y])  # fliter our values with a One Euro Filter
                point_hat = self.one_euro_filter(noisy_point)
                out_x = point_hat[0]
                out_y = point_hat[1]
            except:
                pass

            output_info = EyeInformation(InformationOrigin.RANSAC, out_x, out_y, out_pupil_dialation, False)

            # Draw our image and stack it for visual output
            try:
                cv2.drawContours(self.current_image_gray, contours, -1, (255, 0, 0), 1)
                cv2.circle(self.current_image_gray, (int(cx), int(cy)), 2, (0, 0, 255), -1)
            except:
                pass

            try:
                cv2.ellipse(
                    self.current_image_gray,
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

            try:
                # print(self.lkg_projected_sphere["angle"], self.lkg_projected_sphere["axes"], self.lkg_projected_sphere["center"])
                cv2.ellipse(
                    self.current_image_gray,
                    tuple(int(v) for v in self.lkg_projected_sphere["center"]),
                    tuple(int(v) for v in self.lkg_projected_sphere["axes"]),
                    self.lkg_projected_sphere["angle"],
                    0,
                    360,  # start/end angle for drawing
                    (0, 255, 0),  # color (BGR): red
                )
            except:
                pass

            # draw line from center of eyeball to center of pupil
            cv2.line(
                self.current_image_gray,
                tuple(int(v) for v in self.lkg_projected_sphere["center"]),
                tuple(int(v) for v in ellipse_3d["center"]),
                (0, 255, 0),  # color (BGR): red
            )

            # Shove a concatenated image out to the main GUI thread for rendering
            self.output_images_and_update(thresh, output_info)
