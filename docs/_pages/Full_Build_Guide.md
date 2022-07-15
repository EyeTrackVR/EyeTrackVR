---
layout: page
title: Full Build Guide
permalink: /full-build-guide/
nav_order: 5
parent: How to build
---

## This page will contain a step-by-step assembly guide.

## Step 1: Read the [Things to know before you start](https://redhawk989.github.io/EyeTrackVR/things-to-know) guide.
This will give you a basic overview of the project's status and what to expect currently.

## Step 2: Please read the [Differences between wired and wireless setups](https://redhawk989.github.io/EyeTrackVR/Wired-VS-Wireless-Setups/) guide.
This will help you decide if wireless or wired is better. Don't want to read it? Go with wireless, USB issues make it complicated to do wired setups.

## Step 3: Order all the parts listed on our [Parts list](https://redhawk989.github.io/EyeTrackVR/partslist/)
Please take note of the fact that hardware still may change, although with more developments it seems like we are going to stick with current hardware.

## Step 4: Wait for things to arrive.
Long shipping times from China are  *f u n*.
Please allow from 3 weeks to 2 months for everything to arrive.

## Step 5: Gather up all of your hardware.

Make sure you have the following:

- [x] 2 ESP 32 CAM boards
- [x] 2 160 degree cameras
- [x] 1 USB board to power your ESPs
- [x] 1 Programmer board
- [x] IR emitters, resistors, and preferably PCBs
- [x] Lower gauge wire to power ESPs (I use spare 24 AWG speaker wire)
- [x] Higher gauge wire to power IR LEDs
- [x] 3d printer to print mounts.
- [x] Glue of some form, hot glue highly recommended.

{% include custom/images/image_2.html url="https://i.imgur.com/j18rRI7.jpg" max-width="400" caption="ESPs, cams, a programmer and a USB connector" alt="img of components" %}





## Step 6: Attach cameras to ESPs.

Look at your ESP and locate the camera ribbon cable connector as circled below.
{% include custom/images/image_2.html url="https://i.imgur.com/T5asLGN.jpg" max-width="400" caption="" alt="img" %}

Flip the gray part up to allow the cameras to be connected. Do not force it, or shove objects into it to open, fingernails are fine.
{% include custom/images/image_2.html url="https://i.imgur.com/Z8b8Sin.jpg" max-width="400" caption="" alt="img" %}

Now slide in a camera, please note that the pins are facing down, you should only see the black part.
{% include custom/images/image_2.html url="https://i.imgur.com/dDBIi9j.jpg" max-width="400" caption="" alt="img" %}

Once the camera has been slid in, press the gray part of the connector back down. There will be a small amount of force but still be gentle.
Note the ammount of black coming out of the connector.
{% include custom/images/image_2.html url="https://i.imgur.com/VnFi5XS.jpg" max-width="400" caption="" alt="img" %}

## Step 7: Connect ESP to programmer to flash.
Why flash before you have it assembled? It's simple, to make sure they actually work before you spend time soldering to it.

Slide your ESP into the programmer, note the USB port goes away from the ESP's camera.
{% include custom/images/image_2.html url="https://i.imgur.com/LsLPAcd.jpg" max-width="400" caption="" alt="img" %}

## Step 8: Configure Visual Studio Code and prepare to flash the firmware.
Check out out guide on [Setting up VS Code](https://redhawk989.github.io/EyeTrackVR/setting-up-firmware-enviroment/)

Once VS Code is setup, move onto the next step.

## Step 9: Plug in your ESP and flash firmware.
Our guide, [Building and uploading the firmware manually](https://redhawk989.github.io/EyeTrackVR/building-and-flashing-firmware-manually/) has steps on how to do this.
After it has flashed, make sure you get a video stream in your browser, then flash your next ESP.

## Step 10: Connect your power wires to a USB Type A board.
Get two pairs of wire, perferably two different colors, Cut them to length (56mm in my case) and twist together two for ground and two for 5V.
Here I used speaker wire where the copper denotes positive and silver negitive.
{% include custom/images/image_2.html url="https://i.imgur.com/Cdu9lSN.jpg" max-width="400" caption="" alt="img" %}

## Step 11: 
