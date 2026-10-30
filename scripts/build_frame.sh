#!/usr/bin/env bash
# Build the EyeTrackVR Steam Frame (Linux ARM64) release for FrameDrop.
#
#   bash build_frame.sh <version> <file-safe-version> <repo-root> <out-dir>
#
# Runs on arm64 Ubuntu 24.04 with scripts/frame/apt-packages.txt installed:
# the scripts/frame/Dockerfile image (build_release.bat) or the ubuntu-24.04-arm
# CI runner.
#
# Produces in <out-dir>:
#   EyeTrackVR-<file-safe-version>-steamframe-arm64.zip
#   EyeTrackVR-<file-safe-version>-steamframe.framedrop.json
#
# The manifest points at the zip on the GitHub release tagged
# EyeTrackApp-<file-safe-version>; override with ETVR_RELEASE_BASE_URL.
set -euo pipefail

VERSION="${1:?version required}"
SAFE_VERSION="${2:?file-safe version required}"
REPO_ROOT="${3:?repo root required}"
OUT_DIR="${4:?output dir required}"

RELEASE_BASE_URL="${ETVR_RELEASE_BASE_URL:-https://github.com/EyeTrackVR/EyeTrackVR/releases/download/EyeTrackApp-$SAFE_VERSION}"
# OpenVR SDK matching the pyopenvr 2.12 bindings; the wheel has no aarch64 lib.
OPENVR_TAG="v2.12.14"
OPENVR_SHA256="7fcdc649e5371c60530080c7ed3daef978daefd97304e1ff45b312aa344b3e76"
# Highest glibc the bundle may require: the Frame's own SteamOS (2.39).
# FrameDrop launches titles in Steam Linux Runtime 4.0, which is newer.
MAX_GLIBC="2.39"

BUILD_ROOT="${ETVR_FRAME_BUILD_ROOT:-$HOME/etvr-frame-build}"
SRC_DIR="$BUILD_ROOT/src"
PYTHON_DIR="$BUILD_ROOT/python"
VENV_DIR="$BUILD_ROOT/venv"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$BUILD_ROOT/pip-cache}"
export PIP_DISABLE_PIP_VERSION_CHECK=1
APP_SUBDIR="EyeTrackApp"
ZIP_NAME="EyeTrackVR-$SAFE_VERSION-steamframe-arm64.zip"
MANIFEST_NAME="EyeTrackVR-$SAFE_VERSION-steamframe.framedrop.json"

ARCH="$(uname -m)"
if [ "$ARCH" != "aarch64" ]; then
    echo "ERROR: Steam Frame builds must run on aarch64 (got $ARCH)" >&2
    exit 1
fi
# sed, not head: head closing the pipe early is a SIGPIPE failure under pipefail
GLIBC="$(ldd --version | sed -n '1s/.* \([0-9][0-9]*\.[0-9][0-9]*\)$/\1/p')"
if [ "$(printf '%s\n%s\n' "$GLIBC" "$MAX_GLIBC" | sort -V | tail -1)" != "$MAX_GLIBC" ]; then
    echo "ERROR: build glibc $GLIBC is newer than the Frame's $MAX_GLIBC" >&2
    exit 1
fi
echo "[frame-build] aarch64, glibc $GLIBC"

echo "[frame-build] syncing sources to native filesystem..."
mkdir -p "$SRC_DIR"
rsync -a --delete \
    --exclude "__pycache__" --exclude ".ruff_cache" --exclude "build" \
    --exclude "dist" --exclude "logs" --exclude "INNO/Output" \
    --exclude "*.pyc" --exclude "v5_*_ETVR_Output" \
    "$REPO_ROOT/$APP_SUBDIR/" "$SRC_DIR/$APP_SUBDIR/"
rsync -a --delete "$REPO_ROOT/scripts/" "$SRC_DIR/scripts/"
# The spec bundles the overlay runtime from the overlay/ submodule.
mkdir -p "$SRC_DIR/overlay"
rsync -a --delete "$REPO_ROOT/overlay/dist/" "$SRC_DIR/overlay/dist/"
find "$SRC_DIR/scripts" -name "*.sh" -exec sed -i 's/\r$//' {} +

echo "[frame-build] fetching aarch64 libopenvr_api ($OPENVR_TAG)..."
OPENVR_LIB="$BUILD_ROOT/openvr-arm64/libopenvr_api_64.so"
mkdir -p "$(dirname "$OPENVR_LIB")"
if ! echo "$OPENVR_SHA256  $OPENVR_LIB" | sha256sum -c --status 2>/dev/null; then
    curl -fsSL -o "$OPENVR_LIB" \
        "https://raw.githubusercontent.com/ValveSoftware/openvr/$OPENVR_TAG/bin/linuxarm64/libopenvr_api.so"
    echo "$OPENVR_SHA256  $OPENVR_LIB" | sha256sum -c -
fi

echo "[frame-build] installing python 3.14 and creating venv..."
# pip rather than uv: uv's extraction fails under QEMU (see install_python.sh).
bash "$SRC_DIR/scripts/frame/install_python.sh" "$PYTHON_DIR"
"$PYTHON_DIR/bin/python3.14" -m venv --clear "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[frame-build] installing dependencies..."
# pye3d has no aarch64 wheel and compiles from source (slow under QEMU; pip
# caches the built wheel for the next run).
python -m pip install -q --upgrade pip
python -m pip install -r "$SRC_DIR/scripts/requirements-linux-build.txt"

echo "[frame-build] running PyInstaller..."
cd "$SRC_DIR/$APP_SUBDIR"
rm -rf build dist
# See build_linux.sh: exposes the standalone CPython's libtcl9/libtk9 so
# PyInstaller bundles them.
PY_LIBDIR="$(python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
LD_LIBRARY_PATH="${PY_LIBDIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    ETVR_OPENVR_LIB="$OPENVR_LIB" \
    pyinstaller eyetrackapp_linux.spec --noconfirm

BUNDLE="dist/EyeTrackVR"
test -x "$BUNDLE/eyetrackvr" || { echo "ERROR: bundle missing eyetrackvr binary"; exit 1; }
test -f "$BUNDLE/_internal/openvr/libopenvr_api_64.so" || { echo "ERROR: bundle missing arm64 libopenvr_api"; exit 1; }

echo "[frame-build] bundling espeak-ng for the data-collection voice prompts..."
# The Frame has no text-to-speech engine, on the host or in Steam Linux Runtime
# 4, so the prompts were silent. espeak-ng is a separate GPL-3.0 program run as
# a subprocess, shipped with its libraries (PulseAudio client included; the
# runtime passes the session's sound server through) and its license notices.
# glibc, libstdc++ and libgcc stay system-provided.
TTS="$BUNDLE/_internal/Tools/tts"
rm -rf "$TTS"
mkdir -p "$TTS/lib" "$TTS/licenses"
install -m 0755 /usr/bin/espeak-ng "$TTS/espeak-ng"
cp -a /usr/lib/aarch64-linux-gnu/espeak-ng-data "$TTS/"
ldd /usr/bin/espeak-ng | awk '/=> \// {print $3}' \
    | grep -vE '/(libc|libm|libdl|libpthread|librt|libstdc\+\+|libgcc_s|ld-linux-aarch64)\.so' \
    | while read -r lib; do install -m 0644 "$lib" "$TTS/lib/$(basename "$lib")"; done
for pkg in espeak-ng espeak-ng-data libespeak-ng1 libpcaudio0 libsonic0 libpulse0; do
    notice="/usr/share/doc/$pkg/copyright"
    if [ -f "$notice" ]; then
        install -m 0644 "$notice" "$TTS/licenses/$pkg-copyright.txt"
    fi
done
if LD_LIBRARY_PATH="$TTS/lib" ldd "$TTS/espeak-ng" | grep -q 'not found'; then
    echo "ERROR: unresolved espeak-ng library" >&2
    exit 1
fi
LD_LIBRARY_PATH="$TTS/lib" ESPEAK_DATA_PATH="$TTS" "$TTS/espeak-ng" -q "voice check" \
    || { echo "ERROR: bundled espeak-ng does not run" >&2; exit 1; }

echo "[frame-build] checking bundled glibc symbol versions..."
NEEDED_GLIBC="$(find "$BUNDLE" -type f \( -name '*.so*' -o -name eyetrackvr -o -name espeak-ng \) -exec objdump -T {} + 2>/dev/null \
    | grep -oE 'GLIBC_[0-9]+\.[0-9]+' | sed 's/GLIBC_//' | sort -Vu | tail -1)"
echo "[frame-build] bundle requires glibc $NEEDED_GLIBC"
if [ "$(printf '%s\n%s\n' "$NEEDED_GLIBC" "$MAX_GLIBC" | sort -V | tail -1)" != "$MAX_GLIBC" ]; then
    echo "ERROR: bundle needs glibc $NEEDED_GLIBC, the Frame has $MAX_GLIBC" >&2
    exit 1
fi

echo "[frame-build] smoke test: bundled binary starts and imports..."
# Same pass conditions as build_linux.sh. Under QEMU the app may still be
# importing when the timeout hits, which also counts as running.
set +e
SMOKE_OUT="$(timeout 60 env -u LD_LIBRARY_PATH "$BUNDLE/eyetrackvr" 2>&1)"
SMOKE_RC=$?
set -e
if [ $SMOKE_RC -eq 0 ] || [ $SMOKE_RC -eq 124 ] \
    || echo "$SMOKE_OUT" | grep -qiE "no display name|couldn't connect to display|no \$DISPLAY"; then
    echo "[frame-build] smoke test OK (rc=$SMOKE_RC)"
else
    echo "ERROR: bundle smoke test failed (rc=$SMOKE_RC):"
    echo "$SMOKE_OUT" | tail -20
    exit 1
fi
# The smoke run writes its log into logs/ next to the binary; keep it out of
# the release.
rm -rf "$BUNDLE/logs"
echo "[frame-build] assembling zip..."
# FrameDrop unpacks the zip on Windows, which cannot recreate symlinks, so they
# are dereferenced into real files. eyetrackvr must stay the only executable at
# the top level: FrameDrop uses it as the Steam start command.
STAGE_ROOT="$BUILD_ROOT/stage"
STAGE="$STAGE_ROOT/EyeTrackVR"
rm -rf "$STAGE_ROOT"
mkdir -p "$STAGE"
cp -rL --preserve=mode,timestamps "$BUNDLE/." "$STAGE/"
install -m 0644 "$SRC_DIR/scripts/frame/README-STEAMFRAME.txt" "$STAGE/README-STEAMFRAME.txt"
sed -i 's/\r$//' "$STAGE/README-STEAMFRAME.txt"
echo "$VERSION" > "$STAGE/VERSION"

# NTFS is case-insensitive: two paths differing only by case would clobber
# each other when FrameDrop unpacks on Windows.
CASE_DUPES="$(cd "$STAGE_ROOT" && find . | sort -f | uniq -di)"
if [ -n "$CASE_DUPES" ]; then
    echo "ERROR: paths collide on case-insensitive filesystems:" >&2
    echo "$CASE_DUPES" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
ZIP_PATH="$OUT_DIR/$ZIP_NAME"
rm -f "$ZIP_PATH"
(cd "$STAGE_ROOT" && zip -qr -X "$ZIP_PATH" EyeTrackVR)
echo "[frame-build] wrote $ZIP_PATH ($(du -h "$ZIP_PATH" | cut -f1))"

echo "[frame-build] writing FrameDrop manifest..."
python "$SRC_DIR/scripts/frame/write_framedrop_manifest.py" \
    --zip "$ZIP_PATH" \
    --url "$RELEASE_BASE_URL/$ZIP_NAME" \
    --out "$OUT_DIR/$MANIFEST_NAME" \
    --manifest-url "$RELEASE_BASE_URL/$MANIFEST_NAME"
echo "FRAME_BUILD_DONE"
