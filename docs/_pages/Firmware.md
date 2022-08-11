---
layout: default
title: Firmware Guide
nav_order: 9
has_children: true
permalink: /setting-up-firmware/
---

# What is this?

Firmware is the second part of the equation to get your trackers going. It lives on the ESP32 chip, and is responsible for streaming video data from the tracker.

# What should I download and where?

Current testing has been with `loucass003's` firmware [found here](https://github.com/Futurabeast/futura-face-cam).
It's tried and working although it's a bit more complicated to setup and does not fully fulfil our needs. Download and install this one, for now.

We're working on our own solution called OpenIris, [found here](https://github.com/lorow/OpenIris). So far we have:

### Working right now

- [x] Basic stream in 60FPS at 248x248px in MJPEG in greyscale
- [x] A basic HTTP server with API, which allows for better control of the stream and the camera settings
- [x] Health checks - we know when something goes wrong and we can react to it
- [x] OTA updates - we can update the firmware on the fly
- [x] ROI selection for eye area - this feature hasn't been tested all that much yet.
- [x] MDNS - so that the server itself will detect and communicate with the tracker without you doing anything.

### In development are

- [ ] Persistent storage for storing your settings on the device itself, this will also allow for saving multiple wifi networks!
- [ ] LED status patterns - so that you know what's going on without plugging the tracker in to the PC
- [ ] FEC encoding with packet injection for even faster streams!
- [ ] Better OTA so that updates can be downloaded from github and pushed by the server to the tracker
- [ ] CI/CD with github actions - so we can more seamlessly update the trackers

# How do download this?

[Follow the steps described here](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository)
