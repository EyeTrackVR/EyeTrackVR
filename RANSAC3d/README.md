
# use the app insted

## Installation & Setup
#

Make sure you have Python 3.6.x installed as that is the only compatible version of Python. Be sure to uninstall all other versions or correctly setup a virtual enviroment.

Open the folder in a command prompt and exicute the command: `pip install -r requirements.txt`

Once everything has installed run `RANSAC3d.py`

You will need to enter the IP address of your camera or the port (if using wired cam)

Next you will need to set a threshold. A good starting point is 80-110.

After that a window will appear where you can set a ROI (Region of Interest) 
You will need to Draw a rectangle with your mouse that selects just the area where your eye is in.

Once drawn press enter.

Once tracking has started, run `threshGUI.py`

To adjust the threshold, move the slider. 

Increase the number if a pupil is not detected.

Decrease the number if the pupil is too big.

Find the highest you can go with the best quality and close the program.



#
### The main tracking part is adapted from https://github.com/SummerSigh/TheVrMLEyeToolbox/tree/main/Pupil3dDetector

*I DO NOT OWN THE LICENSE TO THE PUPIL LABS PART OF THE CODE. Distributed under the terms of the GNU Lesser General Public License (LGPL v3.0). See COPYING and COPYING. LESSER for license details.*

Copyright (C) 2018 Pupil Labs

All Rights Reserved.

This is the Pye3d system by Pupil Labs
