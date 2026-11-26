"""
================================================================================
  VortexCore Hub // Lectores de sensores reales de Windows
  - Frecuencia real de CPU y memoria en caché vía contadores PDH (la misma
    fuente que el Administrador de tareas)
  - Módulos de RAM instalados y velocidad configurada (WMI Win32_PhysicalMemory)
  - Voltaje de núcleo de GPU NVIDIA (nvidia-smi -q -d VOLTAGE)
  - Batería real de dispositivos Bluetooth (propiedad de batería de Windows)

  Regla: si Windows no expone un sensor, se devuelve None. Nunca se inventa
  un valor; la interfaz muestra "N/D".
================================================================================
"""

import ctypes
import json
import math
import os
import re
import struct
import subprocess
import sys
import threading
import time
from ctypes import wintypes

try:
    import winreg
except ImportError:
    winreg = None

CREATE_NO_WINDOW = 0x08000000
IS_WINDOWS = sys.platform == "win32"


def _run(args, timeout=8):
    try:
        res = subprocess.run(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0
        )
        return res.returncode, res.stdout
    except Exception:
        return -1, ""


# ==============================================================================
# 1. FRECUENCIA REAL DE CPU (PDH)
# ==============================================================================
class _PDH_FMT_COUNTERVALUE(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000


class PdhCounters:
    """Consulta PDH con varios contadores (nombres en inglés, independientes del idioma de Windows)."""

    def __init__(self, paths):
        self.ok = False
        self._counters = {}
        self._query = wintypes.HANDLE()
        if not IS_WINDOWS:
            return
        try:
            pdh = ctypes.windll.pdh
            pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
            pdh.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
            pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
            pdh.PdhGetFormattedCounterValue.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_PDH_FMT_COUNTERVALUE)]
            for fn in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData", "PdhGetFormattedCounterValue"):
                getattr(pdh, fn).restype = wintypes.LONG
            self._pdh = pdh
            if pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query)) != 0:
                return
            for path in paths:
                h = wintypes.HANDLE()
                if pdh.PdhAddEnglishCounterW(self._query, path, None, ctypes.byref(h)) == 0:
                    self._counters[path] = h
            if not self._counters:
                return
            pdh.PdhCollectQueryData(self._query)  # primera muestra (los contadores de tasa necesitan dos)
            self.ok = True
        except Exception:
            self.ok = False

    def collect(self):
        """Devuelve {ruta: valor float} con los contadores válidos de esta muestra."""
        if not self.ok:
            return {}
        try:
            if self._pdh.PdhCollectQueryData(self._query) != 0:
                return {}
        except Exception:
            return {}
        out = {}
        for path, h in self._counters.items():
            val = _PDH_FMT_COUNTERVALUE()
            ctype = wintypes.DWORD()
            try:
                if self._pdh.PdhGetFormattedCounterValue(h, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100, ctypes.byref(ctype), ctypes.byref(val)) == 0 \
                        and val.CStatus in (0, 1):  # PDH_CSTATUS_VALID_DATA / NEW_DATA
                    out[path] = val.doubleValue
            except Exception:
                pass
        return out


_FREQ = r"\Processor Information(_Total)\Processor Frequency"
_PERF = r"\Processor Information(_Total)\% Processor Performance"
_CACHE = [r"\Memory\Standby Cache Core Bytes", r"\Memory\Standby Cache Normal Priority Bytes",
          r"\Memory\Standby Cache Reserve Bytes", r"\Memory\Modified Page List Bytes"]
_GPU_ENG = r"\GPU Engine(*engtype_3D)\Utilization Percentage"
_GPU_MEM = r"\GPU Adapter Memory(*)\Dedicated Usage"


class _PDH_FMT_COUNTERVALUE_ITEM(ctypes.Structure):
    _fields_ = [
        ("szName", wintypes.LPWSTR),
        ("CStatus", wintypes.DWORD),
        ("doubleValue", ctypes.c_double),
    ]


class PdhWildcardSum:
    """Suma todas las instancias de contadores PDH con comodín (ej. GPU Intel/AMD/NVIDIA)."""

    def __init__(self, paths):
        self.ok = False
        self._counters = {}
        self._query = wintypes.HANDLE()
        if not IS_WINDOWS:
            return
        try:
            pdh = ctypes.windll.pdh
            pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
            pdh.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
            pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
            pdh.PdhGetFormattedCounterArrayW.argtypes = [
                wintypes.HANDLE, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
            ]
            for fn in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData", "PdhGetFormattedCounterArrayW"):
                getattr(pdh, fn).restype = wintypes.LONG
            self._pdh = pdh
            if pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query)) != 0:
                return
            for p in paths:
                h = wintypes.HANDLE()
                if pdh.PdhAddEnglishCounterW(self._query, p, None, ctypes.byref(h)) == 0:
                    self._counters[p] = h
            if not self._counters:
                return
            pdh.PdhCollectQueryData(self._query)
            self.ok = True
        except Exception:
            self.ok = False

    def collect(self) -> dict:
        if not self.ok:
            return {}
        try:
            if self._pdh.PdhCollectQueryData(self._query) != 0:
                return {}
        except Exception:
            return {}
        out = {}
        PDH_MORE_DATA = 0x800007D2
        for path, h in self._counters.items():
            buf_sz = wintypes.DWORD(0)
            item_cnt = wintypes.DWORD(0)
            rc = self._pdh.PdhGetFormattedCounterArrayW(
                h, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100,
                ctypes.byref(buf_sz), ctypes.byref(item_cnt), None,
            )
            if rc != PDH_MORE_DATA and buf_sz.value == 0:
                continue
            buf = (ctypes.c_byte * buf_sz.value)()
            rc = self._pdh.PdhGetFormattedCounterArrayW(
                h, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100,
                ctypes.byref(buf_sz), ctypes.byref(item_cnt), buf,
            )
            if rc != 0:
                continue
            items = ctypes.cast(buf, ctypes.POINTER(_PDH_FMT_COUNTERVALUE_ITEM))
            total = 0.0
            valid = False
            for i in range(item_cnt.value):
                if items[i].CStatus in (0, 1) and math.isfinite(items[i].doubleValue):
                    total += max(0.0, items[i].doubleValue)
                    valid = True
            if valid:
                out[path] = total
        return out


class SystemCounters:
    """
    - Frecuencia efectiva de CPU en MHz = Processor Frequency (base) x % Processor Performance / 100
      (supera la base cuando hay Turbo Boost; es lo que muestra el Administrador de tareas).
    - Memoria en caché = listas Standby + Modified (lo que el Administrador de tareas llama "En caché").
    - Uso y VRAM de GPU WDDM (funciona en Intel Iris/UHD, AMD Radeon y NVIDIA sin drivers externos).
    """

    def __init__(self):
        self._pdh = PdhCounters([_FREQ, _PERF] + _CACHE)
        self._gpu_pdh = PdhWildcardSum([_GPU_ENG, _GPU_MEM])

    def read(self):
        vals = self._pdh.collect()
        cpu_mhz = None
        if vals.get(_FREQ) and _PERF in vals:
            cpu_mhz = int(round(vals[_FREQ] * vals[_PERF] / 100.0))
        cache_parts = [vals[c] for c in _CACHE if c in vals]
        cached_bytes = sum(cache_parts) if cache_parts else None
        gvals = self._gpu_pdh.collect()
        gpu_usage_pct = int(round(min(100.0, max(0.0, gvals[_GPU_ENG])))) if _GPU_ENG in gvals else None
        gpu_vram_mb = int(round(gvals[_GPU_MEM] / (1024 * 1024))) if _GPU_MEM in gvals and gvals[_GPU_MEM] > 0 else None
        return {
            "cpu_mhz": cpu_mhz,
            "cached_bytes": cached_bytes,
            "gpu_usage_pct": gpu_usage_pct,
            "gpu_vram_mb": gpu_vram_mb,
        }


# ==============================================================================
# 2. MÓDULOS DE RAM (WMI)
# ==============================================================================
def read_ram_modules():
    """
    Devuelve {"installed_gb": int, "speed_mts": int|None, "modules": int} leyendo los módulos
    físicos instalados, o None si WMI no responde.
    """
    if not IS_WINDOWS:
        return None
    ps = ("Get-CimInstance Win32_PhysicalMemory | "
          "Select-Object Capacity, ConfiguredClockSpeed, Speed | ConvertTo-Json -Compress")
    code, out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=12)
    if code != 0 or not out.strip():
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = [data]
    total = 0
    speeds = []
    for m in data:
        try:
            total += int(m.get("Capacity") or 0)
        except (TypeError, ValueError):
            pass
        for key in ("ConfiguredClockSpeed", "Speed"):
            try:
                v = int(m.get(key) or 0)
            except (TypeError, ValueError):
                v = 0
            if v > 0:
                speeds.append(v)
                break
    if total <= 0:
        return None
    return {
        "installed_gb": int(round(total / (1024 ** 3))),
        "speed_mts": max(speeds) if speeds else None,
        "modules": len(data),
    }


# ==============================================================================
# 3. VOLTAJE DE GPU NVIDIA
# ==============================================================================
_VOLT_RE = re.compile(r"Graphics\s*:\s*([\d.]+)\s*mV", re.IGNORECASE)


def read_nvidia_voltage_mv():
    """Voltaje del núcleo gráfico en mV según el driver NVIDIA, o None si no lo expone."""
    code, out = _run(["nvidia-smi", "-q", "-d", "VOLTAGE"], timeout=3)
    if code != 0:
        return None
    m = _VOLT_RE.search(out or "")
    if not m:
        return None
    try:
        return int(round(float(m.group(1))))
    except ValueError:
        return None


# ==============================================================================
# 4. BATERÍA REAL DE DISPOSITIVOS BLUETOOTH (cfgmgr32)
# ==============================================================================
class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_string(cls, s):
        s = s.strip("{}")
        p = s.split("-")
        g = cls()
        g.Data1 = int(p[0], 16)
        g.Data2 = int(p[1], 16)
        g.Data3 = int(p[2], 16)
        tail = bytes.fromhex(p[3] + p[4])
        for i in range(8):
            g.Data4[i] = tail[i]
        return g

    def __str__(self):
        d4 = bytes(self.Data4).hex()
        return f"{self.Data1:08x}-{self.Data2:04x}-{self.Data3:04x}-{d4[:4]}-{d4[4:]}"


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.ULONG)]


def _key(guid, pid):
    k = DEVPROPKEY()
    k.fmtid = GUID.from_string(guid)
    k.pid = pid
    return k


# Propiedad que Windows usa en Configuración > Bluetooth para mostrar el % de batería
DEVPKEY_Bluetooth_Battery = ("104EA319-6EE2-4701-BD47-8DDBF425BBE5", 2)
DEVPKEY_Device_FriendlyName = ("a45c254e-df1c-4efd-8020-67d146a850e0", 14)
DEVPKEY_Device_ContainerId = ("8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c", 2)

CM_GETIDLIST_FILTER_PRESENT = 0x00000100
CR_SUCCESS = 0
DEVPROP_TYPE_BYTE = 0x00000003
DEVPROP_TYPE_STRING = 0x00000012
DEVPROP_TYPE_GUID = 0x0000000D

_BT_SUFFIXES = (" hands-free ag audio", " hands-free ag", " hands-free", " avrcp transport", " stereo",
                " audio", " le", " (le)")


def _clean_bt_name(name):
    n = name.strip()
    low = n.lower()
    for suf in _BT_SUFFIXES:
        if low.endswith(suf):
            n = n[: -len(suf)].strip()
            low = n.lower()
    return n


def read_bluetooth_devices():
    """
    Lista de dispositivos Bluetooth CONECTADOS: [{"name", "battery" (int|None), "container"}].
    El % de batería es el mismo que muestra Windows; None si el dispositivo no lo informa.
    """
    if not IS_WINDOWS:
        return []
    try:
        cfg = ctypes.windll.cfgmgr32
        cfg.CM_Get_Device_ID_List_SizeW.argtypes = [ctypes.POINTER(wintypes.ULONG), wintypes.LPCWSTR, wintypes.ULONG]
        cfg.CM_Get_Device_ID_ListW.argtypes = [wintypes.LPCWSTR, ctypes.c_wchar_p, wintypes.ULONG, wintypes.ULONG]
        cfg.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.LPCWSTR, wintypes.ULONG]
        cfg.CM_Get_DevNode_PropertyW.argtypes = [wintypes.DWORD, ctypes.POINTER(DEVPROPKEY), ctypes.POINTER(wintypes.ULONG),
                                                 ctypes.c_void_p, ctypes.POINTER(wintypes.ULONG), wintypes.ULONG]
        cfg.CM_Get_DevNode_Status.argtypes = [ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG), wintypes.DWORD, wintypes.ULONG]
    except Exception:
        return []

    def get_prop(devinst, key):
        k = _key(*key)
        ptype = wintypes.ULONG()
        size = wintypes.ULONG(0)
        cfg.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(k), ctypes.byref(ptype), None, ctypes.byref(size), 0)
        if size.value == 0:
            return None
        buf = ctypes.create_string_buffer(size.value)
        if cfg.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(k), ctypes.byref(ptype), buf, ctypes.byref(size), 0) != CR_SUCCESS:
            return None
        if ptype.value == DEVPROP_TYPE_BYTE:
            return buf.raw[0]
        if ptype.value == DEVPROP_TYPE_STRING:
            return ctypes.wstring_at(ctypes.addressof(buf)).strip()
        if ptype.value == DEVPROP_TYPE_GUID:
            return str(GUID.from_buffer_copy(buf.raw[:ctypes.sizeof(GUID)]))
        return None

    size = wintypes.ULONG()
    if cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), None, CM_GETIDLIST_FILTER_PRESENT) != CR_SUCCESS:
        return []
    buf = ctypes.create_unicode_buffer(size.value)
    if cfg.CM_Get_Device_ID_ListW(None, buf, size.value, CM_GETIDLIST_FILTER_PRESENT) != CR_SUCCESS:
        return []
    ids = [d for d in buf[:size.value].split("\x00") if d]
    bt_ids = [d for d in ids if d.upper().startswith(("BTHENUM\\", "BTHLE\\", "BTHLEDEVICE\\"))]

    by_container = {}
    for dev_id in bt_ids:
        node = wintypes.DWORD()
        if cfg.CM_Locate_DevNodeW(ctypes.byref(node), dev_id, 0) != CR_SUCCESS:
            continue
        # Solo nodos arrancados (DN_STARTED = 0x8): el dispositivo está conectado ahora mismo
        status = wintypes.ULONG()
        problem = wintypes.ULONG()
        if cfg.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), node.value, 0) != CR_SUCCESS:
            continue
        if not (status.value & 0x8):
            continue
        container = get_prop(node.value, DEVPKEY_Device_ContainerId) or dev_id
        name = get_prop(node.value, DEVPKEY_Device_FriendlyName)
        battery = get_prop(node.value, DEVPKEY_Bluetooth_Battery)
        entry = by_container.setdefault(container, {"name": None, "battery": None, "container": container})
        if isinstance(name, str) and name and not name.startswith("@"):
            clean = _clean_bt_name(name)
            if entry["name"] is None or len(clean) < len(entry["name"]):
                entry["name"] = clean
        if isinstance(battery, int) and 0 <= battery <= 100:
            entry["battery"] = battery if entry["battery"] is None else max(entry["battery"], battery)

    # Descartar los nodos del propio adaptador / servicios genéricos sin nombre
    return [e for e in by_container.values() if e["name"] and "enumerator" not in e["name"].lower()]


# ==============================================================================
# 5. PERIFÉRICOS USB CONECTADOS (ratón, teclado, auriculares, mandos)
# ==============================================================================
DEVPKEY_Device_Class = ("a45c254e-df1c-4efd-8020-67d146a850e0", 9)
DEVPKEY_Device_Manufacturer = ("a45c254e-df1c-4efd-8020-67d146a850e0", 13)
DEVPKEY_Device_DeviceDesc = ("a45c254e-df1c-4efd-8020-67d146a850e0", 2)
DEVPKEY_Device_BusReportedDeviceDesc = ("540b947e-8b40-45bc-a8a2-6a0b894cbda2", 4)

# ContainerId que Windows asigna a lo que forma parte del propio equipo
# (teclado interno, touchpad, cámara, adaptador Bluetooth...)
_INTERNAL_CONTAINER = "00000000-0000-0000-ffff-ffffffffffff"

_GENERIC_NAMES = {
    "usb device", "usb composite device", "dispositivo compuesto usb", "usb input device",
    "dispositivo de entrada usb", "usb receiver", "usb keyboard", "usb mouse", "usb audio device",
    "dispositivo de audio usb", "hid keyboard device", "hid-compliant mouse", "",
}
_GENERIC_MANUFACTURERS = ("(", "microsoft", "generic", "genérico")
_WIRELESS_HINTS = ("2.4", "wireless", "inalámbric", "receiver", "receptor", "lightspeed", "unifying", "dongle", "hyperspeed")
_TYPE_PRIORITY = ("gamepad", "headphone", "mouse", "keyboard")
_FALLBACK_NAMES = {"gamepad": "Mando USB", "headphone": "Auriculares USB", "mouse": "Ratón USB", "keyboard": "Teclado USB"}
_VID_PID_RE = re.compile(r"^USB\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})\\", re.I)


def _cfgmgr():
    cfg = ctypes.windll.cfgmgr32
    cfg.CM_Get_Device_ID_List_SizeW.argtypes = [ctypes.POINTER(wintypes.ULONG), wintypes.LPCWSTR, wintypes.ULONG]
    cfg.CM_Get_Device_ID_ListW.argtypes = [wintypes.LPCWSTR, ctypes.c_wchar_p, wintypes.ULONG, wintypes.ULONG]
    cfg.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.LPCWSTR, wintypes.ULONG]
    cfg.CM_Get_DevNode_PropertyW.argtypes = [wintypes.DWORD, ctypes.POINTER(DEVPROPKEY), ctypes.POINTER(wintypes.ULONG),
                                             ctypes.c_void_p, ctypes.POINTER(wintypes.ULONG), wintypes.ULONG]
    cfg.CM_Get_DevNode_Status.argtypes = [ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG), wintypes.DWORD, wintypes.ULONG]
    return cfg


def _node_prop(cfg, devinst, key):
    k = _key(*key)
    ptype = wintypes.ULONG()
    size = wintypes.ULONG(0)
    cfg.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(k), ctypes.byref(ptype), None, ctypes.byref(size), 0)
    if size.value == 0:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if cfg.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(k), ctypes.byref(ptype), buf, ctypes.byref(size), 0) != CR_SUCCESS:
        return None
    if ptype.value == DEVPROP_TYPE_STRING:
        return ctypes.wstring_at(ctypes.addressof(buf)).strip()
    if ptype.value == DEVPROP_TYPE_GUID:
        return str(GUID.from_buffer_copy(buf.raw[:ctypes.sizeof(GUID)]))
    if ptype.value == DEVPROP_TYPE_BYTE:
        return buf.raw[0]
    return None


def classify_device(classes, hid_names):
    """Tipo de periférico según las clases de Windows de sus interfaces (o None si no es uno)."""
    classes = {c.lower() for c in classes if c}
    names = " ".join(n.lower() for n in hid_names if n)
    kinds = set()
    if classes & {"xnacomposite", "xboxcomposite"} or "game controller" in names or "de juego" in names or "juegos" in names:
        kinds.add("gamepad")
    if "media" in classes or "audioendpoint" in classes:
        kinds.add("headphone")
    if "mouse" in classes:
        kinds.add("mouse")
    if "keyboard" in classes:
        kinds.add("keyboard")
    return next((t for t in _TYPE_PRIORITY if t in kinds), None)


def pretty_device_name(friendly, bus_desc, manufacturer, dtype):
    """Nombre legible: el que informa el dispositivo; si es genérico, uno según su tipo."""
    name = next((n.strip() for n in (friendly, bus_desc) if n and n.strip().lower() not in _GENERIC_NAMES), None)
    if not name:
        return _FALLBACK_NAMES.get(dtype, "Dispositivo USB")
    if manufacturer and not manufacturer.lower().startswith(_GENERIC_MANUFACTURERS) and manufacturer.lower() not in name.lower():
        name = f"{manufacturer} {name}"
    return name


def read_usb_peripherals():
    """
    Periféricos USB externos conectados ahora mismo: [{"name", "type", "wireless", "vid"}].
    Se agrupan las interfaces por ContainerId (un dispositivo físico = una entrada) y se
    descarta todo lo que Windows marca como parte del propio equipo.
    """
    if not IS_WINDOWS:
        return []
    try:
        cfg = _cfgmgr()
    except Exception:
        return []

    size = wintypes.ULONG()
    if cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), None, CM_GETIDLIST_FILTER_PRESENT) != CR_SUCCESS:
        return []
    buf = ctypes.create_unicode_buffer(size.value)
    if cfg.CM_Get_Device_ID_ListW(None, buf, size.value, CM_GETIDLIST_FILTER_PRESENT) != CR_SUCCESS:
        return []

    groups = {}
    for dev_id in (d for d in buf[:size.value].split("\x00") if d):
        up = dev_id.upper()
        if not up.startswith(("USB\\VID_", "HID\\VID_")):
            continue
        node = wintypes.DWORD()
        if cfg.CM_Locate_DevNodeW(ctypes.byref(node), dev_id, 0) != CR_SUCCESS:
            continue
        status, problem = wintypes.ULONG(), wintypes.ULONG()
        if cfg.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), node.value, 0) != CR_SUCCESS:
            continue
        if not (status.value & 0x8):  # DN_STARTED
            continue
        container = (_node_prop(cfg, node.value, DEVPKEY_Device_ContainerId) or "").lower()
        if not container or container == _INTERNAL_CONTAINER:
            continue
        g = groups.setdefault(container, {"classes": set(), "hid_names": [], "friendly": None,
                                          "bus_desc": None, "manufacturer": None, "vid": None})
        g["classes"].add(_node_prop(cfg, node.value, DEVPKEY_Device_Class) or "")
        if up.startswith("HID\\"):
            g["hid_names"].append(_node_prop(cfg, node.value, DEVPKEY_Device_DeviceDesc) or "")
        m = _VID_PID_RE.match(dev_id)
        if m and "&MI_" not in up:  # nodo raíz del dispositivo USB (no una interfaz)
            g["vid"] = m.group(1).upper()
            g["friendly"] = _node_prop(cfg, node.value, DEVPKEY_Device_FriendlyName)
            g["bus_desc"] = _node_prop(cfg, node.value, DEVPKEY_Device_BusReportedDeviceDesc)
            g["manufacturer"] = _node_prop(cfg, node.value, DEVPKEY_Device_Manufacturer)

    out = []
    for g in groups.values():
        # Sin nodo USB raíz = dispositivo virtual (p. ej. el teclado virtual de Logitech G HUB)
        if not g["vid"]:
            continue
        dtype = classify_device(g["classes"], g["hid_names"])
        if not dtype:
            continue
        name = pretty_device_name(g["friendly"], g["bus_desc"], g["manufacturer"], dtype)
        wireless = any(h in name.lower() for h in _WIRELESS_HINTS)
        out.append({"name": name, "type": dtype, "wireless": wireless, "vid": g["vid"]})
    out.sort(key=lambda d: (_TYPE_PRIORITY.index(d["type"]), d["name"].lower()))
    return out


# ==============================================================================
# 6. SALUD REAL DE LA BATERÍA (Wear Level, Capacidad mWh y Ciclos)
# ==============================================================================
def compute_battery_health(design_mwh, full_mwh, cycle_count=None, voltage_mv=None,
                           charge_rate_mw=None, discharge_rate_mw=None,
                           power_online=None, manufacturer=None, chemistry=None):
    """Calcula la salud y desgaste reales de la batería a partir de mWh de diseño y carga completa."""
    d_val = int(design_mwh) if isinstance(design_mwh, (int, float)) and design_mwh > 0 else None
    f_val = int(full_mwh) if isinstance(full_mwh, (int, float)) and full_mwh > 0 else None
    if d_val is None and f_val is None:
        return {"present": False}

    health_pct = None
    wear_pct = None
    condition = None
    if d_val and f_val:
        raw_pct = (f_val / float(d_val)) * 100.0
        health_pct = round(min(100.0, max(0.0, raw_pct)), 1)
        wear_pct = round(max(0.0, 100.0 - health_pct), 1)
        if health_pct >= 85.0:
            condition = "Excelente"
        elif health_pct >= 75.0:
            condition = "Buena"
        elif health_pct >= 60.0:
            condition = "Desgastada"
        else:
            condition = "Reemplazo recomendado"

    cycles = int(cycle_count) if isinstance(cycle_count, (int, float)) and cycle_count >= 0 else None
    volt = int(voltage_mv) if isinstance(voltage_mv, (int, float)) and voltage_mv > 0 else None

    rate_mw = None
    if isinstance(charge_rate_mw, (int, float)) and charge_rate_mw > 0:
        rate_mw = int(charge_rate_mw)
    elif isinstance(discharge_rate_mw, (int, float)) and discharge_rate_mw > 0:
        rate_mw = -int(discharge_rate_mw)

    mfg = str(manufacturer).strip() if manufacturer else None
    chem = str(chemistry).strip() if chemistry else None

    return {
        "present": True,
        "design_mwh": d_val,
        "full_charged_mwh": f_val,
        "health_pct": health_pct,
        "wear_pct": wear_pct,
        "cycle_count": cycles,
        "voltage_mv": volt,
        "rate_mw": rate_mw,
        "power_online": bool(power_online) if power_online is not None else None,
        "manufacturer": mfg or None,
        "chemistry": chem or None,
        "condition": condition,
    }


# marca y modelo leidos de la tabla smbios del firmware: el registro se puede modificar
# (por ejemplo para hacer pasar el equipo por un samsung y usar sus apps), el firmware no
def parse_smbios_system(raw: bytes) -> dict:
    out = {}
    if len(raw) < 8:
        return out
    length = struct.unpack_from("<I", raw, 4)[0]
    table = raw[8:8 + length]
    pos = 0
    while pos + 4 <= len(table):
        stype, slen = table[pos], table[pos + 1]
        if slen < 4 or pos + slen > len(table):
            break
        end = table.find(b"\x00\x00", pos + slen)
        if end < 0:
            break
        strings = table[pos + slen:end].split(b"\x00")

        def text(offset):
            if offset >= slen:
                return ""
            idx = table[pos + offset]
            if idx == 0 or idx > len(strings):
                return ""
            return strings[idx - 1].decode("latin-1", errors="replace").strip()

        if stype == 1 and "manufacturer" not in out:
            out["manufacturer"], out["product"] = text(4), text(5)
        elif stype == 2 and "board" not in out:
            out["board"] = text(5)
        elif stype == 127:
            break
        pos = end + 2
    return out


def read_smbios_system() -> dict:
    if not IS_WINDOWS:
        return {}
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetSystemFirmwareTable.argtypes = [wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        k32.GetSystemFirmwareTable.restype = wintypes.UINT
        sig = 0x52534D42  # 'rsmb'
        size = k32.GetSystemFirmwareTable(sig, 0, None, 0)
        if not size:
            return {}
        buf = ctypes.create_string_buffer(size)
        if k32.GetSystemFirmwareTable(sig, 0, buf, size) != size:
            return {}
        return parse_smbios_system(buf.raw)
    except Exception:
        return {}


# bateria del mando dualsense leyendo sus reportes hid sin enviarle nada:
# por bluetooth solo trae bateria en el modo completo (reporte 0x31), que activan steam o los juegos
DUALSENSE_PIDS = ("0ce6", "0df2")
_ds_cache = {"at": 0.0, "value": None}


def parse_dualsense_report(data: bytes, bluetooth: bool = False):
    if not data:
        return None
    rid = data[0]
    if rid == 0x31 and len(data) >= 55:
        status = data[54]
    elif rid == 0x01 and not bluetooth and len(data) == 64:
        # por usb el reporte 0x01 es el completo; por bluetooth es el simple rellenado con ceros
        status = data[53]
    elif rid == 0x01:
        return {"mode": "simple"}
    else:
        return None
    level, state = status & 0x0F, status >> 4
    if level > 10 or state not in (0, 1, 2):
        return None
    return {"mode": "full", "percent": 100 if state == 2 else min(100, level * 10 + 5),
            "charging": state == 1, "full": state == 2}


def _hid_interface_paths() -> list:
    cfg = ctypes.WinDLL("cfgmgr32")
    guid = (ctypes.c_ubyte * 16)(*bytes.fromhex("b2551e4d6ff1cf1188cb001111000030"))
    size = wintypes.ULONG(0)
    if cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), guid, None, 0) != 0 or not size.value:
        return []
    buf = ctypes.create_unicode_buffer(size.value)
    if cfg.CM_Get_Device_Interface_ListW(guid, None, buf, size.value, 0) != 0:
        return []
    return [p for p in ctypes.wstring_at(ctypes.addressof(buf), size.value).split("\x00") if p]


def _read_hid_reports(path: str, count: int = 4, timeout_ms: int = 250) -> list:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CreateEventW.restype = wintypes.HANDLE
    k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
    k32.CancelIo.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    class OVERLAPPED(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                    ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

    # solo lectura y compartido: no se le envia nada al mando ni se le quita a los juegos
    h = k32.CreateFileW(path, 0x80000000, 0x3, None, 3, 0x40000000, None)
    if not h or h == wintypes.HANDLE(-1).value:
        return []
    reports = []
    try:
        for _ in range(count):
            ev = k32.CreateEventW(None, True, False, None)
            ov = OVERLAPPED()
            ov.hEvent = ev
            buf = ctypes.create_string_buffer(128)
            got = wintypes.DWORD(0)
            try:
                if not k32.ReadFile(h, buf, 128, None, ctypes.byref(ov)) and ctypes.get_last_error() != 997:
                    break
                if k32.WaitForSingleObject(ev, timeout_ms) != 0:
                    k32.CancelIo(h)
                    break
                if k32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(got), False) and got.value:
                    reports.append(buf.raw[:got.value])
            finally:
                k32.CloseHandle(ev)
    finally:
        k32.CloseHandle(h)
    return reports


# pide el reporte de calibracion (0x05): asi el dualsense pasa por bluetooth al modo completo con bateria,
# igual que hacen steam y ds4windows; dura hasta que el mando se apaga o se reconecta
def dualsense_request_full_mode(path: str) -> bool:
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        hid = ctypes.WinDLL("hid")
        hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
        hid.HidD_GetFeature.restype = wintypes.BOOLEAN
        h = k32.CreateFileW(path, 0xC0000000, 0x3, None, 3, 0, None)
        if not h or h == wintypes.HANDLE(-1).value:
            return False
        try:
            buf = ctypes.create_string_buffer(64)
            buf[0] = b"\x05"
            return bool(hid.HidD_GetFeature(h, buf, 64))
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False


def read_dualsense_battery(max_age: float = 5.0, force_full: bool = False):
    """devuelve la bateria del primer dualsense conectado, {"mode": "simple"} si no la informa, o none."""
    if not IS_WINDOWS:
        return None
    import time as _t
    if _t.time() - _ds_cache["at"] < max_age:
        return _ds_cache["value"]
    result = None
    try:
        for path in _hid_interface_paths():
            low = path.lower()
            if "054c" not in low or not any(pid in low for pid in DUALSENSE_PIDS):
                continue
            bt = "{00001124" in low
            reports = _read_hid_reports(path)
            simple = reports and all((parse_dualsense_report(r, bluetooth=bt) or {}).get("mode") == "simple" for r in reports)
            if bt and simple and force_full and dualsense_request_full_mode(path):
                reports = _read_hid_reports(path)
            for rep in reports:
                parsed = parse_dualsense_report(rep, bluetooth=bt)
                if parsed and parsed["mode"] == "full":
                    parsed["bluetooth"] = "{00001124" in low
                    result = parsed
                    break
                if parsed:
                    result = result or dict(parsed, bluetooth="{00001124" in low)
            if result and result.get("mode") == "full":
                break
    except Exception:
        result = None
    _ds_cache.update(at=_t.time(), value=result)
    return result


_razer_cache = {"at": 0.0, "value": None}


def parse_razer_barracuda_battery(rep: bytes) -> int | None:
    """Extrae el % de batería desde la respuesta RACE 0x06 0x82 del Razer Barracuda X (mV)."""
    if not rep or len(rep) < 18:
        return None
    if rep[0] != 0x01 or rep[1] != 0x80 or rep[13] != 0x06 or rep[14] != 0x82 or rep[15] != 0x00:
        return None
    mv = rep[16] | (rep[17] << 8)
    if mv < 2500 or mv > 4500:
        return None
    return max(0, min(100, int(round((mv - 3300) / (4200 - 3300) * 100))))


def read_razer_headset_battery(max_age: float = 5.0) -> int | None:
    """Consulta la batería real del Razer Barracuda X 2.4 GHz (PID 0552) vía HID."""
    if not IS_WINDOWS:
        return None
    import time as _t
    if _t.time() - _razer_cache["at"] < max_age:
        return _razer_cache["value"]

    pct = None
    try:
        path = next(
            (p for p in _hid_interface_paths()
             if "1532" in p.lower() and "0552" in p.lower() and "col01" in p.lower()),
            None,
        )
        if path:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateFileW.restype = wintypes.HANDLE
            k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            k32.CreateEventW.restype = wintypes.HANDLE
            k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
            k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
            k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
            k32.CancelIo.argtypes = [wintypes.HANDLE]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]

            class OVERLAPPED(ctypes.Structure):
                _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                            ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

            h = k32.CreateFileW(path, 0xC0000000, 0x3, None, 3, 0x40000000, None)
            if h and h != wintypes.HANDLE(-1).value:
                def _xfer(payload):
                    buf = (ctypes.c_ubyte * 64)(*payload)
                    ov = OVERLAPPED()
                    ov.hEvent = k32.CreateEventW(None, True, False, None)
                    w = wintypes.DWORD(0)
                    try:
                        if not k32.WriteFile(h, buf, 64, None, ctypes.byref(ov)) and ctypes.get_last_error() == 997:
                            if k32.WaitForSingleObject(ov.hEvent, 300) != 0:
                                k32.CancelIo(h)
                                return b""
                            k32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(w), False)
                    finally:
                        k32.CloseHandle(ov.hEvent)

                    rbuf = ctypes.create_string_buffer(64)
                    ov2 = OVERLAPPED()
                    ov2.hEvent = k32.CreateEventW(None, True, False, None)
                    got = wintypes.DWORD(0)
                    try:
                        if not k32.ReadFile(h, rbuf, 64, None, ctypes.byref(ov2)) and ctypes.get_last_error() != 997:
                            return b""
                        if k32.WaitForSingleObject(ov2.hEvent, 450) != 0:
                            k32.CancelIo(h)
                            return b""
                        if k32.GetOverlappedResult(h, ctypes.byref(ov2), ctypes.byref(got), False):
                            return rbuf.raw[:got.value]
                        return b""
                    finally:
                        k32.CloseHandle(ov2.hEvent)

                try:
                    hs = _xfer([0x01, 0x40])
                    if len(hs) >= 4 and hs[0] == 0x01 and hs[1] == 0x40:
                        _xfer([0x01, 0x80, 0x07, 0x50, 0x41, 0x0E, 0x01, 0x02, 0xE1, 0x01])
                        bat = _xfer([0x01, 0x80, 0x07, 0x50, 0x41, 0x06, 0x02, 0x01, 0x00, 0x31])
                        pct = parse_razer_barracuda_battery(bat)
                        _xfer([0x01, 0x80, 0x07, 0x50, 0x41, 0x0E, 0x03, 0x02, 0xE1, 0x00])
                finally:
                    k32.CloseHandle(h)
    except Exception:
        pct = None

    _razer_cache.update(at=_t.time(), value=pct)
    return pct


def read_battery_health():
    """Lee capacidad de diseño, carga máxima actual y ciclos desde WMI (root\\wmi) y/o powercfg."""
    if not IS_WINDOWS:
        return {"present": False}

    design_mwh = None
    full_mwh = None
    cycle_count = None
    voltage_mv = None
    charge_rate_mw = None
    discharge_rate_mw = None
    power_online = None
    manufacturer = None
    chemistry = None

    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$s = Get-CimInstance -Namespace root\\wmi -ClassName BatteryStaticData | Select-Object -First 1 DesignedCapacity, ManufactureName, Chemistry;"
        "$f = Get-CimInstance -Namespace root\\wmi -ClassName BatteryFullChargedCapacity | Select-Object -First 1 FullChargedCapacity;"
        "$c = Get-CimInstance -Namespace root\\wmi -ClassName BatteryCycleCount | Select-Object -First 1 CycleCount;"
        "$st = Get-CimInstance -Namespace root\\wmi -ClassName BatteryStatus | Select-Object -First 1 Voltage, ChargeRate, DischargeRate, PowerOnline;"
        "@{ static=$s; full=$f; cycle=$c; status=$st } | ConvertTo-Json -Compress"
    )
    code, out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=8)
    if code == 0 and out.strip():
        try:
            payload = json.loads(out)
            st_data = payload.get("static") or {}
            full_data = payload.get("full") or {}
            cyc_data = payload.get("cycle") or {}
            status_data = payload.get("status") or {}
            design_mwh = st_data.get("DesignedCapacity")
            full_mwh = full_data.get("FullChargedCapacity")
            cycle_count = cyc_data.get("CycleCount")
            voltage_mv = status_data.get("Voltage")
            charge_rate_mw = status_data.get("ChargeRate")
            discharge_rate_mw = status_data.get("DischargeRate")
            power_online = status_data.get("PowerOnline")
            manufacturer = st_data.get("ManufactureName")
            chemistry = st_data.get("Chemistry")
        except Exception:
            pass

    # Si falta capacidad de diseño o carga completa (p. ej. BatteryStaticData falla con 0x80041001),
    # completar los datos faltantes con powercfg /batteryreport /xml
    if not (isinstance(design_mwh, (int, float)) and design_mwh > 0 and
            isinstance(full_mwh, (int, float)) and full_mwh > 0):
        import tempfile
        import os
        import xml.etree.ElementTree as ET
        tmp_xml = os.path.join(tempfile.gettempdir(), "vortex_bat_report.xml")
        try:
            r_code, _ = _run(["powercfg", "/batteryreport", "/xml", "/output", tmp_xml], timeout=8)
            if r_code == 0 and os.path.isfile(tmp_xml):
                tree = ET.parse(tmp_xml)
                root = tree.getroot()
                ns = ""
                if root.tag.startswith("{"):
                    ns = root.tag.split("}", 1)[0] + "}"
                bat = root.find(f".//{ns}Battery")
                if bat is not None:
                    def _txt(tag):
                        el = bat.find(f"{ns}{tag}")
                        return el.text.strip() if el is not None and el.text else None
                    def _num(tag):
                        t = _txt(tag)
                        try:
                            return int(float(t)) if t is not None else None
                        except ValueError:
                            return None
                    design_mwh = design_mwh or _num("DesignCapacity")
                    full_mwh = full_mwh or _num("FullChargeCapacity")
                    if cycle_count is None:
                        cycle_count = _num("CycleCount")
                    manufacturer = manufacturer or _txt("Manufacturer")
                    chemistry = chemistry or _txt("Chemistry")
        except Exception:
            pass
        finally:
            try:
                if os.path.isfile(tmp_xml):
                    os.remove(tmp_xml)
            except Exception:
                pass

    return compute_battery_health(
        design_mwh=design_mwh,
        full_mwh=full_mwh,
        cycle_count=cycle_count,
        voltage_mv=voltage_mv,
        charge_rate_mw=charge_rate_mw,
        discharge_rate_mw=discharge_rate_mw,
        power_online=power_online,
        manufacturer=manufacturer,
        chemistry=chemistry,
    )


_STORAGE_HEALTH_CACHE: dict = {"ts": 0.0, "data": None}


def _read_lhm_storage_fallback() -> dict[str, dict]:
    """Lee temperatura y vida útil restante desde LibreHardwareMonitor si está disponible."""
    out: dict[str, dict] = {}
    try:
        from HardwareMonitor.Hardware import Computer, SensorType
        comp = Computer()
        comp.IsStorageEnabled = True
        comp.Open()
        try:
            for hw in comp.Hardware:
                try:
                    hw.Update()
                    name = str(hw.Name or "").strip()
                    temp_c = None
                    life_pct = None
                    for s in hw.Sensors:
                        sname = str(s.Name or "").lower()
                        val = s.Value
                        if val is None:
                            continue
                        if s.SensorType == SensorType.Temperature and "warning" not in sname and "critical" not in sname:
                            if temp_c is None or sname == "temperature":
                                temp_c = int(round(float(val)))
                        elif s.SensorType == SensorType.Level and ("remaining life" in sname or "life" in sname or "wear" in sname):
                            v = int(round(float(val)))
                            life_pct = max(0, min(100, 100 - v if "wear" in sname and "remaining" not in sname else v))
                    if name:
                        out[name.lower()] = {"temp_c": temp_c, "life_remaining_pct": life_pct}
                except Exception:
                    continue
        finally:
            try:
                comp.Close()
            except Exception:
                pass
    except Exception:
        pass
    return out


def read_storage_health(force: bool = False) -> dict:
    """Lee temperatura actual, vida útil restante (%) y estado SMART de los SSD/discos físicos."""
    if not IS_WINDOWS:
        return {"present": False, "disks": []}

    now = time.time()
    cached = _STORAGE_HEALTH_CACHE.get("data")
    if not force and cached is not None and (now - float(_STORAGE_HEALTH_CACHE.get("ts") or 0)) < 5.0:
        return cached

    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$disks = Get-PhysicalDisk | ForEach-Object {"
        "  $c = $null; try { $c = $_ | Get-StorageReliabilityCounter } catch {};"
        "  [PSCustomObject]@{"
        "    name = $_.FriendlyName;"
        "    media = [string]$_.MediaType;"
        "    bus = [string]$_.BusType;"
        "    health = [string]$_.HealthStatus;"
        "    op = [string]$_.OperationalStatus;"
        "    size_gb = [math]::Round($_.Size / 1GB, 1);"
        "    temp = if ($c) { $c.Temperature } else { $null };"
        "    wear = if ($c) { $c.Wear } else { $null };"
        "    hours = if ($c) { $c.PowerOnHours } else { $null };"
        "    read_err = if ($c) { $c.ReadErrorsTotal } else { $null };"
        "    write_err = if ($c) { $c.WriteErrorsTotal } else { $null }"
        "  }"
        "};"
        "$disks | ConvertTo-Json -Compress"
    )
    raw_disks: list[dict] = []
    code, out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=8)
    if code == 0 and out.strip():
        try:
            parsed = json.loads(out)
            if isinstance(parsed, dict):
                raw_disks = [parsed]
            elif isinstance(parsed, list):
                raw_disks = [d for d in parsed if isinstance(d, dict)]
        except Exception:
            raw_disks = []

    needs_lhm = any(d.get("temp") is None or d.get("wear") is None for d in raw_disks) or not raw_disks
    lhm_map = _read_lhm_storage_fallback() if needs_lhm else {}

    disks: list[dict] = []
    for d in raw_disks:
        name = str(d.get("name") or "Disco").strip()
        bus = str(d.get("bus") or "").strip()
        media = str(d.get("media") or "").strip()
        health_raw = str(d.get("health") or "Unknown").strip()
        op_raw = str(d.get("op") or "").strip()

        temp_c = int(round(float(d["temp"]))) if d.get("temp") is not None else None
        wear_used = int(round(float(d["wear"]))) if d.get("wear") is not None else None
        life_pct = max(0, min(100, 100 - wear_used)) if wear_used is not None else None

        lhm_match = lhm_map.get(name.lower())
        if not lhm_match and lhm_map:
            for k, v in lhm_map.items():
                if name.lower() in k or k in name.lower():
                    lhm_match = v
                    break
        if lhm_match:
            if temp_c is None and lhm_match.get("temp_c") is not None:
                temp_c = lhm_match["temp_c"]
            if life_pct is None and lhm_match.get("life_remaining_pct") is not None:
                life_pct = lhm_match["life_remaining_pct"]

        h_low = health_raw.lower()
        if h_low == "healthy":
            smart_label = "Saludable"
            smart_level = "green"
        elif h_low == "warning":
            smart_label = "Advertencia"
            smart_level = "orange"
        elif h_low == "unhealthy":
            smart_label = "Crítico"
            smart_level = "red"
        else:
            smart_label = health_raw or "Desconocido"
            smart_level = ""

        if life_pct is not None:
            if life_pct < 20:
                smart_level = "red"
            elif life_pct < 50 and smart_level == "green":
                smart_level = "orange"

        disks.append({
            "name": name,
            "bus_type": bus,
            "media_type": media,
            "is_nvme": "nvme" in bus.lower(),
            "size_gb": d.get("size_gb"),
            "temp_c": temp_c,
            "life_remaining_pct": life_pct,
            "wear_pct": (100 - life_pct) if life_pct is not None else None,
            "smart_status": smart_label,
            "smart_raw": health_raw,
            "operational_status": op_raw,
            "smart_level": smart_level,
            "power_on_hours": d.get("hours"),
            "read_errors": d.get("read_err"),
            "write_errors": d.get("write_err"),
        })

    # Priorizar SSD NVMe primero en la lista
    disks.sort(key=lambda x: (0 if x["is_nvme"] else (1 if "ssd" in x["media_type"].lower() else 2), x["name"]))
    res = {"present": len(disks) > 0, "disks": disks}
    _STORAGE_HEALTH_CACHE["ts"] = now
    _STORAGE_HEALTH_CACHE["data"] = res
    return res


# ==============================================================================
# 7. TEMPERATURAS POR NÚCLEO (LHM/OHM WMI) Y ZONAS TÉRMICAS ACPI + PING DE RED
# ==============================================================================
_PING_MS_RE = re.compile(r"(?:time|tiempo)\s*([=<])\s*(\d+)\s*ms", re.IGNORECASE)


def parse_ping_ms(output: str):
    """Extrae la latencia real en ms de la salida de ping de Windows, o None si falló."""
    if not output:
        return None
    m = _PING_MS_RE.search(output)
    if not m:
        return None
    try:
        val = int(m.group(2))
        return 1 if m.group(1) == "<" and val <= 1 else val
    except ValueError:
        return None


def measure_ping_ms(host: str = "1.1.1.1"):
    """Mide latencia real ICMP con 1 paquete y timeout corto; None si no hay red."""
    if not IS_WINDOWS:
        return None
    code, out = _run(["ping", "-n", "1", "-w", "1000", host], timeout=3)
    if code != 0:
        return None
    return parse_ping_ms(out)


DNS_PRESETS = {
    "auto": {"label": "Automático (DHCP / Router)", "servers": []},
    "cloudflare": {"label": "Cloudflare DNS", "servers": ["1.1.1.1", "1.0.0.1"]},
    "google": {"label": "Google DNS", "servers": ["8.8.8.8", "8.8.4.4"]},
    "adguard": {"label": "AdGuard DNS (Anti-Ads)", "servers": ["94.140.14.14", "94.140.14.15"]},
    "quad9": {"label": "Quad9 (Seguridad)", "servers": ["9.9.9.9", "149.112.112.112"]},
}


def parse_ping_stats(output: str, sent: int = 5) -> dict:
    """Extrae latencia media, mínima, máxima, jitter y pérdida real de varios paquetes ICMP."""
    if not output:
        return {"avg_ms": None, "min_ms": None, "max_ms": None, "jitter_ms": None, "loss_pct": 100, "samples": []}
    samples = []
    for sym, num in _PING_MS_RE.findall(output):
        try:
            v = int(num)
            samples.append(1 if sym == "<" and v <= 1 else v)
        except ValueError:
            pass
    if not samples:
        return {"avg_ms": None, "min_ms": None, "max_ms": None, "jitter_ms": None, "loss_pct": 100, "samples": []}

    avg_ms = round(sum(samples) / len(samples), 1)
    min_ms = min(samples)
    max_ms = max(samples)
    if len(samples) >= 2:
        diffs = [abs(b - a) for a, b in zip(samples, samples[1:])]
        jitter_ms = round(sum(diffs) / len(diffs), 1)
    else:
        jitter_ms = 0.0
    total_sent = max(sent, len(samples))
    loss_pct = int(round(((total_sent - len(samples)) / float(total_sent)) * 100))
    return {
        "avg_ms": avg_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "jitter_ms": jitter_ms,
        "loss_pct": max(0, min(100, loss_pct)),
        "samples": samples,
    }


def measure_network_quality(host: str = "1.1.1.1", count: int = 5) -> dict:
    """Ejecuta una prueba real de latencia, jitter y pérdida de paquetes."""
    if not IS_WINDOWS:
        return parse_ping_stats("", sent=count)
    n = max(1, min(10, int(count)))
    _code, out = _run(["ping", "-n", str(n), "-w", "1000", host], timeout=8)
    return parse_ping_stats(out, sent=n)


def benchmark_dns_servers() -> list[dict]:
    """Mide en paralelo la latencia real de los principales servidores DNS públicos."""
    results = []
    lock = threading.Lock()

    def _probe(key, cfg):
        ip = cfg["servers"][0]
        ms = measure_ping_ms(ip)
        with lock:
            results.append({"id": key, "label": cfg["label"], "primary_ip": ip, "ping_ms": ms})

    threads = []
    for k, cfg in DNS_PRESETS.items():
        if cfg["servers"]:
            t = threading.Thread(target=_probe, args=(k, cfg), daemon=True)
            t.start()
            threads.append(t)
    for t in threads:
        t.join(timeout=4)

    results.sort(key=lambda r: (r["ping_ms"] is None, r["ping_ms"] if r["ping_ms"] is not None else 9999))
    return results


def get_network_boost_status(iface_name: str | None = None) -> dict:
    """Lee la configuración real de red de Windows (DNS actual, Throttling Multimedia, TCP)."""
    if not IS_WINDOWS:
        return {"boost_active": False, "throttling_disabled": False, "tcp_autotuning": None, "dns_servers": [], "is_admin": False}

    throttling_val = 10
    if winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile") as k:
                throttling_val, _ = winreg.QueryValueEx(k, "NetworkThrottlingIndex")
        except OSError:
            pass
    throttling_disabled = (throttling_val == 0xFFFFFFFF)

    dns_servers = []
    if iface_name:
        safe_iface = ps_quote(iface_name)
        code, out = _run([
            "powershell", "-NoProfile", "-Command",
            f"(Get-DnsClientServerAddress -InterfaceAlias '{safe_iface}' -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses | ConvertTo-Json -Compress",
        ], timeout=4)
        if code == 0 and out.strip():
            try:
                parsed = json.loads(out)
                dns_servers = [parsed] if isinstance(parsed, str) else list(parsed)
            except Exception:
                pass

    tcp_auto = None
    code, out = _run(["netsh", "int", "tcp", "show", "global"], timeout=4)
    if code == 0 and out:
        m = re.search(r"(?:Auto-Tuning Level|Nivel de ajuste autom[aá]tico.*?)\s*:\s*(\S+)", out, re.IGNORECASE)
        if m:
            tcp_auto = m.group(1).strip().lower()

    return {
        "boost_active": bool(throttling_disabled),
        "throttling_disabled": bool(throttling_disabled),
        "tcp_autotuning": tcp_auto,
        "dns_servers": dns_servers,
        "iface": iface_name,
        "is_admin": is_admin(),
    }


def ps_quote(text: str) -> str:
    """Escapa texto para una cadena de PowerShell entre comillas simples.
    PowerShell acepta también las comillas tipográficas ‘ ’ ‚ ‛ como delimitadores,
    así que se duplican todas (y se quitan saltos de línea)."""
    out = " ".join(str(text).splitlines())
    for q in ("'", chr(0x2018), chr(0x2019), chr(0x201A), chr(0x201B)):
        out = out.replace(q, q + q)
    return out


def apply_network_boost(enable: bool, dns_preset: str = "keep", iface_name: str | None = None) -> dict:
    """Aplica o revierte optimizaciones reales de red en Windows (sin valores placebo)."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo disponible en Windows."}

    actions = []
    errors = []

    if not is_admin():
        # Sin elevación solo podemos limpiar caché DNS del usuario
        _run(["ipconfig", "/flushdns"], timeout=4)
        return {
            "status": "error",
            "needs_admin": True,
            "message": "Se limpió la caché DNS, pero para modificar TCP/Wi-Fi, DNS del adaptador y Multimedia Throttling abre VortexCore como Administrador.",
        }

    # 1. Eliminar o restaurar límite de paquetes NetworkThrottlingIndex (10 pkt/ms -> ilimitado)
    if winreg is not None:
        try:
            key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE) as k:
                val = 0xFFFFFFFF if enable else 10
                winreg.SetValueEx(k, "NetworkThrottlingIndex", 0, winreg.REG_DWORD, val)
                if enable:
                    winreg.SetValueEx(k, "SystemResponsiveness", 0, winreg.REG_DWORD, 0)
                else:
                    winreg.SetValueEx(k, "SystemResponsiveness", 0, winreg.REG_DWORD, 20)
            actions.append("Throttling de red multimedia desactivado" if enable else "Throttling estándar restaurado")
        except OSError as e:
            errors.append(f"Registro: {e}")

    # 2. TCP Receive Window Auto-Tuning normal + Rendimiento Wi-Fi en AC y DC (evita microcortes)
    _run(["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"], timeout=5)
    actions.append("TCP Auto-Tuning en modo normal")

    wifi_sub = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1"
    wifi_set = "12bbebe6-58d6-4636-95bb-3217ef867c1a"
    wifi_val = "0" if enable else "2"
    _run(["powercfg", "/setacvalueindex", "SCHEME_CURRENT", wifi_sub, wifi_set, "0"], timeout=4)
    _run(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", wifi_sub, wifi_set, wifi_val], timeout=4)
    _run(["powercfg", "/setactive", "SCHEME_CURRENT"], timeout=4)
    actions.append("Adaptador inalámbrico en máximo rendimiento" if enable else "Ahorro Wi-Fi en batería restaurado")

    # 3. Cambio de DNS en la interfaz activa (solo presets validados)
    if dns_preset in DNS_PRESETS and iface_name:
        safe_iface = ps_quote(iface_name)
        if dns_preset == "auto":
            c, _ = _run(["powershell", "-NoProfile", "-Command",
                         f"Set-DnsClientServerAddress -InterfaceAlias '{safe_iface}' -ResetServerAddresses"], timeout=6)
            if c == 0:
                actions.append(f"DNS automático (DHCP) en {iface_name}")
        else:
            srvs = ",".join(f"'{s}'" for s in DNS_PRESETS[dns_preset]["servers"])
            c, _ = _run(["powershell", "-NoProfile", "-Command",
                         f"Set-DnsClientServerAddress -InterfaceAlias '{safe_iface}' -ServerAddresses @({srvs})"], timeout=6)
            if c == 0:
                actions.append(f"{DNS_PRESETS[dns_preset]['label']} aplicado en {iface_name}")
            else:
                errors.append(f"No se pudo fijar DNS en {iface_name}")

    # 4. Vaciar caché DNS
    _run(["ipconfig", "/flushdns"], timeout=5)
    actions.append("Caché DNS vaciada")

    status_info = get_network_boost_status(iface_name)
    return {
        "status": "ok" if not errors else "partial",
        "actions": actions,
        "errors": errors,
        "boost_status": status_info,
        "message": " · ".join(actions),
    }


_HWINFO_CORE_RE = re.compile(
    r"^(?:(?:CPU\s+)?(?:P-?Core|E-?Core|Core)\s*#?\d+\b|Core\s*#?\d+\s*\(|CCD\s*\d+\b)",
    re.IGNORECASE,
)


def parse_coretemp_bytes(raw: bytes) -> list[dict]:
    """Extrae temperaturas por núcleo de memoria compartida CoreTempMappingObject."""
    if not raw or len(raw) < 2686:
        return []
    ui_core_cnt, _ui_cpu_cnt = struct.unpack_from("<II", raw, 1536)
    uc_fahr, uc_delta = struct.unpack_from("<BB", raw, 2684)
    if ui_core_cnt == 0 or ui_core_cnt > 256 or uc_delta:
        return []
    if 1544 + ui_core_cnt * 4 > len(raw):
        return []
    temps = struct.unpack_from(f"<{ui_core_cnt}f", raw, 1544)
    out = []
    for idx, val in enumerate(temps):
        if not math.isfinite(val):
            continue
        temp_c = (val - 32.0) * (5.0 / 9.0) if uc_fahr else val
        if 0.0 < temp_c < 130.0:
            out.append({"name": f"Core #{idx + 1}", "temp_c": round(temp_c, 1)})
    return out


def parse_hwinfo_bytes(raw: bytes) -> list[dict]:
    """Extrae temperaturas por núcleo de memoria compartida HWiNFO_SENS_SM2."""
    if not raw or len(raw) < 44:
        return []
    if raw[:4] != b"HWiS":
        return []
    entry_off, entry_size, entry_cnt = struct.unpack_from("<III", raw, 0x20)
    if entry_size < 324 or entry_cnt == 0 or entry_cnt > 4096:
        return []
    if entry_off + entry_cnt * entry_size > len(raw):
        return []

    out = []
    seen = set()
    for i in range(entry_cnt):
        off = entry_off + i * entry_size
        rtype, _sensor_idx, _rid = struct.unpack_from("<III", raw, off)
        if rtype != 1:  # 1 = SENSOR_TYPE_TEMP
            continue
        lbl_orig = raw[off + 0x0C:off + 0x8C].split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
        lbl_user = raw[off + 0x8C:off + 0x10C].split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
        label = lbl_user or lbl_orig
        low = label.lower()
        if not label or "distance" in low or "tjmax" in low or "critical" in low:
            continue
        if not _HWINFO_CORE_RE.search(label):
            continue
        val = struct.unpack_from("<d", raw, off + 0x11C)[0]
        if math.isfinite(val) and 0.0 < val < 130.0 and label not in seen:
            seen.add(label)
            out.append({"name": label, "temp_c": round(val, 1)})
    return out


def _read_win32_shm(name: str, max_bytes: int) -> bytes | None:
    """Lee un bloque de memoria compartida Windows existente sin crearlo ni bloquearlo."""
    if not IS_WINDOWS:
        return None
    FILE_MAP_READ = 0x0004
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k32.OpenFileMappingW.restype = wintypes.HANDLE
    k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    k32.MapViewOfFile.restype = wintypes.LPVOID
    k32.UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
    k32.UnmapViewOfFile.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL

    h_map = k32.OpenFileMappingW(FILE_MAP_READ, False, name)
    if not h_map:
        return None
    p_buf = None
    try:
        p_buf = k32.MapViewOfFile(h_map, FILE_MAP_READ, 0, 0, max_bytes)
        if not p_buf:
            return None
        return ctypes.string_at(p_buf, max_bytes)
    except Exception:
        return None
    finally:
        if p_buf:
            k32.UnmapViewOfFile(p_buf)
        k32.CloseHandle(h_map)


def read_shm_core_temps() -> tuple[list[dict], str | None]:
    """Lee temperaturas reales por núcleo desde Core Temp o HWiNFO si están abiertos (<1 ms)."""
    if not IS_WINDOWS:
        return ([], None)

    ct_raw = _read_win32_shm("CoreTempMappingObject", 2688)
    if ct_raw:
        ct_cores = parse_coretemp_bytes(ct_raw)
        if ct_cores:
            return (ct_cores, "Core Temp")

    for shm_name in ("Global\\HWiNFO_SENS_SM2", "HWiNFO_SENS_SM2"):
        hdr = _read_win32_shm(shm_name, 44)
        if hdr and hdr[:4] == b"HWiS":
            entry_off, entry_size, entry_cnt = struct.unpack_from("<III", hdr, 0x20)
            total = entry_off + entry_cnt * entry_size
            if 44 <= total <= 2_097_152 and entry_size >= 324:
                full = _read_win32_shm(shm_name, total)
                if full:
                    hw_cores = parse_hwinfo_bytes(full)
                    if hw_cores:
                        return (hw_cores, "HWiNFO")
    return ([], None)


_CORE_EXCLUDE_RE = re.compile(r"distance|tjmax|average|max|package|tdie|tctl|ccd", re.IGNORECASE)


def is_admin() -> bool:
    """Devuelve True si el proceso actual corre con privilegios elevados en Windows."""
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_pawnio_installed() -> bool:
    """Comprueba si el controlador firmado PawnIO (HVCI-safe) está instalado en Windows."""
    if not IS_WINDOWS:
        return False
    if os.path.isfile(r"C:\Program Files\PawnIO\PawnIOLib.dll") or os.path.isdir(r"C:\Program Files\PawnIO"):
        return True
    if winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\PawnIO"):
                return True
        except OSError:
            pass
    return False


def extract_lhm_core_temps(items) -> list[dict]:
    """Filtra lecturas de LibreHardwareMonitor dejando solo temperaturas reales por núcleo."""
    out = []
    seen = set()
    for name, val in items:
        if val is None or not isinstance(val, (int, float)) or not math.isfinite(val):
            continue
        if not (0.0 < float(val) < 130.0):
            continue
        lname = str(name or "").strip()
        if not lname or _CORE_EXCLUDE_RE.search(lname):
            continue
        if "core" not in lname.lower():
            continue
        if lname not in seen:
            seen.add(lname)
            out.append({"name": lname, "temp_c": round(float(val), 1)})
    return out


class _NativeLhmReader:
    """Lector persistente LibreHardwareMonitorLib vía PawnIO (sin abrir programas externos)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._comp = None
        self._sensor_type = None
        self._unavailable = False

    def reset(self):
        with self._lock:
            if self._comp is not None:
                try:
                    self._comp.Close()
                except Exception:
                    pass
                self._comp = None
            self._unavailable = False

    def read(self) -> dict | None:
        if not IS_WINDOWS or self._unavailable:
            return None
        if not (is_admin() and is_pawnio_installed()):
            return None
        with self._lock:
            if self._comp is None:
                try:
                    from HardwareMonitor.Hardware import Computer, HardwareType, SensorType
                    comp = Computer()
                    comp.IsCpuEnabled = True
                    comp.IsGpuEnabled = True
                    comp.IsMotherboardEnabled = True
                    comp.IsControllerEnabled = True
                    comp.Open()
                    self._comp = comp
                    self._sensor_type = SensorType
                    self._hw_type = HardwareType
                except Exception:
                    self._unavailable = True
                    return None
            try:
                raw_temps = []
                pkg_temp = None
                vcore_mv = None
                cpu_power = None
                gpu_data = {}
                fan_rpms = []

                def _walk(hw_node):
                    nonlocal pkg_temp, vcore_mv, cpu_power
                    ht = hw_node.HardwareType
                    # se omite la gpu intel porque su update provoca accessviolation no capturable
                    if ht == self._hw_type.GpuIntel:
                        return
                    hw_node.Update()
                    for sub in hw_node.SubHardware:
                        _walk(sub)
                    is_cpu = (ht == self._hw_type.Cpu)
                    is_gpu = ht in (self._hw_type.GpuNvidia, self._hw_type.GpuAmd)
                    for s in hw_node.Sensors:
                        val = s.Value
                        if val is None or not math.isfinite(float(val)):
                            continue
                        fval = float(val)
                        st = s.SensorType
                        sname = str(s.Name or "")
                        if is_cpu:
                            if st == self._sensor_type.Temperature:
                                raw_temps.append((sname, fval))
                                if sname in ("CPU Package", "Core (Tctl/Tdie)", "Tctl/Tdie") and 0 < fval < 130:
                                    pkg_temp = round(fval, 1)
                            elif st == self._sensor_type.Power and sname == "CPU Package" and 0 < fval < 400:
                                cpu_power = round(fval, 1)
                            elif st == self._sensor_type.Voltage and sname in ("CPU Core", "Core (SVI2 TFN)", "Vcore"):
                                if 0.2 < fval < 2.2:
                                    vcore_mv = int(round(fval * 1000))
                        elif is_gpu:
                            # hotspot y memoria de video usada para el hud
                            if st == self._sensor_type.Temperature and "hot spot" in sname.lower() and 0 < fval < 130:
                                gpu_data.setdefault("hotspot", int(round(fval)))
                            elif st == self._sensor_type.SmallData and sname == "GPU Memory Used" and fval >= 0:
                                gpu_data.setdefault("vram_used_mb", int(round(fval)))
                            elif st == self._sensor_type.SmallData and sname == "GPU Memory Total" and fval > 0:
                                gpu_data.setdefault("vram_total_mb", int(round(fval)))
                            elif st == self._sensor_type.Temperature and 0 < fval < 130 and "hot spot" not in sname.lower():
                                gpu_data.setdefault("temp", int(round(fval)))
                            elif st == self._sensor_type.Load and "core" in sname.lower():
                                gpu_data.setdefault("usage", int(round(min(100.0, max(0.0, fval)))))
                            elif st == self._sensor_type.Clock and "core" in sname.lower() and fval > 0:
                                gpu_data.setdefault("freq_mhz", int(round(fval)))
                            elif st == self._sensor_type.Clock and "memory" in sname.lower() and fval > 0:
                                gpu_data.setdefault("mem_freq_mhz", int(round(fval)))
                            elif st == self._sensor_type.Power and fval >= 0:
                                gpu_data.setdefault("power_w", f"{fval:.1f}")
                        if st == self._sensor_type.Fan and 100 <= fval <= 12000:
                            fan_rpms.append(int(round(fval)))

                for hw in self._comp.Hardware:
                    _walk(hw)

                # descarta potencias de gpu imposibles en reposo que entrega el driver al despertar
                if "power_w" in gpu_data and gpu_data.get("usage", 0) < 5 and float(gpu_data["power_w"]) > 100:
                    del gpu_data["power_w"]

                cores = extract_lhm_core_temps(raw_temps)
                if not cores and pkg_temp is None and vcore_mv is None and not gpu_data and not fan_rpms:
                    return None
                return {
                    "cores": cores,
                    "package_c": pkg_temp,
                    "vcore_mv": vcore_mv,
                    "gpu": gpu_data,
                    "fans": fan_rpms[:2],
                    "cpu_power_w": cpu_power,
                    "source": "PawnIO (Nativo)",
                }
            except Exception:
                return None


_native_lhm = _NativeLhmReader()


def read_native_cpu_sensors() -> dict | None:
    """Lee sensores nativos de CPU vía PawnIO + LibreHardwareMonitorLib si está listo."""
    return _native_lhm.read()


PAWNIO_SETUP_URL = "https://github.com/namazso/PawnIO.Setup/releases/latest/download/PawnIO_setup.exe"


def install_pawnio() -> dict:
    """Instala el controlador firmado PawnIO vía winget (con elevación UAC si hace falta)."""
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo disponible en Windows."}
    if is_pawnio_installed():
        _native_lhm.reset()
        return {"status": "ok", "installed": True, "needs_admin": not is_admin(), "message": "PawnIO ya está instalado."}

    if is_admin():
        code, out = _run(
            ["winget", "install", "--id", "namazso.PawnIO", "-e", "--silent",
             "--accept-source-agreements", "--accept-package-agreements"],
            timeout=90,
        )
        if is_pawnio_installed():
            _native_lhm.reset()
            return {"status": "ok", "installed": True, "needs_admin": False,
                    "message": "Controlador PawnIO instalado. Leyendo temperaturas por núcleo."}
        # Fallback: abrir descarga oficial si winget falló o no está disponible
        if code != 0:
            try:
                os.startfile(PAWNIO_SETUP_URL)
                return {"status": "ok", "installed": False, "fallback_url": True,
                        "message": "Se abrió la descarga oficial de PawnIO_setup.exe; ejecútalo para activar las temperaturas por núcleo."}
            except Exception:
                pass
        return {"status": "error", "installed": False, "message": out or "No se pudo instalar PawnIO automáticamente."}

    # Sin elevación: lanzar winget con RunAs para que Windows muestre el UAC limpio
    ps = (
        "$p = Start-Process winget -ArgumentList "
        "'install --id namazso.PawnIO -e --silent --accept-source-agreements --accept-package-agreements' "
        "-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
    )
    _run(["powershell", "-NoProfile", "-Command", ps], timeout=90)
    if is_pawnio_installed():
        _native_lhm.reset()
        return {"status": "ok", "installed": True, "needs_admin": True,
                "message": "PawnIO instalado correctamente. Reinicia VortexCore como Administrador para leer °C por núcleo."}
    try:
        os.startfile(PAWNIO_SETUP_URL)
        return {"status": "ok", "installed": False, "fallback_url": True,
                "message": "Se abrió la descarga de PawnIO_setup.exe para instalarlo manualmente."}
    except Exception as e:
        return {"status": "error", "installed": False, "message": str(e)}


def read_per_core_temps() -> dict:
    """
    Lee temperaturas individuales por núcleo:
      1. Lector nativo PawnIO + LibreHardwareMonitorLib (sin apps externas abiertas)
      2. Core Temp / HWiNFO memoria compartida (<1 ms)
      3. LibreHardwareMonitor / OpenHardwareMonitor WMI
      4. Zonas térmicas ACPI reales (sin requerir elevación vía ThermalZoneInformation)
    Nunca inventa valores.
    """
    if not IS_WINDOWS:
        return {"cores": [], "acpi_zones": [], "source": None}

    native = read_native_cpu_sensors()
    native_cores = (native or {}).get("cores") or []
    native_src = (native or {}).get("source")

    shm_cores, shm_src = ([], None) if native_cores else read_shm_core_temps()
    skip_wmi_flag = "$true" if (native_cores or shm_cores) else "$false"

    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$cores=@(); $src=$null;"
        f"$skipWmi={skip_wmi_flag};"
        "if(-not $skipWmi){"
        "  foreach($ns in @('root\\LibreHardwareMonitor','root\\OpenHardwareMonitor')){"
        "    $s = Get-CimInstance -Namespace $ns -ClassName Sensor | Where-Object { $_.SensorType -eq 'Temperature' -and $_.Name -match 'Core' -and $_.Name -notmatch 'Distance|TjMax|Average|Max' };"
        "    if(-not $s){ $s = Get-CimInstance -Namespace $ns -ClassName Sensor | Where-Object { $_.SensorType -eq 'Temperature' -and $_.Name -match 'CPU' }; }"
        "    if($s){ $src=($ns -replace 'root\\\\',''); $cores = @($s | ForEach-Object { @{ name=$_.Name; temp_c=[math]::Round($_.Value,1) } }); break }"
        "  }"
        "}"
        "$z = @(Get-CimInstance -Namespace root\\wmi -ClassName MSAcpi_ThermalZoneTemperature | ForEach-Object {"
        "  $c = [math]::Round(($_.CurrentTemperature - 2732) / 10.0, 1);"
        "  if($c -gt 0 -and $c -lt 130){ @{ name=($_.InstanceName -replace 'ACPI\\\\ThermalZone\\\\',''); temp_c=$c } }"
        "});"
        "if(-not $z -or $z.Count -eq 0){"
        "  $z = @(Get-CimInstance -Namespace root\\cimv2 -ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation | ForEach-Object {"
        "    $c = if($_.HighPrecisionTemperature -gt 2732){ [math]::Round(($_.HighPrecisionTemperature - 2732)/10.0, 1) } elseif($_.Temperature -gt 273){ [math]::Round($_.Temperature - 273.15, 1) } else { 0 };"
        "    if($c -gt 0 -and $c -lt 130){ @{ name=($_.Name -replace '^\\\\_TZ\\.','TZ.'); temp_c=$c } }"
        "  });"
        "}"
        "@{ cores=$cores; acpi_zones=$z; source=$src } | ConvertTo-Json -Compress"
    )
    acpi_zones = []
    wmi_cores = []
    wmi_src = None
    code, out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=6)
    if code == 0 and out.strip():
        try:
            data = json.loads(out)
            raw_c = data.get("cores") or []
            if isinstance(raw_c, dict):
                raw_c = [raw_c]
            raw_z = data.get("acpi_zones") or []
            if isinstance(raw_z, dict):
                raw_z = [raw_z]
            wmi_cores = [c for c in raw_c if isinstance(c, dict) and c.get("temp_c") is not None]
            acpi_zones = [z for z in raw_z if isinstance(z, dict) and z.get("temp_c") is not None]
            wmi_src = data.get("source")
        except Exception:
            pass

    if native_cores:
        return {"cores": native_cores, "acpi_zones": acpi_zones, "source": native_src}
    if shm_cores:
        return {"cores": shm_cores, "acpi_zones": acpi_zones, "source": shm_src}
    return {"cores": wmi_cores, "acpi_zones": acpi_zones, "source": wmi_src}
