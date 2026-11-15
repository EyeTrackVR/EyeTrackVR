# -*- mode: python ; coding: utf-8 -*-
# Run from the repo root (see packaging/build_release.bat).

import glob
import importlib.util
import os
import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)
import openvr

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
APP = os.path.join(ROOT, "eyetrackapp")
# pye3d loads its refraction models from its own package folder.
PYE3D = importlib.util.find_spec("pye3d").submodule_search_locations[0]

# Models live in Git LFS; refuse to bundle the pointer files a clone without git-lfs leaves.
for _model in glob.glob(os.path.join(APP, "assets", "models", "*.onnx")):
    with open(_model, "rb") as _f:
        if _f.read(8) == b"version ":
            sys.exit(f"{_model} is a Git LFS pointer; run `git lfs pull` first.")

sys.path.insert(0, os.path.join(ROOT, "packaging"))
from fetch_overlay import fetch

overlay_dir = fetch("windows")
block_cipher = None

# The calibration overlay (packaging/fetch_overlay.py): its exe and DLLs, its assets
# in tools/assets, where it looks for its font, and its license notices. Named one by
# one so a local log or the download marker in that folder is not shipped.
OVERLAY = str(overlay_dir)

# As data, so they are copied as built (not UPX-packed or scanned for imports).
resources=[(f"{OVERLAY}/*.exe", "tools"), (f"{OVERLAY}/*.dll", "tools"),(f"{APP}/assets/audio/*", "assets/audio"), (f"{APP}/assets/images/*", "assets/images"), (f"{PYE3D}/refraction_models/*", "pye3d/refraction_models/"), (f"{APP}/assets/models/*", "assets/models"), (f"{OVERLAY}/assets/*", "tools/assets"), (f"{OVERLAY}/licenses/*", "tools/licenses"), (f"{APP}/lang/*", "lang/"), (f"{APP}/contributions/notice.json", "contributions")]

a = Analysis(
[os.path.join(APP, 'eyetrackapp.py')],
pathex=[APP],
binaries=[
    (os.path.abspath(openvr.__file__ + "\\..\\libopenvr_api_32.dll"), "openvr"),
    (os.path.abspath(openvr.__file__ + "\\..\\libopenvr_api_64.dll"), "openvr"),
],
datas=resources,
hiddenimports=['cv2', 'numpy', 'sv_ttk', 'tkinter', 'tkinter.ttk', 'pywinstyles',
               # Pillow's Tk bridge, imported lazily by name inside ImageTk, so
               # PyInstaller misses it; without it previews never draw.
               'PIL.Image', 'PIL.ImageTk', 'PIL._tkinter_finder',
               'pyrage', 'webview', 'webview.platforms.winforms',
               'webview.platforms.edgechromium'],
hookspath=[],
hooksconfig={},
runtime_hooks=[],
excludes=[],
win_no_prefer_redirects=False,
win_private_assemblies=False,
cipher=block_cipher,
noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# A folder build (exe + _internal), like Linux: a one-file exe unpacks all of its models
# and runtimes to %TEMP% on every launch.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='eyetrackapp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(APP, "assets", "images", "logo.ico"),
)

# Named "dist" so the output is <distpath>/dist/eyetrackapp.exe: built with
# --distpath build/windows, the layout the installer and build_release.bat use
# (build/windows/dist/eyetrackapp.exe, native integrations beside it) stays the same.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='dist',
)
