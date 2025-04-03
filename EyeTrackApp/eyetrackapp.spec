# -*- mode: python ; coding: utf-8 -*-

import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)
import openvr

block_cipher = None

resources=[("Audio/*", "Audio"), ("Images/*", "Images/"), ("pye3d/refraction_models/*", "pye3d/refraction_models/"), ("Models/*", "Models/"),("Tools/*", "Tools/")]

a = Analysis(
['eyetrackapp.py'],
pathex=[],
binaries=[
    (os.path.abspath(openvr.__file__ + "\\..\\libopenvr_api_32.dll"), "openvr"),
    (os.path.abspath(openvr.__file__ + "\\..\\libopenvr_api_64.dll"), "openvr"),
],
datas=resources,
hiddenimports=['cv2', 'numpy', 'PySimpleGui', 'pkg_resources.extern'],
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='eyetrackapp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="Images/logo.ico", 
)