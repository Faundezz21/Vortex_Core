"""
================================================================================
  VortexCore Hub // Puente DualSense (Bluetooth 0x31) -> DualShock 4 / Xbox 360
  - Modo "ds4" (por defecto): emula un DualShock 4 para que juegos como Rocket
    League, Fortnite o Apex muestren botones de PlayStation (✕ ○ □ △).
  - Modo "xbox": emula Xbox 360 (XInput) para juegos antiguos o Game Pass.
  - Modo "off": desactiva el puente virtual (modo nativo DualSense PS5).
  - Incluye zona muerta (deadzone) configurable y color LED de la barra de luz.
================================================================================
"""

import ctypes
import json
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zlib
from ctypes import wintypes

import hw_sensors

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000

VIGEM_BUS_GUID_BYTES = bytes.fromhex("222be496e9f5f842b043ed0f932f014f")
VIGEM_INSTALLER_URL = "https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBus_1.22.0_x64_x86_arm64.exe"

_DPAD_MAP = {
    0: 0x0001,  # UP
    1: 0x0001 | 0x0008,  # UP | RIGHT
    2: 0x0008,  # RIGHT
    3: 0x0002 | 0x0008,  # DOWN | RIGHT
    4: 0x0002,  # DOWN
    5: 0x0002 | 0x0004,  # DOWN | LEFT
    6: 0x0004,  # LEFT
    7: 0x0001 | 0x0004,  # UP | LEFT
}


class XUSB_REPORT(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.USHORT),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class DS4_REPORT(ctypes.Structure):
    _fields_ = [
        ("bThumbLX", wintypes.BYTE),
        ("bThumbLY", wintypes.BYTE),
        ("bThumbRX", wintypes.BYTE),
        ("bThumbRY", wintypes.BYTE),
        ("wButtons", wintypes.USHORT),
        ("bSpecial", wintypes.BYTE),
        ("bTriggerL", wintypes.BYTE),
        ("bTriggerR", wintypes.BYTE),
    ]


def _clamp_short(val: int) -> int:
    return max(-32768, min(32767, int(val)))


def _apply_deadzone_byte(val: int, deadzone_pct: int, curve: str = "linear", invert: bool = False) -> int:
    v = int(val)
    if invert:
        v = 255 - v
    dx = v - 128
    thr = int(round(127.0 * min(30, max(0, deadzone_pct)) / 100.0)) if deadzone_pct > 0 else 0
    if abs(dx) <= thr:
        return 128
    if curve != "linear":
        norm = (abs(dx) - thr) / max(1.0, 127.0 - thr)
        norm = max(0.0, min(1.0, norm))
        if curve == "precision":
            norm = norm ** 1.65
        elif curve == "fast":
            norm = norm ** 0.65
        v = 128 + int(round((1 if dx > 0 else -1) * norm * 127.0))
    return max(0, min(255, v))


def _apply_deadzone_short(val: int, deadzone_pct: int, curve: str = "linear", invert: bool = False) -> int:
    v = -int(val) if invert else int(val)
    thr = int(round(32767.0 * min(30, max(0, deadzone_pct)) / 100.0)) if deadzone_pct > 0 else 0
    if abs(v) <= thr:
        return 0
    if curve != "linear":
        norm = (abs(v) - thr) / max(1.0, 32767.0 - thr)
        norm = max(0.0, min(1.0, norm))
        if curve == "precision":
            norm = norm ** 1.65
        elif curve == "fast":
            norm = norm ** 0.65
        v = int(round((1 if v > 0 else -1) * norm * 32767.0))
    return _clamp_short(v)


def _apply_trigger(val: int, hair_triggers: bool = False) -> int:
    v = max(0, min(255, int(val)))
    if hair_triggers and v > 28:
        return 255
    return v


def dualsense_to_ds4_report(data: bytes, deadzone_pct: int = 0, curve: str = "linear",
                           hair_triggers: bool = False, invert_y: bool = False) -> DS4_REPORT | None:
    """Convierte un reporte Bluetooth completo (0x31, >=55 bytes) a DS4_REPORT (botones PlayStation)."""
    if not data or data[0] != 0x31 or len(data) < 55:
        return None
    b0, b1, b2 = data[9], data[10], data[11]
    special = 0
    if b2 & 0x01:
        special |= 0x01  # PS
    if b2 & 0x02:
        special |= 0x02  # Touchpad click
    return DS4_REPORT(
        bThumbLX=_apply_deadzone_byte(data[2], deadzone_pct, curve, False),
        bThumbLY=_apply_deadzone_byte(data[3], deadzone_pct, curve, invert_y),
        bThumbRX=_apply_deadzone_byte(data[4], deadzone_pct, curve, False),
        bThumbRY=_apply_deadzone_byte(data[5], deadzone_pct, curve, invert_y),
        wButtons=b0 | (b1 << 8),
        bSpecial=special,
        bTriggerL=_apply_trigger(data[6], hair_triggers),
        bTriggerR=_apply_trigger(data[7], hair_triggers),
    )


def dualsense_to_xusb_report(data: bytes, deadzone_pct: int = 0, curve: str = "linear",
                            hair_triggers: bool = False, invert_y: bool = False) -> XUSB_REPORT | None:
    """Convierte un reporte Bluetooth completo (0x31, >=55 bytes) a XUSB_REPORT."""
    if not data or data[0] != 0x31 or len(data) < 55:
        return None

    lx = _apply_deadzone_short((data[2] - 128) * 256, deadzone_pct, curve, False)
    ly = _apply_deadzone_short((127 - data[3]) * 256, deadzone_pct, curve, invert_y)
    rx = _apply_deadzone_short((data[4] - 128) * 256, deadzone_pct, curve, False)
    ry = _apply_deadzone_short((127 - data[5]) * 256, deadzone_pct, curve, invert_y)

    b0, b1, b2 = data[9], data[10], data[11]
    buttons = _DPAD_MAP.get(b0 & 0x0F, 0)
    if b0 & 0x10:
        buttons |= 0x4000  # Square -> X
    if b0 & 0x20:
        buttons |= 0x1000  # Cross -> A
    if b0 & 0x40:
        buttons |= 0x2000  # Circle -> B
    if b0 & 0x80:
        buttons |= 0x8000  # Triangle -> Y
    if b1 & 0x01:
        buttons |= 0x0100  # L1 -> LB
    if b1 & 0x02:
        buttons |= 0x0200  # R1 -> RB
    if b1 & 0x10:
        buttons |= 0x0020  # Create -> Back
    if b1 & 0x20:
        buttons |= 0x0010  # Options -> Start
    if b1 & 0x40:
        buttons |= 0x0040  # L3 -> Left Thumb
    if b1 & 0x80:
        buttons |= 0x0080  # R3 -> Right Thumb
    if b2 & 0x01:
        buttons |= 0x0400  # PS -> Guide

    return XUSB_REPORT(
        wButtons=buttons,
        bLeftTrigger=_apply_trigger(data[6], hair_triggers),
        bRightTrigger=_apply_trigger(data[7], hair_triggers),
        sThumbLX=lx,
        sThumbLY=ly,
        sThumbRX=rx,
        sThumbRY=ry,
    )


def _ds_cfg_path() -> str:
    d = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "dualsense.json")


def load_dualsense_config() -> dict:
    cfg = {
        "mode": "ds4",
        "deadzone": 5,
        "led_color": "#a855f7",
        "led_brightness": 100,
        "rainbow_speed": 4,
        "player_leds": "all",
        "curve": "linear",
        "hair_triggers": False,
        "invert_y": False,
        "touchpad_mouse": False,
        "mic_mute": False,
        "idle_timeout": 15,
        "power_save": True,
        "rumble_enabled": True,
        "rumble_intensity": 80,
    }
    try:
        with open(_ds_cfg_path(), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            if raw.get("mode") in ("ds4", "xbox"):
                cfg["mode"] = raw["mode"]
            if isinstance(raw.get("deadzone"), (int, float)):
                cfg["deadzone"] = max(0, min(25, int(raw["deadzone"])))
            if isinstance(raw.get("led_color"), str) and raw["led_color"]:
                cfg["led_color"] = raw["led_color"][:16]
            if isinstance(raw.get("led_brightness"), (int, float)):
                cfg["led_brightness"] = max(0, min(100, int(raw["led_brightness"])))
            if isinstance(raw.get("rainbow_speed"), (int, float)):
                cfg["rainbow_speed"] = max(1, min(10, int(raw["rainbow_speed"])))
            if raw.get("player_leds") in ("off", "center", "two", "three", "four", "all"):
                cfg["player_leds"] = raw["player_leds"]
            if raw.get("curve") in ("linear", "precision", "fast"):
                cfg["curve"] = raw["curve"]
            if "hair_triggers" in raw:
                cfg["hair_triggers"] = bool(raw["hair_triggers"])
            if "invert_y" in raw:
                cfg["invert_y"] = bool(raw["invert_y"])
            if "touchpad_mouse" in raw:
                cfg["touchpad_mouse"] = bool(raw["touchpad_mouse"])
            if "mic_mute" in raw:
                cfg["mic_mute"] = bool(raw["mic_mute"])
            if isinstance(raw.get("idle_timeout"), (int, float)) and int(raw["idle_timeout"]) in (0, 5, 15, 30):
                cfg["idle_timeout"] = int(raw["idle_timeout"])
            if "power_save" in raw:
                cfg["power_save"] = bool(raw["power_save"])
            if "rumble_enabled" in raw:
                cfg["rumble_enabled"] = bool(raw["rumble_enabled"])
            if isinstance(raw.get("rumble_intensity"), (int, float)):
                cfg["rumble_intensity"] = max(0, min(100, int(raw["rumble_intensity"])))
    except Exception:
        pass
    return cfg


def save_dualsense_config(cfg: dict) -> None:
    try:
        with open(_ds_cfg_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        pass


def _hsv_to_rgb(h: float) -> tuple[int, int, int]:
    h = (h % 1.0) * 6.0
    i = int(h)
    f = h - i
    q = int(round((1.0 - f) * 255))
    t = int(round(f * 255))
    if i == 0:
        return (255, t, 0)
    if i == 1:
        return (q, 255, 0)
    if i == 2:
        return (0, 255, t)
    if i == 3:
        return (0, q, 255)
    if i == 4:
        return (t, 0, 255)
    return (255, 0, q)


def resolve_led_rgb(led_color: str, battery_pct: int | None = None, ts: float | None = None,
                    brightness: int = 100, speed: int = 4) -> tuple[int, int, int]:
    c = (led_color or "auto").strip().lower()
    if c == "off":
        return (0, 0, 0)
    scale = max(0.0, min(1.0, float(brightness) / 100.0))
    rgb = (0, 240, 255)
    if c == "rainbow":
        sp = max(1, min(10, int(speed))) * 0.06
        rgb = _hsv_to_rgb(((ts if ts is not None else time.time()) * sp) % 1.0)
    elif c == "auto":
        if battery_pct is not None:
            if battery_pct <= 20:
                rgb = (239, 68, 68)
            elif battery_pct <= 50:
                rgb = (245, 158, 11)
    elif c.startswith("#") and len(c) == 7:
        try:
            rgb = (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
        except ValueError:
            pass
    return (int(round(rgb[0] * scale)), int(round(rgb[1] * scale)), int(round(rgb[2] * scale)))


_bt_seq = 0
_led_initialized_paths: set[str] = set()

PLAYER_LED_MASKS = {
    "off": 0x00,
    "center": 0x04,  # 1 LED central debajo del touchpad (○○●○○)
    "two": 0x0A,     # 2 LEDs (○●○●○)
    "three": 0x0E,   # 3 LEDs centrales (○●●●○)
    "four": 0x1B,    # 4 LEDs (●●○●●)
    "all": 0x1F,     # 5 LEDs (●●●●●)
}


class _HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


def _get_hid_output_len(h) -> int:
    """Obtiene el OutputReportByteLength exacto que exige hidclass.sys para este dispositivo."""
    try:
        hid = ctypes.WinDLL("hid")
        hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
        hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
        hid.HidD_FreePreparsedData.restype = wintypes.BOOLEAN
        hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(_HIDP_CAPS)]
        hid.HidP_GetCaps.restype = wintypes.LONG
        pp = ctypes.c_void_p(0)
        if not hid.HidD_GetPreparsedData(h, ctypes.byref(pp)) or not pp.value:
            return 0
        try:
            caps = _HIDP_CAPS()
            if hid.HidP_GetCaps(pp, ctypes.byref(caps)) == 0x00110000:  # HIDP_STATUS_SUCCESS
                return int(caps.OutputReportByteLength)
        finally:
            hid.HidD_FreePreparsedData(pp)
    except Exception:
        pass
    return 0


def _populate_common_report(buf: bytearray, base: int, r: int, g: int, b: int,
                            light_out: bool = False, motor_left: int = 0, motor_right: int = 0,
                            rumble: bool = False, mic_mute: bool = False,
                            player_leds: str = "center") -> None:
    if rumble:
        buf[base + 0] = 0x03  # valid_flag0: COMPATIBLE_VIBRATION (0x01) | HAPTICS_SELECT (0x02)
        buf[base + 2] = max(0, min(255, int(motor_right)))
        buf[base + 3] = max(0, min(255, int(motor_left)))
    if light_out:
        # Paquete inicial que apaga el modo azul por defecto del firmware para habilitar control RGB
        buf[base + 1] = 0x00
        buf[base + 38] = 0x02  # DS_OUTPUT_VALID_FLAG2_LIGHTBAR_SETUP_CONTROL_ENABLE
        buf[base + 41] = 0x02  # DS_OUTPUT_LIGHTBAR_SETUP_LIGHT_OUT
    else:
        # Control directo de Lightbar RGB + LEDs centrales de jugador + LED de micrófono
        buf[base + 1] = 0x01 | 0x04 | 0x10  # MIC_MUTE_LED (0x01) | LIGHTBAR (0x04) | PLAYER_INDICATOR (0x10)
        buf[base + 8] = 0x01 if mic_mute else 0x00
        buf[base + 38] = 0x01  # DS_OUTPUT_VALID_FLAG2_LED_BRIGHTNESS_CONTROL_ENABLE (sin LIGHT_OUT)
        buf[base + 41] = 0x00
        buf[base + 42] = 0x00  # Brillo máximo para LEDs centrales
        pmask = PLAYER_LED_MASKS.get(str(player_leds or "center").lower(), 0x04)
        buf[base + 43] = pmask
        buf[base + 44] = max(0, min(255, int(r)))
        buf[base + 45] = max(0, min(255, int(g)))
        buf[base + 46] = max(0, min(255, int(b)))


def _build_bt_led_packet(r: int, g: int, b: int, light_out: bool = False,
                         motor_left: int = 0, motor_right: int = 0, rumble: bool = False,
                         mic_mute: bool = False, player_leds: str = "center",
                         report_len: int = 547) -> bytes:
    global _bt_seq
    size = max(78, int(report_len or 547))
    buf = bytearray(size)
    buf[0] = 0x31
    buf[1] = (_bt_seq << 4) & 0xF0
    _bt_seq = (_bt_seq + 1) & 0x0F
    buf[2] = 0x10  # DS_OUTPUT_TAG
    _populate_common_report(
        buf, 3, r, g, b, light_out=light_out,
        motor_left=motor_left, motor_right=motor_right,
        rumble=rumble, mic_mute=mic_mute, player_leds=player_leds,
    )
    crc = zlib.crc32(b"\xA2" + bytes(buf[:74])) & 0xFFFFFFFF
    struct.pack_into("<I", buf, 74, crc)
    return bytes(buf)


def _build_usb_led_packet(r: int, g: int, b: int, light_out: bool = False,
                          motor_left: int = 0, motor_right: int = 0, rumble: bool = False,
                          mic_mute: bool = False, player_leds: str = "center",
                          report_len: int = 64) -> bytes:
    size = max(48, int(report_len or 64))
    buf = bytearray(size)
    buf[0] = 0x02  # USB Output Report ID
    _populate_common_report(
        buf, 1, r, g, b, light_out=light_out,
        motor_left=motor_left, motor_right=motor_right,
        rumble=rumble, mic_mute=mic_mute, player_leds=player_leds,
    )
    return bytes(buf)


def _write_dualsense_packet(k32, h, is_bt: bool, r: int, g: int, b: int,
                            light_out: bool = False, motor_left: int = 0, motor_right: int = 0,
                            rumble: bool = False, mic_mute: bool = False,
                            player_leds: str = "center") -> bool:
    caps_len = _get_hid_output_len(h)
    if is_bt:
        candidates = []
        if caps_len >= 78:
            candidates.append(caps_len)
        for c in (78, 547, 634):
            if c not in candidates:
                candidates.append(c)
    else:
        candidates = []
        if caps_len >= 48:
            candidates.append(caps_len)
        for c in (48, 64):
            if c not in candidates:
                candidates.append(c)

    written = wintypes.DWORD(0)
    for size in candidates:
        pkt = (_build_bt_led_packet if is_bt else _build_usb_led_packet)(
            r, g, b, light_out=light_out, motor_left=motor_left, motor_right=motor_right,
            rumble=rumble, mic_mute=mic_mute, player_leds=player_leds, report_len=size,
        )
        raw = (ctypes.c_ubyte * len(pkt)).from_buffer_copy(pkt)
        if k32.WriteFile(h, raw, len(pkt), ctypes.byref(written), None):
            return True

    # Fallback vía HidD_SetOutputReport si WriteFile fue rechazado por el stack HID
    try:
        hid = ctypes.WinDLL("hid")
        hid.HidD_SetOutputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
        hid.HidD_SetOutputReport.restype = wintypes.BOOLEAN
        base_len = 78 if is_bt else 48
        pkt = (_build_bt_led_packet if is_bt else _build_usb_led_packet)(
            r, g, b, light_out=light_out, motor_left=motor_left, motor_right=motor_right,
            rumble=rumble, mic_mute=mic_mute, player_leds=player_leds, report_len=base_len,
        )
        raw = (ctypes.c_ubyte * len(pkt)).from_buffer_copy(pkt)
        return bool(hid.HidD_SetOutputReport(h, raw, len(pkt)))
    except Exception:
        return False


def send_dualsense_bt_rumble(bt_path: str, r: int, g: int, b: int, duration_ms: int = 350,
                             player_leds: str = "center", intensity_pct: int = 80) -> bool:
    """Activa una vibración corta de prueba en el DualSense (Bluetooth o USB)."""
    if not IS_WINDOWS or not bt_path:
        return False
    is_bt = "{00001124" in bt_path.lower()
    scale = max(0.0, min(1.0, float(intensity_pct) / 100.0))
    ml = max(25, int(round(200 * scale))) if intensity_pct > 0 else 0
    mr = max(20, int(round(150 * scale))) if intensity_pct > 0 else 0
    try:
        if is_bt:
            hw_sensors.dualsense_request_full_mode(bt_path)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k32.CreateFileW(bt_path, 0xC0000000, 0x3, None, 3, 0, None)
        if not h or h == wintypes.HANDLE(-1).value:
            h = k32.CreateFileW(bt_path, 0x40000000, 0x3, None, 3, 0, None)
        if not h or h == wintypes.HANDLE(-1).value:
            return False
        try:
            ok = _write_dualsense_packet(
                k32, h, is_bt, r, g, b,
                motor_left=ml, motor_right=mr, rumble=True, player_leds=player_leds,
            )
            time.sleep(max(0.1, min(1.0, duration_ms / 1000.0)))
            _write_dualsense_packet(
                k32, h, is_bt, r, g, b,
                motor_left=0, motor_right=0, rumble=True, player_leds=player_leds,
            )
            return ok
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False


def parse_dualsense_live_state(data: bytes, deadzone_pct: int = 0) -> dict | None:
    """Extrae ejes, gatillos y botones en tiempo real de un reporte DualSense BT (0x31) o USB (0x01)."""
    if not data:
        return None
    if data[0] == 0x31 and len(data) >= 55:
        off = 0
    elif data[0] == 0x01 and len(data) >= 64:
        off = -1
    else:
        return None
    lx_raw, ly_raw, rx_raw, ry_raw = data[2 + off], data[3 + off], data[4 + off], data[5 + off]
    lx_eff = _apply_deadzone_byte(lx_raw, deadzone_pct)
    ly_eff = _apply_deadzone_byte(ly_raw, deadzone_pct)
    rx_eff = _apply_deadzone_byte(rx_raw, deadzone_pct)
    ry_eff = _apply_deadzone_byte(ry_raw, deadzone_pct)
    b0, b1, b2 = data[9 + off], data[10 + off], data[11 + off]
    dpad = b0 & 0x0F
    return {
        "lx": round((lx_raw - 128) / 127.0, 3),
        "ly": round((ly_raw - 128) / 127.0, 3),
        "rx": round((rx_raw - 128) / 127.0, 3),
        "ry": round((ry_raw - 128) / 127.0, 3),
        "lx_eff": round((lx_eff - 128) / 127.0, 3),
        "ly_eff": round((ly_eff - 128) / 127.0, 3),
        "rx_eff": round((rx_eff - 128) / 127.0, 3),
        "ry_eff": round((ry_eff - 128) / 127.0, 3),
        "l2": round(data[6 + off] / 255.0, 3),
        "r2": round(data[7 + off] / 255.0, 3),
        "buttons": {
            "dpad_up": dpad in (0, 1, 7),
            "dpad_right": dpad in (1, 2, 3),
            "dpad_down": dpad in (3, 4, 5),
            "dpad_left": dpad in (5, 6, 7),
            "square": bool(b0 & 0x10),
            "cross": bool(b0 & 0x20),
            "circle": bool(b0 & 0x40),
            "triangle": bool(b0 & 0x80),
            "l1": bool(b1 & 0x01),
            "r1": bool(b1 & 0x02),
            "l2_btn": bool(b1 & 0x04),
            "r2_btn": bool(b1 & 0x08),
            "share": bool(b1 & 0x10),
            "options": bool(b1 & 0x20),
            "l3": bool(b1 & 0x40),
            "r3": bool(b1 & 0x80),
            "ps": bool(b2 & 0x01),
            "touchpad": bool(b2 & 0x02),
        },
    }


def send_dualsense_bt_led(bt_path: str, r: int, g: int, b: int, mic_mute: bool = False,
                          player_leds: str = "center", force_reset: bool = False) -> bool:
    """Envía el color de la barra LED central, LEDs de jugador y estado de micrófono (BT 0x31 o USB 0x02)."""
    if not IS_WINDOWS or not bt_path:
        return False
    low = bt_path.lower()
    is_bt = "{00001124" in low
    try:
        if is_bt and (force_reset or low not in _led_initialized_paths):
            hw_sensors.dualsense_request_full_mode(bt_path)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k32.CreateFileW(bt_path, 0xC0000000, 0x3, None, 3, 0, None)
        if not h or h == wintypes.HANDLE(-1).value:
            h = k32.CreateFileW(bt_path, 0x40000000, 0x3, None, 3, 0, None)
        if not h or h == wintypes.HANDLE(-1).value:
            return False
        try:
            if force_reset or low not in _led_initialized_paths:
                _write_dualsense_packet(
                    k32, h, is_bt, r, g, b,
                    light_out=True, mic_mute=mic_mute, player_leds=player_leds,
                )
                time.sleep(0.06)
                _led_initialized_paths.add(low)
            return _write_dualsense_packet(
                k32, h, is_bt, r, g, b,
                light_out=False, mic_mute=mic_mute, player_leds=player_leds,
            )
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False


def find_vigem_dll() -> str | None:
    bases = [os.path.dirname(os.path.abspath(__file__))]
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            bases.insert(0, sys._MEIPASS)
        bases.insert(0, os.path.dirname(os.path.abspath(sys.executable)))
    for base in bases:
        for rel in (("tools", "ViGEmClient.dll"), ("ViGEmClient.dll",)):
            p = os.path.join(base, *rel)
            if os.path.isfile(p):
                return p
    return None


def is_vigembus_installed() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        cfg = ctypes.WinDLL("cfgmgr32")
        guid = (ctypes.c_ubyte * 16)(*VIGEM_BUS_GUID_BYTES)
        size = wintypes.ULONG(0)
        if cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), guid, None, 0) != 0:
            return False
        return size.value > 2
    except Exception:
        return False


def install_vigembus() -> dict:
    if not IS_WINDOWS:
        return {"status": "error", "message": "Solo compatible con Windows."}
    if not hw_sensors.is_admin():
        return {"status": "error", "needs_admin": True, "message": "Ejecuta VortexCore como Administrador para instalar el driver ViGEmBus."}
    if is_vigembus_installed():
        return {"status": "ok", "installed": True}

    installer = os.path.join(tempfile.gettempdir(), "ViGEmBusSetup.exe")
    try:
        req = urllib.request.Request(
            VIGEM_INSTALLER_URL,
            headers={"User-Agent": "VortexCoreHub/1.0"},
        )
        with urllib.request.urlopen(req, timeout=45) as resp, open(installer, "wb") as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
        with open(installer, "rb") as chk:
            if chk.read(2) != b"MZ":
                return {"status": "error", "message": "El instalador descargado de ViGEmBus no es válido."}
        r = subprocess.run([installer, "/quiet", "/norestart"], timeout=120, creationflags=CREATE_NO_WINDOW)
        if r.returncode not in (0, 3010):
            return {"status": "error", "message": f"Instalación falló con código {r.returncode}."}
        return {"status": "ok", "installed": is_vigembus_installed()}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        try:
            if os.path.isfile(installer):
                os.remove(installer)
        except OSError:
            pass


def ensure_vigembus_in_background() -> None:
    """Instala ViGEmBus en silencio una sola vez si falta y hay permisos de Administrador."""
    if not IS_WINDOWS or is_vigembus_installed() or not hw_sensors.is_admin():
        return
    install_vigembus()


def _find_bt_dualsense_path() -> str | None:
    for path in hw_sensors._hid_interface_paths():
        low = path.lower()
        if "054c" in low and any(pid in low for pid in hw_sensors.DUALSENSE_PIDS) and "{00001124" in low:
            return path
    return None


def _find_all_dualsense_paths() -> list[str]:
    """Devuelve todas las rutas HID DualSense conectadas (Bluetooth primero, luego USB)."""
    bt_paths = []
    usb_paths = []
    for path in hw_sensors._hid_interface_paths():
        low = path.lower()
        if "054c" in low and any(pid in low for pid in hw_sensors.DUALSENSE_PIDS):
            if "{00001124" in low:
                bt_paths.append(path)
            else:
                usb_paths.append(path)
    return bt_paths + usb_paths


class DualSenseBridge:
    """Mantiene activo un mando virtual DualShock 4 (botones PS) o Xbox 360 cuando hay DualSense BT."""

    def __init__(self, enabled: bool = True):
        cfg = load_dualsense_config()
        self.mode = cfg["mode"]  # "ds4", "xbox"
        self.deadzone = cfg["deadzone"]
        self.led_color = cfg["led_color"]
        self.led_brightness = cfg["led_brightness"]
        self.rainbow_speed = cfg["rainbow_speed"]
        self.player_leds = cfg.get("player_leds", "all")
        self.curve = cfg["curve"]
        self.hair_triggers = cfg["hair_triggers"]
        self.invert_y = cfg["invert_y"]
        self.touchpad_mouse = cfg["touchpad_mouse"]
        self.mic_mute = cfg["mic_mute"]
        self.idle_timeout = cfg.get("idle_timeout", 15)
        self.power_save = cfg.get("power_save", True)
        self.rumble_enabled = cfg.get("rumble_enabled", True)
        self.rumble_intensity = cfg.get("rumble_intensity", 80)
        self.enabled = bool(enabled) and self.mode != "off"
        self.active = False
        self._stop_ev = threading.Event()
        self._thread = None
        self._last_bt_path = None
        self._last_led_rgb = None
        self._led_dirty = True
        self._last_activity_t = time.monotonic()
        self._idle_dimmed = False
        self.live_state = None

    def start(self) -> None:
        if not IS_WINDOWS or self._thread is not None:
            return
        self._stop_ev.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_ev.set()

    def set_enabled(self, enabled: bool) -> None:
        if not enabled:
            self.set_config(mode="off")
        elif self.mode == "off":
            self.set_config(mode="ds4")

    def _apply_leds_now(self, force_reset: bool = False, battery_pct: int | None = None) -> None:
        paths = _find_all_dualsense_paths()
        if not paths and self._last_bt_path:
            paths = [self._last_bt_path]
        if not paths:
            return
        if battery_pct is None:
            cached = (hw_sensors._ds_cache or {}).get("value") or {}
            battery_pct = cached.get("percent")
        eff_brightness = self.led_brightness
        eff_pleds = self.player_leds
        if self.power_save and battery_pct is not None and battery_pct <= 20:
            eff_brightness = min(eff_brightness, 25)
        if self.idle_timeout > 0 and (time.monotonic() - self._last_activity_t) >= (self.idle_timeout * 60):
            eff_brightness = 0
            eff_pleds = "off"
            self._idle_dimmed = True
        else:
            self._idle_dimmed = False
        rgb = resolve_led_rgb(
            self.led_color, battery_pct=battery_pct,
            brightness=eff_brightness, speed=self.rainbow_speed,
        )
        for p in paths:
            send_dualsense_bt_led(
                p, *rgb, mic_mute=self.mic_mute,
                player_leds=eff_pleds, force_reset=force_reset,
            )
        self._last_led_rgb = rgb
        self._led_dirty = False

    def set_config(self, mode: str = None, deadzone: int = None, led_color: str = None,
                   led_brightness: int = None, rainbow_speed: int = None,
                   player_leds: str = None,
                   curve: str = None, hair_triggers: bool = None, invert_y: bool = None,
                   touchpad_mouse: bool = None, mic_mute: bool = None,
                   idle_timeout: int = None, power_save: bool = None,
                   rumble_enabled: bool = None, rumble_intensity: int = None) -> dict:
        self._last_activity_t = time.monotonic()
        if mode in ("ds4", "xbox"):
            self.mode = mode
            self.enabled = True
        if deadzone is not None:
            self.deadzone = max(0, min(25, int(deadzone)))
        if led_brightness is not None:
            self.led_brightness = max(0, min(100, int(led_brightness)))
        if rainbow_speed is not None:
            self.rainbow_speed = max(1, min(10, int(rainbow_speed)))
        if player_leds in ("off", "center", "two", "three", "four", "all"):
            self.player_leds = player_leds
        if curve in ("linear", "precision", "fast"):
            self.curve = curve
        if hair_triggers is not None:
            self.hair_triggers = bool(hair_triggers)
        if invert_y is not None:
            self.invert_y = bool(invert_y)
        if touchpad_mouse is not None:
            self.touchpad_mouse = bool(touchpad_mouse)
        if mic_mute is not None:
            self.mic_mute = bool(mic_mute)
        if idle_timeout is not None and int(idle_timeout) in (0, 5, 15, 30):
            self.idle_timeout = int(idle_timeout)
        if power_save is not None:
            self.power_save = bool(power_save)
        if rumble_enabled is not None:
            self.rumble_enabled = bool(rumble_enabled)
        if rumble_intensity is not None:
            self.rumble_intensity = max(0, min(100, int(rumble_intensity)))
        if led_color is not None:
            self.led_color = str(led_color)[:16] or "auto"
            self._last_led_rgb = None
        save_dualsense_config({
            "mode": self.mode,
            "deadzone": self.deadzone,
            "led_color": self.led_color,
            "led_brightness": self.led_brightness,
            "rainbow_speed": self.rainbow_speed,
            "player_leds": self.player_leds,
            "curve": self.curve,
            "hair_triggers": self.hair_triggers,
            "invert_y": self.invert_y,
            "touchpad_mouse": self.touchpad_mouse,
            "mic_mute": self.mic_mute,
            "idle_timeout": self.idle_timeout,
            "power_save": self.power_save,
            "rumble_enabled": self.rumble_enabled,
            "rumble_intensity": self.rumble_intensity,
        })
        if any(x is not None for x in (led_color, led_brightness, rainbow_speed, player_leds, mic_mute, power_save, idle_timeout)):
            self._led_dirty = True
            self._apply_leds_now(force_reset=False)
        return self.status()

    def test_rumble(self) -> bool:
        paths = _find_all_dualsense_paths()
        target_path = (paths[0] if paths else None) or self._last_bt_path
        if not target_path:
            return False
        rgb = self._last_led_rgb or resolve_led_rgb(
            self.led_color, brightness=self.led_brightness, speed=self.rainbow_speed
        )
        eff_int = self.rumble_intensity if self.rumble_enabled else 50
        if self.power_save:
            cached = (hw_sensors._ds_cache or {}).get("value") or {}
            if cached.get("percent") is not None and cached.get("percent") <= 20:
                eff_int = min(eff_int, 40)
        return send_dualsense_bt_rumble(
            target_path, *rgb, player_leds=self.player_leds, intensity_pct=eff_int
        )

    def get_live_state(self) -> dict:
        st = self.status()
        st["live"] = self.live_state
        return st

    def status(self) -> dict:
        cached = (hw_sensors._ds_cache or {}).get("value") or {}
        cache_age = time.time() - float((hw_sensors._ds_cache or {}).get("at") or 0.0)
        if (cached.get("percent") is None or cache_age > 8.0) and not self.active:
            try:
                fresh = hw_sensors.read_dualsense_battery(max_age=4.0, force_full=True)
                if isinstance(fresh, dict):
                    cached = fresh
            except Exception:
                pass
        bat_pct = cached.get("percent")
        bat_charging = bool(cached.get("charging"))
        return {
            "vigem_installed": is_vigembus_installed(),
            "dll_present": find_vigem_dll() is not None,
            "bridge_active": self.active or bool(_find_all_dualsense_paths()),
            "enabled": self.enabled,
            "mode": self.mode,
            "deadzone": self.deadzone,
            "led_color": self.led_color,
            "led_brightness": self.led_brightness,
            "rainbow_speed": self.rainbow_speed,
            "player_leds": self.player_leds,
            "curve": self.curve,
            "hair_triggers": self.hair_triggers,
            "invert_y": self.invert_y,
            "touchpad_mouse": self.touchpad_mouse,
            "mic_mute": self.mic_mute,
            "idle_timeout": self.idle_timeout,
            "power_save": self.power_save,
            "rumble_enabled": self.rumble_enabled,
            "rumble_intensity": self.rumble_intensity,
            "battery_pct": bat_pct,
            "battery_charging": bat_charging,
        }

    def _run(self) -> None:
        while not self._stop_ev.is_set():
            dll_path = find_vigem_dll()
            bt_path = _find_bt_dualsense_path()
            if not self.enabled or self.mode == "off" or not is_vigembus_installed() or not dll_path or not bt_path:
                self.active = False
                # Aunque el puente ViGEm no esté activo (o el mando esté por USB), mantenemos LEDs y telemetría
                paths = _find_all_dualsense_paths()
                if paths:
                    p0 = paths[0]
                    is_bt = "{00001124" in p0.lower()
                    if self._led_dirty or self.led_color == "rainbow":
                        self._apply_leds_now(force_reset=False)
                    reps = hw_sensors._read_hid_reports(p0, count=1, timeout_ms=120)
                    if reps:
                        parsed = hw_sensors.parse_dualsense_report(reps[-1], bluetooth=is_bt)
                        if is_bt and parsed and parsed.get("mode") == "simple":
                            hw_sensors.dualsense_request_full_mode(p0)
                            reps = hw_sensors._read_hid_reports(p0, count=1, timeout_ms=120)
                            if reps:
                                parsed = hw_sensors.parse_dualsense_report(reps[-1], bluetooth=is_bt)
                        live = parse_dualsense_live_state(reps[-1], self.deadzone) if reps else None
                        if live is not None:
                            self.live_state = live
                            self.active = True
                        if parsed and parsed.get("mode") == "full":
                            parsed["bluetooth"] = is_bt
                            hw_sensors._ds_cache.update(at=time.time(), value=parsed)
                            if self.led_color == "auto":
                                new_rgb = resolve_led_rgb("auto", parsed.get("percent"), brightness=self.led_brightness)
                                if new_rgb != self._last_led_rgb:
                                    self._apply_leds_now(force_reset=False, battery_pct=parsed.get("percent"))
                    self._stop_ev.wait(0.035)
                else:
                    self.live_state = None
                    _led_initialized_paths.clear()
                    self._stop_ev.wait(1.2)
                continue

            self._last_bt_path = bt_path
            self._bridge_session(dll_path, bt_path, self.mode)
            self.active = False
            self._stop_ev.wait(0.15)

    def _bridge_session(self, dll_path: str, bt_path: str, active_mode: str) -> None:
        vigem = None
        client = None
        target = None
        h = None
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, ctypes.c_ulong, wintypes.DWORD, ctypes.c_void_p,
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

        try:
            vigem = ctypes.WinDLL(dll_path)
            vigem.vigem_alloc.restype = ctypes.c_void_p
            vigem.vigem_connect.argtypes = [ctypes.c_void_p]
            vigem.vigem_connect.restype = wintypes.UINT
            vigem.vigem_target_x360_alloc.restype = ctypes.c_void_p
            vigem.vigem_target_ds4_alloc.restype = ctypes.c_void_p
            vigem.vigem_target_add.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            vigem.vigem_target_add.restype = wintypes.UINT
            vigem.vigem_target_x360_update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, XUSB_REPORT]
            vigem.vigem_target_x360_update.restype = wintypes.UINT
            vigem.vigem_target_ds4_update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, DS4_REPORT]
            vigem.vigem_target_ds4_update.restype = wintypes.UINT
            vigem.vigem_target_remove.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            vigem.vigem_target_free.argtypes = [ctypes.c_void_p]
            vigem.vigem_disconnect.argtypes = [ctypes.c_void_p]
            vigem.vigem_free.argtypes = [ctypes.c_void_p]

            # Activar modo completo 0x31 en el DualSense Bluetooth
            hw_sensors.dualsense_request_full_mode(bt_path)
            time.sleep(0.05)
            self._apply_leds_now(force_reset=True)
            first_031_led_sent = False

            u32 = ctypes.windll.user32
            prev_tp_xy = None
            prev_tp_click = False

            h = k32.CreateFileW(bt_path, 0x80000000, 0x3, None, 3, 0x40000000, None)
            if not h or h == wintypes.HANDLE(-1).value:
                h = None
                return

            client = vigem.vigem_alloc()
            if not client or vigem.vigem_connect(client) != 0x20000000:
                return
            target = vigem.vigem_target_ds4_alloc() if active_mode == "ds4" else vigem.vigem_target_x360_alloc()
            if not target or vigem.vigem_target_add(client, target) != 0x20000000:
                return

            self.active = True
            buf = ctypes.create_string_buffer(128)
            got = wintypes.DWORD(0)

            while not self._stop_ev.is_set() and self.enabled and self.mode == active_mode and is_vigembus_installed():
                ev = k32.CreateEventW(None, True, False, None)
                ov = OVERLAPPED()
                ov.hEvent = ev
                try:
                    ok = k32.ReadFile(h, buf, 128, None, ctypes.byref(ov))
                    if not ok and ctypes.get_last_error() != 997:
                        break
                    w = k32.WaitForSingleObject(ev, 250)
                    if w != 0:
                        k32.CancelIo(h)
                        if w == 0x102:  # WAIT_TIMEOUT
                            continue
                        break
                    if not k32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(got), False) or got.value == 0:
                        continue
                    rep = buf.raw[: got.value]
                    live = parse_dualsense_live_state(rep, self.deadzone)
                    if live is not None:
                        self.live_state = live
                    if self.touchpad_mouse and active_mode == "ds4" and len(rep) >= 38 and rep[0] == 0x31:
                        tp_active = (rep[34] & 0x80) == 0
                        if tp_active:
                            tx = rep[35] | ((rep[36] & 0x0F) << 8)
                            ty = ((rep[36] & 0xF0) >> 4) | (rep[37] << 4)
                            if prev_tp_xy is not None:
                                dx = int(round((tx - prev_tp_xy[0]) * 0.55))
                                dy = int(round((ty - prev_tp_xy[1]) * 0.55))
                                if dx or dy:
                                    u32.mouse_event(0x0001, dx, dy, 0, 0)
                            prev_tp_xy = (tx, ty)
                        else:
                            prev_tp_xy = None
                        tp_click = bool(rep[11] & 0x02)
                        if tp_click != prev_tp_click:
                            u32.mouse_event(0x0002 if tp_click else 0x0004, 0, 0, 0, 0)
                            prev_tp_click = tp_click
                    else:
                        prev_tp_xy = None
                        if prev_tp_click:
                            u32.mouse_event(0x0004, 0, 0, 0, 0)
                            prev_tp_click = False
                    if active_mode == "ds4":
                        ds4 = dualsense_to_ds4_report(
                            rep, self.deadzone, self.curve, self.hair_triggers, self.invert_y
                        )
                        if ds4 is not None:
                            vigem.vigem_target_ds4_update(client, target, ds4)
                    else:
                        xusb = dualsense_to_xusb_report(
                            rep, self.deadzone, self.curve, self.hair_triggers, self.invert_y
                        )
                        if xusb is not None:
                            vigem.vigem_target_x360_update(client, target, xusb)

                    parsed = hw_sensors.parse_dualsense_report(rep, bluetooth=True)
                    if parsed and parsed.get("mode") == "full":
                        parsed["bluetooth"] = True
                        hw_sensors._ds_cache.update(at=time.time(), value=parsed)
                        bat_pct = parsed.get("percent")
                        if not first_031_led_sent or self._led_dirty:
                            first_031_led_sent = True
                            self._apply_leds_now(force_reset=False, battery_pct=bat_pct)
                        elif self.led_color == "auto":
                            new_rgb = resolve_led_rgb("auto", bat_pct, brightness=self.led_brightness)
                            if new_rgb != self._last_led_rgb:
                                self._apply_leds_now(force_reset=False, battery_pct=bat_pct)
                        elif self.led_color == "rainbow":
                            now_t = time.monotonic()
                            if now_t - getattr(self, "_last_rainbow_t", 0.0) >= 0.12:
                                self._last_rainbow_t = now_t
                                self._apply_leds_now(force_reset=False, battery_pct=bat_pct)
                finally:
                    k32.CloseHandle(ev)
        except Exception:
            pass
        finally:
            self.active = False
            self.live_state = None
            if h:
                try:
                    k32.CloseHandle(h)
                except Exception:
                    pass
            if vigem and client and target:
                try:
                    vigem.vigem_target_remove(client, target)
                    vigem.vigem_target_free(target)
                except Exception:
                    pass
            if vigem and client:
                try:
                    vigem.vigem_disconnect(client)
                    vigem.vigem_free(client)
                except Exception:
                    pass
