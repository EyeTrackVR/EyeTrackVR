---
layout: default
title: EyeTrackVR
nav_exclude: true
has_children: false
permalink: index.html
---

[![GitHub issues](https://img.shields.io/github/issues/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/issues) [![GitHub forks](https://img.shields.io/github/forks/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/network) [![GitHub stars](https://img.shields.io/github/stars/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/stargazers)

## Table of contents
{: .no_toc .text-delta }

* TOC
{:toc}

# EyeTrackVR
{: .no_toc }

Open source and *affordable* VR eye tracker platform for [VRChat](https://hello.vrchat.com/) via `OSC` and `UDP` protocol.

This project is in development and is not fully finished
{: .fs-5 .fw-300 }

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

> <p>
>   <span class="icon-span-warning"><svg class="octicon octicon-alert mr-2" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path fill-rule="evenodd" d="M8.22 1.754a.25.25 0 00-.44 0L1.698 13.132a.25.25 0 00.22.368h12.164a.25.25 0 00.22-.368L8.22 1.754zm-1.763-.707c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0114.082 15H1.918a1.75 1.75 0 01-1.543-2.575L6.457 1.047zM9 11a1 1 0 11-2 0 1 1 0 012 0zm-.25-5.25a.75.75 0 00-1.5 0v2.5a.75.75 0 001.5 0v-2.5z"></path></svg><b>Warning:</b></span>
> Make sure you are using **NON-focused** emitters and at around ***5ma total power***.
{: .fs-5 .fw-300 }
> </p>

<p style="page-break-after:always;"></p>

[Effect of infrared radiation on the lens](/EyeTrackVR/Reference_Docs/saftey/effect_of_ir_on_the_lens.pdf)

[Training-library Nir Stds](/EyeTrackVR/Reference_Docs/saftey/training-library_nir_stds_20021011.pdf)

[AN002_Details on photobiological safety of LED light sources](/EyeTrackVR/Reference_Docs/saftey/AN002_Details_on_photobiological_safety_of_LED_light_sources.pdf)

## Firmware

Current testing has been with `loucass003's` firmware found [here](https://github.com/Futurabeast/futura-face-cam).
There has been work for a different firmware by a community member but that ***has not been tested by me*** [here](https://github.com/lorow/OpenIris).

## Headset support

Initial support will be Quest 2 (pcvr).

Support for other headsets, comes from the community.

### Licenses

[![GitHub license](https://img.shields.io/github/license/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/blob/main/LICENSE)

***All software is under the MIT license.
All documentation, including the Wiki, is under the Creative Commons CC-BY-SA-4.0 license***.

<!-- <div align="center">
<img src="./docs/assets/images/licenses/licenses.svg" width="300" alt="Open Licenses" />
</div> -->
