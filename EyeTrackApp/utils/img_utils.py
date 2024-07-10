import cv2
import numpy as np

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
        if '!ssize.empty()' in str(e):
            print("Image is None or has zero dimensions. Skipping resizing.")
        else:
            raise

def circle_crop(img, xc, yc, radius, cct):

    avg_color_per_row = np.average(img, axis=0)
    avg_color = np.average(avg_color_per_row, axis=0)
    if cct <= 0:
        try:
            ht, wd = img.shape[:2]

            if radius < 10: #minimum size
                radius = 10
            # draw filled circle in white on black background as mask
            mask = np.zeros((ht, wd), dtype=np.uint8)
            mask = cv2.circle(mask, (xc, yc), radius, 255, -1)
            # create white colored background
            color = np.full_like(img, (avg_color))
            # apply mask to image
            masked_img = cv2.bitwise_and(img, img, mask=mask)
            # apply inverse mask to colored image
            masked_color = cv2.bitwise_and(color, color, mask=255 - mask)
            # combine the two masked images
            outimg = cv2.add(masked_img, masked_color)
            return outimg, cct
        except:
            return img, cct
            pass
    else:
        cct = cct - 1
        return img, cct
