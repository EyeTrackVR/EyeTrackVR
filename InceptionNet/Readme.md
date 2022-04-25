***This is the first working method for VR Chat***
Not perfect and a lot more work needs to be done on all aspects of this project.

**How to run**
You will fist need python 3.9.x or earlier installed

Then install the dependencies in requirements.txt

You will want to run the gui and make first 2 sliders max then re adjust the next 2 up and back to the minimum.

Now open both inferno calib and inferno and set your device stream address in the cv2.VideoCapture('[set your address here]') line

Now run the inferno calib program and follow the audio prompts to calibrate.

After you have calibrated it you can start inferno.py and watch your eyes more in vrchat

*Please note this process will change and become more streamlined in the near future.*



***This is a model implementaion form https://github.com/isohrab/Pupil-locator***

**what is this Model**

This Model is a hybrid model inspiered by YOLO, Network in Network (NiN) cnns and using YINInception as the core CNN to predict the pupil location inside the image of the eye.

**Why did you name the techique InceptionNet if thats not what its called?**

The authors of the original paper did not specifiy a name, and since its super close to InceptionNet I just named it that

**How good is this method**

In terms of easy of implementaion and accuracy its currently one of the best methods of eye tracking in this repo


This model setup comes from https://github.com/SummerSigh/TheVrMLEyeToolbox
