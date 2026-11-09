# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

project_dir = os.path.abspath(SPECPATH)

added_datas = [
    (os.path.join(project_dir, 'vortex-hub'), 'vortex-hub'),
    (os.path.join(project_dir, 'hp_fan_controller.ps1'), '.'),
    (os.path.join(project_dir, 'vortex_icon.ico'), '.'),
    (os.path.join(project_dir, 'tray_manager.py'), '.'),
]

a = Analysis(
    ['vortex_engine.py'],
    pathex=[project_dir],
    binaries=[],
    datas=added_datas,
    hiddenimports=[
        'psutil',
        'pycaw',
        'pycaw.pycaw',
        'comtypes',
        'comtypes.client',
        'ctypes',
        'ctypes.wintypes',
        'winreg',
        'http.server',
        'urllib.request',
        'json',
        'threading',
        'subprocess',
        'time',
        'sys',
        'os',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas', 'unittest', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VortexCoreHub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'vortex_icon.ico'),
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VortexCoreHub',
)
