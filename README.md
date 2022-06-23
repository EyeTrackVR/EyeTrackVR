[![GitHub issues](https://img.shields.io/github/issues/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/issues) [![GitHub forks](https://img.shields.io/github/forks/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/network) [![GitHub stars](https://img.shields.io/github/stars/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/stargazers)

- [EyeTrackVR](#eyetrackvr)
      - [This project is in development and is not fully finished](#this-project-is-in-development-and-is-not-fully-finished)
  - [Hardware](#hardware)
  - [About IR Emitter Safety](#about-ir-emitter-safety)
        - [Make sure you are using NON-focused emmiters and at around 5ma total power](#make-sure-you-are-using-non-focused-emmiters-and-at-around-5ma-total-power)
  - [Firmware](#firmware)
  - [Headset support](#headset-support)
      - [Contact](#contact)
- [Licenses](#licenses)

### [Documentation](https://redhawk989.github.io/EyeTrackVR/)

# EyeTrackVR

Open source and *affordable* VR eye tracker platform for [VRChat](https://hello.vrchat.com/) via `OSC` and `UDP` protocol.

> **Note:** This project is in development and is not fully finished

# Check out our documentation [here](https://redhawk989.github.io/EyeTrackVR/)

## Hardware

3d files for mounting brackets will be found [here](https://github.com/RedHawk989/EyeTrackVR-Hardware)
IR emitter files are also located there.

## About IR Emitter Safety

Please *exercise extreme caution* when messing around with IR emitters.
<ins>Once safety testing has been completed links and files will be provided for the emitters</ins>. Please make sure you know what you are doing when assembling the IR emitters.
 <ins>**DO NOT BYPASS (OR NOT DO) ANY SAFETY FEATURES PUT IN PLACE**</ins>. This can result in irreversible bodily harm.
The safety measures were put in place to REDUCE the potential failure risk. All further safety responsibilities is on the user.
This includes visually checking with an IR camera that the brightness is correct and making sure you do not feel warmth.

> **Warning:** Make sure you are using **NON-focused** emitters and at around ***5ma total power***.

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

Please join our Discord for updates and any questions.

[![Discord](https://img.shields.io/badge/Discord-7289DA?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/kkXYbVykZX)

# Licenses

[![GitHub license](https://img.shields.io/github/license/RedHawk989/EyeTrackVR?style=plastic)](https://github.com/RedHawk989/EyeTrackVR/blob/master/LICENSE)

***All software is under the [MIT License](http://opensource.org/licenses/MIT).
All documentation, including the [Wiki](https://github.com/RedHawk989/EyeTrackVR/wiki), is under the Creative Commons CC-BY-SA-4.0 license***.

<!-- <div align="center">
<img src="./docs/assets/images/licenses/licenses.svg" width="300" alt="Open Licenses" />
</div> -->

[Top](#eyetrackvr)
