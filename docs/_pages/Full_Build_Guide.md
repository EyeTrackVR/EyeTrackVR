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

## Step 7: Connect ESP to the programmer to flash.
Why flash before you have it assembled? It's simple, to make sure they actually work before you spend time soldering to them.

Slide your ESP into the programmer, and note the USB port goes away from the ESP's camera.
{% include custom/images/image_2.html url="https://i.imgur.com/LsLPAcd.jpg" max-width="400" caption="" alt="img" %}

## Step 8: Configure Visual Studio Code and prepare to flash the firmware.
Check out our guide on [Setting up VS Code](https://redhawk989.github.io/EyeTrackVR/setting-up-firmware-enviroment/)

Once VS Code is set up, move on to the next step.

## Step 9: Plug in your ESP and flash the firmware.
Our guide, [Building and uploading the firmware manually](https://redhawk989.github.io/EyeTrackVR/building-and-flashing-firmware-manually/) has steps on how to do this.
After it has flashed, make sure you get a video stream in your browser, then power it down and flash your next ESP.

## Step 10: Connect your power wires to a USB Type-A board.
Get two pairs of wire, preferably two different colors, Cut them to length (56mm in my case) and twist together two for ground and two for 5V.
Here I used speaker wire where the copper denotes positive and silver negative.
Then, strip the wires to about 3mm of exposed wire.
{% include custom/images/image_2.html url="https://i.imgur.com/Cdu9lSN.jpg" max-width="400" caption="" alt="img" %}

## Step 11: Cut wires for IR LEDs. 
To find the optimal length, take a piece of wire and a marker and mock up your wire route, and mark the wire, cut it, then make another at the same size for the other eye.
You will need 3 different cuts of wire. 2 short ones for connecting the 2 PCBs per eye together, 2 Longer ones for power, or ground and 2 slightly longer ones for power or ground for the LED near the camera at the bottom.

Once cut, strip them to around 4mm of exposed wire.

## Step 12: Twist the positive USB wire and positive IR LED wires together and tin them.
Once twisted together add solder to keep them together. This makes the connection much easier.
{% include custom/images/image_2.html url="https://i.imgur.com/QlRrWNn.jpg" max-width="400" caption="" alt="img" %} 

## Step 13: Solder the positive wire to ESP.
Lay the wire on the outside of the 5V pin and apply solder.
{% include custom/images/image_2.html url="https://i.imgur.com/DhnmLBG.jpg" max-width="400" caption="" alt="img" %} 

## Step 14: Solder the negative wire to ESP
Repeat [step 12](https://redhawk989.github.io/EyeTrackVR/full-build-guide/#step-12-twist-the-positive-usb-wire-and-positive-ir-led-wires-together-and-tin-them) but with the negative wires.

Now the hard part, attaching it without shorting it with nearby pins.
In the below example I put it on the top of the pin, It will be a week-ish joint but that's where glue comes in handy.
{% include custom/images/image_2.html url="https://i.imgur.com/PWA0gtq.jpg" max-width="400" caption="" alt="img" %} 

## Step 15: Wire up the 2nd ESP.
Repeat steps [12](https://redhawk989.github.io/EyeTrackVR/full-build-guide/#step-12-twist-the-positive-usb-wire-and-positive-ir-led-wires-together-and-tin-them)-[14](https://redhawk989.github.io/EyeTrackVR/full-build-guide/#step-14-solder-the-negative-wire-to-esp) with the 2nd ESP.

## Step 16: Prepare to solder IR LED PCBs.
Get your magnifying glass out, it's time to solder very smol things.

Gather 4 PCBs, 4 IR LEDs, and either 4 ~350ohm, or 2 ~700ohm resistors.

357ohm resistors and V3 PCBs
{% include custom/images/image_2.html url="https://i.imgur.com/0zXY79j.jpg" max-width="400" caption="" alt="img" %} 

698ohm resistors and V2 PCBs
{% include custom/images/image_2.html url="https://i.imgur.com/WyoVdcR.jpg" max-width="400" caption="" alt="img" %} 

Here are the PCB pin-out labels:

V2
{% include custom/images/image_2.html url="https://i.imgur.com/sNB6ju2.png" max-width="400" caption="" alt="img" %} 

V3
{% include custom/images/image_2.html url="https://i.imgur.com/n1noWKq.png" max-width="400" caption="" alt="img" %} 

LED labels:

{% include custom/images/image_2.html url="https://i.imgur.com/Ap8OAWY.png" max-width="400" caption="" alt="img" %} 
The green markings and notched corners mark the positive sides of the LEDs pictured above.

If you have different LEDs, please consult their datasheet.

Some terminology related to them:

5V: 5-volt power in.

GND: Ground or power out.

AR: After-Resistor this is to be used as the power in on the 2nd PCB in series as resistors are not needed on the 2nd PCB since they are on the 1st one.

SNG: Single resistor, use this as 5V in if you are using only 1 ~700ohm resistor on V3 boards (not recommended).

Negative: This marks the negative side of the LED.

Positive: This marks the positive side of the LED.

## Solder resistors on PCB V3.

You only need 1 PCB to have resistors per eye.

Tin the resistor pads. Note: in this example, I use too much solder, it should only be enough to lightly cover the pad.
{% include custom/images/image_2.html url="https://i.imgur.com/gb4etdB.jpg" max-width="400" caption="" alt="img" %} 


Next, grab a resistor and hold it on the pads.
{% include custom/images/image_2.html url="https://i.imgur.com/ev5QFch.jpg" max-width="400" caption="" alt="img" %} 

While holding the resistor add solder to your soldering iron and apply it to the resistor.

I like to do this by having a piece of my solder stick up in the air and then put it on my iron that way.
{% include custom/images/image_2.html url="https://i.imgur.com/8jCQOHw.jpg" max-width="400" caption="" alt="img" %} 

Flip the PCB and solder the other end.
{% include custom/images/image_2.html url="https://i.imgur.com/CHUb7Iv.jpg" max-width="400" caption="" alt="img" %} 

Now repeat for the other one. 
{% include custom/images/image_2.html url="https://i.imgur.com/jZYAm5O.jpg" max-width="400" caption="" alt="img" %} 


## Solder LEDs on PCB V3.
Tin the LED pads.
{% include custom/images/image_2.html url="https://i.imgur.com/pjvLHJL.jpg" max-width="400" caption="" alt="img" %} 

Orientate the LED and hold in place.
{% include custom/images/image_2.html url="https://i.imgur.com/RbHZQhl.jpg" max-width="400" caption="" alt="img" %} 

Solder one end.
{% include custom/images/image_2.html url="https://i.imgur.com/VyClWvp.jpg" max-width="400" caption="" alt="img" %} 

Flip areound and solder the other end.
{% include custom/images/image_2.html url="https://i.imgur.com/tFCQTqE.jpg" max-width="400" caption="" alt="img" %} 


## Solder resistors on PCB V2.

You only need 1 PCB to have a resistor per eye.

{% include custom/images/image_2.html url="https://i.imgur.com/ayQ5vkf.jpg" max-width="400" caption="" alt="img" %} 

Tin the resistor pads.
{% include custom/images/image_2.html url="https://i.imgur.com/DpFwecO.jpg" max-width="400" caption="" alt="img" %} 

Hold the resistor in place.
{% include custom/images/image_2.html url="https://i.imgur.com/50ydMrl.jpg" max-width="400" caption="" alt="img" %} 

Solder one end.
{% include custom/images/image_2.html url="https://i.imgur.com/Qq3cvxi.jpg" max-width="400" caption="" alt="img" %} 

Flip to the ther side of the resistor and solder it.
{% include custom/images/image_2.html url="https://i.imgur.com/yWGaKaC.jpg" max-width="400" caption="" alt="img" %} 


## Solder LEDs on PCB V2.

{% include custom/images/image_2.html url="https://i.imgur.com/Ql4zYCq.jpg" max-width="400" caption="" alt="img" %} 


Tin the pads
{% include custom/images/image_2.html url="https://i.imgur.com/Xrczoyv.jpg" max-width="400" caption="" alt="img" %} 

Place the resistor on the pads in the correct orientation.
{% include custom/images/image_2.html url="https://i.imgur.com/KKgP8qs.jpg" max-width="400" caption="" alt="img" %} 

Solder each side of the resistor. Be careful not to solder at too high of a temp, recommended soldering temp is 230C with a max of 245C.
{% include custom/images/image_2.html url="https://i.imgur.com/SvbHAuY.jpg" max-width="400" caption="" alt="img" %} 

## Wire up the PCBs V2.

Basic full wiring diagram of IR PCBs V2
{% include custom/images/image_2.html url="https://i.imgur.com/gopjVG3.png" max-width="500" caption="" alt="drawing" %}

The PCB that receives the 5V power is the one with the resistor. The second one, which gets its power from the ground pin of the first, does not have a resistor on it and its power input pin is the AR pin (After-Resistor). The 2nd PCBs ground pin goes to the ground of the system, in the diagram it is the ESPs ground pin.

## Wire up the PCBs V3.

{% include custom/images/image_2.html url="https://i.imgur.com/AxgHiAU.png" max-width="500" caption="" alt="drawing" %}

The PCB that receives the 5V power is the one with the resistor. The second one, which gets its power from the ground pin of the first, does not have a resistor on it and its power input pin is the AR pin (After-Resistor). The 2nd PCBs ground pin goes to the ground of the system, in the diagram it is the ESPs ground pin.
