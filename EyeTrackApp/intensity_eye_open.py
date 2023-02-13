import numpy as np
import time
import os
import cv2
from enum import IntEnum
from osc import EyeId
#higher intensity means more closed/ more white/less pupil

#Hm I need an acronym for this, any ideas?
#IBO Intensity Based Openess 
class EyeId(IntEnum):
    RIGHT = 0
    LEFT = 1
    BOTH = 2
    SETTINGS = 3

# HOW THIS WORKS: 
# we get the intensity of pupil area from HSF crop, When the eyelid starts to close, the pupil starts being obstructed by skin which is generally lighter than the pupil. 
# This causes the intensity to increase. We save all of the darkest intensities of each pupil position to calculate for pupil movement. 
# ex. when you look up there is less pupil visible, which results in an uncalculated change in intensity even though the eyelid has not moved in a meaningful way. 
# We compare the darkest intensity of that area, to the lightest (global) intensity to find the appropriate openness state via a float.


# Note.
# OpenCV on Windows will generate an error if the file path contains non-ASCII characters when using cv2.imread(), cv2.imwrite(), etc.
# https://stackoverflow.com/questions/43185605/how-do-i-read-an-image-from-a-path-with-unicode-characters
# https://github.com/opencv/opencv/issues/18305



#TODO There is a bug where eyeID is not correct which causes dual eye to fail when frame of 
# one eye is smaller than tracked cord of other eye. seems to be stuck on LEFT


lct = time.time()
data = None


def csv2data(frameshape, filepath):
    # For data checking
    frameshape = (frameshape[0], frameshape[1]+1)
    out = np.zeros(frameshape, dtype=np.uint32)
    xy_list = []
    val_list = []
    with open(filepath, mode="r", encoding="utf-8") as in_f:
        # Skip header.
        _ = in_f.readline()
        for s in in_f:
            xyval = [int(val) for val in s.strip().split(',')]
            xy_list.append((xyval[0], xyval[1]))
            val_list.append(xyval[2])
    xy_list = np.array(xy_list)
    val_list = np.array(val_list)
    out[xy_list[:, 1], xy_list[:, 0]] = val_list[:]
    return out

def data2csv(data_u32, filepath):
    # For data checking
    nonzero_index = np.nonzero(data_u32) #(row,col)
    data_list = data_u32[nonzero_index].tolist()
    datalines = ["{},{},{}\n".format(x, y, val) for y, x, val in zip(*nonzero_index, data_list)]
    with open(filepath, 'w', encoding="utf-8") as out_f:
        out_f.write("x,y,intensity\n")
        out_f.writelines(datalines)
    return


def u32_u16_1ch3ch(img):
    img_copy = img.copy()
    # In the case of bit operations. (img>>32)&0xffff,(img>>16)&0xffff,img&0xffff
    out = np.zeros((*img.shape[:2], 3), dtype=np.uint16)
    for i in range(3):
        out[:, :, i] = img_copy % 0xffff
        img_copy //= 0xffff
    return out


def u16_u32_3ch_1ch(img):
    # In the case of bit operations. ((img >> 32) & 0xffff) << 32 |((img >> 16) & 0xffff) << 16 | (img & 0xffff)
    out = np.zeros(img.shape[:2], dtype=np.uint32)
    for i in range(3):
        out += img[:, :, i] if i == 0 else img[:, :, i] * (i * 0xffff)
    return out


def newdata(frameshape):
    print("Initialise data for blinking.")
    return np.zeros(frameshape, dtype=np.uint32)


def check_and_load(frameshape, now_data, fname):
    # In the future, both eyes may be processed at the same time. Therefore, data should be passed as arguments.
    req_newdata = False
    # Not very clever, but increase the width by 1px to save the maximum value.
    frameshape = (frameshape[0], frameshape[1]+1)
    if now_data is None:
        print("Load data for blinking: {}".format(fname))
        if os.path.isfile(fname):
            img = cv2.imread(fname, flags=cv2.IMREAD_UNCHANGED)
            if img.shape[:2] != frameshape:
                print("size does not match the input frame.")
                req_newdata = True
            else:
                now_data = u16_u32_3ch_1ch(img)
        else:
            print("File does not exist.")
            req_newdata = True
    else:
        if now_data.shape != frameshape:
            # Using the previous and current frame sizes and centre positions from the original, etc., the data can be ported to some extent, but there may be many areas where code changes are required.
            print("Frame size changed.")
            req_newdata = True
    if req_newdata:
        now_data = newdata(frameshape)
    # data2csv(now_data, "a.csv")
    # csv2data(frameshape,"a.csv")
    return now_data


def intense(x, y, frame, eye_id):
    global lct, data
    e = False
    print(eye_id)
    if eye_id in [EyeId.RIGHT]:
        fname = "IBO_RIGHT.png"
        eye = "RIGHT"
    if eye_id in [EyeId.LEFT]:
        fname = "IBO_LEFT.png"
        eye = "LEFT"

    # 0 in data is used as the initial value.
    # When assigning a value, +1 is added to the value to be assigned.
    data = check_and_load(frame.shape[:2], data, fname)
    int_x, int_y = int(x), int(y)

   # upper_x = min(int_x + 25, frame.shape[1]) #TODO make this a setting
    #lower_x = max(int_x - 25, 0)
    #upper_y = min(int_y + 25, frame.shape[0])
    #lower_y = max(int_y - 25, 0)
    
    #frame_crop = frame[lower_y:upper_y, lower_x:upper_x]
    frame_crop = frame
    
    # The same can be done with cv2.integral, but since there is only one area of the rectangle for which we want to know the total value, there is no advantage in terms of computational complexity.
    intensity = frame_crop.sum()+1
    # numpy:np.sum(),ndarray.sum()
    # opencv:cv2.sumElems()
    # I don't know which is faster.
    print(frame.shape[1], frame.shape[0], int_x, int_y, eye)
    changed = False
    newval_flg = False
    if int_y >= frame.shape[0]:
      #  data_val = 1
        int_y = frame.shape[0] - 1
        e = True
        print('CAUGHT Y OUT OF BOUNDS')

    if int_x >= frame.shape[1]:
       # data_val = 1
        e = True
        int_x = frame.shape[0] - 1
        print('CAUGHT X OUT OF BOUNDS')

    #if e == False: #TODO clean this up 
        
    data_val = data[int_y, int_x]


    # max pupil per cord
    if data_val == 0:
        # The value of the specified coordinates has not yet been recorded.
        data[int_y, int_x] = intensity
        changed = True
        newval_flg = True
    elif intensity < data_val:  # if current intensity value is less (more pupil), save that
        data[int_y, int_x] = intensity  # set value
        changed = True
        print("var adjusted")
    else:
        intensitya = max(data_val - 3, 1)  # if current intensity value is less (more pupil), save that
        data[int_y, int_x] = intensitya  # set value
        changed = True

    # min pupil global
    if data[0, -1] == 0: # that value is not yet saved
        data[0, -1] = intensity # set value at 0 index
        changed = True
        print("create max", intensity)
    elif intensity > data[0, -1]:  # if current intensity value is more (less pupil), save that NOTE: we have the
        data[0, -1] = intensity  # set value at 0 index
        changed = True
        print("new max", intensity)
    else:
        intensityd = max(data[0, -1] - 10, 1) #continuously adjust closed intensity, will be set when user blink, used to allow eyes to close when lighting changes
        data[0, -1] = intensityd # set value at 0 index
        changed = True
    
    if newval_flg:
        # Do the same thing as in the original version.
        print('[INFO] Something went wrong, assuming blink.')
        eyeopen = 0.7
    else:
        maxp = data[int_y, int_x]
        minp = data[0, -1]
        diffp = minp - maxp if (minp - maxp) != 0 else 1
        eyeopen = (intensity - maxp) / diffp
        eyeopen = 1 - eyeopen
        #eyeopen = eyeopen - 0.2
        # print(intensity, maxp, minp, x, y)
        # print(f"EYEOPEN: {eyeopen}")
        # print(int(x), int(y), eyeopen, maxp, minp)

    if changed and ((time.time() - lct) > 4):  # save every 4 seconds if something changed to save disk usage
        cv2.imwrite(fname, u32_u16_1ch3ch(data))
        lct = time.time()
        print("SAVED")

    return eyeopen
