# -*- mode: py -3.10 ; coding: utf-8 -*-
import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)
block_cipher = None


a = Analysis(['eyetrackapp.py'],
             pathex=[],
             binaries=[],
             datas=[("Audio/*", "Audio"), ("Images/*", "Images/"), ("pye3d/refraction_models/*", "pye3d/refraction_models/"), ("Models/*", "Models/")],
             hiddenimports=['cv2', 'numpy', 'PySimpleGui'],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas, 
          [],
          exclude_binaries=True,
          name='eyetrackapp',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True,
          runtime_tmpdir=None,
          disable_windowed_traceback=False,
          argv_emulation=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None,
          icon="Images/logo.ico" )

