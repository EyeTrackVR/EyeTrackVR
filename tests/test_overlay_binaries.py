"""The in-VR overlay runtimes packaging/fetch_overlay.py downloads into overlay/<platform>/:
a source checkout launches them, each ships its loaders, font and notices, and the
runnable one knows every language the app ships.

The binaries are not in git. Locally a folder that was never fetched skips with the
command to run; CI (tests.yml "Download the calibration overlay") fetches all three
before the tests, so there a missing folder fails instead of hiding these tests."""

import os
from pathlib import Path
import platform
import struct
import subprocess
import sys

import pytest

from utils.overlay_launch import overlay_executable

DIST = Path(__file__).resolve().parents[1] / "overlay"
LANG = Path(__file__).resolve().parents[1] / "eyetrackapp" / "lang"
EXECUTABLE = {"windows": "EyeTrackVR-Overlay.exe", "linux": "EyeTrackVR-Overlay", "linux-arm64": "EyeTrackVR-Overlay"}
ELF_MACHINE = {"linux": 62, "linux-arm64": 183}  # x86-64, AArch64


def fetched(folder):
    """overlay/<folder>, or a skip (a fail on CI) when it has not been downloaded."""
    runtime = DIST / folder
    if not (runtime / EXECUTABLE[folder]).is_file():
        message = f"overlay/{folder} is not downloaded; run: python packaging/fetch_overlay.py {folder}"
        if os.environ.get("CI"):
            pytest.fail(f"{message} (the CI workflow fetches it before the tests)")
        pytest.skip(message)
    return runtime


@pytest.mark.parametrize("machine, folder", [("x86_64", "linux"), ("aarch64", "linux-arm64")])
def test_source_checkout_uses_fetched_linux_overlay(monkeypatch, machine, folder):
    runtime = fetched(folder)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: machine)
    path = Path(overlay_executable()).resolve()
    assert path == runtime.resolve() / "EyeTrackVR-Overlay"
    header = path.read_bytes()[:20]
    assert header[:6] == b"\x7fELF\x02\x01"  # 64-bit, little endian
    assert struct.unpack("<H", header[18:20])[0] == ELF_MACHINE[folder]


@pytest.mark.parametrize("folder", ["linux", "linux-arm64"])
def test_linux_overlay_ships_loaders_assets_and_notices(folder):
    runtime = fetched(folder)
    for name in ("libopenvr_api.so", "libopenxr_loader.so.1", "libjsoncpp.so.25", "libvulkan.so.1"):
        assert (runtime / name).read_bytes()[:4] == b"\x7fELF"
    # The target sprites are drawn procedurally; the font is the only asset.
    assert (runtime / "assets" / "OpenSans-Regular.ttf").stat().st_size > 0
    for name in ("overlay-MIT.txt", "OpenVR-LICENSE.txt", "libopenxr-loader1-copyright.txt"):
        assert (runtime / "licenses" / name).stat().st_size > 0


def test_windows_overlay_ships_exe_dlls_and_font(monkeypatch):
    runtime = fetched("windows")
    monkeypatch.setattr(sys, "platform", "win32")
    path = Path(overlay_executable()).resolve()
    assert path == runtime.resolve() / "EyeTrackVR-Overlay.exe"
    for name in ("EyeTrackVR-Overlay.exe", "openvr_api.dll", "openxr_loader.dll", "vulkan-1.dll", "jsoncpp.dll"):
        assert (runtime / name).read_bytes()[:2] == b"MZ"
    assert (runtime / "assets" / "OpenSans-Regular.ttf").stat().st_size > 0


def _runnable_folder():
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "linux":
        return {"x86_64": "linux", "aarch64": "linux-arm64"}.get(platform.machine())
    return None


def test_bundled_overlay_supports_every_app_language():
    folder = _runnable_folder()
    if folder is None:
        pytest.skip(f"no overlay build runs on {sys.platform}/{platform.machine()} (Windows and Linux only)")
    exe = fetched(folder) / EXECUTABLE[folder]
    out = subprocess.run(
        [str(exe), "--list-langs"], capture_output=True, text=True, timeout=30, check=True
    ).stdout.split()
    shipped = {p.stem for p in LANG.glob("*.toml") if not p.stem.startswith("_")}
    missing = shipped - set(out)
    assert not missing, f"overlay lacks built-in text for {sorted(missing)}; rebuild it"


@pytest.mark.parametrize(
    "platform_name, machine, folder, name",
    [
        ("win32", "AMD64", "windows", "EyeTrackVR-Overlay.exe"),
        ("linux", "x86_64", "linux", "EyeTrackVR-Overlay"),
        ("linux", "arm64", "linux-arm64", "EyeTrackVR-Overlay"),
    ],
)
def test_a_source_checkout_without_the_overlay_says_what_to_run(
    monkeypatch, tmp_path, platform_name, machine, folder, name
):
    from utils import overlay_launch

    monkeypatch.setattr(overlay_launch, "OVERLAY_DIST", tmp_path)
    monkeypatch.setattr(sys, "platform", platform_name)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    with pytest.raises(FileNotFoundError, match=f"run: python packaging/fetch_overlay.py {folder}$"):
        overlay_executable()
    (tmp_path / folder).mkdir()
    (tmp_path / folder / name).write_bytes(b"")
    assert overlay_executable() == str(tmp_path / folder / name)
