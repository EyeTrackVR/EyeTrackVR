#!/usr/bin/env bash
# Build the EyeTrackVR Linux release artifact inside WSL (or any Ubuntu 22.04+).
#
#   bash build_linux.sh <version> <file-safe-version> <repo-root-in-wsl> <out-dir-in-wsl>
#   e.g. bash build_linux.sh "0.3.0 BETA 7" "0.3.0-BETA-7" \
#            /mnt/c/Users/beaul/Documents/GitHub/EyeTrackVR /mnt/c/.../release
#
# Produces: <out-dir>/EyeTrackVR-<file-safe-version>-linux-x86_64.tar.gz
#
# Strategy: rsync the sources to the native ext4 filesystem first (PyInstaller
# on /mnt/c is 10-20x slower and can hit permission quirks), then venv + build.
set -euo pipefail

VERSION="${1:?version required}"
SAFE_VERSION="${2:?file-safe version required}"
REPO_ROOT="${3:?repo root (WSL path) required}"
OUT_DIR="${4:?output dir (WSL path) required}"

export PATH="$HOME/.local/bin:/root/.local/bin:$PATH"
BUILD_ROOT="$HOME/etvr-build"
SRC_DIR="$BUILD_ROOT/src"
VENV_DIR="$BUILD_ROOT/venv"
APP_SUBDIR="eyetrackapp"

echo "[linux-build] syncing sources to native filesystem..."
mkdir -p "$SRC_DIR"
rsync -a --delete \
    --exclude "__pycache__" --exclude ".ruff_cache" --exclude "build" \
    --exclude "dist" --exclude "logs" --exclude "INNO/Output" \
    --exclude "*.pyc" --exclude "v5_*_ETVR_Output" \
    "$REPO_ROOT/$APP_SUBDIR/" "$SRC_DIR/$APP_SUBDIR/"
rsync -a "$REPO_ROOT/scripts/" "$SRC_DIR/scripts/"
# Strip CRLF from anything bash/python parses out of the repo checkout.
find "$SRC_DIR/scripts" -name "*.sh" -exec sed -i 's/\r$//' {} +

echo "[linux-build] creating venv (python 3.14 via uv)..."
uv venv --python 3.14 --clear "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[linux-build] installing dependencies..."
# pye3d compiles from source (no cp314 Linux wheel); a previously failed build
# leaves a stale _skbuild/CMakeCache in uv's sdist cache that poisons retries.
# Cleaning just pye3d is cheap (small package) and makes installs deterministic.
uv cache clean pye3d >/dev/null 2>&1 || true
uv pip install -r "$SRC_DIR/scripts/requirements-linux-build.txt"

echo "[linux-build] running PyInstaller..."
cd "$SRC_DIR/$APP_SUBDIR"
rm -rf build dist
# uv's standalone CPython links _tkinter against its own libtcl9/libtk9 living
# in the interpreter's lib dir, which isn't on the default search path. Expose
# it so PyInstaller resolves and BUNDLES those libs (ImportError: libtcl9.0.so
# on end-user machines otherwise).
PY_LIBDIR="$(python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
LD_LIBRARY_PATH="${PY_LIBDIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    pyinstaller eyetrackapp_linux.spec --noconfirm

BUNDLE="dist/EyeTrackVR"
test -x "$BUNDLE/eyetrackvr" || { echo "ERROR: bundle missing eyetrackvr binary"; exit 1; }

echo "[linux-build] smoke test: bundled binary starts and imports..."
# Run WITHOUT the build env's LD_LIBRARY_PATH, exactly like an end-user machine.
# Pass conditions:
#   rc=124: timeout killed it, i.e. the app was RUNNING (WSLg gives a display;
#             camera threads spin with "no camera" errors, which is fine)
#   rc=0: clean exit
#   "no display" in output: headless box; still proves libs link and unpack
# Anything else (missing .so, ImportError, instant crash) fails the build.
set +e
SMOKE_OUT="$(timeout 20 env -u LD_LIBRARY_PATH "$BUNDLE/eyetrackvr" 2>&1)"
SMOKE_RC=$?
set -e
if [ $SMOKE_RC -eq 0 ] || [ $SMOKE_RC -eq 124 ] \
    || echo "$SMOKE_OUT" | grep -qiE "no display name|couldn't connect to display|no \$DISPLAY"; then
    echo "[linux-build] smoke test OK (rc=$SMOKE_RC)"
else
    echo "ERROR: bundle smoke test failed (rc=$SMOKE_RC):"
    echo "$SMOKE_OUT" | tail -20
    exit 1
fi

echo "[linux-build] assembling tarball..."
STAGE="$BUILD_ROOT/stage/EyeTrackVR-$SAFE_VERSION"
rm -rf "$BUILD_ROOT/stage"
mkdir -p "$STAGE"
cp -a "$BUNDLE/." "$STAGE/"
install -m 0755 "$SRC_DIR/scripts/linux/install.sh" "$STAGE/install.sh"
install -m 0644 "$SRC_DIR/scripts/linux/EyeTrackVR.desktop" "$STAGE/EyeTrackVR.desktop"
echo "$VERSION" > "$STAGE/VERSION"

mkdir -p "$OUT_DIR"
TARBALL="$OUT_DIR/EyeTrackVR-$SAFE_VERSION-linux-x86_64.tar.gz"
tar -C "$BUILD_ROOT/stage" -czf "$TARBALL" "EyeTrackVR-$SAFE_VERSION"
echo "[linux-build] wrote $TARBALL"
echo "LINUX_BUILD_DONE"
