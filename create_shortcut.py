import os
import sys

desktop = os.path.expanduser("~/Desktop")
lnk_path = os.path.join(desktop, "VortexCore Hub.lnk")
target_bat = os.path.abspath(os.path.join(os.path.dirname(__file__), "Iniciar VortexCore.bat"))
icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "vortex_icon.ico"))
work_dir = os.path.abspath(os.path.dirname(__file__))

ps_code = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{lnk_path}')
$s.TargetPath = '{target_bat}'
$s.WorkingDirectory = '{work_dir}'
$s.IconLocation = '{icon_path}, 0'
$s.Description = 'VortexCore Hub - Hardware Suite para Windows 11'
$s.Save()

# Set Run As Administrator flag in .lnk byte 0x15
$bytes = [System.IO.File]::ReadAllBytes('{lnk_path}')
$bytes[0x15] = $bytes[0x15] -bor 0x20
[System.IO.File]::WriteAllBytes('{lnk_path}', $bytes)
Write-Output "SUCCESS"
"""

import subprocess
res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], capture_output=True, text=True)
if "SUCCESS" in res.stdout:
    print(f"Acceso directo creado exitosamente en: {lnk_path}")
else:
    print(f"Error: {res.stderr}")
