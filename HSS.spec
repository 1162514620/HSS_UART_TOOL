# -*- mode: python ; coding: utf-8 -*-
import sys
import os

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (r'C:\Users\sun\AppData\Local\Programs\Python\Python310\lib\site-packages\ttkbootstrap\assets', 'ttkbootstrap/assets'),
    ],
    hiddenimports=[
        'serial',
        'ttkbootstrap',
        'ttkbootstrap.constants',
        'ttkbootstrap.themes',
        'ttkbootstrap.themes.standard',
        'matplotlib',
        'matplotlib.backends.backend_tkagg',
        'numpy',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HSS串口助手',
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
)
