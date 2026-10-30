# -*- mode: python ; coding: utf-8 -*-
# Linux build of EyeTrackVR. Differences from the Windows spec (eyetrackapp.spec):
#   - onedir (COLLECT) instead of onefile: faster startup, standard for tarballs
#   - openvr ships libopenvr_api*.so on Linux, discovered by glob
#   - Windows-only packages (pywinstyles/pygrabber/winotify/winsound) excluded
#   - native Linux overlay and its loaders are required, with assets alongside
#   - no .ico icon (Linux icons come from the .desktop entry + logo.png)
#
# aarch64 (Steam Frame, scripts/build_frame.sh) differences:
#   - the pyopenvr wheel only ships x86 libs, so the arm64 libopenvr_api.so is
#     supplied via ETVR_OPENVR_LIB and bundled under the name pyopenvr loads
#   - the overlay runtime comes from overlay/dist/linux-arm64/ and is optional;
#     without it the app runs and overlay calibration reports the binary as missing

import os
import platform
import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)
from pathlib import Path

block_cipher = None

resources = [
    ("contributions/notice.json", "contributions"),
    ("Audio/*", "Audio"),
    ("Images/*", "Images/"),
    ("pye3d/refraction_models/*", "pye3d/refraction_models/"),
    ("Models/*", "Models/"),
    ("lang/*", "lang/"),
]

IS_ARM64 = platform.machine() in ("aarch64", "arm64")

if IS_ARM64:
    # pyopenvr picks libopenvr_api_64.so by pointer size, not CPU arch, and
    # PyInstaller binaries keep their source name, so the file must be named so.
    openvr_lib = Path(os.environ.get("ETVR_OPENVR_LIB", ""))
    if not openvr_lib.is_file() or openvr_lib.name != "libopenvr_api_64.so":
        raise FileNotFoundError("Set ETVR_OPENVR_LIB to an aarch64 libopenvr_api_64.so (scripts/build_frame.sh fetches one)")
    openvr_libs = [(str(openvr_lib), "openvr")]
else:
    import openvr

    # The pyopenvr wheel bundles per-arch shared libs next to openvr/__init__.py.
    _openvr_dir = Path(openvr.__file__).parent
    openvr_libs = [(str(p), "openvr") for p in _openvr_dir.glob("libopenvr_api*.so")]

# Prebuilt runtimes from the overlay/ submodule. The app always looks for the
# overlay in Tools/linux/, whatever the source folder.
overlay_dir = Path("../overlay/dist/linux-arm64" if IS_ARM64 else "../overlay/dist/linux")
overlay = overlay_dir / "EyeTrackVR-Overlay"
overlay_libs = []
if overlay.is_file():
    overlay_libs.append((str(overlay), "Tools/linux"))
    for name in ("libopenvr_api.so", "libopenxr_loader.so.1", "libjsoncpp.so.25", "libvulkan.so.1"):
        path = overlay_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing overlay runtime: {path}")
    overlay_libs += [(str(p), "Tools/linux") for p in overlay_dir.glob("*.so*")]
    resources.append((f"{overlay_dir.as_posix()}/assets/*", "Tools/linux/assets/"))
    resources.append((f"{overlay_dir.as_posix()}/licenses/*", "Tools/linux/licenses"))
elif IS_ARM64:
    print(f"WARNING: {overlay} not found; building without the in-VR calibration overlay")
else:
    raise FileNotFoundError(f"Missing {overlay}; run: git submodule update --init overlay")

a = Analysis(
    ["eyetrackapp.py"],
    pathex=[],
    binaries=openvr_libs + overlay_libs,
    datas=resources,
    # PIL._tkinter_finder is the Pillow <-> Tk bridge that registers the
    # PyImagingPhoto Tcl command. PyInstaller does not see it (ImageTk imports
    # it lazily by name), so without it every preview raises
    # ModuleNotFoundError out of the Tk callback and no camera image is drawn.
    hiddenimports=[
        "cv2", "numpy", "sv_ttk", "tkinter", "tkinter.ttk",
        "PIL.Image", "PIL.ImageTk", "PIL._tkinter_finder",
        "pyrage", "webview", "webview.platforms.qt",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pywinstyles", "pygrabber", "winotify", "winsound", "comtypes"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="eyetrackvr",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EyeTrackVR",
)
