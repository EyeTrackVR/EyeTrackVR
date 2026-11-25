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

# Pinned uv, checked against the SHA-256 published with the release, instead of piping
# astral.sh's latest installer into sh. An existing uv of any other version is replaced.
# To update: bump UV_VERSION and UV_SHA256 together (the release's
# uv-x86_64-unknown-linux-gnu.tar.gz.sha256 file), and check the new uv still knows
# ETVR_PYTHON (`uv python list cpython-3.14.9 --all-platforms --all-arches`).
UV_VERSION="0.13.7"
UV_SHA256="c5221ff41b7892bfc223543883600125f6a47fe845093e0f5bdff4f359196d83"
# The exact interpreter build: uv would otherwise take the newest 3.14 it knows, and on a
# newer CPU it can pick an x86_64_v3 build the bundle's users may not be able to run.
# Same CPython build as the Steam Frame release (packaging/steamframe/install_python.sh).
# Keep in sync with ETVR_PYTHON in build.sh.
ETVR_PYTHON="cpython-3.14.9-linux-x86_64-gnu"

if [ "$(uname -m)" != "x86_64" ]; then
    echo "ERROR: the Linux release is built on x86_64 (got $(uname -m))" >&2
    exit 1
fi

if [ "$(uv --version 2>/dev/null | awk '{print $2}')" != "$UV_VERSION" ]; then
    echo "[provision] installing uv $UV_VERSION..."
    UV_TMP="$(mktemp -d)"
    curl -fsSL -o "$UV_TMP/uv.tar.gz" \
        "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz"
    echo "$UV_SHA256  $UV_TMP/uv.tar.gz" | sha256sum -c --quiet -
    tar -xzf "$UV_TMP/uv.tar.gz" -C "$UV_TMP"
    mkdir -p /root/.local/bin
    install -m 0755 "$UV_TMP/uv-x86_64-unknown-linux-gnu/uv" "$UV_TMP/uv-x86_64-unknown-linux-gnu/uvx" /root/.local/bin/
    rm -rf -- "${UV_TMP:?}"
    hash -r
fi

echo "[provision] ensuring Python ($ETVR_PYTHON)..."
uv python install "$ETVR_PYTHON"

uv --version
uv run --managed-python --python "$ETVR_PYTHON" --no-project python -c 'import sys; print("python", sys.version)'
echo "PROVISION_DONE"
