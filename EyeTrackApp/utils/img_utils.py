import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def safe_crop(img, x, y, x2, y2, keepsize=False):
    try:
        # The order of the arguments can be reconsidered.
        img_h, img_w = img.shape[:2]
        outimg = img[max(0, y) : min(img_h, y2), max(0, x) : min(img_w, x2)].copy()
        reqsize_x, reqsize_y = abs(x2 - x), abs(y2 - y)
        if keepsize and outimg.shape[:2] != (reqsize_y, reqsize_x):
            # If the size is different from the expected size (smaller by the amount that is out of range)
            outimg = cv2.resize(outimg, (reqsize_x, reqsize_y))
        return outimg
    except cv2.error as e:
        if "!ssize.empty()" in str(e):
            print("Image is None or has zero dimensions. Skipping resizing.")
        else:
            raise


def circle_crop(img, center_x, center_y, radius):
    """Mask everything outside the circle with the frame's average color.
    Caller is responsible for warmup gating (previously a frame-count
    parameter inside this helper)."""
    try:
        # Sample a 1x1 resize as a cheap average color estimate.
        small_img = cv2.resize(img, (1, 1))
        avg_color = small_img[0, 0]

        ht, wd = img.shape[:2]

        if radius < 10:  # minimum size
            radius = 10
        mask = np.zeros((ht, wd), dtype=np.uint8)
        mask = cv2.circle(mask, (center_x, center_y), radius, 255, -1)
        color = np.full_like(img, (avg_color))
        masked_img = cv2.bitwise_and(img, img, mask=mask)
        masked_color = cv2.bitwise_and(color, color, mask=255 - mask)
        return cv2.add(masked_img, masked_color)
    except cv2.error:
        return img


# Pillow's Tk bridge (PIL._tkinter_finder + the PyImagingPhoto Tcl command) is a
# separate native piece that can be absent even though `from PIL import ImageTk`
# imports fine: frozen Linux builds miss it unless it is a declared hidden
# import, and some distro Pillow packages are built without it. Every call then
# raises out of the Tk callback and the whole render tick dies, so no preview is
# ever drawn. Latch the first failure and use Tk's own PPM decoder from then on.
_imagetk_failed = False


def tk_photo_from_rgb(rgb, master):
    """RGB uint8 [H, W, 3] -> a Tk image for `master`, or None.

    Prefers PIL.ImageTk and falls back to a raw PPM handed to tkinter's own
    PhotoImage, which needs no Pillow Tk support. Bytes reach Tcl as a byte
    array, so the binary pixel data survives intact."""
    global _imagetk_failed
    import tkinter as tk

    if not _imagetk_failed:
        try:
            from PIL import Image, ImageTk

            return ImageTk.PhotoImage(Image.fromarray(rgb), master=master)
        except Exception as exc:
            _imagetk_failed = True
            logger.warning(
                "Pillow's Tk image bridge is unavailable (%s); falling back to "
                "tkinter's PPM decoder for previews.", exc,
            )

    h, w = rgb.shape[:2]
    data = b"P6 %d %d 255 " % (w, h) + np.ascontiguousarray(rgb).tobytes()
    return tk.PhotoImage(master=master, data=data, format="ppm")
