# -*- mode: python ; coding: utf-8 -*-
# Linux build of EyeTrackVR. Differences from the Windows spec (eyetrackapp.spec):
#   - onedir (COLLECT) instead of onefile: faster startup, standard for tarballs
#   - openvr ships libopenvr_api*.so on Linux, discovered by glob
#   - Windows-only packages (pywinstyles/pygrabber/winotify/winsound) excluded
#   - native Linux overlay and its loaders are required, with assets alongside
#   - no .ico icon (Linux icons come from the .desktop entry + logo.png)

import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)
from pathlib import Path
import openvr

block_cipher = None

resources = [
    ("contributions/notice.json", "contributions"),
    ("Audio/*", "Audio"),
    ("Images/*", "Images/"),
    ("pye3d/refraction_models/*", "pye3d/refraction_models/"),
    ("Models/*", "Models/"),
    ("Tools/linux/assets/*", "Tools/linux/assets/"),
    ("lang/*", "lang/"),
]

# The pyopenvr wheel bundles per-arch shared libs next to openvr/__init__.py.
_openvr_dir = Path(openvr.__file__).parent
openvr_libs = [(str(p), "openvr") for p in _openvr_dir.glob("libopenvr_api*.so")]
overlay = Path("Tools/linux/EyeTrackVR-Overlay")
if not overlay.is_file():
    raise FileNotFoundError("Missing Tools/linux/EyeTrackVR-Overlay; copy the Linux runtime folder from the overlay repository")
overlay_libs = [(str(overlay), "Tools/linux")]
for name in ("libopenvr_api.so", "libopenxr_loader.so.1", "libjsoncpp.so.25", "libvulkan.so.1"):
    path = overlay.parent / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing overlay runtime: {path}")
overlay_libs += [(str(p), "Tools/linux") for p in overlay.parent.glob("*.so*")]
resources.append(("Tools/linux/licenses/*", "Tools/linux/licenses"))

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
