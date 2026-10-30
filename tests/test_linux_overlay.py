"""Source checkouts use the prebuilt overlay runtimes from the overlay/ submodule."""

from pathlib import Path
import platform
import struct
import sys

import pytest

import osc_calibrate_filter as calibration

DIST = Path(__file__).resolve().parents[1] / "overlay" / "dist"
ELF_MACHINE = {"linux": 62, "linux-arm64": 183}  # x86-64, AArch64


@pytest.mark.parametrize("machine, folder", [("x86_64", "linux"), ("aarch64", "linux-arm64")])
def test_source_checkout_uses_submodule_linux_overlay(monkeypatch, machine, folder):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: machine)
    path = Path(calibration._overlay_executable()).resolve()
    assert path == DIST / folder / "EyeTrackVR-Overlay"
    header = path.read_bytes()[:20]
    assert header[:6] == b"\x7fELF\x02\x01"  # 64-bit, little endian
    assert struct.unpack("<H", header[18:20])[0] == ELF_MACHINE[folder]


@pytest.mark.parametrize("folder", ["linux", "linux-arm64"])
def test_linux_overlay_ships_loaders_assets_and_notices(folder):
    runtime = DIST / folder
    for name in ("libopenvr_api.so", "libopenxr_loader.so.1", "libjsoncpp.so.25", "libvulkan.so.1"):
        assert (runtime / name).read_bytes()[:4] == b"\x7fELF"
    # The target sprites are drawn procedurally; the font is the only asset.
    assert (runtime / "assets" / "OpenSans-Regular.ttf").stat().st_size > 0
    for name in ("overlay-MIT.txt", "OpenVR-LICENSE.txt", "libopenxr-loader1-copyright.txt"):
        assert (runtime / "licenses" / name).stat().st_size > 0


def test_windows_overlay_ships_exe_dlls_and_font(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    path = Path(calibration._overlay_executable()).resolve()
    assert path == DIST / "windows" / "EyeTrackVR-Overlay.exe"
    for name in ("EyeTrackVR-Overlay.exe", "openvr_api.dll", "openxr_loader.dll", "vulkan-1.dll", "jsoncpp.dll"):
        assert (DIST / "windows" / name).read_bytes()[:2] == b"MZ"
    assert (DIST / "windows" / "assets" / "OpenSans-Regular.ttf").stat().st_size > 0
