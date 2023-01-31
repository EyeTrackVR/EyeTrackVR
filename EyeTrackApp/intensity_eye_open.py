import pandas as pd
import numpy as np
import time

from enum import IntEnum
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


if EyeId.RIGHT:
    fname = "IBO_RIGHT.csv"
if EyeId.LEFT:
    fname = "IBO_LEFT.csv"

lct = time.time()

try:
    data = pd.read_csv(fname, sep=",")
except:
    cf = open(fname, "w")
    cf.write("xy,intensity")
    cf.close()
    data = pd.read_csv(fname, sep=",")

#TODO we need more pixel points for smooth operation, lets get this setup in hsrac

def intense(x, y, frame):
    global lct

    upper_x = int(x) + 25 #TODO make this a setting
    lower_x = int(x) - 25
    upper_y = int(y) + 25
    lower_y = int(y) - 25
    frame = frame[lower_y:upper_y, lower_x:upper_x]

    print(x, y, int(x), int(y), upper_x, upper_y, lower_x, lower_y)
    try:
        xy = int(str(int(x)) + str(int(y)) + str(int(x)+int(y)))
        intensity = np.sum(frame) #why is this outputting 0s?
       # print(intensity, upper_x, upper_y, lower_x, lower_y)
    except:
        return 0.0 #TODO find how on earth a hyphen gets thrown into this

    changed = False
    try: #max pupil per cord
        dfb = data[data['xy']==xy].index.values.astype(int)[0] # find pandas index of line with matching xy value

        if intensity < data.at[dfb, 'intensity']: #if current intensity value is less (more pupil), save that
            data.at[dfb, 'intensity'] = intensity # set value
            changed = True
            print("var adjusted")
        
        else: 
            intensitya = data.at[dfb, 'intensity'] - 3 #if current intensity value is less (more pupil), save that
            data.at[dfb, 'intensity'] = intensitya # set value
            changed = True

    except: # that value is not yet saved
        data.loc[len(data.index)] = [xy, intensity] #create new data on last line of csv with current intesity
        changed = True

    try: # min pupil global
        if intensity > data.at[0, 'intensity']: #if current intensity value is more (less pupil), save that NOTE: we have the 
            data.at[0, 'intensity'] = intensity # set value at 0 index
            changed = True
            print("new max", intensity)

        else:
            intensityd = data.at[0, 'intensity'] - 10 #continuously adjust closed intensity, will be set when user blink, used to allow eyes to close when lighting changes
            data.at[0, 'intensity'] = intensityd # set value at 0 index
            changed = True
            
    except: # there is no max intensity yet, create
        data.at[0, 'intensity'] = intensity # set value at 0 index
        changed = True
        print("create max", intensity)
    try:
        maxp = data.at[dfb, 'intensity']
        minp = data.at[0, 'intensity']
        #eyeopen = (intensity - minp) / (maxp - minp)
        eyeopen = (intensity - maxp) / (minp - maxp)
        eyeopen = 1 - eyeopen
        eyeopen = eyeopen - 0.2
       # print(intensity, maxp, minp, x, y)
      #  print(f"EYEOPEN: {eyeopen}")
     #   print(int(x), int(y), eyeopen, maxp, minp)

    except:
        print('[INFO] Something went wrong, assuming blink.')
        eyeopen = 0.0
    if changed == True and ((time.time() - lct) > 4): #save every 4 seconds if something changed to save disk usage
        data.to_csv(fname, encoding='utf-8', index=False) #save file since we made a change
        lct = time.time()
        print("SAVED")


    return eyeopen
