# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

project_dir = os.path.abspath(SPECPATH)

extra_datas = []
extra_binaries = []
extra_hiddenimports = []
for _pkg in ('HardwareMonitor', 'pythonnet', 'clr_loader'):
    try:
        _d, _b, _h = collect_all(_pkg)
        extra_datas += _d
        extra_binaries += _b
        extra_hiddenimports += _h
    except Exception:
        pass

# presentmon de intel para medir fps en el overlay (se descarga y verifica si falta)
PRESENTMON_URL = "https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/PresentMon-2.6.0-x64.exe"
PRESENTMON_SHA256 = "b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af"
presentmon_exe = os.path.join(project_dir, 'tools', 'PresentMon.exe')


def _sha256(path):
    import hashlib
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


if not os.path.isfile(presentmon_exe) or _sha256(presentmon_exe) != PRESENTMON_SHA256:
    import urllib.request
    os.makedirs(os.path.dirname(presentmon_exe), exist_ok=True)
    urllib.request.urlretrieve(PRESENTMON_URL, presentmon_exe)
    if _sha256(presentmon_exe) != PRESENTMON_SHA256:
        os.remove(presentmon_exe)
        raise SystemExit('presentmon descargado no coincide con el sha256 esperado')

# Solo los archivos de la interfaz web (sin carpetas de desarrollo)
hub_dir = os.path.join(project_dir, 'vortex-hub')
hub_files = [
    (os.path.join(hub_dir, f), 'vortex-hub')
    for f in os.listdir(hub_dir)
    if os.path.isfile(os.path.join(hub_dir, f))
]

added_datas = hub_files + [
    (os.path.join(project_dir, 'hp_fan_controller.ps1'), '.'),
    (os.path.join(project_dir, 'acer_fan_controller.ps1'), '.'),
    (os.path.join(project_dir, 'oem_fan_controller.ps1'), '.'),
    (os.path.join(project_dir, 'vortex_icon.ico'), '.'),
    (os.path.join(project_dir, 'VERSION'), '.'),
    (presentmon_exe, 'tools'),
]

a = Analysis(
    ['vortex_engine.py'],
    pathex=[project_dir],
    binaries=extra_binaries,
    datas=added_datas + extra_datas,
    hiddenimports=[
        'hw_sensors',
        'tray_manager',
        'fps_monitor',
        'game_overlay',
        'net_monitor',
        'updater',
        'game_mode',
        'psutil',
        'pycaw',
        'pycaw.pycaw',
        'comtypes',
        'comtypes.client',
        'HardwareMonitor',
        'HardwareMonitor.Hardware',
        'pythonnet',
        'clr_loader',
        'cffi',
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
    ] + extra_hiddenimports,
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
