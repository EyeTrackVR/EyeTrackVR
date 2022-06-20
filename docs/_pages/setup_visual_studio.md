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


## 3. Install git client

For Windows, you can download and install [Git for Windows](https://git-scm.com/download/win). If you have other OS, visit [https://git-scm.com/downloads](https://git-scm.com/downloads).

_Note: you will most likely have to click "Click here to download manually". If that doesn't work, you can try [here](https://gitforwindows.org/)._

![img](https://i.imgur.com/wam3ea1.gif)

## 4. Clone the firmware project

Make sure you close any current projects you have open or open a new window before moving forward with these steps.

1. Click the **Source Control** button, click on **Clone Repository** and enter: `https://github.com/lorow/OpenIris.git`. 
   
   If you installed git while Visual Studio Code was open you may have to close it and re-open it first.
   
   ![img](https://i.imgur.com/dBwJylD.gif)

1. Once you have chosen a download location click the **Open button** that may appear at the bottom right.
   
   ![img](https://i.imgur.com/59zXAJQ.png)

1. Click **Yes, I trust the authors**.



_This is a direct adaptation from SlimeVR Credit goes to the SlimeVR team [adapted from here](https://docs.slimevr.dev/firmware/setup-and-install.html)_
