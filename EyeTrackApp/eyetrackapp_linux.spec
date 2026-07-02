# -*- mode: python ; coding: utf-8 -*-
# Linux build of EyeTrackVR. Differences from the Windows spec (eyetrackapp.spec):
#   - onedir (COLLECT) instead of onefile: faster startup, standard for tarballs
#   - openvr ships libopenvr_api*.so on Linux, discovered by glob
#   - Windows-only packages (pywinstyles/pygrabber/winotify/winsound) excluded
#   - Tools/ Windows overlay binaries (.exe/.dll) are NOT bundled; overlay
#     assets are kept so a future Linux overlay drop-in finds them
#   - no .ico icon (Linux icons come from the .desktop entry + logo.png)

import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)
from pathlib import Path
import openvr

block_cipher = None

resources = [
    ("Audio/*", "Audio"),
    ("Images/*", "Images/"),
    ("pye3d/refraction_models/*", "pye3d/refraction_models/"),
    ("Models/*", "Models/"),
    ("Tools/assets/*", "Tools/assets/"),
]

# The pyopenvr wheel bundles per-arch shared libs next to openvr/__init__.py.
_openvr_dir = Path(openvr.__file__).parent
openvr_libs = [(str(p), "openvr") for p in _openvr_dir.glob("libopenvr_api*.so")]

a = Analysis(
    ["eyetrackapp.py"],
    pathex=[],
    binaries=openvr_libs,
    datas=resources,
    hiddenimports=["cv2", "numpy", "sv_ttk", "tkinter", "tkinter.ttk"],
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
