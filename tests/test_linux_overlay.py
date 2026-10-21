"""Native files must be present in source checkouts, not only release bundles."""

from pathlib import Path
import struct

import osc_calibrate_filter as calibration


TOOLS = Path(__file__).resolve().parents[1] / "EyeTrackApp" / "Tools" / "linux"


def test_source_checkout_ships_linux_x86_64_overlay(monkeypatch):
    monkeypatch.setattr(calibration.sys, "platform", "linux")
    path = Path(calibration._overlay_executable())
    assert path == TOOLS / "EyeTrackVR-Overlay"
    header = path.read_bytes()[:20]
    assert header[:6] == b"\x7fELF\x02\x01"  # 64-bit, little endian
    assert struct.unpack("<H", header[18:20])[0] == 62  # AMD x86-64


def test_source_checkout_ships_overlay_loaders_assets_and_notices():
    for name in ("libopenvr_api.so", "libopenxr_loader.so.1", "libjsoncpp.so.25", "libvulkan.so.1"):
        assert (TOOLS / name).read_bytes()[:4] == b"\x7fELF"
    # The target sprites are drawn procedurally; the font is the only asset.
    assert (TOOLS / "assets" / "OpenSans-Regular.ttf").stat().st_size > 0
    for name in ("overlay-MIT.txt", "OpenVR-LICENSE.txt", "libopenxr-loader1-copyright.txt"):
        assert (TOOLS / "licenses" / name).stat().st_size > 0
