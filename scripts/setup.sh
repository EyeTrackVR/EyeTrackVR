#!/usr/bin/env bash
# Set up a Debian/Ubuntu machine to run EyeTrackVR from source.
# (Arch equivalents: base-devel cmake ninja eigen tk libglvnd glib2 libsm libice)
#
#   sudo bash scripts/setup.sh
#   poetry install
#   cd eyetrackapp && poetry run python eyetrackapp.py
#
# Python: the project targets Python ~3.14. If your distro doesn't ship it,
# the easiest routes are `uv python install 3.14` (https://astral.sh/uv) or the
# deadsnakes PPA (python3.14 python3.14-tk python3.14-dev).
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
    echo "Non-apt distro: install the equivalents of the package list in this script." >&2
    exit 1
fi

apt-get update
# Toolchain: pye3d has no Linux wheel for Python 3.14 and compiles its C++
# extension (needs a compiler, CMake, and Eigen3 headers) during install.
apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build libeigen3-dev
# Runtime libraries: OpenCV (libgl/glib/sm/ice/xext) and desktop niceties.
apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libice6 libxext6 libnotify-bin

if ! command -v poetry >/dev/null 2>&1; then
    echo "poetry could not be found, installing it now"
    apt-get install -y --no-install-recommends python3-pip
    pip3 install poetry
fi

echo "OK. Next: poetry install && cd eyetrackapp && poetry run python eyetrackapp.py"
