#!/usr/bin/env bash
# Provision the WSL Ubuntu build environment for EyeTrackVR Linux release builds.
# Idempotent: safe to run on every build; fast no-op when already provisioned.
# Run as root inside the distro:  wsl -d Ubuntu-22.04 -u root bash wsl_provision.sh
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export PATH="/root/.local/bin:$PATH"

MARKER=/opt/etvr-build/.provisioned-v5

if [ ! -f "$MARKER" ]; then
    echo "[provision] installing system packages..."
    apt-get update -qq
    # binutils: required by PyInstaller (objdump/objcopy)
    # libgl1/libglib2.0-0: required to import cv2 during PyInstaller analysis
    # file: used by PyInstaller to classify binaries
    # build-essential/cmake/eigen: pye3d has no Linux wheel for Python 3.14 and
    # compiles its C++ extension (which links Eigen3) from source during
    # dependency install.
    # libsm6/libice6/libtbb12: runtime deps of cv2's Qt plugin and numba's tbb
    # pool. Present at build time -> PyInstaller bundles them -> end users on
    # any distro don't need them preinstalled.
    apt-get install -y -qq curl git binutils file rsync libgl1 libglib2.0-0 \
        build-essential cmake ninja-build libeigen3-dev \
        libsm6 libice6 libtbb12 >/dev/null
    mkdir -p /opt/etvr-build
    touch "$MARKER"
else
    echo "[provision] system packages already installed"
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "[provision] installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
fi

echo "[provision] ensuring Python 3.14 toolchain..."
uv python install 3.14

uv --version
uv run --python 3.14 --no-project python -c 'import sys; print("python", sys.version)'
echo "PROVISION_DONE"
