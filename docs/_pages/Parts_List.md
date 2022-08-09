---
layout: page
title: Part List
permalink: /partslist/
nav_order: 3
parent: How to build
---

## This page will include a basic part list for building an EyeTrackVR setup

{% include custom/alerts/Warning.html content="Please note that no hardware has been fully set in stone, all purchases are at your loss if hardware changes" %}

{% include custom/alerts/Note.html content="It is recommended to source parts from AliExpress as it is much cheaper" %}

## Wireless setup

- 2x ESP-CAM-32 modules [AliExpress here](https://a.aliexpress.com/_mKjL9Cq)

- 2x ov2640 160° fov IR / Night vers 75mm (850nm) [AliExpress here](https://a.aliexpress.com/_mrNbZww)

- 1x ESP-CAM programmer/ MB [AliExpress here](https://a.aliexpress.com/_mPaPgPu)

Here is an amazon link for 3 esps and programmers without the proper cameras [here](https://www.amazon.com/ESP32-CAM-ESP32-CAM-MB-Development-Compatible-Raspberry/dp/B097H2KLCH?crid=1A1UYKT1Z3MZ6&keywords=espcam32&qid=1656094793&sprefix=espca,aps,114&sr=8-3&linkCode=sl1&tag=alexanderbead-20&linkId=fa7595a5963c6260fd05d3dca6d8d9f7&language=en_US&ref_=as_li_ss_tl)

- 1x USB type-A male port to power both ESPs
[AliExpress here](https://a.aliexpress.com/_mOCRTcq)

- 1x Lower gauge wire to power ESPs
[28 gauge wire from AliExpress here](https://a.aliexpress.com/_mK72cy6)

## Wired setup

{% include custom/alerts/Warning.html content="Due to USB issues, only 1 camera per headset is supported unless you have 2 seperate USB ports to plug in to. USB hubs WILL NOT WORK." %}

- 2x Wired Ov5640 160 deg cameras [AliExpress here](https://www.aliexpress.com/item/2255799933896897.html)

{% include custom/alerts/Note.html content="if the wired option is used, you will need to disassemble the camera to remove the ir filters.
I would recommend getting extra cameras, either the full thing above or just the camera" hyper_link="https://www.aliexpress.com/item/3256803544318475.html" description="from AliExpress here" %}

- 1x USB type-A male port to power both IR emitters
[AliExpress here](https://a.aliexpress.com/_mOCRTcq)

## IR Emitters
#### Needed for both wireless and wired options.

- 4x Unfocused SMD IR emitters
Recomended ones [from LCSC here](https://www.lcsc.com/product-detail/Infrared-IR-LEDs_XINGLIGHT-XL-3216HIRC-850_C965891.html).
Alternative ones [from Digikey here](https://www.digikey.com/en/products/detail/inolux/IN-P32ZTIR/10384796). The difference between them is the ones from LCSC are rated for lower power, this means in the event of a short or misshap they should be safer, hence why they are recomended. 
{% include custom/alerts/Note.html content="The smaller ones can not be soldered at temps above 245C or they will burn. Low temp solder is recomended" %}

{% include custom/alerts/Warning.html content="(DO NOT BUY FOCUSED ONES! If they look like something you would find in a TV remote do not use them, if you aren't exactly sure what you are doing, buy them from the LCSC or Digikey link)" %}


- 4x IR emitter PCB's (highly recommended) 

- 2x 698-710ohm resistors or the more recommend way, 4x 350ohm 1206 SMD resistors for IR emitters (If you are not using PCB's for the emitters then buying regular  through-hole resistors is acceptable)
  
- [357 ohm from Digikey here](https://www.digikey.com/en/products/detail/stackpole-electronics-inc/RMCF1206FT357R/1759919)

or

- [698 ohm from LCSC here](https://lcsc.com/product-detail/Chip-Resistor-Surface-Mount_FOJAN-FRC1206F6980TS_C2933749.html)

- 1x Wire to power IR emitters
[32 gauge wire from AliExpress here](https://a.aliexpress.com/_mK72cy6)

I have a kit with resistors, IR LEDs, and PCBs on [Tindie here.](https://www.tindie.com/products/eyetrackvr/eyetrackvr-ir-emitter-kit-pack-of-5/)

## Other parts

- 1x Hot glue or another form of glue

- 1x Soldering iron and solder (lead free solder highly recommended)

## 3d Printed Parts

{% include custom/3d_printed_parts/Parts.html %}

### Other Headsets

If you own another headset not listed above, that means there are no mounts designed for them yet. If you have basic skills in modeling or think up a solution to mount cams and emitters, please try to make a mount and then let us in the discord know so it can be added here. Any headset that can fit the camera is potentially compatible. If you are willing, give it a shot to design a mount for the rest of the community.

{% include custom/alerts/Tip.html content="If you have a headset that is not listed above, please let us know in the discord so it can be added here" %}
