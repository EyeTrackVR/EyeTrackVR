---
layout: page
title: Setup Visual Studio Code environment
nav_order: 1
permalink: /setting-up-firmware-enviroment/
parent: Firmware Guide
---

# Setting up the environment

This procedure will show how to prepare your system for uploading the firmware to your tracker.

## 1. Install Visual Studio Code

Download the [latest Visual Studio Code](https://code.visualstudio.com/download) and install it.

### Download

![img](https://i.imgur.com/jXPXIFz.gif)

### Install

![img](https://i.imgur.com/hAm3Zu0.gif)

## 2. Install PlatformIO IDE

Once Visual Studio Code is installed, open it and install [PlatformIO IDE for VSCode](https://marketplace.visualstudio.com/items?itemName=platformio.platformio-ide), an extension that will allow you to connect to the tracker, build and upload the firmware.

![img](https://i.imgur.com/ebV0IgT.gif)


## 3. Clone the firmware project

Make sure you close any current projects you have open or open a new window before moving forward with these steps.

1. Go to [https://github.com/lorow/OpenIris](https://github.com/lorow/OpenIris) and download the code.

3. Open the firmware in VS Code by going to PlatformIO, selecting open, then navigating to OpenIris ESP folder and opening it.
   



_This is a direct adaptation from SlimeVR. Credit goes to the SlimeVR team [adapted from here](https://docs.slimevr.dev/firmware/setup-and-install.html)_
