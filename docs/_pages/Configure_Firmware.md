---
layout: page
title: Configuring firmware
permalink: /configure-firmware/
nav_order: 2
parent: Firmware Guide
---


## Once you have opened the project, you should see something on the left side like this.

{% include custom/images/image_2.html url="https://i.imgur.com/VZeI39I.png" max-width="500" caption="" alt="" %}


## Open the `platformio.ini` file.
{% include custom/images/image_2.html url="https://i.imgur.com/ySzUMPO.png" max-width="500" caption="" alt="" %}

On lines 17 and 18 replace the placeholder text with your correct SSID (WiFi access point name), and password respectfully.

{% include custom/alerts/Note.html content="Make sure your wifi router has a 2.4 GHz band. While most do, this is not always the case. Setting each band, (5GHz, and 2.4GHz) to different SSIDs is recommended though not required." %}

Double check that you have correctly entered your WiFi credentials and that said wifi network has a 2.4GHz band.

## [Now, move on to uploading the firmware](https://redhawk989.github.io/EyeTrackVR/building-and-flashing-firmware-manually/)
