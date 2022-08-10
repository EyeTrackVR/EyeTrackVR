---
layout: default
title: Software Guide
nav_order: 10
has_children: false
permalink: /software-guide/
---

# How to install, run and adjust the EyeTrackVR app.
{% include custom/alerts/Note.html content="This will only cover the dual eye program, most things will transfer to the single eye app." %}

### Step 1: Download the EyeTrackVR Installer and install the EyeTrackVR app.

Go to the latest [GitHub release here](https://github.com/RedHawk989/EyeTrackVR-Installer/releases/tag/EyeTrackVR-Installer-0.2.1) and download the .zip

Extract the zip file and then run the .exe as administrator.
You will be greeted with a window that looks like this:
{% include custom/images/image_2.html url="https://i.imgur.com/olwRFYI.png" max-width="500" caption="" alt="" %}

By default, it will install to `C:\Program Files\EyeTrackVR` and create a shortcut on your desktop.
Pressing the `Change Install Path` button will open up a window where you can navigate to an alternate install path.

Press `Install` to install the app. 
{% include custom/alerts/Note.html content=" The installer can also be used to update the app, just go through the install process again." %}

If it has been successfully installed it should change to look like this:
{% include custom/images/image_2.html url="https://i.imgur.com/Ugzzgbh.png" max-width="500" caption="" alt="" %}

## Step 2: Run the EyeTrackVR app.

If the `Create Desktop Shortcut` option was checked you should see an icon on your desktop, double click it to run.

You then should be greeted with a GUI that looks like this:
{% include custom/images/image_2.html url="https://i.imgur.com/oId9CUk.png" max-width="500" caption="" alt="" %}

## Step 3: Getting familiar with settings and terminology.

Let's go over some basic terminology you will find in the app.

Starting from the top:

### `Right eye`: 
Shows the right eye feed and settings only.

###  `Left eye`: 
Shows the left eye feed and settings only.

### `Both eyes`: 
Shows both eyes' feed and settings.

### `Camera Address`:
This is where you enter the IP address of your camera.
Alternatively, it can be used to put the cam number for wired cameras or pass in a video file.

### `Tracking Mode`: 
This changes the GUI to the tracking mode where it outputs values.

### `ROI Mode`: 
ROI or Region of Intrest is where you will crop out your eye. 
We will go more in-depth on how to do this later.

### `Threshold`: 
This is used to cut out things that aren't dark like your pupil.
We will go more into depth on how to properly adjust this later.

### `Rotation`: 
For our method to work best, you want your eye to be level. 
Use this slider to adjust it to where that is the case.

### `Eye Position Scalar`: 
This is a form of multiplier for OSC output.
Increase it if when looking in all directions moves the eye not enough, if it works fine, leave it at default.

### `Restart Calibrationn`: 
This will start a calibration mode for your eye where you look to all extremes.

### `Recenter Eye`: 
This will recenter your eye to whatever point you are looking at.

### `Show color Image`
Shows Color feed from camera source. Will be removed in a future version.

## Step 4: Adding your cameras to the software and configuring them.
Power your ESPs and find what the IP address is for your right eye. This can be done by opening both Cameras in a browser and then holding your finger over your right eye camera. 

Copy that IP address and then close the browser tab with it open.

Enter that IP address into the app's `Camera Address` field and press the `Save and Restart Tracking` button.

Don't see your camera feed? That's because we haven't set an ROI.

{% include custom/images/image_2.html url="https://i.imgur.com/PKkjw9s.png" max-width="500" caption="See the Awating ROI SettingS text?" alt="" %}

Now press the `ROI Mode` button.
You should see a feed of your camera.

Put your headset on and use an application to see your desktop. (Virtual desktop, SteamVR desktop, etc.)

You should see something like this:
{% include custom/images/image_2.html url="https://i.imgur.com/1ksGmGU.png" max-width="500" caption=":O It's my eye!" alt="" %}

Now, Draw a rectangle that selects your eye.

A good example of an ROI
{% include custom/images/image_2.html url="https://i.imgur.com/iw7o0VT.png" max-width="500" caption=":O It's my eye!" alt="" %}

Head back over to the `Tracking mode`.

We will now adjust our rotation by moving the `Rotation` slider.

From this:
{% include custom/images/image_2.html url="https://i.imgur.com/xXTB3sM.png" max-width="500" caption="It's crooked!" alt="" %}

To this:
{% include custom/images/image_2.html url="https://i.imgur.com/blsrpCX.png" max-width="500" caption="Much better" alt="" %}

Now we will adjust our threshold.

Continuing with your headset on, move the slider all the way up.
start slowly backing it off until mainly only your pupil is being visualized in the threshold viewer.

Example of a threshold being too low:
{% include custom/images/image_2.html url="https://i.imgur.com/30fFadH.png" max-width="500" caption="Where is my entire pupil?" alt="" %}

Example of too high of a threshold:
{% include custom/images/image_2.html url="https://i.imgur.com/ZjpKfCV.png" max-width="500" caption="Woah what's all that junk? notice how my cornea is also being picked up, that's not good." alt="" %}

Example of a good or correct threshold:
{% include custom/images/image_2.html url="https://i.imgur.com/KPUn8S1.png" max-width="500" caption="" alt="" %}
