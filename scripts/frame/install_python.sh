#!/usr/bin/env bash
# Install the pinned aarch64 standalone CPython used by build_frame.sh.
#
#   bash install_python.sh <dest-dir>     -> <dest-dir>/bin/python3.14
#
# Same python-build-standalone builds uv uses for the x86 Linux release (Tk
# bundled, glibc 2.17 baseline). Unpacked with Python's tarfile instead of GNU
# tar or `uv python install`: under Docker Desktop's QEMU both fail with EINVAL
# on file creation (openat2), while plain openat works. Idempotent.
set -euo pipefail

DEST="${1:?destination dir required}"
PBS_RELEASE="20261021"
PBS_FILE="cpython-3.14.9+${PBS_RELEASE}-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz"
PBS_SHA256="6f77731d85a14ed848dd4041478cd3ed511523caa3d896b84b436a7edf13cf62"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${PBS_FILE//+/%2B}"

if [ -f "$DEST/.installed-$PBS_SHA256" ] && [ -x "$DEST/bin/python3.14" ]; then
    exit 0
fi

ARCHIVE="$(mktemp)"
trap 'rm -f "$ARCHIVE"' EXIT
curl -fsSL -o "$ARCHIVE" "$PBS_URL"
echo "$PBS_SHA256  $ARCHIVE" | sha256sum -c --quiet -

rm -rf "$DEST"
mkdir -p "$DEST"
python3 - "$ARCHIVE" "$DEST" <<'PY'
import sys, tarfile
archive, dest = sys.argv[1:]
with tarfile.open(archive) as tar:
    members = []
    for m in tar.getmembers():
        # strip the top-level "python/" folder
        if "/" not in m.name:
            continue
        m.name = m.name.split("/", 1)[1]
        members.append(m)
    tar.extractall(dest, members=members, filter="tar")
PY
touch "$DEST/.installed-$PBS_SHA256"
"$DEST/bin/python3.14" -c "import sys, tkinter; print('python', sys.version.split()[0], 'tk', tkinter.TkVersion)"
