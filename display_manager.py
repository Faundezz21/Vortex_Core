"""
================================================================================
  VortexCore Hub // Gestión de Pantalla
  - Lista tasas de refresco (Hz) reales soportadas por la pantalla principal
  - Cambia Hz al instante vía Win32 (EnumDisplaySettingsW / ChangeDisplaySettingsExW)
  - Cambio automático de Hz entre Cargador (AC) y Batería
  - Lectura y ajuste de brillo nativo de notebook vía WMI (root\\wmi)
================================================================================
"""

import ctypes
import json
import os
import struct
import subprocess
import sys
import threading
import time
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000

ENUM_CURRENT_SETTINGS = -1
ENUM_REGISTRY_SETTINGS = -2
DM_POSITION = 0x00000020
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
CDS_UPDATEREGISTRY = 0x00000001
CDS_SET_PRIMARY = 0x00000010
CDS_NORESET = 0x10000000
DISP_CHANGE_SUCCESSFUL = 0


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def config_path() -> str:
    return os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "VortexCoreHub",
        "pantalla.json",
    )


def load_config() -> dict:
    cfg = {"auto_hz": False, "ac_hz": None, "battery_hz": None}
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "auto_hz" in data:
                cfg["auto_hz"] = bool(data["auto_hz"])
            for k in ("ac_hz", "battery_hz"):
                v = data.get(k)
                cfg[k] = int(v) if isinstance(v, (int, float)) and int(v) >= 24 else None
    except (OSError, ValueError, TypeError):
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(config_path()), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def get_ac_plugged() -> bool | None:
    """Devuelve True si está conectado al cargador, False si está en batería, None si no aplica."""
    if not IS_WINDOWS:
        return None
    try:
        st = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
            if st.ACLineStatus == 1:
                return True
            if st.ACLineStatus == 0:
                return False
    except Exception:
        pass
    return None


def get_display_modes(device_name: str | None = None) -> dict:
    """Lee resolución actual, nombre del adaptador/pantalla y frecuencias Hz soportadas."""
    if not IS_WINDOWS:
        return {
            "supported": False,
            "id": device_name or "",
            "width": 0,
            "height": 0,
            "current_hz": 0,
            "available_hz": [],
            "adapter": "",
            "dpi_scale": 100,
        }

    user32 = ctypes.windll.user32
    cur = DEVMODEW()
    cur.dmSize = ctypes.sizeof(DEVMODEW)
    if not user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(cur)):
        return {
            "supported": False,
            "id": device_name or "",
            "width": 0,
            "height": 0,
            "current_hz": 0,
            "available_hz": [],
            "adapter": "",
            "dpi_scale": 100,
        }

    hz_set = set()
    res_set = set()
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    idx = 0
    while user32.EnumDisplaySettingsW(device_name, idx, ctypes.byref(mode)):
        if mode.dmPelsWidth >= 800 and mode.dmPelsHeight >= 600 and mode.dmBitsPerPel >= 16:
            res_set.add((int(mode.dmPelsWidth), int(mode.dmPelsHeight)))
        if (
            mode.dmPelsWidth == cur.dmPelsWidth
            and mode.dmPelsHeight == cur.dmPelsHeight
            and mode.dmBitsPerPel == cur.dmBitsPerPel
            and mode.dmDisplayFrequency >= 24
        ):
            hz_set.add(int(mode.dmDisplayFrequency))
        idx += 1
        if idx > 2048:
            break

    res_set.add((int(cur.dmPelsWidth), int(cur.dmPelsHeight)))
    avail_res = [
        {"width": w, "height": h, "label": f"{w} × {h}"}
        for w, h in sorted(res_set, key=lambda r: (r[0] * r[1], r[0]), reverse=True)
    ]

    if cur.dmDisplayFrequency >= 24:
        hz_set.add(int(cur.dmDisplayFrequency))

    adapter = ""
    try:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if device_name:
            i = 0
            while user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                if dd.DeviceName == device_name:
                    adapter = (dd.DeviceString or "").strip()
                    break
                i += 1
        elif user32.EnumDisplayDevicesW(None, 0, ctypes.byref(dd), 0):
            adapter = (dd.DeviceString or "").strip()
    except Exception:
        pass

    dpi_scale = 100
    try:
        dpi = user32.GetDpiForSystem()
        if dpi and dpi > 0:
            dpi_scale = int(round((dpi / 96.0) * 100))
    except Exception:
        pass

    return {
        "supported": True,
        "id": device_name or "",
        "width": int(cur.dmPelsWidth),
        "height": int(cur.dmPelsHeight),
        "x": int(cur.dmPositionX),
        "y": int(cur.dmPositionY),
        "current_hz": int(cur.dmDisplayFrequency),
        "available_hz": sorted(hz_set),
        "available_resolutions": avail_res,
        "adapter": adapter,
        "dpi_scale": dpi_scale,
    }


def _query_display_targets(return_details: bool = False):
    """Devuelve {gdi_name: nombre_edid} (y opcionalmente lista completa de targets físicos)."""
    targets: dict[str, str] = {}
    details: list[dict] = []
    if not IS_WINDOWS:
        return (targets, details) if return_details else targets
    try:
        u = ctypes.windll.user32
        np = ctypes.c_uint32()
        nm = ctypes.c_uint32()
        if u.GetDisplayConfigBufferSizes(1, ctypes.byref(np), ctypes.byref(nm)) != 0 or np.value == 0:
            return (targets, details) if return_details else targets
        paths = (ctypes.c_byte * (72 * np.value))()
        modes = (ctypes.c_byte * (64 * nm.value))()
        if u.QueryDisplayConfig(1, ctypes.byref(np), paths, ctypes.byref(nm), modes, None) != 0:
            return (targets, details) if return_details else targets
        raw = bytes(paths)
        seen = set()
        for i in range(np.value):
            c = raw[i * 72:(i + 1) * 72]
            t_aid, t_id, tech, t_avail, p_flags = (
                struct.unpack_from("<q", c, 20)[0],
                struct.unpack_from("<I", c, 28)[0],
                struct.unpack_from("<I", c, 36)[0],
                struct.unpack_from("<I", c, 60)[0],
                struct.unpack_from("<I", c, 68)[0],
            )
            if not t_avail or (t_aid, t_id) in seen:
                continue
            seen.add((t_aid, t_id))
            is_active = bool(p_flags & 1)
            is_internal = (tech == 0x80000000)
            hdr = ctypes.create_string_buffer(84)
            struct.pack_into("<IIqI", hdr, 0, 1, 84, struct.unpack_from("<q", c, 0)[0], struct.unpack_from("<I", c, 8)[0])
            gname = hdr.raw[20:84].decode("utf-16-le", "ignore").split("\x00")[0] if u.DisplayConfigGetDeviceInfo(hdr) == 0 else ""
            thdr = ctypes.create_string_buffer(420)
            struct.pack_into("<IIqI", thdr, 0, 2, 420, t_aid, t_id)
            fname = thdr.raw[36:164].decode("utf-16-le", "ignore").split("\x00")[0].strip() if u.DisplayConfigGetDeviceInfo(thdr) == 0 else ""
            if is_active or fname or is_internal:
                details.append({
                    "t_aid": t_aid,
                    "t_id": t_id,
                    "gname": gname,
                    "fname": fname,
                    "active": is_active,
                    "internal": is_internal,
                })
            if gname and (fname or is_active):
                if gname not in targets or (fname and not targets[gname]):
                    targets[gname] = fname
    except Exception:
        pass
    return (targets, details) if return_details else targets


def list_displays() -> list[dict]:
    """Lista todas las pantallas conectadas a Windows (activas y desconectadas)."""
    if not IS_WINDOWS:
        return []
    user32 = ctypes.windll.user32
    real_targets, target_details = _query_display_targets(return_details=True)
    displays = []
    seen_ids = set()
    i = 0
    while True:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        i += 1
        attached = bool(dd.StateFlags & 0x1)  # ATTACHED_TO_DESKTOP
        if not attached and dd.DeviceName not in real_targets:
            continue
        mon = DISPLAY_DEVICEW()
        mon.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        has_mon = bool(user32.EnumDisplayDevicesW(dd.DeviceName, 0, ctypes.byref(mon), 0))

        info = get_display_modes(dd.DeviceName)
        if not info["supported"]:
            reg = DEVMODEW()
            reg.dmSize = ctypes.sizeof(DEVMODEW)
            ok = user32.EnumDisplaySettingsW(dd.DeviceName, ENUM_REGISTRY_SETTINGS, ctypes.byref(reg))
            if not ok or reg.dmPelsWidth == 0:
                ok = user32.EnumDisplaySettingsW(dd.DeviceName, 0, ctypes.byref(reg))
            w = int(reg.dmPelsWidth) if ok and reg.dmPelsWidth >= 800 else 1920
            h = int(reg.dmPelsHeight) if ok and reg.dmPelsHeight >= 600 else 1080
            hz = int(reg.dmDisplayFrequency) if ok and reg.dmDisplayFrequency >= 24 else 60
            info = {
                "supported": True,
                "id": dd.DeviceName,
                "width": w,
                "height": h,
                "x": 0,
                "y": 0,
                "current_hz": hz,
                "available_hz": [],
                "available_resolutions": [],
                "adapter": (dd.DeviceString or "").strip(),
                "dpi_scale": 100,
            }

        edid_name = real_targets.get(dd.DeviceName, "")
        mon_name = edid_name or ((mon.DeviceString or "").strip() if has_mon else "")
        is_primary = attached and bool(dd.StateFlags & 0x4)
        seen_ids.add(dd.DeviceName)
        displays.append({
            **info,
            "id": dd.DeviceName,
            "attached": attached,
            "is_primary": is_primary,
            "monitor": mon_name or "Monitor",
            "adapter": (dd.DeviceString or "").strip() or info["adapter"],
        })

    # Agregar monitores físicamente conectados pero desconectados del escritorio (ej. panel interno eDP)
    known_fnames = {d["monitor"] for d in displays if d.get("monitor")}
    for td in target_details:
        if td["active"]:
            continue
        if td["fname"] and td["fname"] in known_fnames:
            continue
        tid = f"target:{td['t_aid']}:{td['t_id']}"
        if td["gname"] and td["gname"] not in seen_ids:
            tid = td["gname"]
        label = td["fname"] or ("Pantalla integrada" if td["internal"] else "Monitor")
        displays.append({
            "supported": True,
            "id": tid,
            "width": 1920,
            "height": 1080,
            "x": 0,
            "y": 0,
            "current_hz": 60,
            "available_hz": [],
            "available_resolutions": [],
            "adapter": "Desconectada",
            "dpi_scale": 100,
            "attached": False,
            "is_primary": False,
            "monitor": label,
            "name": f"{label} (Desconectada)",
        })

    displays.sort(key=lambda d: (not d["attached"], not d["is_primary"], d["id"]))
    for idx, d in enumerate(displays, 1):
        label = d["monitor"] if d["monitor"] != "Generic PnP Monitor" else f"Pantalla {idx}"
        suffix = " (Principal)" if d["is_primary"] else (" (Desconectada)" if not d["attached"] else "")
        d["name"] = f"{label}{suffix}"
    return displays


def _commit_display_changes(user32) -> int:
    return int(user32.ChangeDisplaySettingsExW(None, None, None, 0, None))


def set_primary_display(device_name: str) -> dict:
    """Establece la pantalla indicada como monitor principal."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}
    displays = [d for d in list_displays() if d.get("attached")]
    target = next((d for d in displays if d["id"] == device_name), None)
    if not target:
        return {"status": "error", "message": "La pantalla debe estar activa para hacerla principal."}
    if target["is_primary"]:
        return {"status": "ok", "message": "Ya es la pantalla principal."}

    user32 = ctypes.windll.user32
    t_dm = DEVMODEW()
    t_dm.dmSize = ctypes.sizeof(DEVMODEW)
    if not user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(t_dm)):
        return {"status": "error", "message": "No se pudo leer la configuración actual."}
    ox, oy = int(t_dm.dmPositionX), int(t_dm.dmPositionY)

    for d in displays:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        if not user32.EnumDisplaySettingsW(d["id"], ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
            continue
        dm.dmPositionX = int(dm.dmPositionX) - ox
        dm.dmPositionY = int(dm.dmPositionY) - oy
        dm.dmFields = DM_POSITION
        flags = CDS_UPDATEREGISTRY | CDS_NORESET | (CDS_SET_PRIMARY if d["id"] == device_name else 0)
        user32.ChangeDisplaySettingsExW(d["id"], ctypes.byref(dm), None, flags, None)

    rc = _commit_display_changes(user32)
    if rc == DISP_CHANGE_SUCCESSFUL:
        return {"status": "ok"}
    return {"status": "error", "message": f"Windows devolvió código {rc}."}


def disconnect_display(device_name: str) -> dict:
    """Desconecta del escritorio una pantalla secundaria (o promueve otra si era principal)."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}
    active = [d for d in list_displays() if d.get("attached")]
    if len(active) <= 1:
        return {"status": "error", "message": "No puedes desconectar la única pantalla activa."}
    target = next((d for d in active if d["id"] == device_name), None)
    if not target:
        return {"status": "error", "message": "La pantalla ya está desconectada."}
    if target["is_primary"]:
        other = next((d for d in active if d["id"] != device_name), None)
        if other:
            set_primary_display(other["id"])

    user32 = ctypes.windll.user32
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    dm.dmFields = DM_POSITION | DM_PELSWIDTH | DM_PELSHEIGHT
    dm.dmPelsWidth = 0
    dm.dmPelsHeight = 0
    user32.ChangeDisplaySettingsExW(device_name, ctypes.byref(dm), None, CDS_UPDATEREGISTRY | CDS_NORESET, None)
    rc = _commit_display_changes(user32)
    if rc == DISP_CHANGE_SUCCESSFUL:
        return {"status": "ok"}
    return {"status": "error", "message": f"Windows devolvió código {rc}."}


def connect_display(device_name: str) -> dict:
    """Conecta (extiende) una pantalla desconectada al escritorio."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}
    displays = list_displays()
    target = next((d for d in displays if d["id"] == device_name), None)
    if not target:
        return {"status": "error", "message": "No se encontró la pantalla."}
    if target.get("attached"):
        return {"status": "ok", "message": "La pantalla ya está conectada."}

    if str(device_name).startswith("target:"):
        # Activar pantalla desconectada vía SetDisplayConfig (extender todas las disponibles)
        try:
            ctypes.windll.user32.SetDisplayConfig(0, None, 0, None, 0x00000004 | 0x00000080)  # SDC_TOPOLOGY_EXTEND | SDC_APPLY
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    user32 = ctypes.windll.user32
    max_right = 0
    for d in displays:
        if not d.get("attached"):
            continue
        cur = DEVMODEW()
        cur.dmSize = ctypes.sizeof(DEVMODEW)
        if user32.EnumDisplaySettingsW(d["id"], ENUM_CURRENT_SETTINGS, ctypes.byref(cur)):
            max_right = max(max_right, int(cur.dmPositionX) + int(cur.dmPelsWidth))

    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    best = None
    best_score = (-1, -1)
    idx = 0
    probe = DEVMODEW()
    probe.dmSize = ctypes.sizeof(DEVMODEW)
    while user32.EnumDisplaySettingsW(device_name, idx, ctypes.byref(probe)):
        score = (int(probe.dmPelsWidth) * int(probe.dmPelsHeight), int(probe.dmDisplayFrequency))
        if int(probe.dmBitsPerPel) >= 32 and score > best_score:
            best_score = score
            best = (int(probe.dmPelsWidth), int(probe.dmPelsHeight), int(probe.dmDisplayFrequency), int(probe.dmBitsPerPel))
        idx += 1
        if idx > 2048:
            break

    if best:
        dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency, dm.dmBitsPerPel = best
    else:
        ok = user32.EnumDisplaySettingsW(device_name, ENUM_REGISTRY_SETTINGS, ctypes.byref(dm))
        if not ok or dm.dmPelsWidth == 0:
            ok = user32.EnumDisplaySettingsW(device_name, 0, ctypes.byref(dm))
        if not ok:
            return {"status": "error", "message": "No se encontró un modo válido para esa pantalla."}

    dm.dmPositionX = max_right
    dm.dmPositionY = 0
    dm.dmFields = DM_POSITION | DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    user32.ChangeDisplaySettingsExW(device_name, ctypes.byref(dm), None, CDS_UPDATEREGISTRY | CDS_NORESET, None)
    rc = _commit_display_changes(user32)
    if rc == DISP_CHANGE_SUCCESSFUL:
        return {"status": "ok"}
    return {"status": "error", "message": f"Windows devolvió código {rc}."}


def set_resolution(width: int, height: int, device_name: str | None = None) -> dict:
    """Cambia la resolución de la pantalla indicada manteniendo o maximizando los Hz."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}
    try:
        tw, th = int(width), int(height)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Resolución inválida."}
    target_dev = device_name or None
    user32 = ctypes.windll.user32
    cur = DEVMODEW()
    cur.dmSize = ctypes.sizeof(DEVMODEW)
    if not user32.EnumDisplaySettingsW(target_dev, ENUM_CURRENT_SETTINGS, ctypes.byref(cur)):
        return {"status": "error", "message": "No se pudo leer la pantalla."}

    best_hz = 0
    probe = DEVMODEW()
    probe.dmSize = ctypes.sizeof(DEVMODEW)
    idx = 0
    while user32.EnumDisplaySettingsW(target_dev, idx, ctypes.byref(probe)):
        if int(probe.dmPelsWidth) == tw and int(probe.dmPelsHeight) == th and int(probe.dmBitsPerPel) == int(cur.dmBitsPerPel):
            if int(probe.dmDisplayFrequency) == int(cur.dmDisplayFrequency):
                best_hz = int(cur.dmDisplayFrequency)
                break
            best_hz = max(best_hz, int(probe.dmDisplayFrequency))
        idx += 1
        if idx > 2048:
            break
    if best_hz == 0:
        return {"status": "error", "message": f"{tw}×{th} no está soportado por esta pantalla."}

    cur.dmPelsWidth = tw
    cur.dmPelsHeight = th
    cur.dmDisplayFrequency = best_hz
    cur.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    rc = user32.ChangeDisplaySettingsExW(target_dev, ctypes.byref(cur), None, CDS_UPDATEREGISTRY, None)
    if rc == DISP_CHANGE_SUCCESSFUL:
        return {"status": "ok", "width": tw, "height": th, "hz": best_hz}
    return {"status": "error", "message": f"Windows devolvió código {rc}."}


def set_projection_mode(mode: str) -> dict:
    """Cambia el modo de proyección de Windows: internal, clone, extend o external."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}
    valid = {"internal", "clone", "extend", "external"}
    m = str(mode or "").strip().lower()
    if m not in valid:
        return {"status": "error", "message": "Modo de proyección inválido."}
    try:
        subprocess.Popen(["DisplaySwitch.exe", f"/{m}"], creationflags=CREATE_NO_WINDOW)
        return {"status": "ok", "mode": m}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_display_layout(positions: list[dict]) -> dict:
    """Aplica las posiciones (x, y) de las pantallas activas (la principal queda en 0, 0)."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}
    if not isinstance(positions, list) or len(positions) < 2:
        return {"status": "error", "message": "Se requieren al menos 2 pantallas activas."}

    active = {d["id"]: d for d in list_displays() if d.get("attached")}
    pos_map = {}
    for p in positions:
        if isinstance(p, dict) and p.get("id") in active:
            try:
                pos_map[p["id"]] = (int(round(float(p["x"]))), int(round(float(p["y"]))))
            except (TypeError, ValueError):
                pass
    if len(pos_map) < 2:
        return {"status": "error", "message": "Coordenadas inválidas."}

    primary_id = next((did for did, d in active.items() if d.get("is_primary")), None) or next(iter(pos_map))
    ox, oy = pos_map.get(primary_id, (0, 0))

    user32 = ctypes.windll.user32
    for did, (px, py) in pos_map.items():
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        if not user32.EnumDisplaySettingsW(did, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
            continue
        dm.dmPositionX = px - ox
        dm.dmPositionY = py - oy
        dm.dmFields = DM_POSITION
        flags = CDS_UPDATEREGISTRY | CDS_NORESET | (CDS_SET_PRIMARY if did == primary_id else 0)
        user32.ChangeDisplaySettingsExW(did, ctypes.byref(dm), None, flags, None)

    rc = _commit_display_changes(user32)
    if rc == DISP_CHANGE_SUCCESSFUL:
        return {"status": "ok"}
    return {"status": "error", "message": f"Windows devolvió código {rc}."}


_IDENTIFY_LOCK = threading.Lock()
_IDENTIFY_SEQ = 0


def _show_identify_overlays(targets: list[tuple[int, int, int, int, str]], duration_ms: int, seq: int) -> None:
    """Muestra números flotantes topmost sin robar foco en cada monitor activo."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hdc", wintypes.HDC),
            ("fErase", wintypes.BOOL),
            ("rcPaint", wintypes.RECT),
            ("fRestore", wintypes.BOOL),
            ("fIncUpdate", wintypes.BOOL),
            ("rgbReserved", ctypes.c_byte * 32),
        ]

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.UnregisterClassW.restype = wintypes.BOOL
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.UpdateWindow.argtypes = [wintypes.HWND]
    user32.UpdateWindow.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    user32.BeginPaint.restype = wintypes.HDC
    user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    user32.EndPaint.restype = wintypes.BOOL
    user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
    user32.FillRect.restype = ctypes.c_int
    user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT]
    user32.DrawTextW.restype = ctypes.c_int
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    user32.SetWindowRgn.restype = ctypes.c_int
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
    user32.SetTimer.restype = ctypes.c_size_t
    user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
    user32.KillTimer.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None

    gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
    gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
    gdi32.CreatePen.restype = wintypes.HPEN
    gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
    gdi32.RoundRect.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    gdi32.RoundRect.restype = wintypes.BOOL
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.SetBkMode.restype = ctypes.c_int
    gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi32.SetTextColor.restype = wintypes.COLORREF
    gdi32.CreateFontW.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR,
    ]
    gdi32.CreateFontW.restype = wintypes.HFONT

    WM_PAINT = 0x000F
    WM_TIMER = 0x0113
    WS_POPUP = 0x80000000
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    SW_SHOWNOACTIVATE = 4
    DT_CENTER = 0x00000001
    DT_VCENTER = 0x00000004
    DT_SINGLELINE = 0x00000020
    TRANSPARENT = 1
    PS_SOLID = 0

    badge_w, badge_h = 136, 136
    labels_by_hwnd: dict[int, str] = {}
    hwnds: list[int] = []

    bg_brush = gdi32.CreateSolidBrush(0x001E140B)
    border_pen = gdi32.CreatePen(PS_SOLID, 2, 0x00FFD924)
    font = gdi32.CreateFontW(-64, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")

    def wnd_proc(hwnd, msg, wparam, lparam):
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            rc = wintypes.RECT(0, 0, badge_w, badge_h)
            user32.FillRect(hdc, ctypes.byref(rc), bg_brush)
            old_brush = gdi32.SelectObject(hdc, bg_brush)
            old_pen = gdi32.SelectObject(hdc, border_pen)
            gdi32.RoundRect(hdc, 1, 1, badge_w - 1, badge_h - 1, 22, 22)
            gdi32.SelectObject(hdc, old_pen)
            gdi32.SelectObject(hdc, old_brush)

            old_font = gdi32.SelectObject(hdc, font)
            gdi32.SetBkMode(hdc, TRANSPARENT)
            gdi32.SetTextColor(hdc, 0x00FFFFFF)
            txt = labels_by_hwnd.get(int(hwnd), "1")
            user32.DrawTextW(hdc, txt, -1, ctypes.byref(rc), DT_CENTER | DT_VCENTER | DT_SINGLELINE)
            gdi32.SelectObject(hdc, old_font)
            user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == WM_TIMER:
            user32.KillTimer(hwnd, 1)
            for h in list(hwnds):
                user32.DestroyWindow(h)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    proc_ref = WNDPROC(wnd_proc)
    hinst = kernel32.GetModuleHandleW(None)
    cls_name = f"VortexIdentifyBadge_{seq}"

    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = proc_ref
    wc.hInstance = hinst
    wc.hbrBackground = bg_brush
    wc.lpszClassName = cls_name

    if not user32.RegisterClassExW(ctypes.byref(wc)):
        gdi32.DeleteObject(font)
        gdi32.DeleteObject(border_pen)
        gdi32.DeleteObject(bg_brush)
        return

    try:
        for mx, my, mw, mh, label in targets:
            bx = mx + 44
            by = my + max(44, mh - badge_h - 44)
            hwnd = user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                cls_name,
                f"VortexCore {label}",
                WS_POPUP,
                bx,
                by,
                badge_w,
                badge_h,
                None,
                None,
                hinst,
                None,
            )
            if hwnd:
                rgn = gdi32.CreateRoundRectRgn(0, 0, badge_w + 1, badge_h + 1, 22, 22)
                if rgn:
                    user32.SetWindowRgn(hwnd, rgn, False)
                labels_by_hwnd[int(hwnd)] = label
                hwnds.append(hwnd)
                user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                user32.UpdateWindow(hwnd)

        if hwnds:
            user32.SetTimer(hwnds[0], 1, max(600, int(duration_ms)), None)
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if _IDENTIFY_SEQ != seq:
                    for h in list(hwnds):
                        user32.DestroyWindow(h)
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        for h in list(hwnds):
            user32.DestroyWindow(h)
        user32.UnregisterClassW(cls_name, hinst)
        gdi32.DeleteObject(font)
        gdi32.DeleteObject(border_pen)
        gdi32.DeleteObject(bg_brush)


def _get_monitor_work_rects() -> dict[str, tuple[int, int, int, int]]:
    """Devuelve {device_name: (left, top, width, height)} en coordenadas DPI reales del escritorio."""
    rects: dict[str, tuple[int, int, int, int]] = {}
    if not IS_WINDOWS:
        return rects

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), MONITORENUMPROC, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL

    def _cb(hmon, _hdc, _rect, _lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcWork
            w = max(200, r.right - r.left)
            h = max(200, r.bottom - r.top)
            rects[mi.szDevice] = (r.left, r.top, w, h)
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    return rects


def identify_displays(duration_ms: int = 2400) -> dict:
    """Muestra un número grande en cada pantalla activa durante ~2.4s para identificarlas."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}

    displays = list_displays()
    work_rects = _get_monitor_work_rects()
    targets: list[tuple[int, int, int, int, str]] = []
    for idx, d in enumerate(displays):
        if not d.get("attached"):
            continue
        did = str(d.get("id") or "")
        if did in work_rects:
            x, y, w, h = work_rects[did]
        else:
            w = int(d.get("width") or 1920)
            h = int(d.get("height") or 1080)
            x = int(d.get("x") if d.get("x") is not None else (d.get("pos_x") or 0))
            y = int(d.get("y") if d.get("y") is not None else (d.get("pos_y") or 0))
        num = str(d.get("display_number") or (idx + 1))
        targets.append((x, y, w, h, num))

    if not targets:
        return {"status": "error", "message": "No hay pantallas activas para identificar."}

    global _IDENTIFY_SEQ
    with _IDENTIFY_LOCK:
        _IDENTIFY_SEQ += 1
        seq = _IDENTIFY_SEQ

    t = threading.Thread(target=_show_identify_overlays, args=(targets, duration_ms, seq), daemon=True)
    t.start()
    return {"status": "ok", "count": len(targets)}


def set_refresh_rate(hz: int, device_name: str | None = None) -> dict:
    """Cambia la tasa de refresco de la pantalla indicada (o la principal) al valor Hz."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}

    try:
        target_hz = int(hz)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Frecuencia Hz inválida."}

    target_dev = device_name or None
    info = get_display_modes(target_dev)
    if not info["supported"]:
        return {"status": "error", "message": "No se pudo consultar la pantalla."}
    if target_hz not in info["available_hz"]:
        return {
            "status": "error",
            "message": f"{target_hz} Hz no está disponible para {info['width']}×{info['height']}.",
        }
    if info["current_hz"] == target_hz:
        return {"status": "ok", "current_hz": target_hz}

    user32 = ctypes.windll.user32
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    if not user32.EnumDisplaySettingsW(target_dev, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
        return {"status": "error", "message": "Error leyendo modo de pantalla actual."}

    mode.dmDisplayFrequency = target_hz
    mode.dmFields = DM_DISPLAYFREQUENCY
    res = user32.ChangeDisplaySettingsExW(target_dev, ctypes.byref(mode), None, CDS_UPDATEREGISTRY, None)
    if res != DISP_CHANGE_SUCCESSFUL:
        return {"status": "error", "message": f"Windows rechazó el cambio a {target_hz} Hz (código {res})."}
    return {"status": "ok", "current_hz": target_hz, "device_name": target_dev or ""}


def get_brightness() -> int | None:
    """Lee el brillo actual (0-100) del panel interno del notebook vía WMI."""
    if not IS_WINDOWS:
        return None
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness -ErrorAction Stop | Select-Object -First 1).CurrentBrightness",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            creationflags=CREATE_NO_WINDOW,
        )
        out = (r.stdout or "").strip()
        if out.isdigit():
            return max(0, min(100, int(out)))
    except Exception:
        pass
    return None


def set_brightness(level: int) -> dict:
    """Ajusta el brillo de la pantalla integrada (0-100) vía WMI."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}
    try:
        pct = max(0, min(100, int(level)))
    except (TypeError, ValueError):
        return {"status": "error", "message": "Nivel de brillo inválido."}
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$m = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop | Select-Object -First 1; $m.WmiSetBrightness(1, {pct})",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            return {"status": "error", "message": "Tu monitor actual no permite ajustar brillo por WMI."}
        return {"status": "ok", "brightness": pct}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def pick_default_ac_battery_hz(available_hz: list[int], cfg: dict) -> tuple[int | None, int | None]:
    """Calcula las frecuencias objetivo para cargador (máxima) y batería (mínima o 60 Hz)."""
    if not available_hz:
        return None, None
    ac_hz = cfg.get("ac_hz")
    if ac_hz not in available_hz:
        ac_hz = max(available_hz)
    bat_hz = cfg.get("battery_hz")
    if bat_hz not in available_hz:
        bat_hz = 60 if 60 in available_hz else min(available_hz)
    return ac_hz, bat_hz


def get_full_state(include_brightness: bool = True) -> dict:
    displays = list_displays()
    info = displays[0] if displays else get_display_modes()
    cfg = load_config()
    ac_hz, bat_hz = pick_default_ac_battery_hz(info["available_hz"], cfg)
    cfg_out = {
        "auto_hz": cfg["auto_hz"],
        "ac_hz": ac_hz,
        "battery_hz": bat_hz,
    }
    _, details = _query_display_targets(return_details=True)
    return {
        **info,
        "displays": displays,
        "physical_count": max(len(displays), len(details)),
        "brightness": get_brightness() if include_brightness else None,
        "ac_plugged": get_ac_plugged(),
        "config": cfg_out,
    }


class AutoHzWatcher:
    """Vigila cambios entre cargador y batería para aplicar los Hz elegidos."""

    def __init__(self):
        self.config = load_config()
        self._last_ac = None

    def reload(self, new_cfg: dict) -> dict:
        self.config = {
            "auto_hz": bool(new_cfg.get("auto_hz", self.config["auto_hz"])),
            "ac_hz": new_cfg.get("ac_hz", self.config["ac_hz"]),
            "battery_hz": new_cfg.get("battery_hz", self.config["battery_hz"]),
        }
        save_config(self.config)
        self._last_ac = None
        self.tick()
        return self.config

    def tick(self) -> None:
        if not IS_WINDOWS or not self.config.get("auto_hz"):
            return
        ac = get_ac_plugged()
        if ac is None or ac == self._last_ac:
            return
        self._last_ac = ac
        info = get_display_modes()
        ac_hz, bat_hz = pick_default_ac_battery_hz(info["available_hz"], self.config)
        target = ac_hz if ac else bat_hz
        if target and info["current_hz"] != target:
            set_refresh_rate(target)
