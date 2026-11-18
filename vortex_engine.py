"""
================================================================================
  VortexCore Hub // Backend Engine
  - Servidor REST local ultra-rápido (500ms)
  - Control WMI BIOS HP (Opcode 0x27 Max Fan & 0x2D RPM)
  - Soporte de Sliders de CPU Throttle, Turbo Boost Switch, Liberar RAM
  - Ejecución en ventana de escritorio nativa acelerada por GPU (WebView2)
================================================================================
"""

import sys
import os
import json
import time
import ctypes
from ctypes import wintypes
import threading
import subprocess
import winreg
import platform
import socket
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import hw_sensors
import fps_monitor
import game_overlay
import net_monitor
from tray_manager import SystemTrayApp, is_autostart_enabled, set_autostart, migrate_legacy_autostart

# Modo línea de comandos para el instalador: "--set-autostart on|off" configura y sale
# (se procesa antes de crear el gestor de hardware, que arranca hilos de monitoreo).
if __name__ == "__main__" and "--set-autostart" in sys.argv:
    _idx = sys.argv.index("--set-autostart")
    _val = sys.argv[_idx + 1].lower() if len(sys.argv) > _idx + 1 else "on"
    sys.exit(0 if set_autostart(_val in ("on", "1", "true", "yes")) else 1)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    from pycaw.pycaw import AudioUtilities
    import comtypes
    HAS_PYCAW = True
except Exception:
    HAS_PYCAW = False


def get_audio_mixer_data() -> dict:
    """Obtiene el volumen maestro y todas las aplicaciones con audio activo (estilo EarTrumpet)."""
    res = {
        "master": {"volume": None, "muted": None, "device_name": None},
        "apps": []
    }
    if not HAS_PYCAW:
        return res

    try:
        comtypes.CoInitialize()
        spk = AudioUtilities.GetSpeakers()
        if spk:
            vol = spk.EndpointVolume
            res["master"]["volume"] = int(round(vol.GetMasterVolumeLevelScalar() * 100))
            res["master"]["muted"] = bool(vol.GetMute())
            res["master"]["device_name"] = getattr(spk, "FriendlyName", "Altavoces")
    except Exception:
        pass

    try:
        sessions = AudioUtilities.GetAllSessions()
        for s in sessions:
            try:
                v = s.SimpleAudioVolume
                vol_pct = int(round(v.GetMasterVolume() * 100))
                muted = bool(v.GetMute())
                if s.Process:
                    raw_name = s.Process.name()
                    pid = s.ProcessId
                else:
                    raw_name = "Sonidos del Sistema"
                    pid = 0

                # Evitar entradas vacías o duplicados exactos de PID
                if any(x["pid"] == pid and x["name"] == raw_name for x in res["apps"]):
                    continue

                nl = raw_name.lower()
                if "spotify" in nl:
                    disp = "Spotify"
                    icon = "🎵"
                elif "discord" in nl:
                    disp = "Discord"
                    icon = "💬"
                elif "chrome" in nl:
                    disp = "Google Chrome"
                    icon = "🌐"
                elif "brave" in nl:
                    disp = "Brave Browser"
                    icon = "🦁"
                elif "edge" in nl:
                    disp = "Microsoft Edge"
                    icon = "🌊"
                elif "steam" in nl:
                    disp = "Steam"
                    icon = "🎮"
                elif any(g in nl for g in ["cs2", "valorant", "cyberpunk", "cod", "fortnite", "apex", "game"]):
                    disp = raw_name.replace(".exe", "")
                    icon = "🎯"
                elif "system" in nl or "sonidos" in nl:
                    disp = "Sonidos del Sistema"
                    icon = "🔔"
                else:
                    disp = raw_name.replace(".exe", "")
                    icon = "🔊"

                res["apps"].append({
                    "pid": pid,
                    "name": raw_name,
                    "display_name": disp,
                    "volume": vol_pct,
                    "muted": muted,
                    "icon": icon
                })
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass

    return res


def set_app_volume_state(pid: int = None, name: str = None, volume: float = None, muted: bool = None) -> bool:
    """Ajusta el volumen o silencio de una app específica (como Spotify) en Windows."""
    if not HAS_PYCAW:
        return False
    found = False
    try:
        comtypes.CoInitialize()
        sessions = AudioUtilities.GetAllSessions()
        for s in sessions:
            match = False
            if pid is not None and pid != 0 and s.ProcessId == pid:
                match = True
            elif s.Process and name and s.Process.name().lower() == name.lower():
                match = True
            elif not s.Process and name and any(k in name.lower() for k in ["system", "sonidos"]):
                match = True

            if match:
                v = s.SimpleAudioVolume
                if volume is not None:
                    target = max(0.0, min(1.0, float(volume) / 100.0))
                    v.SetMasterVolume(target, None)
                if muted is not None:
                    v.SetMute(bool(muted), None)
                found = True
    except Exception:
        pass
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass
    return found


def set_master_volume_state(volume: float = None, muted: bool = None) -> bool:
    """Ajusta el volumen general del dispositivo de salida de Windows."""
    if not HAS_PYCAW:
        return False
    ok = False
    try:
        comtypes.CoInitialize()
        spk = AudioUtilities.GetSpeakers()
        if spk:
            vol = spk.EndpointVolume
            if volume is not None:
                val = max(0.0, min(1.0, float(volume) / 100.0))
                vol.SetMasterVolumeLevelScalar(val, None)
            if muted is not None:
                vol.SetMute(bool(muted), None)
            ok = True
    except Exception:
        pass
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass
    return ok

CREATE_NO_WINDOW = 0x08000000
PORT = 8765


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def get_app_dir() -> str:
    """Retorna el directorio base de la aplicación (compatible con PyInstaller y script estándar)."""
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_app_version() -> str:
    """Versión del archivo VERSION (se empaqueta junto a la app). 'dev' si no está."""
    try:
        with open(os.path.join(get_app_dir(), "VERSION"), encoding="utf-8") as vf:
            return vf.read().strip() or "dev"
    except OSError:
        return "dev"


APP_VERSION = get_app_version()


def request_admin_elevation():
    if not is_admin():
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        if getattr(sys, 'frozen', False):
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
        else:
            script = os.path.abspath(sys.argv[0])
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{script}" {params}', None, 1
            )
        if ret > 32:
            sys.exit(0)


class DefaultGUIDs:
    SAVER = "a1841308-3541-4fab-bc81-f71556f20b4a"
    BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
    HIGH_PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
    SUBGROUP_PROC = "54533251-82be-4824-96c1-47b60b740d00"
    THROTTLE_MAX = "bc5038f7-23e0-4960-96da-33abaf5935ec"
    THROTTLE_MIN = "893dee8e-2bef-41e0-89c6-b55d0929964c"
    TURBO_BOOST = "be337238-0d82-4146-a960-4f3749d470c7"
    # Windows 10/11 Modern Standby Power Mode Overlays (Slider de Energía)
    OVERLAY_SAVER = "961cc777-2547-4f9d-8174-7d86181b8a7a"
    OVERLAY_BALANCED = "00000000-0000-0000-0000-000000000000"
    OVERLAY_HIGH_PERF = "ded574b5-45a0-4f42-8737-46345c09c238"


def set_windows_power_overlay(guid_str: str) -> bool:
    """Cambia el modo de energía moderno de Windows (funciona en laptops Modern Standby)."""
    if sys.platform != "win32":
        return False
    try:
        import uuid
        raw = uuid.UUID(guid_str).bytes_le
        buf = ctypes.create_string_buffer(raw, 16)
        powrprof = ctypes.WinDLL("powrprof")
        rc = powrprof.PowerSetActiveOverlayScheme(buf)
        return rc == 0
    except Exception:
        return False


# ==============================================================================
# 1. DETECCIÓN DINÁMICA DE HARDWARE REAL (ESPECIFICACIONES DE SILICIO)
# ==============================================================================
def get_system_specs() -> dict:
    """Detecta de forma dinámica la marca, modelo, CPU, GPU y memoria del equipo actual."""
    mfg = "PC Universal"
    model = "Equipo de Rendimiento"
    board = ""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS", 0, winreg.KEY_READ) as k:
            try: mfg, _ = winreg.QueryValueEx(k, "SystemManufacturer")
            except Exception: pass
            try: model, _ = winreg.QueryValueEx(k, "SystemProductName")
            except Exception: pass
            try: board, _ = winreg.QueryValueEx(k, "BaseBoardProduct")
            except Exception: pass
    except Exception:
        pass

    mfg = str(mfg).strip()
    model = str(model).strip()
    if not mfg or mfg.lower() in ("system manufacturer", "to be filled by o.e.m."):
        mfg = "Personalizado"
    if not model or model.lower() in ("system product name", "to be filled by o.e.m."):
        model = f"Placa Base {board}" if board else "Estación de Trabajo"

    # CPU
    cpu_name = "Procesador Multi-Núcleo"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", 0, winreg.KEY_READ) as k:
            cpu_raw, _ = winreg.QueryValueEx(k, "ProcessorNameString")
            cpu_name = str(cpu_raw).strip()
    except Exception:
        pass

    # GPU
    gpu_name = "Gráficos de Sistema"
    gpus = []
    try:
        class_base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, class_base, 0, winreg.KEY_READ) as ck:
            for i in range(winreg.QueryInfoKey(ck)[0]):
                sub = winreg.EnumKey(ck, i)
                if sub.isdigit():
                    try:
                        with winreg.OpenKey(ck, sub, 0, winreg.KEY_READ) as sk:
                            desc, _ = winreg.QueryValueEx(sk, "DriverDesc")
                            if desc and not desc.lower().startswith("microsoft basic"):
                                gpus.append(str(desc).strip())
                    except Exception:
                        pass
    except Exception:
        pass

    dedicated = [g for g in gpus if any(k in g.lower() for k in ["geforce", "rtx", "gtx", "quadro", "radeon rx", "radeon pro"])]
    if dedicated:
        gpu_name = dedicated[0]
    elif gpus:
        gpu_name = gpus[0]

    # Memoria RAM
    ram_gb = 16
    if HAS_PSUTIL:
        try:
            mem = psutil.virtual_memory()
            ram_gb = int(round(mem.total / (1024**3)))
        except Exception:
            pass

    # Sistema Operativo
    os_name = f"Windows {platform.release()}"

    # Detección de Fabricante
    mfg_lower = mfg.lower()
    model_lower = model.lower()
    is_hp = any(k in mfg_lower for k in ["hp", "hewlett"]) or any(k in model_lower for k in ["victus", "omen", "pavilion", "envy", "elitebook"])
    is_asus = "asus" in mfg_lower or "rog" in model_lower or "tuf" in model_lower or "zenbook" in model_lower or "vivobook" in model_lower
    is_lenovo = "lenovo" in mfg_lower or "legion" in model_lower or "loq" in model_lower or "ideapad" in model_lower or "thinkpad" in model_lower
    is_dell = "dell" in mfg_lower or "alienware" in model_lower or "inspiron" in model_lower or "xps" in model_lower or "latitude" in model_lower
    is_acer = "acer" in mfg_lower or "nitro" in model_lower or "predator" in model_lower or "swift" in model_lower or "aspire" in model_lower
    is_msi = "msi" in mfg_lower or "micro-star" in mfg_lower
    is_huawei = "huawei" in mfg_lower or "matebook" in model_lower
    is_samsung = "samsung" in mfg_lower or "galaxy book" in model_lower
    is_lg = "lg electronics" in mfg_lower or "gram" in model_lower
    is_gigabyte = "gigabyte" in mfg_lower or "aorus" in model_lower or "aero" in model_lower
    is_razer = "razer" in mfg_lower or "blade" in model_lower

    if is_hp: brand = "HP"
    elif is_asus: brand = "ASUS"
    elif is_lenovo: brand = "Lenovo"
    elif is_dell: brand = "Dell / Alienware"
    elif is_acer: brand = "Acer"
    elif is_msi: brand = "MSI"
    elif is_huawei: brand = "Huawei"
    elif is_samsung: brand = "Samsung"
    elif is_lg: brand = "LG"
    elif is_gigabyte: brand = "Gigabyte / AORUS"
    elif is_razer: brand = "Razer"
    else: brand = mfg

    gpu_low = gpu_name.lower()
    if any(k in gpu_low for k in ["nvidia", "geforce", "rtx", "gtx", "quadro"]):
        gpu_vendor = "nvidia"
    elif any(k in gpu_low for k in ["amd", "radeon"]):
        gpu_vendor = "amd"
    elif "intel" in gpu_low:
        gpu_vendor = "intel"
    else:
        gpu_vendor = "other"

    # Versiones amigables cortas
    cpu_short = cpu_name
    for r in ["13th Gen ", "12th Gen ", "14th Gen ", "11th Gen ", "(R)", "(TM)", "Processor", "Core"]:
        cpu_short = cpu_short.replace(r, "")
    cpu_short = " ".join(cpu_short.split())

    gpu_short = gpu_name
    for r in ["NVIDIA ", "GeForce ", "Laptop GPU", "Graphics"]:
        gpu_short = gpu_short.replace(r, "")
    gpu_short = " ".join(gpu_short.split())

    model_short = model.replace("Victus by HP Gaming Laptop", "Victus").replace("HP ", "").strip()

    return {
        "manufacturer": brand,
        "model": model,
        "model_short": model_short,
        "cpu": cpu_name,
        "cpu_short": cpu_short,
        "gpu": gpu_name,
        "gpu_short": gpu_short,
        "ram": f"{ram_gb} GB",
        "ram_gb": ram_gb,
        "os": os_name,
        "arch": platform.machine() or "AMD64",
        "gpu_vendor": gpu_vendor,
        "is_hp": is_hp,
        "is_asus": is_asus,
        "is_lenovo": is_lenovo,
        "is_dell": is_dell,
        "is_acer": is_acer,
        "is_msi": is_msi,
        "fans_supported": is_hp or is_acer or is_lenovo or is_asus or is_dell
    }


# ==============================================================================
# 2. GESTOR DE APLICACIONES DE INICIO DE WINDOWS (NATIVO WINDOWS 10 / 11)
# ==============================================================================
def _set_startup_approved_registry(root, name: str, enable: bool) -> bool:
    """Actualiza el registro nativo StartupApproved\\Run de Windows (0x02=Habilitado, 0x03=Deshabilitado)."""
    sub = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    try:
        existing_val = None
        try:
            with winreg.OpenKey(root, sub, 0, winreg.KEY_READ) as k:
                existing_val, _ = winreg.QueryValueEx(k, name)
        except Exception:
            pass

        if isinstance(existing_val, (bytes, bytearray)) and len(existing_val) >= 4:
            new_val = bytearray(existing_val)
            new_val[0] = 0x02 if enable else 0x03
        else:
            new_val = bytearray([0x02 if enable else 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

        with winreg.CreateKey(root, sub) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, bytes(new_val))
        return True
    except Exception:
        return False


def get_startup_apps() -> list[dict]:
    """Obtiene la lista de aplicaciones que inician automáticamente con Windows sincronizada con Task Manager."""
    apps = []
    seen = set()

    # 1. Leer estado real en StartupApproved\Run (Usuario y Sistema)
    user_approved = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run", 0, winreg.KEY_READ) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, val, _ = winreg.EnumValue(k, i)
                if isinstance(val, (bytes, bytearray)) and len(val) > 0:
                    user_approved[name.lower()] = (val[0] % 2 == 0)
    except Exception:
        pass

    sys_approved = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run", 0, winreg.KEY_READ) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, val, _ = winreg.EnumValue(k, i)
                if isinstance(val, (bytes, bytearray)) and len(val) > 0:
                    sys_approved[name.lower()] = (val[0] % 2 == 0)
    except Exception:
        pass

    # 2. Restaurar cualquier clave que haya quedado en Run_VortexDisabled de versiones previas
    for root, app_dict in [
        (winreg.HKEY_CURRENT_USER, user_approved),
        (winreg.HKEY_LOCAL_MACHINE, sys_approved)
    ]:
        dis_path = r"Software\Microsoft\Windows\CurrentVersion\Run_VortexDisabled"
        run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(root, dis_path, 0, winreg.KEY_READ) as dk:
                to_restore = []
                for i in range(winreg.QueryInfoKey(dk)[1]):
                    name, val, typ = winreg.EnumValue(dk, i)
                    to_restore.append((name, val, typ))
                for name, val, typ in to_restore:
                    try:
                        with winreg.CreateKey(root, run_path) as rk:
                            winreg.SetValueEx(rk, name, 0, typ, val)
                        with winreg.OpenKey(root, dis_path, 0, winreg.KEY_SET_VALUE) as sk:
                            winreg.DeleteValue(sk, name)
                        app_dict[name.lower()] = False
                        _set_startup_approved_registry(root, name, False)
                    except Exception:
                        pass
        except Exception:
            pass

    # 3. Enumerar HKCU\...\Run
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, val, _ = winreg.EnumValue(k, i)
                nl = name.lower()
                seen.add(nl)
                is_enabled = user_approved.get(nl, True)
                base_impact = "Alto" if any(w in nl for w in ["discord", "steam", "epic", "spotify", "teams", "overwolf"]) else "Medio"
                apps.append({
                    "name": name,
                    "command": str(val),
                    "scope": "user",
                    "enabled": is_enabled,
                    "impact": base_impact if is_enabled else "Deshabilitado"
                })
    except Exception:
        pass

    # 4. Enumerar HKLM\...\Run
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, val, _ = winreg.EnumValue(k, i)
                nl = name.lower()
                if nl not in seen:
                    seen.add(nl)
                    is_enabled = user_approved.get(nl, sys_approved.get(nl, True))
                    base_impact = "Alto" if any(w in nl for w in ["lghub", "razer", "armoury", "omen", "steelseries"]) else "Bajo"
                    apps.append({
                        "name": name,
                        "command": str(val),
                        "scope": "system",
                        "enabled": is_enabled,
                        "impact": base_impact if is_enabled else "Deshabilitado"
                    })
    except Exception:
        pass

    return apps


def toggle_startup_app(name: str, scope: str = "user", enable: bool = True) -> bool:
    """Habilita o deshabilita una aplicación de inicio en StartupApproved\\Run (sincronizado con Windows)."""
    root_key = winreg.HKEY_LOCAL_MACHINE if scope == "system" else winreg.HKEY_CURRENT_USER
    success = _set_startup_approved_registry(root_key, name, enable)

    if not success or scope == "system":
        if _set_startup_approved_registry(winreg.HKEY_CURRENT_USER, name, enable):
            success = True

    if not success:
        try:
            hex_data = "020000000000000000000000" if enable else "030000000000000000000000"
            sub = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
            cmd = ["reg", "add", sub, "/v", name, "/t", "REG_BINARY", "/d", hex_data, "/f"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW)
            success = (res.returncode == 0)
        except Exception:
            pass

    return success


# ==============================================================================
# 3. WINDOWS DEBLOATER (PROTECCIÓN TOTAL DE MICROSOFT EDGE)
# ==============================================================================
SAFE_DEBLOAT_CATALOG = [
    {"id": "Microsoft.BingNews", "name": "Microsoft Noticias", "desc": "Feed de noticias MSN y telemetría de contenido en segundo plano", "category": "Noticias & Feed", "size": "~35 MB"},
    {"id": "Microsoft.BingWeather", "name": "Microsoft El Tiempo", "desc": "Widget del clima y telemetría de ubicación periódica", "category": "Tiempo", "size": "~42 MB"},
    {"id": "Microsoft.GetHelp", "name": "Obtener Ayuda", "desc": "Asistente web de soporte técnico de Windows", "category": "Utilidades", "size": "~18 MB"},
    {"id": "Microsoft.Getstarted", "name": "Sugerencias de Windows", "desc": "Consejos emergentes y recomendaciones promocionales de apps", "category": "Publicidad", "size": "~24 MB"},
    {"id": "Microsoft.MicrosoftSolitaireCollection", "name": "Colección Solitario", "desc": "Juegos casuales preinstalados con anuncios integrados", "category": "Juegos", "size": "~78 MB"},
    {"id": "Microsoft.People", "name": "Contactos de Windows", "desc": "Antigua libreta de contactos UWP descontinuada", "category": "Comunicación", "size": "~30 MB"},
    {"id": "Microsoft.Todos", "name": "Microsoft To-Do", "desc": "Aplicación de tareas en la nube y sincronización", "category": "Productividad", "size": "~45 MB"},
    {"id": "Microsoft.WindowsFeedbackHub", "name": "Centro de Opiniones", "desc": "Módulo de diagnósticos, encuestas y telemetría", "category": "Telemetría", "size": "~55 MB"},
    {"id": "Microsoft.YourPhone", "name": "Enlace Móvil", "desc": "Sincronización con teléfono móvil en segundo plano", "category": "Conectividad", "size": "~85 MB"},
    {"id": "Microsoft.ZuneVideo", "name": "Películas y TV", "desc": "Reproductor antiguo de video UWP de Microsoft", "category": "Multimedia", "size": "~60 MB"},
    {"id": "Clipchamp.Clipchamp", "name": "Editor Clipchamp", "desc": "Editor de video en la nube promocionado por Windows", "category": "Multimedia", "size": "~90 MB"},
    {"id": "Microsoft.549981C3F5F10", "name": "Cortana", "desc": "Asistente de voz Cortana en desuso por Microsoft", "category": "Asistente", "size": "~40 MB"},
]

# LISTA NEGRA ESTRICTA: ESTAS APLICACIONES NUNCA SE PUEDEN ELIMINAR (EDGE BLINDADO)
PROTECTED_APP_SUBSTRINGS = ["edge", "microsoftedge", "webview", "store", "windowsstore", "calculator", "terminal", "photos"]

def get_installed_debloat_apps() -> list[dict]:
    """Escanea las aplicaciones de bloatware seguras que están actualmente instaladas."""
    installed_ids = set()
    try:
        ps_cmd = "$ErrorActionPreference = 'SilentlyContinue'; (Get-AppxPackage).Name"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=8, creationflags=CREATE_NO_WINDOW)
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.splitlines():
                if line.strip():
                    installed_ids.add(line.strip().lower())
    except Exception:
        pass

    results = []
    for item in SAFE_DEBLOAT_CATALOG:
        is_inst = any(item["id"].lower() == pkg for pkg in installed_ids)
        results.append({
            **item,
            "installed": is_inst
        })
    return results

def remove_debloat_apps(app_ids: list[str]) -> dict:
    """Desinstala las apps seleccionadas con estricta protección de Microsoft Edge."""
    removed = []
    failed = []
    for app_id in app_ids:
        app_lower = app_id.lower()
        # BLINDAJE DE MICROSOFT EDGE Y COMPONENTES CRÍTICOS
        if any(p in app_lower for p in PROTECTED_APP_SUBSTRINGS):
            print(f"BLOQUEADO POR SEGURIDAD: {app_id} es un componente protegido.")
            continue

        if not any(item["id"].lower() == app_lower for item in SAFE_DEBLOAT_CATALOG):
            continue

        try:
            ps_cmd = f"$ErrorActionPreference = 'SilentlyContinue'; Get-AppxPackage -Name '{app_id}' | Remove-AppxPackage"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=20, creationflags=CREATE_NO_WINDOW)
            if res.returncode == 0:
                removed.append(app_id)
            else:
                failed.append(app_id)
        except Exception:
            failed.append(app_id)

    return {"status": "ok", "removed": removed, "failed": failed}


# ==============================================================================
# 3.1 LIMPIADOR REAL DE TEMPORALES, CACHÉ DE SHADERS Y PAPELERA
# ==============================================================================
def _cleanup_specs() -> list[dict]:
    local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    win_root = os.environ.get("SystemRoot", r"C:\Windows")
    user_temp = os.environ.get("TEMP") or os.path.join(local_app, "Temp")
    return [
        {
            "id": "user_temp",
            "name": "Temporales de usuario (%TEMP%)",
            "desc": "Archivos temporales creados por instaladores y aplicaciones.",
            "default_checked": True,
            "paths": [user_temp],
        },
        {
            "id": "win_temp",
            "name": "Temporales de Windows",
            "desc": "Archivos temporales del sistema operativo en Windows\\Temp.",
            "default_checked": True,
            "paths": [os.path.join(win_root, "Temp")],
        },
        {
            "id": "dx_shader",
            "name": "Caché de Shaders (DirectX / GPU)",
            "desc": "Caché de sombreadores (D3DSCache, NVIDIA y AMD). Los juegos la regeneran sola si hace falta.",
            "default_checked": True,
            "paths": [
                os.path.join(local_app, "D3DSCache"),
                os.path.join(local_app, "NVIDIA", "DXCache"),
                os.path.join(local_app, "NVIDIA", "GLCache"),
                os.path.join(local_app, "AMD", "DxCache"),
            ],
        },
        {
            "id": "crash_dumps",
            "name": "Volcados de errores (CrashDumps)",
            "desc": "Registros antiguos de cierres inesperados de programas.",
            "default_checked": True,
            "paths": [os.path.join(local_app, "CrashDumps")],
        },
        {
            "id": "win_update_cache",
            "name": "Caché de Windows Update",
            "desc": "Instaladores antiguos de actualizaciones ya aplicadas en SoftwareDistribution.",
            "default_checked": False,
            "paths": [os.path.join(win_root, "SoftwareDistribution", "Download")],
        },
        {
            "id": "recycle_bin",
            "name": "Papelera de reciclaje",
            "desc": "Vacía de forma definitiva los archivos que ya enviaste a la Papelera.",
            "default_checked": False,
            "paths": [],
            "special": "recycle_bin",
        },
    ]


CLEANUP_CATEGORY_IDS = {c["id"] for c in _cleanup_specs()}


def _query_recycle_bin() -> tuple[int, int]:
    """Devuelve (bytes_total, num_items) de la Papelera de reciclaje mediante Win32."""
    if sys.platform != "win32":
        return (0, 0)
    try:
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("i64Size", ctypes.c_int64),
                ("i64NumItems", ctypes.c_int64),
            ]
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        hr = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if hr == 0:
            return (max(0, int(info.i64Size)), max(0, int(info.i64NumItems)))
    except Exception:
        pass
    return (0, 0)


def _dir_size_and_count(dirs: list[str]) -> tuple[int, int]:
    total_bytes = 0
    file_count = 0
    stack = [d for d in dirs if d and os.path.isdir(d)]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                            file_count += 1
                    except OSError:
                        pass
        except OSError:
            pass
    return (total_bytes, file_count)


def scan_disk_cleanup() -> dict:
    """Calcula el espacio real recuperable por categoría de limpieza segura."""
    items = []
    total_bytes = 0
    for spec in _cleanup_specs():
        if spec.get("special") == "recycle_bin":
            b, cnt = _query_recycle_bin()
        else:
            b, cnt = _dir_size_and_count(spec["paths"])
        total_bytes += b
        items.append({
            "id": spec["id"],
            "name": spec["name"],
            "desc": spec["desc"],
            "default_checked": spec["default_checked"],
            "bytes": b,
            "mb": round(b / (1024 ** 2), 1),
            "files": cnt,
        })
    return {
        "items": items,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 ** 2), 1),
    }


def run_disk_cleanup(target_ids: list[str]) -> dict:
    """Elimina archivos de las categorías permitidas sin tocar archivos bloqueados en uso."""
    specs = {c["id"]: c for c in _cleanup_specs()}
    selected = [tid for tid in target_ids if tid in specs]
    freed_bytes = 0
    removed_files = 0
    skipped_locked = 0
    results = []

    for tid in selected:
        spec = specs[tid]
        cat_freed = 0
        cat_removed = 0
        cat_locked = 0

        if spec.get("special") == "recycle_bin":
            rb_bytes, rb_items = _query_recycle_bin()
            if rb_items > 0 or rb_bytes > 0:
                try:
                    # SHERB_NOCONFIRMATION(1) | SHERB_NOPROGRESSUI(2) | SHERB_NOSOUND(4)
                    hr = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
                    if hr == 0:
                        cat_freed = rb_bytes
                        cat_removed = rb_items
                except Exception:
                    pass
        else:
            for base in spec["paths"]:
                if not base or not os.path.isdir(base):
                    continue
                try:
                    for root, dirs_list, files in os.walk(base, topdown=False, followlinks=False):
                        for fname in files:
                            fp = os.path.join(root, fname)
                            try:
                                if os.path.islink(fp):
                                    continue
                                sz = os.path.getsize(fp)
                                os.unlink(fp)
                                cat_freed += sz
                                cat_removed += 1
                            except OSError:
                                cat_locked += 1
                        for dname in dirs_list:
                            dp = os.path.join(root, dname)
                            try:
                                if not os.path.islink(dp):
                                    os.rmdir(dp)
                            except OSError:
                                pass
                except OSError:
                    pass

        freed_bytes += cat_freed
        removed_files += cat_removed
        skipped_locked += cat_locked
        results.append({
            "id": tid,
            "freed_mb": round(cat_freed / (1024 ** 2), 1),
            "removed_files": cat_removed,
            "skipped_locked": cat_locked,
        })

    return {
        "status": "ok",
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / (1024 ** 2), 1),
        "removed_files": removed_files,
        "skipped_locked": skipped_locked,
        "results": results,
    }


# ==============================================================================
# 4. DIAGNÓSTICO Y OPTIMIZACIÓN DE HARDWARE INTELLIGENCE
# ==============================================================================
def diagnose_hardware_health(manager_obj) -> dict:
    """Realiza un diagnóstico de CPU, temperaturas, RAM y gobernadores."""
    specs = manager_obj.system_specs
    # Valores reales; si un sensor no está disponible se trata como "sin dato" (no se inventa)
    cpu_temp_raw = manager_obj.telemetry.get("cpu_temp")
    gpu_temp_raw = manager_obj.telemetry.get("gpu_temp")
    cpu_temp = cpu_temp_raw if cpu_temp_raw is not None else 0
    gpu_temp = gpu_temp_raw if gpu_temp_raw is not None else 0
    ram_pct = manager_obj.telemetry.get("ram_pct") or 0
    ram_free = manager_obj.telemetry.get("ram_free") or "N/D"

    score = 100
    recs = []

    # Solo se recomiendan acciones que la app ejecuta de verdad y que hacen falta ahora
    if cpu_temp >= 85:
        score -= 22
        recs.append({
            "id": "limit_cpu",
            "title": "Bajar la temperatura de la CPU",
            "desc": f"La CPU está a {cpu_temp}°C. Limitarla al 95% suele bajar varios grados sin una pérdida de rendimiento notable.",
            "impact": "Alto",
            "action": "limit_cpu"
        })
    elif cpu_temp >= 72:
        score -= 8
        recs.append({
            "id": "limit_cpu",
            "title": "Reducir el calor de la CPU",
            "desc": f"La CPU está a {cpu_temp}°C. Limitarla al 95% ayuda a mantenerla más fresca y silenciosa.",
            "impact": "Medio",
            "action": "limit_cpu"
        })

    if ram_pct > 70:
        score -= 15
        recs.append({
            "id": "clean_ram",
            "title": "Liberar memoria RAM",
            "desc": f"La RAM está al {ram_pct}% de uso. Liberar la memoria en espera deja más espacio para juegos y programas.",
            "impact": "Alto" if ram_pct > 85 else "Medio",
            "action": "clean_ram"
        })

    condition = "Buena" if score >= 85 else "Mejorable" if score >= 70 else "Requiere atención"

    return {
        "health_score": max(50, min(100, score)),
        "condition": condition,
        "specs": specs,
        "checks": [
            {
                "name": "Envolvente Térmica CPU",
                "value": f"{cpu_temp}°C" if cpu_temp_raw is not None else "N/D (sin sensor)",
                "status": "Normal" if cpu_temp < 75 else "Alerta",
                "optimal": cpu_temp < 75,
                "desc": f"{specs['cpu_short']} operando sin estrangulamiento térmico (Thermal Throttling)." if cpu_temp < 80 else "Temperatura elevada cercana al límite de silicio."
            },
            {
                "name": "Gráfica GPU",
                "value": f"{gpu_temp}°C" if gpu_temp_raw is not None else "N/D (sin sensor)",
                "status": "Óptima" if gpu_temp < 75 else "Alerta",
                "optimal": gpu_temp < 75,
                "desc": f"{specs['gpu_short']} con conmutación dinámica de energía activa."
            },
            {
                "name": "Presión de Memoria RAM",
                "value": f"{ram_free} GB libres ({ram_pct}% en uso)",
                "status": "Óptima" if ram_pct < 75 else "Elevada",
                "optimal": ram_pct < 75,
                "desc": f"Memoria física instalada de {specs['ram']} disponible."
            },
            {
                "name": "Control Térmico de Firmware",
                "value": "HP BIOS WMI Activo" if specs["is_hp"] else f"Gobernador Universal ({specs['manufacturer']})",
                "status": "Activo",
                "optimal": True,
                "desc": "Ventiladores y envolvente de potencia sincronizados con la arquitectura de silicio."
            }
        ],
        "recommendations": recs
    }


def select_primary_net_iface(stats: dict, addrs: dict, per_nic_io: dict) -> dict | None:
    """Elige la interfaz de red activa principal (descartando loopback si hay NIC real)."""
    if not stats:
        return None
    best = None
    best_score = None
    for name, st in stats.items():
        if not getattr(st, "isup", False):
            continue
        lname = name.lower()
        is_loopback = "loopback" in lname or lname == "lo"
        if is_loopback:
            continue

        ipv4 = None
        for addr in addrs.get(name, []):
            if getattr(addr, "family", None) == socket.AF_INET:
                ip = getattr(addr, "address", "") or ""
                if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                    ipv4 = ip
                    break

        io = per_nic_io.get(name)
        total_bytes = (getattr(io, "bytes_recv", 0) + getattr(io, "bytes_sent", 0)) if io else 0
        speed = getattr(st, "speed", 0) or 0
        # Prioriza: tener IPv4 asignada, tráfico acumulado (>0) y velocidad de enlace
        score = (1 if ipv4 else 0, 1 if total_bytes > 0 else 0, total_bytes, speed)
        if best_score is None or score > best_score:
            best_score = score
            best = {
                "name": name,
                "link_mbps": int(speed) if speed > 0 else None,
                "ipv4": ipv4,
            }
    return best


class VortexCoreManager:
    def __init__(self):
        self.fan_script = os.path.join(get_app_dir(), "hp_fan_controller.ps1")
        self.acer_fan_script = os.path.join(get_app_dir(), "acer_fan_controller.ps1")
        self.oem_fan_script = os.path.join(get_app_dir(), "oem_fan_controller.ps1")
        self._acer_wmi_ok = True
        self._oem_wmi_ok = True
        self._acer_last_manual = None
        self.current_profile = "STANDARD"
        self.fan_mode = "AUTO"
        self.system_specs = get_system_specs()

        # Lectores de sensores reales (sin valores inventados: None = "N/D" en la interfaz)
        self._counters = hw_sensors.SystemCounters()
        self.ram_modules = None
        threading.Thread(target=self._load_ram_modules, daemon=True).start()

        self.telemetry = {
            "cpu_temp": None,
            "cpu_freq": None,
            "cpu_freq_mhz": None,
            "cpu_volt_mv": None,      # Windows no expone el voltaje de CPU sin un driver de kernel
            "cpu_usage": 0,
            "cpu_cores_phys": psutil.cpu_count(logical=False) if HAS_PSUTIL else None,
            "cpu_cores_log": psutil.cpu_count(logical=True) if HAS_PSUTIL else None,
            "cpu_per_core": [],
            "cpu_core_temps": [],
            "cpu_acpi_zones": [],
            "cpu_temp_source": None,
            "cpu_msr_status": {
                "pawnio_installed": hw_sensors.is_pawnio_installed(),
                "is_admin": hw_sensors.is_admin(),
            },
            "network": {
                "iface": None,
                "link_mbps": None,
                "ipv4": None,
                "rx_bps": 0,
                "tx_bps": 0,
                "rx_total_mb": 0.0,
                "tx_total_mb": 0.0,
                "ping_ms": None,
            },
            "gpu_temp": None,
            "gpu_usage": None,
            "gpu_power": None,
            "gpu_freq_mhz": None,
            "gpu_mem_freq_mhz": None,
            "gpu_volt_mv": None,
            "gpu_vram_mb": None,
            "gpu_pcie": None,
            "gpu_power_limit": None,
            "gpu_pstate": None,
            "ram_pct": None,
            "ram_used": None,
            "ram_total": None,
            "ram_free": None,
            "ram_installed": self.system_specs.get("ram_gb"),
            "ram_cached": None,
            "ram_speed_mts": None,
            "disk_used_gb": None,
            "disk_total_gb": None,
            "disk_pct": None,
            "fan1_rpm": None,
            "fan2_rpm": None,
            "fan_target_pct": None,
            "fan_dba": None,          # no existe sensor acústico: se deja sin valor
            "fans_readable": bool(self.system_specs.get("fans_supported")),
            "current_profile": self.current_profile,
            "fan_mode": self.fan_mode,
            "system_specs": self.system_specs,
            "battery_devices": []
        }

        self.manual_config = None
        self._has_nvidia_smi = True
        self._net_prev = None
        self._ping_ms = None
        self._ping_busy = False
        self._core_temp_busy = False
        if HAS_PSUTIL:
            try:
                psutil.cpu_percent(interval=None, percpu=True)
            except Exception:
                pass
        self.running = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _refresh_ping(self):
        try:
            ms = hw_sensors.measure_ping_ms()
            self._ping_ms = ms
            net = dict(self.telemetry.get("network") or {})
            net["ping_ms"] = ms if net.get("iface") else None
            self.telemetry["network"] = net
        except Exception:
            pass
        finally:
            self._ping_busy = False

    def _refresh_core_temps(self):
        try:
            res = hw_sensors.read_per_core_temps()
            cores = res.get("cores") or []
            zones = res.get("acpi_zones") or []
            self.telemetry["cpu_core_temps"] = cores
            self.telemetry["cpu_acpi_zones"] = zones
            self.telemetry["cpu_temp_source"] = res.get("source")
            if self.telemetry.get("cpu_temp") is None:
                if cores:
                    v = int(round(max(c["temp_c"] for c in cores)))
                    if 0 < v <= 115:
                        self.telemetry["cpu_temp"] = v
                elif zones:
                    v = int(round(zones[0]["temp_c"]))
                    if 0 < v <= 115:
                        self.telemetry["cpu_temp"] = v
        except Exception:
            pass
        finally:
            self._core_temp_busy = False

    def _load_ram_modules(self):
        info = hw_sensors.read_ram_modules()
        if info:
            self.ram_modules = info
            self.telemetry["ram_installed"] = info["installed_gb"]
            self.telemetry["ram_speed_mts"] = info["speed_mts"]
            self.system_specs["ram_gb"] = info["installed_gb"]
            self.system_specs["ram"] = f"{info['installed_gb']} GB" + (f" @ {info['speed_mts']} MT/s" if info["speed_mts"] else "")

    def _get_battery_devices(self) -> list[dict]:
        """
        Batería y periféricos conectados. Solo valores reales:
          - "percent": % informado por el dispositivo / Windows, o None si no lo informa.
          - "level": nivel aproximado que entrega XInput (Vacía/Baja/Media/Llena), si aplica.
        """
        devs = []

        def add(name, dtype, percent=None, plugged=False, status="Conectado", level=None):
            if any(d["name"].lower() == name.lower() for d in devs):
                return
            devs.append({"name": name, "type": dtype, "percent": percent, "level": level,
                         "plugged": plugged, "icon": dtype, "status": status})

        # 1. Batería interna (laptop) o alimentación directa (sobremesa)
        if HAS_PSUTIL:
            try:
                bat = psutil.sensors_battery()
                if bat:
                    mfg = self.system_specs.get("manufacturer", "Laptop")
                    model_s = self.system_specs.get("model_short", "")
                    bname = f"Batería {mfg}" if not model_s else f"Batería {mfg} ({model_s})"
                    pct = int(round(bat.percent))
                    add(bname, "laptop", pct, bool(bat.power_plugged),
                        f"{pct}% • {'Cargando (AC)' if bat.power_plugged else 'En Batería'}")
                else:
                    add("Alimentación de Red AC", "desktop", None, True, "PC de Sobremesa (Directo AC)")
            except Exception:
                pass

        # 2. XInput: mandos Xbox y compatibles (cable, 2.4 GHz o Bluetooth).
        #    XInput solo entrega un NIVEL (no un %): se muestra tal cual.
        xinput_levels = {0: "Vacía", 1: "Baja", 2: "Media", 3: "Llena"}
        for dll in ["xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"]:
            try:
                xi = ctypes.windll.LoadLibrary(dll)
                class XINPUT_STATE(ctypes.Structure):
                    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", wintypes.BYTE * 12)]
                class XINPUT_BAT(ctypes.Structure):
                    _fields_ = [("BatteryType", wintypes.BYTE), ("BatteryLevel", wintypes.BYTE)]

                for i in range(4):
                    st = XINPUT_STATE()
                    if xi.XInputGetState(i, ctypes.byref(st)) != 0:
                        continue
                    level, wired = None, False
                    bat_info = XINPUT_BAT()
                    try:
                        if xi.XInputGetBatteryInformation(i, 0, ctypes.byref(bat_info)) == 0:
                            btype = bat_info.BatteryType & 0xFF
                            wired = (btype == 1)  # BATTERY_TYPE_WIRED
                            if btype in (2, 3):   # alcalina / NiMH: nivel real
                                level = xinput_levels.get(bat_info.BatteryLevel)
                    except Exception:
                        pass
                    if wired:
                        status = "Conectado por cable USB"
                    elif level:
                        status = f"Batería {level} • Inalámbrico"
                    else:
                        status = "Inalámbrico"
                    add(f"Mando Xbox / XInput #{i+1}", "gamepad", None, wired, status, level)
                break
            except Exception:
                pass

        # 3. Bluetooth: dispositivos conectados con el % de batería que informa Windows
        bt_battery = {}
        try:
            for bt in hw_sensors.read_bluetooth_devices():
                name = bt["name"]
                nl = name.lower()
                if any(w in nl for w in ["controller", "dualsense", "dualshock", "gamepad", "xbox", "joystick"]):
                    dtype = "gamepad"
                elif any(w in nl for w in ["buds", "airpods", "headphone", "auricular", "headset", "soundcore", "redmi", "jbl", "sony wh", "sony wf"]):
                    dtype = "headphone"
                elif any(w in nl for w in ["mouse", "raton", "ratón"]):
                    dtype = "mouse"
                elif any(w in nl for w in ["keyboard", "teclado"]):
                    dtype = "keyboard"
                else:
                    dtype = "bluetooth"
                pct = bt["battery"]
                bt_battery[nl] = pct
                status = f"{pct}% Batería • Bluetooth" if pct is not None else "Conectado (Bluetooth)"
                add(name, dtype, pct, False, status)
        except Exception:
            pass

        # 4. WinMM: mandos DirectInput (DualSense, DualShock, Switch, receptores 2.4 GHz)
        try:
            winmm = ctypes.windll.winmm
            class JOYINFOEX(ctypes.Structure):
                _fields_ = [("dwSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("dwData", wintypes.DWORD * 11)]
            class JOYCAPSW(ctypes.Structure):
                _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("szPname", wintypes.WCHAR * 32), ("wOther", wintypes.BYTE * 400)]

            for j in range(min(winmm.joyGetNumDevs(), 16)):
                info = JOYINFOEX()
                info.dwSize = ctypes.sizeof(JOYINFOEX)
                info.dwFlags = 255
                if winmm.joyGetPosEx(j, ctypes.byref(info)) == 0:
                    caps = JOYCAPSW()
                    winmm.joyGetDevCapsW(j, ctypes.byref(caps), ctypes.sizeof(caps))
                    pname = (caps.szPname or f"Mando #{j+1}").strip()
                    if "wireless controller" in pname.lower():
                        pname = "Mando Sony DualSense / Wireless Controller"
                    already = any(d["type"] == "gamepad" and (d["name"].lower() == pname.lower()
                                  or "xbox" in d["name"].lower() or "dualsense" in d["name"].lower()
                                  or "controller" in d["name"].lower()) for d in devs)
                    if not already:
                        add(pname, "gamepad", None, False, "Mando conectado")
        except Exception:
            pass

        # 5. Periféricos USB (ratón, teclado, auriculares, mandos, receptores 2.4 GHz).
        #    Detección genérica por la clase de Windows de cada dispositivo; nombre real del dispositivo.
        try:
            for usb in hw_sensors.read_usb_peripherals():
                # Un mando ya detectado por XInput/WinMM (con su nivel de batería) no se repite
                if usb["type"] == "gamepad" and any(d["type"] == "gamepad" for d in devs):
                    continue
                conn = "Inalámbrico 2.4 GHz (receptor USB)" if usb["wireless"] else "Conectado por USB"
                add(usb["name"], usb["type"], None, not usb["wireless"], conn)
        except Exception:
            pass

        # 6. Auriculares activos como salida de audio (MMDevices): se asocia la batería Bluetooth si existe
        try:
            mm_base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, mm_base, 0, winreg.KEY_READ) as mk:
                for i in range(winreg.QueryInfoKey(mk)[0]):
                    guid = winreg.EnumKey(mk, i)
                    try:
                        with winreg.OpenKey(mk, guid, 0, winreg.KEY_READ) as gk:
                            state, _ = winreg.QueryValueEx(gk, "DeviceState")
                            if state != 1:
                                continue
                            with winreg.OpenKey(gk, "Properties", 0, winreg.KEY_READ) as pk:
                                ep_name, _ = winreg.QueryValueEx(pk, "{a45c254e-df1c-4efd-8020-67d146a850e0},2")
                            ep_lower = ep_name.lower()
                            if not any(k in ep_lower for k in ["barracuda", "razer", "hyperx", "headset", "audífono", "auricular", "headphone", "buds", "airpods", "redmi", "soundcore"]):
                                continue
                            if any(d["name"].lower() in ep_lower or ep_lower in d["name"].lower() for d in devs):
                                continue
                            pct = next((v for n, v in bt_battery.items() if n in ep_lower or ep_lower in n), None)
                            conn = "2.4 GHz" if any(x in ep_lower for x in ["2.4", "barracuda", "hyperx", "wireless"]) else "Audio activo"
                            status = f"{pct}% Batería • {conn}" if pct is not None else f"Conectado ({conn})"
                            add(ep_name, "headphone", pct, False, status)
                    except Exception:
                        pass
        except Exception:
            pass

        return devs

    def _run_cmd(self, args: list[str]) -> tuple[bool, str]:
        try:
            res = subprocess.run(
                args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, creationflags=CREATE_NO_WINDOW, timeout=8
            )
            out = res.stdout.strip() or res.stderr.strip()
            return (res.returncode == 0, out)
        except Exception as e:
            return (False, str(e))

    def _monitor_loop(self):
        tick = 0
        while self.running:
            try:
                # 1. RAM Exacta y Almacenamiento
                if HAS_PSUTIL:
                    mem = psutil.virtual_memory()
                    total_gb = mem.total / (1024**3)
                    available_gb = mem.available / (1024**3)
                    used_gb = (mem.total - mem.available) / (1024**3)
                    ram_pct = int(((mem.total - mem.available) / mem.total) * 100)

                    # Capacidad instalada real (módulos físicos vía WMI); si aún no está, la visible del sistema
                    inst_gb = self.ram_modules["installed_gb"] if self.ram_modules else int(round(total_gb))


                    self.telemetry["ram_pct"] = ram_pct
                    self.telemetry["ram_used"] = f"{used_gb:.1f}"
                    self.telemetry["ram_total"] = f"{total_gb:.1f}"
                    self.telemetry["ram_free"] = f"{available_gb:.1f}"
                    self.telemetry["ram_installed"] = inst_gb

                    # Almacenamiento total cada 5s
                    if tick % 10 == 0 or self.telemetry.get("disk_total_gb") is None:
                        try:
                            d_tot = 0
                            d_used = 0
                            for p in psutil.disk_partitions(all=False):
                                if "fixed" in p.opts.lower() or p.fstype:
                                    try:
                                        u = psutil.disk_usage(p.mountpoint)
                                        d_tot += u.total
                                        d_used += u.used
                                    except Exception:
                                        pass
                            if d_tot > 0:
                                self.telemetry["disk_used_gb"] = f"{d_used / (1024**3):.1f}"
                                self.telemetry["disk_total_gb"] = f"{d_tot / (1024**3):.0f}"
                                self.telemetry["disk_pct"] = int((d_used / d_tot) * 100)
                        except Exception:
                            pass

                    # 2. CPU (uso global y por hilo lógico)
                    c_usage = int(psutil.cpu_percent(interval=None))
                    self.telemetry["cpu_usage"] = c_usage
                    per_cpu = psutil.cpu_percent(interval=None, percpu=True)
                    if per_cpu:
                        self.telemetry["cpu_per_core"] = [round(float(v), 1) for v in per_cpu]

                    # 2b. Uso de red en tiempo real cada 1s (tick % 2 == 0)
                    if tick % 2 == 0:
                        try:
                            net_io = psutil.net_io_counters(pernic=True)
                            net_stats = psutil.net_if_stats()
                            net_addrs = psutil.net_if_addrs()
                            primary = select_primary_net_iface(net_stats, net_addrs, net_io)
                            if primary and primary["name"] in net_io:
                                iface = primary["name"]
                                io = net_io[iface]
                                now_ts = time.monotonic()
                                rx_bps = 0
                                tx_bps = 0
                                if self._net_prev and self._net_prev[3] == iface:
                                    dt = now_ts - self._net_prev[0]
                                    if dt > 0.1:
                                        rx_bps = max(0, int((io.bytes_recv - self._net_prev[1]) / dt))
                                        tx_bps = max(0, int((io.bytes_sent - self._net_prev[2]) / dt))
                                self._net_prev = (now_ts, io.bytes_recv, io.bytes_sent, iface)
                                self.telemetry["network"] = {
                                    "iface": iface,
                                    "link_mbps": primary["link_mbps"],
                                    "ipv4": primary["ipv4"],
                                    "rx_bps": rx_bps,
                                    "tx_bps": tx_bps,
                                    "rx_total_mb": round(io.bytes_recv / (1024 * 1024), 1),
                                    "tx_total_mb": round(io.bytes_sent / (1024 * 1024), 1),
                                    "ping_ms": self._ping_ms,
                                }
                            else:
                                self._net_prev = None
                                self.telemetry["network"] = {
                                    "iface": None, "link_mbps": None, "ipv4": None,
                                    "rx_bps": 0, "tx_bps": 0, "rx_total_mb": 0.0, "tx_total_mb": 0.0,
                                    "ping_ms": None,
                                }
                        except Exception:
                            pass

                # 2c. Lectura nativa PawnIO (CPU, GPU AMD/Intel, ventiladores EC) / SHM cada 1s, ping cada 6s y WMI/ACPI cada 5s
                if tick % 2 == 0:
                    try:
                        native = hw_sensors.read_native_cpu_sensors()
                        if native:
                            if native.get("cores"):
                                self.telemetry["cpu_core_temps"] = native["cores"]
                                self.telemetry["cpu_temp_source"] = native["source"]
                            if self.telemetry.get("cpu_temp") is None and native.get("package_c") is not None:
                                self.telemetry["cpu_temp"] = int(round(native["package_c"]))
                            if native.get("vcore_mv") is not None:
                                self.telemetry["cpu_volt_mv"] = native["vcore_mv"]
                            ngpu = native.get("gpu") or {}
                            if ngpu and (not self._has_nvidia_smi or self.telemetry.get("gpu_temp") is None):
                                if ngpu.get("temp") is not None:
                                    self.telemetry["gpu_temp"] = ngpu["temp"]
                                if ngpu.get("usage") is not None:
                                    self.telemetry["gpu_usage"] = ngpu["usage"]
                                if ngpu.get("freq_mhz") is not None:
                                    self.telemetry["gpu_freq_mhz"] = ngpu["freq_mhz"]
                                if ngpu.get("mem_freq_mhz") is not None:
                                    self.telemetry["gpu_mem_freq_mhz"] = ngpu["mem_freq_mhz"]
                                if ngpu.get("power_w") is not None:
                                    self.telemetry["gpu_power"] = ngpu["power_w"]
                            nfans = native.get("fans") or []
                            if nfans:
                                if self.telemetry.get("fan1_rpm") is None and len(nfans) >= 1:
                                    self.telemetry["fan1_rpm"] = nfans[0]
                                if self.telemetry.get("fan2_rpm") is None and len(nfans) >= 2:
                                    self.telemetry["fan2_rpm"] = nfans[1]
                                self.telemetry["fans_readable"] = True
                        if not (native and native.get("cores")):
                            shm_cores, shm_src = hw_sensors.read_shm_core_temps()
                            if shm_cores:
                                self.telemetry["cpu_core_temps"] = shm_cores
                                self.telemetry["cpu_temp_source"] = shm_src
                    except Exception:
                        pass
                if tick % 10 == 0:
                    self.telemetry["cpu_msr_status"] = {
                        "pawnio_installed": hw_sensors.is_pawnio_installed(),
                        "is_admin": hw_sensors.is_admin(),
                    }
                if tick % 12 == 0 and not self._ping_busy:
                    self._ping_busy = True
                    threading.Thread(target=self._refresh_ping, daemon=True).start()
                if tick % 10 == 0 and not self._core_temp_busy:
                    self._core_temp_busy = True
                    threading.Thread(target=self._refresh_core_temps, daemon=True).start()
                # Contadores de Windows: frecuencia efectiva de CPU (incluye Turbo) y memoria en caché
                counters = self._counters.read()
                if counters["cached_bytes"] is not None:
                    self.telemetry["ram_cached"] = f"{counters['cached_bytes'] / (1024**3):.1f}"
                live_mhz = counters["cpu_mhz"]
                if live_mhz is None and HAS_PSUTIL:
                    freq = psutil.cpu_freq()
                    live_mhz = int(freq.current) if freq and freq.current > 0 else None
                self.telemetry["cpu_freq_mhz"] = live_mhz
                self.telemetry["cpu_freq"] = f"{live_mhz / 1000.0:.2f}" if live_mhz else None
                # Respaldo universal WDDM GPU (Intel Iris/UHD, AMD Radeon o si falla nvidia-smi)
                if not self._has_nvidia_smi:
                    if counters.get("gpu_usage_pct") is not None:
                        self.telemetry["gpu_usage"] = counters["gpu_usage_pct"]
                    if counters.get("gpu_vram_mb") is not None and self.telemetry.get("gpu_vram_mb") is None:
                        self.telemetry["gpu_vram_mb"] = counters["gpu_vram_mb"]

                # 3. GPU NVIDIA cada 1s (Temp, Uso, Power, Clock MHz, Mem MHz)
                # (Aislado en su propio try: en equipos sin NVIDIA, nvidia-smi no existe y antes
                #  congelaba toda la telemetría porque la excepción saltaba el resto del ciclo.)
                gpu_proc = None
                if tick % 2 == 0 and self._has_nvidia_smi:
                    try:
                        gpu_proc = subprocess.run(
                            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,power.draw,clocks.gr,clocks.mem,memory.total,pcie.link.gen.current,pcie.link.width.current,power.limit,pstate", "--format=csv,noheader,nounits"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            creationflags=CREATE_NO_WINDOW, timeout=2
                        )
                    except FileNotFoundError:
                        self._has_nvidia_smi = False
                    except Exception:
                        gpu_proc = None
                if gpu_proc is not None:
                    if gpu_proc.returncode == 0 and gpu_proc.stdout:
                        parts = [p.strip() for p in gpu_proc.stdout.strip().split(",")]
                        if len(parts) >= 3:
                            try:
                                self.telemetry["gpu_temp"] = int(float(parts[0]))
                                self.telemetry["gpu_usage"] = int(float(parts[1]))
                                self.telemetry["gpu_power"] = f"{float(parts[2]):.1f}"
                            except Exception:
                                pass
                        if len(parts) >= 5:
                            try:
                                g_clk = int(float(parts[3]))
                                m_clk = int(float(parts[4]))
                                self.telemetry["gpu_freq_mhz"] = g_clk
                                self.telemetry["gpu_mem_freq_mhz"] = m_clk if m_clk > 0 else None
                            except Exception:
                                pass
                        if len(parts) >= 10:
                            def _num(x):
                                try:
                                    return float(x)
                                except ValueError:
                                    return None  # "[N/A]" u otros: el driver no lo informa
                            vram = _num(parts[5])
                            gen, width = _num(parts[6]), _num(parts[7])
                            plim = _num(parts[8])
                            self.telemetry["gpu_vram_mb"] = int(vram) if vram else None
                            self.telemetry["gpu_pcie"] = f"PCIe Gen{int(gen)} x{int(width)}" if gen and width else None
                            self.telemetry["gpu_power_limit"] = f"{plim:.0f}" if plim else None
                            self.telemetry["gpu_pstate"] = parts[9] if parts[9].startswith("P") else None

                # Voltaje real del núcleo GPU (si el driver NVIDIA lo expone) cada 4s
                if tick % 8 == 0 and self._has_nvidia_smi:
                    self.telemetry["gpu_volt_mv"] = hw_sensors.read_nvidia_voltage_mv()

                # 4. Telemetría BIOS HP / Acer Nitro WMI (RPM & Temp) cada 1.5s
                if tick % 3 == 0 and self.system_specs.get("is_hp", False):
                    ok, out = self._run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", self.fan_script, "-Mode", "query"])
                    if ok and "CPU_TEMP=" in out:
                        for item in out.strip().splitlines()[-1].split("|"):
                            try:
                                k, v = item.strip().split("=", 1)
                                v = int(v)
                            except ValueError:
                                continue
                            if k == "CPU_TEMP" and 0 < v <= 115:
                                self.telemetry["cpu_temp"] = v
                            elif k == "FAN1_RPM" and v > 0:
                                self.telemetry["fan1_rpm"] = v
                            elif k == "FAN2_RPM" and v > 0:
                                self.telemetry["fan2_rpm"] = v
                elif tick % 3 == 0 and self.system_specs.get("is_acer", False) and self._acer_wmi_ok:
                    ok, out = self._run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", self.acer_fan_script, "-Mode", "query"])
                    if "NO_WMI:" in out:
                        self._acer_wmi_ok = False
                    elif ok and "CPU_TEMP=" in out:
                        for item in out.strip().splitlines()[-1].split("|"):
                            try:
                                k, v = item.strip().split("=", 1)
                                v = int(v)
                            except ValueError:
                                continue
                            if k == "CPU_TEMP" and 0 < v <= 115:
                                self.telemetry["cpu_temp"] = v
                            elif k == "FAN1_RPM" and v > 0:
                                self.telemetry["fan1_rpm"] = v
                            elif k == "FAN2_RPM" and v > 0:
                                self.telemetry["fan2_rpm"] = v
                elif tick % 3 == 0 and self._oem_wmi_ok and any(
                    self.system_specs.get(k, False) for k in ("is_lenovo", "is_asus", "is_dell")
                ):
                    oem_brand = (
                        "lenovo" if self.system_specs.get("is_lenovo")
                        else "asus" if self.system_specs.get("is_asus")
                        else "dell"
                    )
                    ok, out = self._run_cmd([
                        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", self.oem_fan_script, "-Brand", oem_brand, "-Mode", "query",
                    ])
                    if "NO_WMI:" in out:
                        self._oem_wmi_ok = False
                        self.telemetry["fans_readable"] = False
                    elif ok and "FAN1_RPM=" in out:
                        for item in out.strip().splitlines()[-1].split("|"):
                            try:
                                k, v = item.strip().split("=", 1)
                                v = int(v)
                            except ValueError:
                                continue
                            if k == "CPU_TEMP" and 0 < v <= 115:
                                self.telemetry["cpu_temp"] = v
                            elif k == "FAN1_RPM" and v > 0:
                                self.telemetry["fan1_rpm"] = v
                            elif k == "FAN2_RPM" and v > 0:
                                self.telemetry["fan2_rpm"] = v

                elif tick % 6 == 0:
                    # Equipos no-HP: temperatura de la zona térmica ACPI (si el firmware la expone)
                    ok, out = self._run_cmd(["powershell", "-NoProfile", "-Command",
                        "$t=Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -First 1; if($t){[int](($t.CurrentTemperature-2732)/10)}"])
                    if ok and out.strip().lstrip("-").isdigit():
                        v = int(out.strip())
                        if 0 < v <= 115:
                            self.telemetry["cpu_temp"] = v


                # 5. Cálculo de Diagnóstico e Inteligencia de Hardware (Health Score)
                c_temp = self.telemetry.get("cpu_temp") or 0
                g_temp = self.telemetry.get("gpu_temp") or 0
                r_pct = self.telemetry.get("ram_pct") or 0

                health = 100
                if c_temp > 85: health -= 25
                elif c_temp > 75: health -= 12
                elif c_temp > 65: health -= 5

                if g_temp > 80: health -= 20
                elif g_temp > 70: health -= 10

                if r_pct > 85: health -= 15
                elif r_pct > 70: health -= 5

                self.telemetry["health_score"] = max(45, health)
                self.telemetry["health_status"] = "ÓPTIMO" if health >= 85 else "MODERADO" if health >= 70 else "ELEVADO"

                # 6. Detección instantánea de Dispositivos y Mandos (2.4GHz y Bluetooth) cada 2s
                if tick % 4 == 0:
                    self.telemetry["battery_devices"] = self._get_battery_devices()

                # Si está activo el Laboratorio de Tuning Manual, interpolar la curva de 8 puntos en vivo
                manual_cfg = getattr(self, "manual_config", None)
                if self.current_profile == "MANUAL" and manual_cfg:
                    curve_temps = [30, 49, 57, 62, 70, 80, 90, 100]
                    cpu_curve = manual_cfg.get("fan_curve") or [10, 16, 23, 29, 34, 39, 55, 67]
                    gpu_curve = manual_cfg.get("gpu_fan_curve") or cpu_curve
                    c_t = self.telemetry.get("cpu_temp")
                    g_t = self.telemetry.get("gpu_temp")
                    if c_t is None:
                        c_t = g_t if g_t is not None else 0
                    if g_t is None:
                        g_t = c_t

                    def _interp_curve(temp_val, curve_pts):
                        if not curve_pts or len(curve_pts) < 8:
                            return 45
                        if temp_val <= curve_temps[0]:
                            return int(curve_pts[0])
                        if temp_val >= curve_temps[-1]:
                            return int(curve_pts[-1])
                        for idx in range(len(curve_temps) - 1):
                            t0, t1 = curve_temps[idx], curve_temps[idx + 1]
                            if t0 <= temp_val <= t1:
                                ratio = (temp_val - t0) / float(max(1, t1 - t0))
                                return int(curve_pts[idx] + ratio * (curve_pts[idx + 1] - curve_pts[idx]))
                        return 50

                    target_cpu_fan_pct = _interp_curve(c_t, cpu_curve)
                    target_gpu_fan_pct = _interp_curve(g_t, gpu_curve)
                    # Objetivo de la curva (las RPM mostradas siguen siendo las leídas del BIOS)
                    self.telemetry["fan_target_pct"] = max(target_cpu_fan_pct, target_gpu_fan_pct)

                    # Conmutar turbina física WMI cada 3s si la curva exige >= 75% (o curva manual directa en Acer Nitro)
                    if tick % 6 == 0:
                        if self.system_specs.get("is_acer", False) and self._acer_wmi_ok:
                            pair = (target_cpu_fan_pct, target_gpu_fan_pct)
                            if pair != self._acer_last_manual:
                                ok, out = self._run_cmd([
                                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                    "-File", self.acer_fan_script, "-Mode", "manual",
                                    "-CpuPct", str(target_cpu_fan_pct), "-GpuPct", str(target_gpu_fan_pct),
                                ])
                                if "NO_WMI:" in out:
                                    self._acer_wmi_ok = False
                                elif ok:
                                    self._acer_last_manual = pair
                                    self.fan_mode = f"MANUAL ({max(pair)}% Nitro)"
                        else:
                            want_max = max(target_cpu_fan_pct, target_gpu_fan_pct) >= 75
                            if want_max and "TURBO" not in self.fan_mode:
                                self.set_fan("max")
                            elif not want_max and "TURBO" in self.fan_mode:
                                self.set_fan("auto")
                else:
                    self._acer_last_manual = None
                    self.telemetry["fan_target_pct"] = None

                self.telemetry["current_profile"] = self.current_profile
                self.telemetry["fan_mode"] = self.fan_mode
            except Exception:
                pass
            # El contador SIEMPRE avanza (antes, una excepción lo dejaba fijo y el ciclo se repetía fallando)
            tick += 1
            time.sleep(0.5)

    def set_fan(self, mode: str) -> bool:
        if mode not in ("max", "auto", "cool"):
            mode = "auto"
        self._acer_last_manual = None
        if getattr(self, "system_specs", {}).get("is_hp", False):
            ok, out = self._run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", self.fan_script, "-Mode", mode])
            if mode == "max":
                self.fan_mode = "TURBO (100%)"
            else:
                self.fan_mode = "AUTO"
            return ok
        elif getattr(self, "system_specs", {}).get("is_acer", False) and self._acer_wmi_ok:
            ok, out = self._run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", self.acer_fan_script, "-Mode", mode])
            if "NO_WMI:" in out:
                self._acer_wmi_ok = False
            elif ok and "OK:" in out:
                if mode == "max":
                    self.fan_mode = "TURBO (100% Nitro)"
                    self.set_scheme("high")
                    self.set_cpu_limit(100)
                    self.set_turbo(2)
                else:
                    self.fan_mode = "AUTO (Nitro)"
                return True
        elif self._oem_wmi_ok and any(
            getattr(self, "system_specs", {}).get(k, False) for k in ("is_lenovo", "is_asus", "is_dell")
        ):
            oem_brand = (
                "lenovo" if self.system_specs.get("is_lenovo")
                else "asus" if self.system_specs.get("is_asus")
                else "dell"
            )
            ok, out = self._run_cmd([
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", self.oem_fan_script, "-Brand", oem_brand, "-Mode", mode,
            ])
            if "NO_WMI:" in out:
                self._oem_wmi_ok = False
            elif ok and "OK:" in out:
                tag = oem_brand.upper()
                if mode == "max":
                    self.fan_mode = f"TURBO ({tag})"
                    self.set_scheme("high")
                    self.set_cpu_limit(100)
                    self.set_turbo(2)
                elif mode == "cool":
                    self.fan_mode = f"SILENCIOSO ({tag})"
                else:
                    self.fan_mode = f"AUTO ({tag})"
                return True
        if mode == "max":
            self.fan_mode = "TURBO (Universal)"
            self.set_scheme("high")
            self.set_cpu_limit(100)
            self.set_turbo(2)
        else:
            self.fan_mode = "AUTO (Universal)"
            self.set_scheme("balanced")
            self.set_cpu_limit(95)
            self.set_turbo(2)
        return True

    def set_cpu_limit(self, max_pct: int) -> bool:
        val = str(max(50, min(100, max_pct)))
        self._run_cmd(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.THROTTLE_MAX, val])
        self._run_cmd(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.THROTTLE_MAX, val])
        self._run_cmd(["powercfg", "/setactive", "SCHEME_CURRENT"])
        return True

    def set_turbo(self, turbo_val: int) -> bool:
        # PERFBOOSTMODE de Windows: 0=Desactivado 1=Activado 2=Agresivo 3=Eficiente 4=Eficiente agresivo
        # (antes cualquier valor distinto de 2 apagaba Turbo Boost, incluido el modo 3 del Laboratorio Manual)
        try:
            turbo_val = int(turbo_val)
        except (TypeError, ValueError):
            turbo_val = 2
        val = str(turbo_val if turbo_val in (0, 1, 2, 3, 4) else 2)
        self._run_cmd(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.TURBO_BOOST, val])
        self._run_cmd(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.TURBO_BOOST, val])
        self._run_cmd(["powercfg", "/setactive", "SCHEME_CURRENT"])
        return True

    def set_scheme(self, scheme_name: str) -> bool:
        if scheme_name == "saver":
            set_windows_power_overlay(DefaultGUIDs.OVERLAY_SAVER)
            self._run_cmd(["powercfg", "/setactive", DefaultGUIDs.SAVER])
        elif scheme_name == "high":
            set_windows_power_overlay(DefaultGUIDs.OVERLAY_HIGH_PERF)
            self._run_cmd(["powercfg", "/setactive", DefaultGUIDs.HIGH_PERF])
        else:
            set_windows_power_overlay(DefaultGUIDs.OVERLAY_BALANCED)
            self._run_cmd(["powercfg", "/setactive", DefaultGUIDs.BALANCED])
        return True

    def clean_ram(self) -> dict:
        """Libera la memoria en caché y reduce el working set de los procesos."""
        try:
            mem_before = psutil.virtual_memory().available if HAS_PSUTIL else 0
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.EmptyWorkingSet(handle)
            # También vaciar procesos accesibles
            if HAS_PSUTIL:
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        p_handle = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, proc.info['pid'])
                        if p_handle:
                            ctypes.windll.psapi.EmptyWorkingSet(p_handle)
                            ctypes.windll.kernel32.CloseHandle(p_handle)
                    except Exception:
                        pass
                mem_after = psutil.virtual_memory().available
                freed_mb = max(0, int((mem_after - mem_before) / (1024**2)))
            else:
                freed_mb = 0
            return {"status": "ok", "freed_mb": freed_mb}
        except Exception as e:
            return {"status": "error", "message": str(e), "freed_mb": 0}

    def set_profile(self, profile: str) -> bool:
        self.current_profile = profile
        if profile == "ECO":
            self.set_scheme("balanced")
            self._set_cpu(min_pct=5, max_pct=60, boost=0)
            self.set_fan("cool")
        elif profile == "SILENT":
            self.set_scheme("balanced")
            self._set_cpu(min_pct=5, max_pct=80, boost=0)
            self.set_fan("auto")
        elif profile == "DEFAULT":
            self.set_scheme("balanced")
            self._set_cpu(min_pct=5, max_pct=100, boost=2)
            self.set_fan("auto")
        elif profile == "PERFORMANCE":
            self.set_scheme("high")
            self._set_cpu(min_pct=100, max_pct=100, boost=2)
            self.set_fan("max")
        return True

    def _set_cpu(self, min_pct: int, max_pct: int, boost: int):
        self._run_cmd(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.THROTTLE_MAX, str(max_pct)])
        self._run_cmd(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.THROTTLE_MAX, str(max_pct)])
        self._run_cmd(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.THROTTLE_MIN, str(min_pct)])
        self._run_cmd(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.THROTTLE_MIN, str(min_pct)])
        self._run_cmd(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.TURBO_BOOST, str(boost)])
        self._run_cmd(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.TURBO_BOOST, str(boost)])
        self._run_cmd(["powercfg", "/setactive", "SCHEME_CURRENT"])


# En modo prueba (tests automáticos) no se inicia el gestor de hardware real
manager = None if os.environ.get("VORTEXCORE_TEST_MODE") == "1" else VortexCoreManager()
# overlay en juego con fps de presentmon
fps_mon = fps_monitor.FpsMonitor(fps_monitor.find_presentmon(get_app_dir()))
# consumo de red por app y ping al servidor del juego (se enciende solo cuando se consulta)
net_mon = net_monitor.NetMonitor(ping_func=hw_sensors.measure_ping_ms, prefer_game=fps_mon.recent_game)
overlay = None if manager is None else game_overlay.GameOverlay(
    lambda: manager.telemetry, fps_mon, get_net=net_mon.snapshot)


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    """Convierte a entero y acota al rango [lo, hi]. Valores inválidos -> default."""
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _clamp_float(value, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return max(lo, min(hi, v))


def _sanitize_curve(curve, default: list) -> list:
    """Curva de ventilador: exactamente 8 puntos enteros entre 0 y 100."""
    if not isinstance(curve, list) or len(curve) != 8:
        return list(default)
    return [_clamp_int(v, 0, 100, d) for v, d in zip(curve, default)]


# Orígenes autorizados para hablar con la API local (la propia ventana de la app)
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
MAX_BODY_BYTES = 64 * 1024

APO_BASE_DIR = r"C:\Program Files\EqualizerAPO"
APO_DOWNLOAD_URL = "https://sourceforge.net/projects/equalizerapo/"
SENSOR_APP_URLS = {
    "lhm": "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest",
    "coretemp": "https://www.alcpu.com/CoreTemp/",
}


def get_apo_status() -> dict:
    """Comprueba si Equalizer APO y su configurador están instalados en Windows."""
    config_dir = os.path.join(APO_BASE_DIR, "config")
    config_txt = os.path.join(config_dir, "config.txt")
    configurator = os.path.join(APO_BASE_DIR, "Configurator.exe")
    installed = os.path.isdir(config_dir) or os.path.isfile(configurator)
    return {
        "installed": installed,
        "config_dir": config_dir,
        "config_exists": os.path.isfile(config_txt),
        "configurator_exists": os.path.isfile(configurator),
        "download_url": APO_DOWNLOAD_URL,
    }


def get_top_memory_processes(limit: int = 8) -> list[dict]:
    """Devuelve los procesos activos con mayor consumo real de RAM (RSS en MB)."""
    procs = []
    if HAS_PSUTIL:
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                mi = p.info.get("memory_info")
                if not mi:
                    continue
                rss = mi.rss / (1024 ** 2)
                if rss > 10:
                    mb = round(rss, 1)
                    procs.append({
                        "pid": p.info.get("pid"),
                        "name": p.info.get("name") or "Proceso",
                        "mem_mb": mb,
                        "memory_mb": mb,
                    })
            except Exception:
                pass
        procs.sort(key=lambda x: x["memory_mb"], reverse=True)
    return procs[:limit]


class VortexHttpHandler(SimpleHTTPRequestHandler):
    # El servidor corre como Administrador: solo la interfaz propia puede usar la API.
    # Cualquier página web abierta en el navegador podría, si no, mandar peticiones a
    # 127.0.0.1:8765 (cambiar límites de GPU, desinstalar apps, tocar el registro...).

    def __init__(self, *args, **kwargs):
        directory = os.path.join(get_app_dir(), "vortex-hub")
        super().__init__(*args, directory=directory, **kwargs)

    def _is_request_allowed(self) -> bool:
        # Anti DNS-rebinding: el Host debe ser exactamente nuestro loopback
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in ALLOWED_HOSTS:
            return False
        # Anti CSRF: los navegadores envían Origin en peticiones entre sitios
        origin = self.headers.get("Origin")
        if origin is not None and origin.lower() not in ALLOWED_ORIGINS:
            return False
        sec_site = (self.headers.get("Sec-Fetch-Site") or "").lower()
        if sec_site in ("cross-site", "same-site"):
            return False
        return True

    def _reject(self, code: int = 403, message: str = "Forbidden"):
        self._send_json({"status": "error", "message": message}, code=code)

    def do_OPTIONS(self):
        # No se ofrece CORS a terceros: cualquier preflight se rechaza
        self._reject(403)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        # Revalidar siempre: tras actualizar la app, la ventana no debe mostrar CSS/JS antiguos
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/"):
            if not self._is_request_allowed():
                return self._reject()
            try:
                self._handle_get()
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, code=500)
        else:
            if (self.headers.get("Host") or "").strip().lower() not in ALLOWED_HOSTS:
                return self._reject()
            super().do_GET()

    def _handle_get(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/telemetry":
            self._send_json(manager.telemetry)
        elif path == "/api/specs":
            self._send_json(manager.system_specs)
        elif path == "/api/hardware_diagnose":
            self._send_json(diagnose_hardware_health(manager))
        elif path == "/api/startup/apps":
            self._send_json({"apps": get_startup_apps()})
        elif path == "/api/debloat/apps":
            self._send_json({"apps": get_installed_debloat_apps()})
        elif path == "/api/autostart":
            self._send_json({"enabled": is_autostart_enabled()})
        elif path == "/api/overlay":
            self._send_json(overlay.get_config())
        elif path == "/api/audio_mixer":
            self._send_json(get_audio_mixer_data())
        elif path == "/api/apo_status":
            self._send_json(get_apo_status())
        elif path == "/api/battery_health":
            self._send_json(hw_sensors.read_battery_health())
        elif path == "/api/cleanup/scan":
            self._send_json(scan_disk_cleanup())
        elif path == "/api/top_processes":
            self._send_json({"processes": get_top_memory_processes(8)})
        elif path == "/api/network/apps":
            self._send_json(net_mon.snapshot())
        elif path == "/api/network/status":
            iface = (manager.telemetry.get("network") or {}).get("iface")
            self._send_json(hw_sensors.get_network_boost_status(iface))
        elif path == "/api/network/benchmark":
            self._send_json({
                "dns": hw_sensors.benchmark_dns_servers(),
                "quality": hw_sensors.measure_network_quality(),
            })
        else:
            self._send_json({"status": "error", "message": "Not found"}, code=404)

    def do_POST(self):
        if not self._is_request_allowed():
            return self._reject()
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in ("application/json", ""):
            return self._reject(415, "Content-Type debe ser application/json")
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            return self._reject(400, "Content-Length inválido")
        if length < 0 or length > MAX_BODY_BYTES:
            return self._reject(413, "Cuerpo demasiado grande")
        try:
            body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            data = json.loads(body) if body.strip() else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._reject(400, "JSON inválido")
        if not isinstance(data, dict):
            return self._reject(400, "Se esperaba un objeto JSON")
        try:
            self._handle_post(data)
        except (TypeError, ValueError) as e:
            self._send_json({"status": "error", "message": f"Parámetros inválidos: {e}"}, code=400)
        except Exception as e:
            self._send_json({"status": "error", "message": str(e)}, code=500)

    def _handle_post(self, data: dict):
        if self.path == "/api/profile":
            prof = str(data.get("profile", "DEFAULT")).upper()
            if prof not in ("ECO", "SILENT", "DEFAULT", "PERFORMANCE"):
                return self._reject(400, "Perfil desconocido")
            manager.set_profile(prof)
            self._send_json({"status": "ok", "profile": prof})
        elif self.path == "/api/manual_mode":
            # Todos los valores se acotan a rangos seguros antes de tocar el hardware
            default_curve = [10, 16, 23, 29, 34, 39, 55, 67]
            spl = _clamp_int(data.get("spl"), 15, 65, 35)
            sppt = _clamp_int(data.get("sppt"), 15, 90, 45)
            fppt = _clamp_int(data.get("fppt"), 15, 120, 60)
            gpu_base = _clamp_int(data.get("gpu_base"), 0, 200, 50)
            gpu_mem = _clamp_int(data.get("gpu_mem"), 0, 1500, 100)
            gpu_boost = _clamp_int(data.get("gpu_boost"), 0, 200, 25)
            gpu_temp = _clamp_int(data.get("gpu_temp"), 60, 90, 87)
            gpu_tgp = _clamp_int(data.get("gpu_tgp"), 30, 175, 115)
            fan_curve = _sanitize_curve(data.get("fan_curve"), default_curve)
            gpu_fan_curve = _sanitize_curve(data.get("gpu_fan_curve", fan_curve), fan_curve)

            manager.current_profile = "MANUAL"
            manager.manual_config = {
                "spl": spl, "sppt": sppt, "fppt": fppt,
                "gpu_base": gpu_base, "gpu_mem": gpu_mem,
                "gpu_boost": gpu_boost, "gpu_temp": gpu_temp,
                "gpu_tgp": gpu_tgp,
                "fan_curve": fan_curve,
                "gpu_fan_curve": gpu_fan_curve
            }

            # 1. CPU: Mapear SPL (15W..65W) a límite de procesador en Windows (PROCTHROTTLEMAX)
            cpu_pct = min(100, max(55, int(50 + ((spl - 15) / 50.0) * 50)))
            manager.set_cpu_limit(cpu_pct)

            # 2. CPU: Mapear SPPT/FPPT a modo Turbo Boost (0=Off <42W, 3=Eficiente 42..64W, 2=Agresivo >=65W)
            if fppt < 42:
                manager.set_turbo(0)
                manager.set_scheme("saver")
            elif fppt < 65:
                manager.set_turbo(3)
                manager.set_scheme("balanced")
            else:
                manager.set_turbo(2)
                manager.set_scheme("high")

            # 3. GPU NVIDIA: Aplicar límite TGP (Watts) y Thermal Target (°C) mediante nvidia-smi
            #    (el driver además rechaza valores fuera del rango que admite la tarjeta)
            try:
                subprocess.Popen(
                    ["nvidia-smi", "-pl", str(gpu_tgp)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW
                )
                subprocess.Popen(
                    ["nvidia-smi", "-gtt", str(gpu_temp)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW
                )
            except Exception:
                pass

            # 4. Ventiladores: Evaluar curva de 8 puntos de inmediato
            c_temp = manager.telemetry.get("cpu_temp") or 0
            if isinstance(fan_curve, list) and len(fan_curve) >= 6:
                high_curve = any(int(v) >= 75 for v in fan_curve[4:]) and c_temp >= 60
                manager.set_fan("max" if high_curve else "auto")

            self._send_json({
                "status": "ok",
                "profile": "MANUAL",
                "applied": {
                    "spl": spl, "sppt": sppt, "fppt": fppt,
                    "gpu_base": gpu_base, "gpu_mem": gpu_mem,
                    "gpu_tgp": gpu_tgp, "cpu_pct": cpu_pct
                }
            })
        elif self.path == "/api/fan":
            mode = str(data.get("mode", "auto")).lower()
            if mode not in ("max", "auto", "cool"):
                return self._reject(400, "Modo de ventilador desconocido")
            manager.set_fan(mode)
            self._send_json({"status": "ok", "fan": mode})
        elif self.path == "/api/set_master_volume":
            vol = data.get("volume")
            vol = None if vol is None else _clamp_float(vol, 0.0, 100.0, 50.0)
            muted = data.get("muted")
            muted = None if muted is None else bool(muted)
            ok = set_master_volume_state(vol, muted)
            self._send_json({"status": "ok" if ok else "error"})
        elif self.path == "/api/set_app_volume":
            pid = data.get("pid")
            name = data.get("name")
            pid = _clamp_int(pid, 0, 2**32 - 1, 0) if pid is not None else None
            name = str(name)[:260] if name is not None else None
            vol = data.get("volume")
            vol = None if vol is None else _clamp_float(vol, 0.0, 100.0, 50.0)
            muted = data.get("muted")
            muted = None if muted is None else bool(muted)
            ok = set_app_volume_state(pid, name, vol, muted)
            self._send_json({"status": "ok" if ok else "error"})
        elif self.path == "/api/set_cpu_limit":
            max_pct = _clamp_int(data.get("max_pct"), 50, 100, 100)
            manager.set_cpu_limit(max_pct)
            self._send_json({"status": "ok", "cpu_limit": max_pct})
        elif self.path == "/api/set_turbo":
            turbo = _clamp_int(data.get("turbo"), 0, 4, 2)
            manager.set_turbo(turbo)
            self._send_json({"status": "ok", "turbo": turbo})
        elif self.path == "/api/set_scheme":
            scheme = str(data.get("scheme", "balanced")).lower()
            if scheme not in ("saver", "balanced", "high"):
                scheme = "balanced"
            manager.set_scheme(scheme)
            self._send_json({"status": "ok", "scheme": scheme})
        elif self.path == "/api/clean_ram":
            res = manager.clean_ram()
            self._send_json({"status": "ok", "cleaned": res})
        elif self.path == "/api/hardware_apply_optimizations":
            # Aplica exactamente las recomendaciones que muestra el diagnóstico (sin cambios ocultos)
            actions = {r["action"] for r in diagnose_hardware_health(manager)["recommendations"]}
            done = []
            if "clean_ram" in actions:
                freed = (manager.clean_ram() or {}).get("freed_mb")
                done.append(f"RAM liberada ({freed} MB)" if isinstance(freed, (int, float)) else "RAM liberada")
            if "limit_cpu" in actions:
                manager.set_cpu_limit(95)
                done.append("CPU limitada al 95%")
            self._send_json({
                "status": "ok",
                "applied": sorted(actions),
                "message": ("Aplicado: " + ", ".join(done) + ".") if done else "No hay nada que aplicar: el equipo está en buen estado."
            })
        elif self.path == "/api/startup/toggle":
            name = str(data.get("name", "")).strip()
            scope = "system" if data.get("scope") == "system" else "user"
            enable = bool(data.get("enabled", True))
            if not name or len(name) > 260 or any(c in name for c in "\\\r\n\x00"):
                return self._reject(400, "Nombre de aplicación inválido")
            # Solo se pueden conmutar entradas que realmente existen en el inicio de Windows
            if name not in {a.get("name") for a in get_startup_apps()}:
                return self._reject(404, "La aplicación no está en el inicio de Windows")
            ok = toggle_startup_app(name, scope, enable)
            self._send_json({"status": "ok" if ok else "error", "name": name, "enabled": enable})
        elif self.path == "/api/debloat/remove":
            app_ids = data.get("apps", [])
            if not isinstance(app_ids, list):
                return self._reject(400, "Se esperaba una lista de apps")
            res = remove_debloat_apps([str(a) for a in app_ids][:50])
            self._send_json(res)
        elif self.path == "/api/cleanup/clean":
            raw_targets = data.get("targets", [])
            if not isinstance(raw_targets, list):
                return self._reject(400, "Se esperaba una lista de categorías")
            targets = [str(t) for t in raw_targets if str(t) in CLEANUP_CATEGORY_IDS]
            if not targets:
                return self._reject(400, "No se especificó ninguna categoría de limpieza válida")
            self._send_json(run_disk_cleanup(targets))
        elif self.path == "/api/overlay":
            self._send_json(overlay.update_config(data))
        elif self.path == "/api/autostart":
            enable = bool(data.get("enabled", True))
            ok = set_autostart(enable)
            self._send_json({"status": "ok", "enabled": is_autostart_enabled()})
        elif self.path == "/api/open_sound_settings":
            try:
                subprocess.Popen(["control", "mmsys.cpl", "sounds"], creationflags=CREATE_NO_WINDOW)
            except Exception:
                try:
                    subprocess.Popen(["start", "ms-settings:sound"], shell=True)
                except Exception:
                    pass
            self._send_json({"status": "ok", "message": "Panel de audio abierto"})
        elif self.path == "/api/set_eq":
            enabled = bool(data.get("enabled", True))
            raw_bands = data.get("bands", [0] * 10)
            if not isinstance(raw_bands, list):
                raw_bands = [0] * 10
            bands = [round(_clamp_float(b, -20.0, 20.0, 0.0), 1) for b in raw_bands[:10]]
            bands += [0.0] * (10 - len(bands))
            # El preset se escribe en config.txt de Equalizer APO: solo caracteres seguros (sin saltos de línea)
            preset = "".join(c for c in str(data.get("preset", "custom")) if c.isalnum() or c in " -_")[:40] or "custom"
            freqs = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

            apo_dir = r"C:\Program Files\EqualizerAPO\config"
            apo_config = os.path.join(apo_dir, "config.txt")
            if enabled:
                eq_line = "GraphicEQ: " + "; ".join(f"{freqs[i]} {bands[i]}" for i in range(min(len(bands), len(freqs)))) + "\n"
            else:
                eq_line = "# GraphicEQ desactivado por VortexCore Hub (Modo Normal / Bypass)\n"

            written = False
            if os.path.isdir(apo_dir):
                try:
                    with open(apo_config, "w", encoding="utf-8") as f:
                        f.write(f"# VortexCore Hub - Estado EQ: {'ACTIVO (' + preset + ')' if enabled else 'DESACTIVADO (NORMAL)'}\n")
                        f.write(eq_line)
                    written = True
                except Exception:
                    pass

            vortex_cfg_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub")
            os.makedirs(vortex_cfg_dir, exist_ok=True)
            vortex_cfg = os.path.join(vortex_cfg_dir, "audio_eq.json")
            try:
                with open(vortex_cfg, "w", encoding="utf-8") as f:
                    json.dump({"enabled": enabled, "bands": bands, "preset": preset}, f)
            except Exception:
                pass

            self._send_json({"status": "ok", "enabled": enabled, "apo_synced": written, "bands": bands})
        elif self.path == "/api/open_apo_setup":
            action = str(data.get("action", "")).lower()
            if action == "download":
                try:
                    os.startfile(APO_DOWNLOAD_URL)
                    self._send_json({"status": "ok", "action": "download"})
                except Exception as e:
                    self._send_json({"status": "error", "message": str(e)}, code=500)
            elif action == "configurator":
                cfg_exe = os.path.join(APO_BASE_DIR, "Configurator.exe")
                if os.path.isfile(cfg_exe):
                    try:
                        subprocess.Popen([cfg_exe], cwd=APO_BASE_DIR)
                        self._send_json({"status": "ok", "action": "configurator"})
                    except Exception as e:
                        self._send_json({"status": "error", "message": str(e)}, code=500)
                else:
                    self._send_json({"status": "error", "message": "Equalizer APO no está instalado en este equipo."}, code=404)
            else:
                self._reject(400, "Acción de Equalizer APO desconocida")
        elif self.path == "/api/open_sensor_app":
            target = str(data.get("app", "")).lower()
            url = SENSOR_APP_URLS.get(target)
            if url:
                try:
                    os.startfile(url)
                    self._send_json({"status": "ok", "app": target})
                except Exception as e:
                    self._send_json({"status": "error", "message": str(e)}, code=500)
            else:
                self._reject(400, "Proveedor térmico desconocido")
        elif self.path == "/api/install_pawnio":
            res = hw_sensors.install_pawnio()
            manager.telemetry["cpu_msr_status"] = {
                "pawnio_installed": hw_sensors.is_pawnio_installed(),
                "is_admin": hw_sensors.is_admin(),
            }
            self._send_json(res, code=200 if res.get("status") == "ok" else 500)
        elif self.path == "/api/relaunch_admin":
            try:
                exe = sys.executable
                args_str = " ".join(f'"{a}"' for a in ([os.path.abspath(__file__)] if not getattr(sys, "frozen", False) else sys.argv[1:]))
                ps = (
                    "Start-Sleep -Milliseconds 700; "
                    f"Start-Process -FilePath '{exe}' "
                    + (f"-ArgumentList '{args_str}' " if args_str else "")
                    + f"-WorkingDirectory '{get_app_dir()}' -Verb RunAs"
                )
                subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                                 creationflags=CREATE_NO_WINDOW)
                self._send_json({"status": "ok", "message": "Reiniciando con privilegios de Administrador..."})
                threading.Timer(0.25, lambda: os._exit(0)).start()
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, code=500)
        elif self.path == "/api/network/boost":
            enable = bool(data.get("enable", True))
            dns_preset = str(data.get("dns_preset", "keep")).lower().strip()
            if dns_preset not in ("keep", *hw_sensors.DNS_PRESETS.keys()):
                return self._reject(400, "Preset de DNS no válido")
            iface = (manager.telemetry.get("network") or {}).get("iface")
            res = hw_sensors.apply_network_boost(enable=enable, dns_preset=dns_preset, iface_name=iface)
            code = 200 if res.get("status") in ("ok", "partial") else (403 if res.get("needs_admin") else 500)
            self._send_json(res, code=code)
        elif self.path == "/api/focus_window":
            launch_or_focus_window()
            self._send_json({"status": "ok", "action": "focused"})
        else:
            self._send_json({"status": "error", "message": "Not found"}, code=404)

    def _send_json(self, payload, code: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


_launch_lock = threading.Lock()
_last_launch_time = 0.0
_window_hicons = None


def _find_suite_window_hwnd():
    """Localiza el HWND de la ventana nativa de VortexCore Hub (descartando pestañas del navegador)."""
    try:
        user32 = ctypes.windll.user32
        found_hwnd = None

        def enum_proc(hwnd, lparam):
            nonlocal found_hwnd
            if not user32.IsWindow(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                val_low = buff.value.lower()
                is_suite_title = (val_low == "vortexcore hub" or "vortexcore hub // clean hardware suite" in val_low) or (
                    "clean hardware suite" in val_low and "vortexcore" in val_low
                )
                is_excluded = any(bad in val_low for bad in (
                    "github", "release ", "faundezz21", "tray", "vch_", "setup", "instalador", "downloads", "descargas"
                ))
                if is_suite_title and not is_excluded:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if user32.IsIconic(hwnd) or (w > 200 and h > 200):
                        found_hwnd = hwnd
                        return False
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_proc), 0)
        return found_hwnd
    except Exception:
        return None


def apply_window_icon(hwnd):
    """Fuerza el icono oficial (vortex_icon.ico) en la barra de título y barra de tareas de la ventana."""
    global _window_hicons
    if not hwnd:
        return
    try:
        icon_path = os.path.abspath(os.path.join(get_app_dir(), "vortex_icon.ico"))
        if not os.path.isfile(icon_path):
            return
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_longlong

        if _window_hicons is None:
            sm_cx = user32.GetSystemMetrics(49) or 16
            sm_cy = user32.GetSystemMetrics(50) or 16
            lg_cx = user32.GetSystemMetrics(11) or 32
            lg_cy = user32.GetSystemMetrics(12) or 32
            h_sm = user32.LoadImageW(0, icon_path, 1, sm_cx, sm_cy, 0x00000010)
            h_lg = user32.LoadImageW(0, icon_path, 1, lg_cx, lg_cy, 0x00000010)
            _window_hicons = (h_sm, h_lg)

        h_sm, h_lg = _window_hicons
        WM_SETICON = 0x0080
        if h_sm:
            user32.SendMessageW(hwnd, WM_SETICON, 0, int(h_sm))
        if h_lg:
            user32.SendMessageW(hwnd, WM_SETICON, 1, int(h_lg))
    except Exception:
        pass


def _refresh_edge_icon_cache(user_data: str):
    """Invalida la caché de favicons de Edge si cambió la versión o el icono."""
    try:
        icon_path = os.path.abspath(os.path.join(get_app_dir(), "vortex_icon.ico"))
        icon_sig = f"{APP_VERSION}:{os.path.getsize(icon_path) if os.path.isfile(icon_path) else 0}"
        marker = os.path.join(user_data, ".icon_sig")
        prev = ""
        if os.path.isfile(marker):
            with open(marker, encoding="utf-8", errors="ignore") as f:
                prev = f.read().strip()
        if prev != icon_sig:
            default_dir = os.path.join(user_data, "Default")
            for fname in ("Favicons", "Favicons-journal"):
                fpath = os.path.join(default_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
            with open(marker, "w", encoding="utf-8") as f:
                f.write(icon_sig)
    except Exception:
        pass


def focus_existing_window() -> bool:
    """Busca la ventana gráfica de VortexCore Hub en Windows y la trae al frente."""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        found_hwnd = _find_suite_window_hwnd()

        if found_hwnd:
            apply_window_icon(found_hwnd)
            # Si estaba minimizada, restaurar
            if user32.IsIconic(found_hwnd):
                user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
            else:
                user32.ShowWindow(found_hwnd, 5)  # SW_SHOW

            # Forzar foco al frente (Foreground) superando restricciones de foco en Windows
            fore_hwnd = user32.GetForegroundWindow()
            if fore_hwnd != found_hwnd:
                fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
                cur_thread = kernel32.GetCurrentThreadId()
                if fore_thread != cur_thread:
                    user32.AttachThreadInput(cur_thread, fore_thread, True)
                    user32.BringWindowToTop(found_hwnd)
                    user32.SetForegroundWindow(found_hwnd)
                    user32.AttachThreadInput(cur_thread, fore_thread, False)
                else:
                    user32.BringWindowToTop(found_hwnd)
                    user32.SetForegroundWindow(found_hwnd)
            else:
                user32.BringWindowToTop(found_hwnd)
                user32.SetForegroundWindow(found_hwnd)
            return True
    except Exception:
        pass
    return False


def launch_native_window():
    if focus_existing_window():
        return

    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    edge_exe = next((p for p in edge_paths if os.path.isfile(p)), "msedge.exe")
    # La versión en la URL obliga a Edge a pedir la interfaz nueva tras cada actualización
    # (la caché del perfil de la ventana guarda páginas de versiones anteriores)
    url = f"http://127.0.0.1:{PORT}/?v={APP_VERSION}"
    user_data = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub", "Profile")
    os.makedirs(user_data, exist_ok=True)
    _refresh_edge_icon_cache(user_data)

    args = [
        edge_exe,
        f"--app={url}",
        f"--user-data-dir={user_data}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1260,820",
        "--disable-extensions",
        "--disable-background-networking"
    ]
    subprocess.Popen(args)

    def _apply_icon_when_ready():
        for _ in range(28):
            time.sleep(0.25)
            hwnd = _find_suite_window_hwnd()
            if hwnd:
                apply_window_icon(hwnd)
                break

    threading.Thread(target=_apply_icon_when_ready, daemon=True).start()


def launch_or_focus_window():
    """
    Garantiza una ÚNICA ventana abierta. Si el usuario hace doble clic o
    múltiples clics seguidos, solo se restaura o enfoca la ventana existente,
    impidiendo la apertura de procesos duplicados.
    """
    global _last_launch_time
    with _launch_lock:
        # 1. Si la ventana ya existe, enfocarla de inmediato
        if focus_existing_window():
            return

        now = time.time()
        # 2. Si se solicitó abrir hace menos de 2.2 segundos, esperar a que aparezca la ventana en vez de lanzar otra
        if now - _last_launch_time < 2.2:
            for _ in range(6):
                time.sleep(0.25)
                if focus_existing_window():
                    return
            return

        _last_launch_time = now
        launch_native_window()


def check_and_focus_existing_instance():
    """
    Si VortexCore Hub ya se encuentra abierto, envía una petición local
    para enfocar la ventana existente y termina el nuevo proceso de inmediato.
    """
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/focus_window", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            if resp.status == 200:
                print("VortexCore Hub ya está activo. Enfocando ventana existente...")
                sys.exit(0)
    except Exception:
        pass


if __name__ == "__main__":
    # 1. Guardia de Instancia Única (evita abrir ventanas duplicadas)
    check_and_focus_existing_instance()

    # 2. Asignar Identidad Nativa en Barra de Tareas de Windows (AppUserModelID)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Faundezz21.VortexCoreHub.Suite.7.8")
    except Exception:
        pass

    if not is_admin():
        request_admin_elevation()

    # Servidor multihilo: una petición lenta (debloat, apps de inicio) ya no congela la telemetría
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.allow_reuse_address = False  # en Windows permitiría dos instancias en el mismo puerto
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), VortexHttpHandler)
    except OSError:
        # Puerto ocupado: probablemente otra instancia arrancando; intentar enfocarla y salir
        check_and_focus_existing_instance()
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"VortexCore Hub no pudo iniciar: el puerto {PORT} está en uso por otro programa.",
                "VortexCore Hub", 0x10)
        except Exception:
            pass
        sys.exit(1)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Migrar auto-inicio de versiones anteriores (Run / carpeta Inicio) a tarea programada
    if is_admin():
        threading.Thread(target=migrate_legacy_autostart, daemon=True).start()

    print("=====================================================")
    print("  VORTEXCORE HUB // SYSTEM TRAY & REST ACTIVE")
    print(f"  Local Host: http://127.0.0.1:{PORT}")
    print("=====================================================")

    # Iniciar icono en la bandeja del sistema (System Tray junto al reloj)
    tray = SystemTrayApp(
        manager,
        on_open_callback=launch_or_focus_window,
        on_exit_callback=lambda: os._exit(0)
    )
    threading.Thread(target=tray.run, daemon=True).start()
    overlay.start()

    # Si se inicia automáticamente con Windows (--minimized o --tray), no abre la ventana
    is_minimized = any(arg in sys.argv for arg in ["--minimized", "--tray", "-m"])
    if not is_minimized:
        launch_or_focus_window()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.running = False
        server.shutdown()
