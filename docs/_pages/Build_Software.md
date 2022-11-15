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

- [x] [Python 3.11.0](https://www.python.org/downloads/release/python-3110/)
- [x] [Poetry](https://python-poetry.org/)
- [x] Windows PC

## Install Python
EyetrackVR is currently using python version 3.11.0 before attempting to continue please install it. [Python 3.11.0](https://www.python.org/downloads/release/python-3110/)

## Installing Poetry

Since version 0.1.7 of EyeTrackVR we have been using Poetry to manage app dependencies, to build the app you must first install Poetry so you are able to fetch the required dependecies.

To install Poetry open windows powershell and run the following command `(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -`

[Poetry Documentation](https://python-poetry.org/docs/)


## Install the required Python modules.

After cloning the project and installing poetry open a command prompt in the eyetrack app folder and run the command: `poetry install`

This should install all of the required modules.

## Build the app.

Now, you should be ready to build the app.
With a command promt open in the EyeTrackApp folder, run the command `poetry run pyinstaller eyetrackapp.spec`

Give it time to build the app. Once done the app should be under `dist/eyetrackapp`

## Optional step:

1. Use a program like [Resource Hacker](http://www.angusj.com/resourcehacker/) to replace the .exe icon with the correct logo.
- [Here is a tutorial](https://www.howtogeek.com/75983/stupid-geek-tricks-how-to-modify-the-icon-of-an-.exe-file/)
