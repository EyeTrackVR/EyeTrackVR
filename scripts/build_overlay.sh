#!/usr/bin/env bash
# Build the calibration overlay from the overlay/ submodule for this machine's
# architecture and copy it into the app:
#   x86_64  -> EyeTrackApp/Tools/linux/        (Ubuntu 22.04, glibc 2.35)
#   aarch64 -> EyeTrackApp/Tools/linux-arm64/  (Ubuntu 24.04, Steam Frame)
#
#   bash scripts/build_overlay.sh [repo-root]
#
# Needs: build-essential cmake ninja-build libvulkan-dev libopenxr-dev
#        libstb-dev patchelf git curl
# scripts/build_overlay.bat runs this in WSL and in an arm64 Docker container.
#
# Builds from a clean export of the pinned commit on the native filesystem, so
# a Windows checkout's CRLF line endings and /mnt/c speed don't matter. Writes
# OVERLAY_COMMIT next to the binaries; tests/test_overlay_submodule.py checks
# it against the submodule.
set -euo pipefail

REPO_ROOT="$(cd "${1:-$(dirname "${BASH_SOURCE[0]}")/..}" && pwd)"
OVERLAY="$REPO_ROOT/overlay"
GIT=(git -c safe.directory='*' -c core.autocrlf=false)

case "$(uname -m)" in
    x86_64) TARGET="linux" ;;
    aarch64 | arm64) TARGET="linux-arm64" ;;
    *) echo "ERROR: unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac
DEST="$REPO_ROOT/EyeTrackApp/Tools/$TARGET"

# OpenVR SDK matching the app's pyopenvr 2.12 bindings. The overlay repo's
# older SDK build looks for its path registry in /data/work on aarch64 and so
# can't find SteamVR on a Steam Frame (see Tools/linux-arm64/README.txt).
OPENVR_TAG="v2.12.14"
OPENVR_ARM64_SHA256="7fcdc649e5371c60530080c7ed3daef978daefd97304e1ff45b312aa344b3e76"

test -f "$OVERLAY/CMakeLists.txt" || { echo "ERROR: overlay/ is empty; run: git submodule update --init overlay" >&2; exit 1; }
COMMIT="$("${GIT[@]}" -C "$OVERLAY" rev-parse HEAD)"
if [ ! -f "$OVERLAY/external/OpenVR/headers/openvr.h" ]; then
    echo "[overlay] fetching the overlay's OpenVR SDK submodule..."
    "${GIT[@]}" -C "$OVERLAY" submodule update --init --depth 1 external/OpenVR
fi

BUILD_ROOT="${ETVR_OVERLAY_BUILD:-$HOME/etvr-overlay-build}"
echo "[overlay] exporting $COMMIT to $BUILD_ROOT..."
rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT/external/OpenVR"
"${GIT[@]}" -C "$OVERLAY" archive HEAD | tar -x -C "$BUILD_ROOT"
"${GIT[@]}" -C "$OVERLAY/external/OpenVR" archive HEAD headers lib/linux64 lib/linuxarm64 LICENSE \
    | tar -x -C "$BUILD_ROOT/external/OpenVR"

echo "[overlay] building for $TARGET..."
bash "$BUILD_ROOT/build-linux.sh"
PACKAGE="$BUILD_ROOT/build-linux/package"

if [ "$TARGET" = "linux-arm64" ]; then
    echo "[overlay] replacing libopenvr_api.so with OpenVR $OPENVR_TAG..."
    curl -fsSL -o "$PACKAGE/libopenvr_api.so" \
        "https://raw.githubusercontent.com/ValveSoftware/openvr/$OPENVR_TAG/bin/linuxarm64/libopenvr_api.so"
    echo "$OPENVR_ARM64_SHA256  $PACKAGE/libopenvr_api.so" | sha256sum -c -
fi

echo "[overlay] installing into ${DEST#"$REPO_ROOT/"}..."
mkdir -p "$DEST"
find "$DEST" -mindepth 1 -maxdepth 1 ! -name README.txt -exec rm -rf {} +
cp -a "$PACKAGE/." "$DEST/"
echo "$COMMIT" > "$DEST/OVERLAY_COMMIT"
echo "[overlay] done: $TARGET built from overlay $COMMIT"
