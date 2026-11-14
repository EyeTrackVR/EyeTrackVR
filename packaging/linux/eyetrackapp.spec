# -*- mode: python ; coding: utf-8 -*-
# Linux build of EyeTrackVR. Differences from the Windows spec (packaging/windows/eyetrackapp.spec):
#   - onedir (COLLECT) instead of onefile: faster startup, standard for tarballs
#   - openvr ships libopenvr_api*.so on Linux, discovered by glob
#   - Windows-only packages (pywinstyles/pygrabber/winotify/winsound) excluded
#   - native Linux overlay and its loaders are required, with assets alongside
#   - no .ico icon (Linux icons come from the .desktop entry + logo.png)
#
# aarch64 (Steam Frame, packaging/steamframe/build.sh) differences:
#   - the pyopenvr wheel only ships x86 libs, so the arm64 libopenvr_api.so is
#     supplied via ETVR_OPENVR_LIB and bundled under the name pyopenvr loads

import glob
import importlib.util
import os
import platform
import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
APP = ROOT / "eyetrackapp"
# pye3d loads its refraction models from its own package folder.
PYE3D = importlib.util.find_spec("pye3d").submodule_search_locations[0]

# Models live in Git LFS; refuse to bundle the pointer files a clone without git-lfs leaves.
for _model in glob.glob(os.path.join(APP, "assets", "models", "*.onnx")):
    with open(_model, "rb") as _f:
        if _f.read(8) == b"version ":
            sys.exit(f"{_model} is a Git LFS pointer; run `git lfs pull` first.")

block_cipher = None

resources = [
    (f"{APP}/contributions/notice.json", "contributions"),
    (f"{APP}/assets/audio/*", "assets/audio"),
    (f"{APP}/assets/images/*", "assets/images"),
    (f"{PYE3D}/refraction_models/*", "pye3d/refraction_models/"),
    (f"{APP}/assets/models/*", "assets/models"),
    (f"{APP}/lang/*", "lang/"),
]

IS_ARM64 = platform.machine() in ("aarch64", "arm64")

if IS_ARM64:
    # pyopenvr picks libopenvr_api_64.so by pointer size, not CPU arch, and
    # PyInstaller binaries keep their source name, so the file must be named so.
    openvr_lib = Path(os.environ.get("ETVR_OPENVR_LIB", ""))
    if not openvr_lib.is_file() or openvr_lib.name != "libopenvr_api_64.so":
        raise FileNotFoundError("Set ETVR_OPENVR_LIB to an aarch64 libopenvr_api_64.so (packaging/steamframe/build.sh fetches one)")
    openvr_libs = [(str(openvr_lib), "openvr")]
else:
    import openvr

    # The pyopenvr wheel bundles per-arch shared libs next to openvr/__init__.py.
    _openvr_dir = Path(openvr.__file__).parent
    openvr_libs = [(str(p), "openvr") for p in _openvr_dir.glob("libopenvr_api*.so")]

# The overlay runtime. The app always looks for it in tools/linux/.
sys.path.insert(0, str(ROOT / "packaging"))
from fetch_overlay import fetch

overlay_dir = fetch("linux-arm64" if IS_ARM64 else "linux")
overlay_libs = [(str(p), "tools/linux") for p in [overlay_dir / "EyeTrackVR-Overlay", *overlay_dir.glob("*.so*")]]
resources.append((f"{overlay_dir.as_posix()}/assets/*", "tools/linux/assets/"))
resources.append((f"{overlay_dir.as_posix()}/licenses/*", "tools/linux/licenses"))

a = Analysis(
    [str(APP / "eyetrackapp.py")],
    pathex=[str(APP)],
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
