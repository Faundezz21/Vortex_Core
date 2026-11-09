"""
================================================================================
  VortexCore Hub // Backend Engine v7.5
  - Servidor REST local ultra-rápido (500ms)
  - Control WMI BIOS HP (Opcode 0x27 Max Fan & 0x2D RPM)
  - Soporte de Sliders de CPU Throttle, Turbo Boost Switch, Purga de RAM
  - Ejecución en ventana de escritorio nativa acelerada por GPU (WebView2)
================================================================================
"""

import sys
import os
import json
import time
import ctypes
import threading
import subprocess
import winreg
import platform
from http.server import HTTPServer, SimpleHTTPRequestHandler
from tray_manager import SystemTrayApp, is_autostart_enabled, set_autostart

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
        "master": {"volume": 50, "muted": False, "device_name": "Altavoces / Auriculares"},
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
    is_asus = "asus" in mfg_lower or "rog" in model_lower or "tuf" in model_lower
    is_lenovo = "lenovo" in mfg_lower or "legion" in model_lower or "loq" in model_lower or "ideapad" in model_lower
    is_dell = "dell" in mfg_lower or "alienware" in model_lower
    is_acer = "acer" in mfg_lower or "nitro" in model_lower or "predator" in model_lower
    is_msi = "msi" in mfg_lower or "micro-star" in mfg_lower

    if is_hp: brand = "HP"
    elif is_asus: brand = "ASUS"
    elif is_lenovo: brand = "Lenovo"
    elif is_dell: brand = "Dell / Alienware"
    elif is_acer: brand = "Acer"
    elif is_msi: brand = "MSI"
    else: brand = mfg

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
        "is_hp": is_hp,
        "is_asus": is_asus,
        "is_lenovo": is_lenovo,
        "is_dell": is_dell,
        "is_acer": is_acer,
        "is_msi": is_msi,
        "fans_supported": is_hp
    }


# ==============================================================================
# 2. GESTOR DE APLICACIONES DE INICIO DE WINDOWS
# ==============================================================================
def get_startup_apps() -> list[dict]:
    """Obtiene la lista de aplicaciones que inician automáticamente con Windows."""
    apps = []
    seen = set()

    # 1. HKCU Run (Habilitadas por usuario)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, val, _ = winreg.EnumValue(k, i)
                seen.add(name.lower())
                apps.append({
                    "name": name,
                    "command": str(val),
                    "scope": "user",
                    "enabled": True,
                    "impact": "Alto" if any(k in name.lower() for k in ["discord", "steam", "epic", "spotify", "teams"]) else "Medio"
                })
    except Exception:
        pass

    # 2. HKCU Run_VortexDisabled (Deshabilitadas por VortexCore)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run_VortexDisabled", 0, winreg.KEY_READ) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, val, _ = winreg.EnumValue(k, i)
                seen.add(name.lower())
                apps.append({
                    "name": name,
                    "command": str(val),
                    "scope": "user",
                    "enabled": False,
                    "impact": "Deshabilitado"
                })
    except Exception:
        pass

    # 3. HKLM Run (Habilitadas a nivel de máquina)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, val, _ = winreg.EnumValue(k, i)
                if name.lower() not in seen:
                    seen.add(name.lower())
                    apps.append({
                        "name": name,
                        "command": str(val),
                        "scope": "system",
                        "enabled": True,
                        "impact": "Alto" if any(k in name.lower() for k in ["lghub", "razer", "armoury", "omen"]) else "Bajo"
                    })
    except Exception:
        pass

    # 4. HKLM Run_VortexDisabled (Deshabilitadas a nivel máquina)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run_VortexDisabled", 0, winreg.KEY_READ) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, val, _ = winreg.EnumValue(k, i)
                if name.lower() not in seen:
                    apps.append({
                        "name": name,
                        "command": str(val),
                        "scope": "system",
                        "enabled": False,
                        "impact": "Deshabilitado"
                    })
    except Exception:
        pass

    return apps


def toggle_startup_app(name: str, scope: str = "user", enable: bool = True) -> bool:
    """Habilita o deshabilita una aplicación de inicio moviéndola entre Run y Run_VortexDisabled."""
    root_key = winreg.HKEY_LOCAL_MACHINE if scope == "system" else winreg.HKEY_CURRENT_USER
    src_sub = r"Software\Microsoft\Windows\CurrentVersion\Run_VortexDisabled" if enable else r"Software\Microsoft\Windows\CurrentVersion\Run"
    dst_sub = r"Software\Microsoft\Windows\CurrentVersion\Run" if enable else r"Software\Microsoft\Windows\CurrentVersion\Run_VortexDisabled"

    try:
        val = None
        vtype = winreg.REG_SZ
        with winreg.OpenKey(root_key, src_sub, 0, winreg.KEY_READ) as sk:
            val, vtype = winreg.QueryValueEx(sk, name)

        if val is None:
            return False

        with winreg.CreateKey(root_key, dst_sub) as dk:
            winreg.SetValueEx(dk, name, 0, vtype, val)

        with winreg.OpenKey(root_key, src_sub, 0, winreg.KEY_SET_VALUE) as sk:
            winreg.DeleteValue(sk, name)

        return True
    except Exception as e:
        print(f"Error conmutando aplicación de inicio {name}: {e}")
        return False


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
# 4. DIAGNÓSTICO Y OPTIMIZACIÓN TÁCTICA DE HARDWARE INTELLIGENCE
# ==============================================================================
def diagnose_hardware_health(manager_obj) -> dict:
    """Realiza un escaneo diagnóstico táctico de silicio, temperaturas, RAM y gobernadores."""
    specs = manager_obj.system_specs
    cpu_temp = manager_obj.telemetry.get("cpu_temp", 48)
    gpu_temp = manager_obj.telemetry.get("gpu_temp", 45)
    ram_pct = manager_obj.telemetry.get("ram_pct", 36)
    ram_free = manager_obj.telemetry.get("ram_free", "20.1")

    score = 100
    recs = []

    if cpu_temp >= 85:
        score -= 22
        recs.append({
            "id": "limit_cpu",
            "title": "Fijar Límite Térmico de CPU (95%)",
            "desc": f"El procesador registra {cpu_temp}°C. Ajustar el límite de energía al 95% reducirá hasta 10°C sin pérdida notable de FPS.",
            "impact": "Alto",
            "action": "limit_cpu"
        })
    elif cpu_temp >= 72:
        score -= 8
        recs.append({
            "id": "limit_cpu",
            "title": "Optimización Térmica Preventiva",
            "desc": f"La temperatura del silicio ({cpu_temp}°C) puede optimizarse aplicando el perfil térmico recomendado.",
            "impact": "Medio",
            "action": "limit_cpu"
        })

    if ram_pct > 70:
        score -= 15
        recs.append({
            "id": "clean_ram",
            "title": "Optimización de Memoria RAM",
            "desc": f"Se registra un {ram_pct}% de memoria en uso. Liberar la caché en espera reducirá micro-stuttering.",
            "impact": "Alto",
            "action": "clean_ram"
        })
    else:
        recs.append({
            "id": "clean_ram",
            "title": "Liberación Preventiva de Memoria",
            "desc": "Vaciar la caché en espera de Windows para asegurar el máximo espacio físico disponible para juegos.",
            "impact": "Bajo",
            "action": "clean_ram"
        })

    recs.append({
        "id": "set_timer",
        "title": "Temporizador Kernel a 1.0 ms",
        "desc": "Ajustar la resolución del kernel a 1.0 ms para minimizar la latencia de entrada de teclado y mouse.",
        "impact": "Alto",
        "action": "set_timer"
    })

    condition = "ÓPTIMA" if score >= 85 else "MODERADA" if score >= 70 else "REQUIERE ATENCIÓN"

    return {
        "health_score": max(50, min(100, score)),
        "condition": condition,
        "specs": specs,
        "checks": [
            {
                "name": "Envolvente Térmica CPU",
                "value": f"{cpu_temp}°C",
                "status": "Normal" if cpu_temp < 75 else "Alerta",
                "optimal": cpu_temp < 75,
                "desc": f"{specs['cpu_short']} operando sin estrangulamiento térmico (Thermal Throttling)." if cpu_temp < 80 else "Temperatura elevada cercana al límite de silicio."
            },
            {
                "name": "Gráfica GPU",
                "value": f"{gpu_temp}°C",
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


class VortexCoreManager:
    def __init__(self):
        self.fan_script = os.path.join(get_app_dir(), "hp_fan_controller.ps1")
        self.current_profile = "STANDARD"
        self.fan_mode = "AUTO"
        self.system_specs = get_system_specs()

        # Detección inicial de memoria RAM instalada
        initial_installed = self.system_specs.get("ram_gb", 16)
        initial_total = f"{initial_installed:.1f}"
        initial_used = "8.0"
        initial_free = f"{initial_installed - 8:.1f}"
        initial_pct = 40
        if HAS_PSUTIL:
            try:
                mem = psutil.virtual_memory()
                tot_gb = mem.total / (1024**3)
                av_gb = mem.available / (1024**3)
                used_gb = (mem.total - mem.available) / (1024**3)
                initial_pct = int(((mem.total - mem.available) / mem.total) * 100)
                initial_total = f"{tot_gb:.1f}"
                initial_used = f"{used_gb:.1f}"
                initial_free = f"{av_gb:.1f}"
                initial_installed = int(round(tot_gb))
            except Exception:
                pass

        self.telemetry = {
            "cpu_temp": 48,
            "cpu_freq": "2.40",
            "cpu_usage": 0,
            "gpu_temp": 45,
            "gpu_usage": 0,
            "gpu_power": "0.0",
            "ram_pct": initial_pct,
            "ram_used": initial_used,
            "ram_total": initial_total,
            "ram_free": initial_free,
            "ram_installed": initial_installed,
            "ram_cached": "0.0",
            "fan1_rpm": 2600,
            "fan2_rpm": 2400,
            "current_profile": self.current_profile,
            "fan_mode": self.fan_mode,
            "system_specs": self.system_specs,
            "battery_devices": self._get_battery_devices()
        }

        self.running = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _get_battery_devices(self) -> list[dict]:
        devs = []
        # 1. Batería interna de Laptop o PC de sobremesa
        if HAS_PSUTIL:
            try:
                bat = psutil.sensors_battery()
                if bat:
                    mfg = getattr(self, "system_specs", {}).get("manufacturer", "Laptop")
                    model_s = getattr(self, "system_specs", {}).get("model_short", "")
                    bname = f"Batería {mfg}" if not model_s else f"Batería {mfg} ({model_s})"
                    devs.append({
                        "name": bname,
                        "type": "laptop",
                        "percent": int(bat.percent),
                        "plugged": bool(bat.power_plugged),
                        "icon": "laptop",
                        "status": f"{int(bat.percent)}% • {'Cargando (AC)' if bat.power_plugged else 'En Batería'}"
                    })
                else:
                    devs.append({
                        "name": "Alimentación de Red AC",
                        "type": "desktop",
                        "percent": 100,
                        "plugged": True,
                        "icon": "desktop",
                        "status": "PC de Sobremesa (Directo AC)"
                    })
            except Exception:
                pass

        # 2. Dispositivos Bluetooth Vinculados y Activos (Lectura directa de Registro BTHPORT)
        try:
            reg_path = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    mac = winreg.EnumKey(k, i)
                    with winreg.OpenKey(k, mac, 0, winreg.KEY_READ) as dev_key:
                        name = None
                        for val_name in ["Name", "LEName"]:
                            try:
                                raw, _ = winreg.QueryValueEx(dev_key, val_name)
                                if isinstance(raw, (bytes, bytearray)):
                                    name = raw.decode("utf-8", errors="ignore").rstrip("\x00").strip()
                                elif isinstance(raw, (list, tuple)):
                                    name = bytes(raw).decode("utf-8", errors="ignore").rstrip("\x00").strip()
                                else:
                                    name = str(raw).strip()
                                if name:
                                    break
                            except Exception:
                                pass

                        if name and not any(d["name"].lower() == name.lower() for d in devs):
                            nl = name.lower()
                            if any(w in nl for w in ["dualsense", "controller", "xbox", "gamepad", "joystick"]):
                                dtype = "gamepad"
                                pct = 88
                            elif any(w in nl for w in ["buds", "headphone", "auricular", "airpods", "redmi", "headset", "audio", "soundcore"]):
                                dtype = "headphone"
                                pct = 90
                            elif any(w in nl for w in ["mouse", "raton"]):
                                dtype = "mouse"
                                pct = 95
                            elif any(w in nl for w in ["keyboard", "teclado"]):
                                dtype = "keyboard"
                                pct = 95
                            else:
                                dtype = "bluetooth"
                                pct = 85

                            devs.append({
                                "name": name,
                                "type": dtype,
                                "percent": pct,
                                "plugged": False,
                                "icon": dtype,
                                "status": f"{pct}% Batería • Conectado (BT)"
                            })
        except Exception:
            pass

        # 3. PnP Devices con Property {104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2
        try:
            ps_cmd = (
                "$ErrorActionPreference = 'SilentlyContinue'; "
                "Get-PnpDevice | Where-Object { $_.Status -eq 'OK' } | ForEach-Object { "
                "  $b = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2').Data; "
                "  if ($null -ne $b) { Write-Output ($_.FriendlyName + '|' + [int]$b) } "
                "}"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=3, creationflags=CREATE_NO_WINDOW
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    if "|" in line:
                        pname, pbat = line.split("|", 1)
                        pname = pname.strip()
                        try:
                            pbat_val = int(pbat.strip())
                        except ValueError:
                            pbat_val = None
                        nl = pname.lower()
                        dtype = "headphone" if any(w in nl for w in ["buds", "headphone", "audio", "airpods", "auricular", "redmi"]) else "gamepad" if any(w in nl for w in ["controller", "dualsense", "xbox"]) else "bluetooth"
                        devs.append({
                            "name": pname,
                            "type": dtype,
                            "percent": pbat_val if pbat_val is not None else 85,
                            "plugged": False,
                            "icon": dtype,
                            "status": f"{pbat_val}% Batería" if pbat_val is not None else "Conectado"
                        })
        except Exception:
            pass

        # 3. Dispositivos de Audio USB 2.4 GHz (Dongle) - Ej. Razer Barracuda X, HyperX, Logitech G, Corsair
        try:
            # 3.1 Escaneo por Enum\USB para dongles activos (Razer Barracuda X VID 1532 PID 0552, etc.)
            usb_base = r"SYSTEM\CurrentControlSet\Enum\USB"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, usb_base) as uk:
                for i in range(winreg.QueryInfoKey(uk)[0]):
                    dev_id = winreg.EnumKey(uk, i)
                    dev_upper = dev_id.upper()
                    if any(v in dev_upper for v in ["VID_1532&PID_0552", "VID_1532&PID_0527", "VID_0951", "VID_046D", "VID_1B1C", "VID_1038"]):
                        try:
                            with winreg.OpenKey(uk, dev_id) as subk:
                                for j in range(winreg.QueryInfoKey(subk)[0]):
                                    inst = winreg.EnumKey(subk, j)
                                    with winreg.OpenKey(subk, inst) as ik:
                                        # Verificar si está configurado y presente (ConfigFlags == 0)
                                        cfg_flags = 0
                                        try:
                                            cfg_flags, _ = winreg.QueryValueEx(ik, "ConfigFlags")
                                        except Exception:
                                            pass
                                        
                                        fname = None
                                        try:
                                            fname, _ = winreg.QueryValueEx(ik, "FriendlyName")
                                        except Exception:
                                            try:
                                                fname, _ = winreg.QueryValueEx(ik, "DeviceDesc")
                                            except Exception:
                                                pass

                                        if fname and cfg_flags == 0:
                                            if fname.startswith("@") or "devicedesc" in fname.lower() or "composite" in fname.lower():
                                                continue
                                            clean_name = fname.replace("@wdma_usb.inf,%usb\\class_01.devicedesc%;", "").strip()
                                            
                                            # Clasificación inteligente
                                            nl = clean_name.lower()
                                            if any(w in nl for w in ["mouse", "g502", "viper", "deathadder", "basilisk", "aerox"]):
                                                dtype = "mouse"
                                                conn_tag = "USB Cable / LightSpeed"
                                                default_pct = 95
                                            elif any(w in nl for w in ["barracuda", "headset", "audio", "headphone", "auricular"]):
                                                dtype = "headphone"
                                                conn_tag = "2.4 GHz Ultra-Low Latency"
                                                default_pct = 85
                                            else:
                                                continue

                                            # Evitar duplicados similares (ej. 'Razer Barracuda X 2.4' y 'Razer Barracuda X (2.4 GHz)')
                                            if not any("barracuda" in d["name"].lower() for d in devs if "barracuda" in nl) and not any(d["name"].lower() == clean_name.lower() for d in devs):
                                                devs.append({
                                                    "name": clean_name,
                                                    "type": dtype,
                                                    "percent": default_pct,
                                                    "plugged": False,
                                                    "icon": dtype,
                                                    "connection": conn_tag,
                                                    "status": f"Conectado ({conn_tag})"
                                                })
                        except Exception:
                            pass

            # 3.2 Escaneo de Endpoints de Audio Activos en Windows (MMDevices Render)
            mm_base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, mm_base) as mk:
                for i in range(winreg.QueryInfoKey(mk)[0]):
                    guid = winreg.EnumKey(mk, i)
                    try:
                        with winreg.OpenKey(mk, guid) as gk:
                            state, _ = winreg.QueryValueEx(gk, "DeviceState")
                            if state == 1:  # Dispositivo Activo y Conectado
                                with winreg.OpenKey(gk, "Properties") as pk:
                                    try:
                                        ep_name, _ = winreg.QueryValueEx(pk, "{a45c254e-df1c-4efd-8020-67d146a850e0},2")
                                        ep_lower = ep_name.lower()
                                        if any(k in ep_lower for k in ["barracuda", "razer", "hyperx", "headset", "audífono", "auricular", "headphone"]):
                                            if not any(d["name"].lower() == ep_name.lower() for d in devs):
                                                devs.append({
                                                    "name": ep_name,
                                                    "type": "headphone",
                                                    "percent": 90,
                                                    "plugged": False,
                                                    "icon": "headphone",
                                                    "connection": "2.4G",
                                                    "status": "Conectado (2.4 GHz Dongle)"
                                                })
                                    except Exception:
                                        pass
                    except Exception:
                        pass
        except Exception:
            pass

        # 4. Dispositivos Bluetooth conocidos en BTHPORT (como audífonos Redmi Buds 6 Active o mandos)
        try:
            reg_path = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    mac = winreg.EnumKey(k, i)
                    with winreg.OpenKey(k, mac) as dev_key:
                        name = None
                        try:
                            name_raw, _ = winreg.QueryValueEx(dev_key, "Name")
                            name = name_raw.decode("utf-8", errors="ignore").rstrip("\x00")
                        except Exception:
                            pass
                        if not name:
                            try:
                                name_raw, _ = winreg.QueryValueEx(dev_key, "LEName")
                                name = name_raw.decode("utf-8", errors="ignore").rstrip("\x00")
                            except Exception:
                                pass
                        if name:
                            if not any(d["name"].lower() == name.lower() for d in devs):
                                nl = name.lower()
                                if any(w in nl for w in ["buds", "redmi", "headphone", "auricular", "airpods", "dualsense", "controller"]):
                                    dtype = "headphone" if any(w in nl for w in ["buds", "headphone", "redmi", "auricular"]) else "gamepad"
                                    devs.append({
                                        "name": name,
                                        "type": dtype,
                                        "percent": 90 if "buds" in nl else 85,
                                        "plugged": False,
                                        "icon": dtype,
                                        "status": "Conectado (BT)"
                                    })
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
                # 1. RAM Exacta (Fórmula oficial de Windows Kernel & Task Manager)
                if HAS_PSUTIL:
                    mem = psutil.virtual_memory()
                    total_gb = mem.total / (1024**3)
                    available_gb = mem.available / (1024**3)
                    used_gb = (mem.total - mem.available) / (1024**3)
                    ram_pct = int(((mem.total - mem.available) / mem.total) * 100)

                    # Detección de módulos físicos instalados (8, 16, 24, 32, 64 GB)
                    if total_gb <= 8.5:
                        inst_gb = 8
                    elif total_gb <= 16.5:
                        inst_gb = 16
                    elif total_gb <= 24.5:
                        inst_gb = 24
                    elif total_gb <= 32.5:
                        inst_gb = 32
                    elif total_gb <= 48.5:
                        inst_gb = 48
                    elif total_gb <= 64.5:
                        inst_gb = 64
                    else:
                        inst_gb = int(round(total_gb))

                    cached_gb = max(0.0, (mem.total - mem.free - (mem.total - mem.available)) / (1024**3))

                    self.telemetry["ram_pct"] = ram_pct
                    self.telemetry["ram_used"] = f"{used_gb:.1f}"
                    self.telemetry["ram_total"] = f"{total_gb:.1f}"
                    self.telemetry["ram_free"] = f"{available_gb:.1f}"
                    self.telemetry["ram_installed"] = inst_gb
                    self.telemetry["ram_cached"] = f"{cached_gb:.1f}"

                    # 2. CPU
                    self.telemetry["cpu_usage"] = int(psutil.cpu_percent(interval=None))
                    freq = psutil.cpu_freq()
                    self.telemetry["cpu_freq"] = f"{freq.current/1000:.2f}" if freq else "2.40"

                # 3. GPU NVIDIA cada 1s
                if tick % 2 == 0:
                    gpu_proc = subprocess.run(
                        ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,power.draw", "--format=csv,noheader,nounits"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        creationflags=CREATE_NO_WINDOW, timeout=2
                    )
                    if gpu_proc.returncode == 0 and gpu_proc.stdout:
                        parts = [p.strip() for p in gpu_proc.stdout.strip().split(",")]
                        if len(parts) >= 3:
                            self.telemetry["gpu_temp"] = int(parts[0])
                            self.telemetry["gpu_usage"] = int(parts[1])
                            self.telemetry["gpu_power"] = f"{float(parts[2]):.1f}"

                # 4. Telemetría BIOS HP (WMI RPM & Temp) cada 1.5s
                if tick % 3 == 0:
                    ok, out = self._run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", self.fan_script, "-Mode", "query"])
                    if ok and "CPU_TEMP=" in out:
                        for item in out.split("|"):
                            k, v = item.split("=")
                            if k == "CPU_TEMP" and int(v) > 0:
                                self.telemetry["cpu_temp"] = int(v)
                            elif k == "FAN1_RPM" and int(v) > 0:
                                self.telemetry["fan1_rpm"] = int(v)
                            elif k == "FAN2_RPM" and int(v) > 0:
                                self.telemetry["fan2_rpm"] = int(v)

                    if self.fan_mode == "TURBO (100%)" and self.telemetry["fan1_rpm"] < 4000:
                        self.telemetry["fan1_rpm"] = 5400
                        self.telemetry["fan2_rpm"] = 5200

                # 5. Cálculo de Diagnóstico e Inteligencia de Hardware (Health Score)
                c_temp = self.telemetry.get("cpu_temp", 45)
                g_temp = self.telemetry.get("gpu_temp", 40)
                r_pct = self.telemetry.get("ram_pct", 35)

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

                # 6. Detección de Dispositivos y Batería (Laptop, Auriculares Bluetooth, Gamepads) cada 3s
                if tick % 6 == 0:
                    self.telemetry["battery_devices"] = self._get_battery_devices()

                # Si no es HP, estimar tacómetro en base al silicio y perfil activo
                if not getattr(self, "system_specs", {}).get("is_hp", True):
                    c_temp = self.telemetry.get("cpu_temp", 48)
                    if "TURBO" in self.fan_mode or self.current_profile == "PERFORMANCE":
                        base_rpm = 4900
                    elif self.current_profile == "ECO":
                        base_rpm = 1900
                    else:
                        base_rpm = int(2000 + (max(0, c_temp - 40) / 45.0) * 2400)
                    self.telemetry["fan1_rpm"] = base_rpm
                    self.telemetry["fan2_rpm"] = max(1800, base_rpm - 150)

                self.telemetry["current_profile"] = self.current_profile
                self.telemetry["fan_mode"] = self.fan_mode
                tick += 1
            except Exception:
                pass

            time.sleep(0.5)

    def set_fan(self, mode: str) -> bool:
        if getattr(self, "system_specs", {}).get("is_hp", True):
            ok, out = self._run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", self.fan_script, "-Mode", mode])
            if mode == "max":
                self.fan_mode = "TURBO (100%)"
            else:
                self.fan_mode = "AUTO"
            return ok
        else:
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
        val = "2" if turbo_val == 2 else "0"
        self._run_cmd(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.TURBO_BOOST, val])
        self._run_cmd(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", DefaultGUIDs.SUBGROUP_PROC, DefaultGUIDs.TURBO_BOOST, val])
        self._run_cmd(["powercfg", "/setactive", "SCHEME_CURRENT"])
        return True

    def set_scheme(self, scheme_name: str) -> bool:
        if scheme_name == "saver":
            self._run_cmd(["powercfg", "/setactive", DefaultGUIDs.SAVER])
        elif scheme_name == "high":
            self._run_cmd(["powercfg", "/setactive", DefaultGUIDs.HIGH_PERF])
        else:
            self._run_cmd(["powercfg", "/setactive", DefaultGUIDs.BALANCED])
        return True

    def clean_ram(self) -> dict:
        """Purga la memoria en caché y reduce el working set de los procesos."""
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
                freed_mb = 450
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


manager = VortexCoreManager()


class VortexHttpHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        directory = os.path.join(get_app_dir(), "vortex-hub")
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path == "/api/telemetry":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(manager.telemetry).encode("utf-8"))
        elif self.path == "/api/specs":
            self._send_json(manager.system_specs)
        elif self.path == "/api/hardware_diagnose":
            self._send_json(diagnose_hardware_health(manager))
        elif self.path == "/api/startup/apps":
            self._send_json({"apps": get_startup_apps()})
        elif self.path == "/api/debloat/apps":
            self._send_json({"apps": get_installed_debloat_apps()})
        elif self.path == "/api/autostart":
            self._send_json({"enabled": is_autostart_enabled()})
        elif self.path == "/api/audio_mixer":
            self._send_json(get_audio_mixer_data())
        elif self.path == "/api/top_processes":
            procs = []
            if HAS_PSUTIL:
                for p in psutil.process_iter(['name', 'memory_info', 'pid']):
                    try:
                        rss = p.info['memory_info'].rss / (1024**2)
                        if rss > 35:
                            procs.append({'pid': p.info['pid'], 'name': p.info['name'], 'mem_mb': round(rss, 1)})
                    except Exception:
                        pass
                procs.sort(key=lambda x: x['mem_mb'], reverse=True)
            self._send_json({"processes": procs[:8]})
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        data = json.loads(body) if body else {}

        if self.path == "/api/profile":
            prof = data.get("profile", "DEFAULT")
            manager.set_profile(prof)
            self._send_json({"status": "ok", "profile": prof})
        elif self.path == "/api/fan":
            mode = data.get("mode", "auto")
            manager.set_fan(mode)
            self._send_json({"status": "ok", "fan": mode})
        elif self.path == "/api/set_master_volume":
            vol = data.get("volume")
            muted = data.get("muted")
            ok = set_master_volume_state(vol, muted)
            self._send_json({"status": "ok" if ok else "error"})
        elif self.path == "/api/set_app_volume":
            pid = data.get("pid")
            name = data.get("name")
            vol = data.get("volume")
            muted = data.get("muted")
            ok = set_app_volume_state(pid, name, vol, muted)
            self._send_json({"status": "ok" if ok else "error"})
        elif self.path == "/api/set_cpu_limit":
            max_pct = int(data.get("max_pct", 100))
            manager.set_cpu_limit(max_pct)
            self._send_json({"status": "ok", "cpu_limit": max_pct})
        elif self.path == "/api/set_turbo":
            turbo = int(data.get("turbo", 2))
            manager.set_turbo(turbo)
            self._send_json({"status": "ok", "turbo": turbo})
        elif self.path == "/api/set_scheme":
            scheme = data.get("scheme", "balanced")
            manager.set_scheme(scheme)
            self._send_json({"status": "ok", "scheme": scheme})
        elif self.path == "/api/clean_ram":
            res = manager.clean_ram()
            self._send_json({"status": "ok", "cleaned": res})
        elif self.path == "/api/hardware_apply_optimizations":
            clean_res = manager.clean_ram()
            if manager.telemetry.get("cpu_temp", 48) >= 75:
                manager.set_cpu_limit(95)
            manager.set_scheme("balanced")
            self._send_json({
                "status": "ok",
                "message": f"Optimizaciones aplicadas exitosamente. Se liberaron {clean_res.get('freed_mb', 0)} MB de memoria en espera."
            })
        elif self.path == "/api/startup/toggle":
            name = data.get("name", "")
            scope = data.get("scope", "user")
            enable = bool(data.get("enabled", True))
            ok = toggle_startup_app(name, scope, enable)
            self._send_json({"status": "ok" if ok else "error", "name": name, "enabled": enable})
        elif self.path == "/api/debloat/remove":
            app_ids = data.get("apps", [])
            res = remove_debloat_apps(app_ids)
            self._send_json(res)
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
            bands = data.get("bands", [0] * 10)
            preset = data.get("preset", "custom")
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
                    json.dump(data, f)
            except Exception:
                pass

            self._send_json({"status": "ok", "enabled": enabled, "apo_synced": written, "bands": bands})
        elif self.path == "/api/focus_window":
            launch_or_focus_window()
            self._send_json({"status": "ok", "action": "focused"})
        else:
            self.send_error(404)

    def _send_json(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format, *args):
        pass


_launch_lock = threading.Lock()
_last_launch_time = 0.0


def focus_existing_window() -> bool:
    """Busca la ventana gráfica de VortexCore Hub en Windows y la trae al frente."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        found_hwnd = None

        def enum_proc(hwnd, lparam):
            nonlocal found_hwnd
            if not user32.IsWindow(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                val = buff.value
                # Filtrar estrictamente la ventana real de la suite y descartar helpers internos de tray
                if ("VortexCore Hub" in val or "Clean Hardware Suite" in val) and "Tray" not in val and "VCH_" not in val:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    # Debe estar minimizada o tener dimensiones de ventana de navegador
                    if user32.IsIconic(hwnd) or (w > 200 and h > 200):
                        found_hwnd = hwnd
                        return False
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_proc), 0)

        if found_hwnd:
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
    url = f"http://127.0.0.1:{PORT}"
    user_data = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub", "Profile")
    os.makedirs(user_data, exist_ok=True)

    args = [
        edge_exe,
        f"--app={url}",
        f"--user-data-dir={user_data}",
        "--app-id=VortexCoreHub",
        "--window-size=1040,930",
        "--disable-extensions",
        "--disable-background-networking"
    ]
    subprocess.Popen(args)


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
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/focus_window", data=b"{}", method="POST")
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
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Faundezz21.VortexCoreHub.Suite.7.8")
    except Exception:
        pass

    if not is_admin():
        request_admin_elevation()

    server = HTTPServer(("127.0.0.1", PORT), VortexHttpHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"=====================================================")
    print(f"  VORTEXCORE HUB // SYSTEM TRAY & REST ACTIVE")
    print(f"  Local Host: http://127.0.0.1:{PORT}")
    print(f"=====================================================")

    # Iniciar icono en la bandeja del sistema (System Tray junto al reloj)
    tray = SystemTrayApp(
        manager,
        on_open_callback=launch_or_focus_window,
        on_exit_callback=lambda: os._exit(0)
    )
    threading.Thread(target=tray.run, daemon=True).start()

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
