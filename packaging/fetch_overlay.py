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

RELEASE = "https://github.com/RedlineTriad/EyeTrackVR-OpenVR-Calibration-Overlay/releases/download/v0.4.0-rc.7"
ASSETS = {  # overlay/ folder: release asset, SHA-256
    "windows": (
        "EyeTrackVR-Overlay-win64.tar.xz",
        "17c4de29e5859591faa0a9c30575a03fd56fc5159148a8f7bcb11859e3302a34",
    ),
    "linux": (
        "EyeTrackVR-Overlay-linux64.tar.xz",
        "b42dde207015862a6c63d551537853d89c4baecf20732f6564d98971f1603687",
    ),
    "linux-arm64": (
        "EyeTrackVR-Overlay-linuxarm64.tar.xz",
        "df4dce46caf2b50a87e253e407b0d64d943a069c5d7261303ed58e3af1e9f6b0",
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
