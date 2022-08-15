---
layout: page
title: Part List
permalink: /partslist/
nav_order: 2
parent: How to build
---

## This page will include a basic part list for building an EyeTrackVR setup

{% include custom/alerts/Warning.html content="Please note that no hardware has been fully set in stone, all purchases are at your loss if hardware changes" %}

{% include custom/alerts/Note.html content="It is recommended to source parts from AliExpress as it is much cheaper" %}

## Camera setup

- 2x ESP-CAM-32 modules [AliExpress here](https://a.aliexpress.com/_mKjL9Cq)

- 2x ov2640 160° fov IR / Night vers 75mm (850nm) [AliExpress here](https://a.aliexpress.com/_mrNbZww)

- 1x ESP-CAM programmer/ MB [AliExpress here](https://a.aliexpress.com/_mPaPgPu)

Here is an amazon link for 3 ESP32-Cams and programmers without the proper cameras [here](https://www.amazon.com/ESP32-CAM-ESP32-CAM-MB-Development-Compatible-Raspberry/dp/B097H2KLCH?crid=1A1UYKT1Z3MZ6&keywords=espcam32&qid=1656094793&sprefix=espca,aps,114&sr=8-3&linkCode=sl1&tag=alexanderbead-20&linkId=fa7595a5963c6260fd05d3dca6d8d9f7&language=en_US&ref_=as_li_ss_tl)

- 1x USB type-A male port to power both ESPs

[Bare breakout on AliExpress here](https://www.aliexpress.com/item/2255801092919590.html?spm=a2g0o.productlist.0.0.33fa704cNwXXlG&algo_pvid=6e43e022-3366-4beb-865b-2efb26b09c31&algo_exp_id=6e43e022-3366-4beb-865b-2efb26b09c31-2&pdp_ext_f=%7B%22sku_id%22%3A%2210000015583716962%22%7D&pdp_npi=2%40dis%21USD%210.63%210.57%21%21%21%21%21%40210318cb16603411009925346e6d32%2110000015583716962%21sea&curPageLogUid=1jn4Kch58pW5)

[Or one with a cover on AliExpress here](https://www.aliexpress.com/item/2251832820552545.html?spm=a2g0o.productlist.0.0.24906d82STgtT2&algo_pvid=215ca169-e724-4aef-8cd4-597ceeb899f2&algo_exp_id=215ca169-e724-4aef-8cd4-597ceeb899f2-0&pdp_ext_f=%7B%22sku_id%22%3A%2267040749896%22%7D&pdp_npi=2%40dis%21USD%211.14%211.13%21%21%21%21%21%402101d64d16603413470056035e536c%2167040749896%21sea&curPageLogUid=ziYPxg6un38w)

[Or this one for more plug and play power](https://es.aliexpress.com/item/3256802826910871.html?spm=a2g0o.productlist.0.0.592c2d4fAXThal&algo_pvid=41a349ba-5582-4aff-9eed-70745cad6f1a&algo_exp_id=41a349ba-5582-4aff-9eed-70745cad6f1a-0&pdp_ext_f=%7B%22sku_id%22%3A%2212000023231721054%22%7D&pdp_npi=2%40dis%21USD%211.92%211.8%21%21%21%21%21%40210318d116603418291097152e829e%2112000023231721054%21sea&curPageLogUid=V05SfF2D6xcN)

{% include custom/alerts/Note.html content=" Note that with the above cable if you use the connectors included you will need 1 USB per ESP and another for the IR emitters. I would recommend not using the connectors because you would be using more USB ports than necessary. Also, note that data is not used so I would not get the variant with data cables. " %}


- 1x Lower gauge wire to power ESPs
[28 gauge wire from AliExpress here](https://a.aliexpress.com/_mK72cy6)



## IR Emitters

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

I have a kit with the resistors, IR LEDs, and PCBs on [Tindie here.](https://www.tindie.com/products/eyetrackvr/eyetrackvr-ir-emitter-kit-pack-of-5/) 
This ensures you get the correct IR emitter parts.

- 1x Wire to power IR emitters
[32 gauge wire from AliExpress here](https://a.aliexpress.com/_mK72cy6)



## Other parts

- 1x Hot glue or another form of glue

- 1x Soldering iron and solder (lead free solder highly recommended)


{% include custom/3d_printed_parts/Parts.html %}

### Other Headsets

If you own another headset not listed above, that means there are no mounts designed for them yet. If you have basic skills in modeling or think up a solution to mount cams and emitters, please try to make a mount and then let us in the discord know so it can be added here. Any headset that can fit the camera is potentially compatible. If you are willing, give it a shot to design a mount for the rest of the community.

{% include custom/alerts/Tip.html content="If you have a headset that is not listed above, please let us know in the discord so it can be added here" %}
