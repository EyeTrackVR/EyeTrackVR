#!/bin/sh

# This script is used to setup the environment for the build process.

# check if make is installed and if not install it
if ! command -v make &> /dev/null
then
    echo "make could not be found, installing it now"
    apt-get update
    apt-get install ffmpeg libsm6 libxext6  -y
    apt install libgl1-mesa-glx
    apt install build-essential -y --no-install-recommends
    apt-get install make
fi

# check if poetry is installed and if not install it

if ! command -v poetry &> /dev/null
then
    echo "poetry could not be found, installing it now"
    apt-get install python3-pip -y --no-install-recommends
    pip3 install poetry
fi

