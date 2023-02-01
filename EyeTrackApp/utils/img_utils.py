import cv2


def safe_crop(img, x, y, x2, y2, keepsize=True):
    # The order of the arguments can be reconsidered.
    img_h, img_w = img.shape[:2]
    outimg = img[max(0, y) : min(img_h, y2), max(0, x) : min(img_w, x2)].copy()
    reqsize_x, reqsize_y = abs(x2 - x), abs(y2 - y)
    if keepsize and outimg.shape[:2] != (reqsize_y, reqsize_x):
        # If the size is different from the expected size (smaller by the amount that is out of range)
        outimg = cv2.resize(outimg, (reqsize_x, reqsize_y))
    return outimg
