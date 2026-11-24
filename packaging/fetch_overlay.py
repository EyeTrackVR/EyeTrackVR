"""Download the calibration overlay runtimes into overlay/<platform>/.

    python packaging/fetch_overlay.py windows linux linux-arm64

The PyInstaller specs fetch their own platform. To update the overlay, point
RELEASE at a newer EyeTrackVR-Calibration-Overlay release and copy each asset's
SHA-256 from its release page.

To run a local overlay build instead, install it into that folder, for example
from an overlay checkout next to this one:

    cmake --install build --config Release --prefix ../EyeTrackVR/overlay/linux

A folder without the download marker is left alone. Delete it to go back to
the pinned release.
"""

import hashlib
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

RELEASE = "https://github.com/EyeTrackVR/EyeTrackVR-Calibration-Overlay/releases/download/v0.5.0"
ASSETS = {  # overlay/ folder: release asset, SHA-256
    "windows": (
        "EyeTrackVR-Overlay-win64.tar.xz",
        "c07b8ea7e177c48c86020f96056021e4d38e739406a9c9c679280af3f176209b",
    ),
    "linux": (
        "EyeTrackVR-Overlay-linux64.tar.xz",
        "b27443b938e8b7a4134216b222156e5a4e4a0dae8648c7a1aab58a589fecbaa9",
    ),
    "linux-arm64": (
        "EyeTrackVR-Overlay-linuxarm64.tar.xz",
        "6e0bfa6dcfa2a67721a0b2752551334fbd354b171666b8ddd6853b1b307d6585",
    ),
}
DIST = Path(__file__).resolve().parents[1] / "overlay"


def fetch(platform: str) -> Path:
    asset, sha256 = ASSETS[platform]
    folder = DIST / platform
    marker = folder / ".release"
    if folder.is_dir() and not marker.is_file():
        print(f"Using the local overlay build in {folder}")
        return folder
    if marker.is_file() and marker.read_text() == sha256:
        return folder
    with urllib.request.urlopen(f"{RELEASE}/{asset}") as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"{asset} does not match the SHA-256 pinned in {__file__}")
    staged = folder.with_name(f"{platform}.download")
    shutil.rmtree(staged, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(staged, filter="data")
    (staged / ".release").write_text(sha256)
    if folder.exists():
        shutil.rmtree(folder)
    staged.rename(folder)
    return folder


if __name__ == "__main__":
    for platform in sys.argv[1:]:
        fetch(platform)
