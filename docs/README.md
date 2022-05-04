---
layout: default
title: EyeTrackVR
nav_order: 1
has_children: false
permalink: index.html
---

[![GitHub issues](https://img.shields.io/github/issues/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/issues) [![GitHub forks](https://img.shields.io/github/forks/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/network) [![GitHub stars](https://img.shields.io/github/stars/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/stargazers)

- [EyeTrackVR](#eyetrackvr)
      - [This project is in development and is not fully finished](#this-project-is-in-development-and-is-not-fully-finished)
  - [Hardware](#hardware)
  - [About IR Emitter Safety](#about-ir-emitter-safety)
        - [Make sure you are using NON-focused emitters and at around 5ma total power](#make-sure-you-are-using-non-focused-emitters-and-at-around-5ma-total-power)
  - [Firmware](#firmware)
  - [Headset support](#headset-support)
      - [Contact](#contact)
- [Licenses](#licenses)

# EyeTrackVR

Open source and *affordable* VR eye tracker platform for [VRChat](https://hello.vrchat.com/) via `OSC` and `UDP` protocol.

#### This project is in development and is not fully finished

## Hardware

3d files for mounting brackets will be found [here](https://github.com/RedHawk989/EyeTrackVR-Hardware)
IR emitter files will also be located there.

Hardware will hopefully be a `ESP32-Cam` with a `160fov ir camera`. ***This is not confirmed and very likely could change***.

## About IR Emitter Safety

Please *exercise extreme caution* when messing around with IR emitters.
<ins>Once safety testing has been completed links and files will be provided for the emitters</ins>. Please do not try to make, or use any emitters unless you know exactly what you are doing as it could be very harmful for your eyes if not done correctly.
When files and resources are released <ins>**DO NOT BYPASS (OR NOT DO) ANY SAFETY FEATURES PUT IN PLACE**</ins>. This can result in irreversible bodily harm.
The safety measures were put in place to REDUCE the potential failure risk. All further safety responsibilities is on the user.
This includes visually checking with an IR camera that the brightness is correct.

##### Make sure you are using NON-focused emitters and at around 5ma total power

[Effect of infrared radiation on the lens](./docs/Reference_Docs/saftey/effect_of_ir_on_the_lens.pdf)

[Training-library Nir Stds](./docs/Reference_Docs/saftey/training-library_nir_stds_20021011.pdf)

[AN002_Details on photobiological safety of LED light sources](./docs/Reference_Docs/saftey/AN002_Details_on_photobiological_safety_of_LED_light_sources.pdf)

## Firmware

Current testing has been with `loucass003's` firmware found [here](https://github.com/Futurabeast/futura-face-cam).
There has been work for a different firmware by a community member but that ***has not been tested by me*** [here](https://github.com/lorow/OpenIris).

## Headset support

Initial support will be Quest 2 (pcvr)
Support for other headsets from the community.

#### Contact

Please join our discord for updates and any questions.

[![Discord](https://img.shields.io/badge/Discord-7289DA?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/kkXYbVykZX)

# Licenses

[![GitHub license](https://img.shields.io/github/license/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/blob/main/LICENSE)

***All software is under the MIT license.
All documentation, including the Wiki, is under the Creative Commons CC-BY-SA-4.0 license***.

<!-- <div align="center">
<img src="./docs/assets/images/licenses/licenses.svg" width="300" alt="Open Licenses" />
</div> -->

[Top](#eyetrackvr)
