import os
import sys
import subprocess

desktop = os.path.expanduser("~/Desktop")
lnk_path = os.path.join(desktop, "VortexCore Hub.lnk")
work_dir = os.path.abspath(os.path.dirname(__file__))
vbs_runner = os.path.abspath(os.path.join(work_dir, "run_vortex.vbs"))
icon_path = os.path.abspath(os.path.join(work_dir, "vortex_icon.ico"))
wscript_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")

ps_code = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{lnk_path}')
$s.TargetPath = '{wscript_exe}'
$s.Arguments = '"{vbs_runner}"'
$s.WorkingDirectory = '{work_dir}'
$s.IconLocation = '{icon_path}, 0'
$s.Description = 'VortexCore Hub - Hardware Suite para Windows 11'
$s.Save()

# Activar bandera 'Ejecutar como Administrador' en byte 0x15
$bytes = [System.IO.File]::ReadAllBytes('{lnk_path}')
$bytes[0x15] = $bytes[0x15] -bor 0x20
[System.IO.File]::WriteAllBytes('{lnk_path}', $bytes)
Write-Output "SUCCESS"
"""

res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], capture_output=True, text=True)
if "SUCCESS" in res.stdout:
    print(f"Acceso directo creado exitosamente en: {lnk_path}")
else:
    print(f"Error: {res.stderr}")
