---
layout: page
title: Building the app from source
permalink: /building-the-app/
nav_order: 3
parent: Software Guide
---

## This guide will show how to build the app from source

{% include custom/alerts/Note.html content="This is NOT a required step, you do not need to build the app from source." %}

## Requirements:

- [x] [Python 3.6.8](https://www.python.org/downloads/release/python-368/)
- [x] [Pyinstaller](https://pyinstaller.org/en/stable/installation.html)
- [x] Windows PC

## Install the required Python modules.

After cloning the project open a command prompt in the eyetrack app folder and run the command: `pip install -r requirements.txt`

If you have multiple python versions installed on your machine, run the command: `py -3.6 -m pip install -r requirements.txt`
 
This should install all of the required modules.

## Build the app.

Now, you should be ready to build the app.
With a command promt open in the EyeTrackApp folder, run the command `pyinstaller eyetrackapp.spec`

Give it time to build the app. Once done the app should be under `dist/eyetrackapp`

## Additional Steps:

1. Move the `Images` and `Audio` folders from the source folder into the folder with the built .exe in it
- this will let it have an icon in the app and taskbar and allow sounds to play.

## Optional steps:

1. Use a program like [Resource Hacker](http://www.angusj.com/resourcehacker/) to replace the .exe icon with the correct logo.
- [Here is a tutorial](https://www.howtogeek.com/75983/stupid-geek-tricks-how-to-modify-the-icon-of-an-.exe-file/)