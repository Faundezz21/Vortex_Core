# overlay en juego: ventana win32 con transparencia por pixel, siempre encima y que deja pasar los clics

import ctypes
import json
import os
import sys
import threading
from collections import deque
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

CORNERS = ("tl", "tr", "bl", "br")
SIZES = {"s": 0.85, "m": 1.0, "l": 1.25}
ITEMS = ("fps", "cpu", "gpu", "ram", "fan")
DEFAULT_CONFIG = {
    "enabled": False,
    "corner": "tl",
    "size": "m",
    "opacity": 85,
    "only_games": False,
    "items": list(ITEMS),
}
HOTKEY_LABEL = "Ctrl+Shift+F10"
HISTORY_LEN = 48

# colores en formato rgb
C_ACCENT = (0x00, 0xE5, 0xFF)
C_TEXT = (0xF4, 0xF6, 0xFA)
C_MUTED = (0x8B, 0x95, 0xA8)
C_OK = (0x34, 0xD3, 0x99)
C_WARN = (0xFB, 0xBF, 0x24)
C_HOT = (0xF8, 0x71, 0x71)
C_BG = (0x0C, 0x10, 0x18)


def config_path() -> str:
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub")
    return os.path.join(base, "overlay.json")


def sanitize_config(data, base: dict | None = None) -> dict:
    cfg = dict(base or DEFAULT_CONFIG)
    if not isinstance(data, dict):
        return cfg
    if "enabled" in data:
        cfg["enabled"] = bool(data["enabled"])
    if "only_games" in data:
        cfg["only_games"] = bool(data["only_games"])
    if data.get("corner") in CORNERS:
        cfg["corner"] = data["corner"]
    if data.get("size") in SIZES:
        cfg["size"] = data["size"]
    try:
        cfg["opacity"] = max(30, min(100, int(data.get("opacity", cfg["opacity"]))))
    except (TypeError, ValueError):
        pass
    if isinstance(data.get("items"), list):
        cfg["items"] = [i for i in ITEMS if i in data["items"]]
    return cfg


def load_config() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as f:
            return sanitize_config(json.load(f))
    except (OSError, ValueError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(config_path()), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except OSError:
        pass


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def temp_color(t):
    if t is None:
        return C_MUTED
    if t >= 90:
        return C_HOT
    if t >= 80:
        return C_WARN
    return C_OK


def fps_color(fps):
    if fps is None:
        return C_MUTED
    if fps < 30:
        return C_HOT
    if fps < 55:
        return C_WARN
    return C_OK


def _app_title(app: str) -> str:
    name = os.path.splitext(app or "")[0]
    return name[:22]


# arma el modelo que dibuja el overlay a partir de la telemetria
def build_model(tel: dict, fps: dict | None, items, fps_note: str | None = None, history=()) -> dict:
    model = {"fps": None, "rows": []}
    for item in items:
        if item == "fps":
            value = fps.get("fps") if fps else None
            model["fps"] = {
                "value": value,
                "color": fps_color(value),
                "frametime": f"{fps['frametime_ms']:.1f} ms" if fps and fps.get("frametime_ms") is not None else None,
                "low": f"1% low {fps['low1_fps']}" if fps and fps.get("low1_fps") else None,
                "app": _app_title(fps.get("app", "")) if fps else "",
                "note": None if value else (fps_note or "sin juego activo"),
                "history": list(history),
            }
        elif item in ("cpu", "gpu"):
            usage = _num(tel.get(f"{item}_usage"))
            temp = _num(tel.get(f"{item}_temp"))
            extra = []
            if item == "cpu":
                ghz = _num(tel.get("cpu_freq"))
                if ghz:
                    extra.append(f"{ghz:.1f} GHz")
            else:
                power = _num(tel.get("gpu_power"))
                mhz = _num(tel.get("gpu_freq_mhz"))
                if power is not None:
                    extra.append(f"{power:.0f} W")
                if mhz:
                    extra.append(f"{mhz:.0f} MHz")
            model["rows"].append({
                "label": item.upper(),
                "value": f"{usage:.0f}%" if usage is not None else "--",
                "extra": " · ".join(extra),
                "pill": (f"{temp:.0f}°C", temp_color(temp)) if temp is not None else None,
                "bar": max(0.0, min(1.0, usage / 100)) if usage is not None else None,
                "bar_color": C_ACCENT,
            })
        elif item == "ram":
            used = _num(tel.get("ram_used"))
            total = _num(tel.get("ram_total"))
            pct = _num(tel.get("ram_pct"))
            model["rows"].append({
                "label": "RAM",
                "value": f"{used:.1f}" if used is not None else "--",
                "extra": f"/ {total:.0f} GB" if total else "",
                "pill": (f"{pct:.0f}%", C_WARN if pct >= 90 else C_ACCENT) if pct is not None else None,
                "bar": max(0.0, min(1.0, pct / 100)) if pct is not None else None,
                "bar_color": C_WARN if (pct or 0) >= 90 else C_ACCENT,
            })
        elif item == "fan":
            rpms = [int(r) for r in (_num(tel.get("fan1_rpm")), _num(tel.get("fan2_rpm"))) if r]
            if rpms:
                model["rows"].append({
                    "label": "FAN",
                    "value": str(rpms[0]),
                    "extra": (f"/ {rpms[1]} RPM" if len(rpms) > 1 else "RPM"),
                    "pill": None,
                    "bar": None,
                    "bar_color": C_ACCENT,
                })
    return model


# calcula alto total del overlay segun el modelo y la escala
def model_height(model: dict, s: float) -> int:
    pad = 12 * s
    h = pad * 2
    if model["fps"] is not None:
        h += 14 * s + 38 * s + 24 * s
        if model["rows"]:
            h += 12 * s
    rows = model["rows"]
    h += sum((30 if r["bar"] is not None else 22) * s for r in rows)
    h += max(0, len(rows) - 1) * 6 * s
    return int(round(h))


if IS_WINDOWS:
    # instancias propias para no pisar los argtypes que define tray_manager
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        _gdip = ctypes.WinDLL("gdiplus")
    except OSError:
        _gdip = None

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    VP = ctypes.c_void_p
    F = ctypes.c_float

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    class SIZE(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    class GdiplusStartupInput(ctypes.Structure):
        _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", VP),
                    ("SuppressBackgroundThread", wintypes.BOOL), ("SuppressExternalCodecs", wintypes.BOOL)]

    class RectF(ctypes.Structure):
        _fields_ = [("X", F), ("Y", F), ("Width", F), ("Height", F)]

    class PointF(ctypes.Structure):
        _fields_ = [("X", F), ("Y", F)]

    _sigs = {
        (_user32, "RegisterClassExW"): ([ctypes.POINTER(WNDCLASSEXW)], wintypes.ATOM),
        (_user32, "CreateWindowExW"): ([wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                        wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID], wintypes.HWND),
        (_user32, "DefWindowProcW"): ([wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], LRESULT),
        (_user32, "GetMessageW"): ([ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
        (_user32, "TranslateMessage"): ([ctypes.POINTER(wintypes.MSG)], wintypes.BOOL),
        (_user32, "DispatchMessageW"): ([ctypes.POINTER(wintypes.MSG)], LRESULT),
        (_user32, "SetTimer"): ([wintypes.HWND, ctypes.c_size_t, wintypes.UINT, VP], ctypes.c_size_t),
        (_user32, "RegisterHotKey"): ([wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
        (_user32, "ShowWindow"): ([wintypes.HWND, ctypes.c_int], wintypes.BOOL),
        (_user32, "IsWindowVisible"): ([wintypes.HWND], wintypes.BOOL),
        (_user32, "SetWindowPos"): ([wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, wintypes.UINT], wintypes.BOOL),
        (_user32, "GetForegroundWindow"): ([], wintypes.HWND),
        (_user32, "MonitorFromWindow"): ([wintypes.HWND, wintypes.DWORD], wintypes.HMONITOR),
        (_user32, "GetMonitorInfoW"): ([wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)], wintypes.BOOL),
        (_user32, "PostMessageW"): ([wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
        (_user32, "GetDpiForWindow"): ([wintypes.HWND], wintypes.UINT),
        (_user32, "SetThreadDpiAwarenessContext"): ([VP], VP),
        (_user32, "GetDC"): ([wintypes.HWND], wintypes.HDC),
        (_user32, "ReleaseDC"): ([wintypes.HWND, wintypes.HDC], ctypes.c_int),
        (_user32, "UpdateLayeredWindow"): ([wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                            ctypes.POINTER(SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                            wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD], wintypes.BOOL),
        (_kernel32, "GetModuleHandleW"): ([wintypes.LPCWSTR], wintypes.HMODULE),
        (_gdi32, "CreateCompatibleDC"): ([wintypes.HDC], wintypes.HDC),
        (_gdi32, "CreateDIBSection"): ([wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
                                        ctypes.POINTER(VP), wintypes.HANDLE, wintypes.DWORD], wintypes.HBITMAP),
        (_gdi32, "SelectObject"): ([wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ),
        (_gdi32, "DeleteObject"): ([wintypes.HGDIOBJ], wintypes.BOOL),
        (_gdi32, "DeleteDC"): ([wintypes.HDC], wintypes.BOOL),
    }
    if _gdip is not None:
        _sigs.update({
            (_gdip, "GdiplusStartup"): ([ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(GdiplusStartupInput), VP], ctypes.c_int),
            (_gdip, "GdipCreateBitmapFromScan0"): ([ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, VP,
                                                    ctypes.POINTER(VP)], ctypes.c_int),
            (_gdip, "GdipGetImageGraphicsContext"): ([VP, ctypes.POINTER(VP)], ctypes.c_int),
            (_gdip, "GdipDeleteGraphics"): ([VP], ctypes.c_int),
            (_gdip, "GdipDisposeImage"): ([VP], ctypes.c_int),
            (_gdip, "GdipSetSmoothingMode"): ([VP, ctypes.c_int], ctypes.c_int),
            (_gdip, "GdipSetTextRenderingHint"): ([VP, ctypes.c_int], ctypes.c_int),
            (_gdip, "GdipGraphicsClear"): ([VP, ctypes.c_uint32], ctypes.c_int),
            (_gdip, "GdipCreateSolidFill"): ([ctypes.c_uint32, ctypes.POINTER(VP)], ctypes.c_int),
            (_gdip, "GdipDeleteBrush"): ([VP], ctypes.c_int),
            (_gdip, "GdipCreatePen1"): ([ctypes.c_uint32, F, ctypes.c_int, ctypes.POINTER(VP)], ctypes.c_int),
            (_gdip, "GdipDeletePen"): ([VP], ctypes.c_int),
            (_gdip, "GdipSetPenLineJoin"): ([VP, ctypes.c_int], ctypes.c_int),
            (_gdip, "GdipCreatePath"): ([ctypes.c_int, ctypes.POINTER(VP)], ctypes.c_int),
            (_gdip, "GdipAddPathArc"): ([VP, F, F, F, F, F, F], ctypes.c_int),
            (_gdip, "GdipClosePathFigure"): ([VP], ctypes.c_int),
            (_gdip, "GdipDeletePath"): ([VP], ctypes.c_int),
            (_gdip, "GdipFillPath"): ([VP, VP, VP], ctypes.c_int),
            (_gdip, "GdipDrawPath"): ([VP, VP, VP], ctypes.c_int),
            (_gdip, "GdipFillRectangle"): ([VP, VP, F, F, F, F], ctypes.c_int),
            (_gdip, "GdipDrawLines"): ([VP, VP, ctypes.POINTER(PointF), ctypes.c_int], ctypes.c_int),
            (_gdip, "GdipFillPolygon"): ([VP, VP, ctypes.POINTER(PointF), ctypes.c_int, ctypes.c_int], ctypes.c_int),
            (_gdip, "GdipCreateFontFamilyFromName"): ([wintypes.LPCWSTR, VP, ctypes.POINTER(VP)], ctypes.c_int),
            (_gdip, "GdipDeleteFontFamily"): ([VP], ctypes.c_int),
            (_gdip, "GdipCreateFont"): ([VP, F, ctypes.c_int, ctypes.c_int, ctypes.POINTER(VP)], ctypes.c_int),
            (_gdip, "GdipDeleteFont"): ([VP], ctypes.c_int),
            (_gdip, "GdipStringFormatGetGenericTypographic"): ([ctypes.POINTER(VP)], ctypes.c_int),
            (_gdip, "GdipDrawString"): ([VP, wintypes.LPCWSTR, ctypes.c_int, VP, ctypes.POINTER(RectF), VP, VP], ctypes.c_int),
            (_gdip, "GdipMeasureString"): ([VP, wintypes.LPCWSTR, ctypes.c_int, VP, ctypes.POINTER(RectF), VP,
                                            ctypes.POINTER(RectF), ctypes.POINTER(ctypes.c_int),
                                            ctypes.POINTER(ctypes.c_int)], ctypes.c_int),
        })
    for (_dll, _name), (_args, _res) in _sigs.items():
        _fn = getattr(_dll, _name)
        _fn.argtypes = _args
        _fn.restype = _res

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WM_TIMER = 0x0113
WM_HOTKEY = 0x0312
WM_APP_REFRESH = 0x8001
SW_HIDE = 0
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
MONITOR_DEFAULTTOPRIMARY = 1
MOD_CONTROL = 0x2
MOD_SHIFT = 0x4
MOD_NOREPEAT = 0x4000
VK_F10 = 0x79
ULW_ALPHA = 0x2
HOTKEY_ID = 0x5643
TIMER_ID = 1
PIXEL_FORMAT_32BPP_PARGB = 0x000E200B
UNIT_PIXEL = 2


def _argb(c, a=255) -> int:
    return ((a & 0xFF) << 24) | (c[0] << 16) | (c[1] << 8) | c[2]


class _Painter:
    # envoltorio minimo de gdi+ para dibujar con antialias sobre un buffer argb

    def __init__(self, graphics, scale: float):
        self.g = graphics
        self.s = scale
        self._fonts = {}
        self._families = {}
        fmt = VP()
        _gdip.GdipStringFormatGetGenericTypographic(ctypes.byref(fmt))
        self.fmt = fmt

    def close(self):
        for f in self._fonts.values():
            _gdip.GdipDeleteFont(f)
        for fam in self._families.values():
            _gdip.GdipDeleteFontFamily(fam)

    def font(self, size: float, bold: bool = False, family: str = "Segoe UI"):
        key = (round(size * self.s, 2), bold, family)
        if key not in self._fonts:
            fam = self._families.get(family)
            if fam is None:
                fam = VP()
                if _gdip.GdipCreateFontFamilyFromName(family, None, ctypes.byref(fam)) != 0:
                    _gdip.GdipCreateFontFamilyFromName("Segoe UI", None, ctypes.byref(fam))
                self._families[family] = fam
            f = VP()
            _gdip.GdipCreateFont(fam, F(size * self.s), 1 if bold else 0, UNIT_PIXEL, ctypes.byref(f))
            self._fonts[key] = f
        return self._fonts[key]

    def _brush(self, argb):
        b = VP()
        _gdip.GdipCreateSolidFill(argb, ctypes.byref(b))
        return b

    def round_rect(self, x, y, w, h, r, fill=None, stroke=None, stroke_w=1.0):
        r = max(0.5, min(r, w / 2, h / 2))
        d = r * 2
        path = VP()
        _gdip.GdipCreatePath(0, ctypes.byref(path))
        _gdip.GdipAddPathArc(path, F(x), F(y), F(d), F(d), F(180), F(90))
        _gdip.GdipAddPathArc(path, F(x + w - d), F(y), F(d), F(d), F(270), F(90))
        _gdip.GdipAddPathArc(path, F(x + w - d), F(y + h - d), F(d), F(d), F(0), F(90))
        _gdip.GdipAddPathArc(path, F(x), F(y + h - d), F(d), F(d), F(90), F(90))
        _gdip.GdipClosePathFigure(path)
        if fill is not None:
            b = self._brush(fill)
            _gdip.GdipFillPath(self.g, b, path)
            _gdip.GdipDeleteBrush(b)
        if stroke is not None:
            pen = VP()
            _gdip.GdipCreatePen1(stroke, F(stroke_w), UNIT_PIXEL, ctypes.byref(pen))
            _gdip.GdipDrawPath(self.g, pen, path)
            _gdip.GdipDeletePen(pen)
        _gdip.GdipDeletePath(path)

    def rect(self, x, y, w, h, argb):
        b = self._brush(argb)
        _gdip.GdipFillRectangle(self.g, b, F(x), F(y), F(w), F(h))
        _gdip.GdipDeleteBrush(b)

    def measure(self, text, font):
        box = RectF()
        _gdip.GdipMeasureString(self.g, text, len(text), font, ctypes.byref(RectF(0, 0, 4000, 1000)),
                                self.fmt, ctypes.byref(box), None, None)
        return box.Width, box.Height

    def text(self, text, font, argb, x, y, align="left"):
        if not text:
            return 0.0
        w, h = self.measure(text, font)
        if align == "right":
            x -= w
        elif align == "center":
            x -= w / 2
        b = self._brush(argb)
        _gdip.GdipDrawString(self.g, text, len(text), font, ctypes.byref(RectF(x, y, w + 4, h + 4)), self.fmt, b)
        _gdip.GdipDeleteBrush(b)
        return w

    def area_chart(self, values, x, y, w, h, color):
        if len(values) < 2:
            return
        # escala ajustada al rango reciente para que se noten las caidas
        hi, lo = max(values), min(values)
        margin = max(5.0, hi * 0.15)
        top, bottom = hi + margin * 0.3, max(0.0, lo - margin)
        span = max(top - bottom, 1.0)
        n = HISTORY_LEN - 1
        step = w / n
        x0 = x + w - step * (len(values) - 1)
        pts = [PointF(x0 + i * step, y + h - ((v - bottom) / span) * h) for i, v in enumerate(values)]
        poly = (PointF * (len(pts) + 2))(*pts, PointF(pts[-1].X, y + h), PointF(pts[0].X, y + h))
        b = self._brush(_argb(color, 46))
        _gdip.GdipFillPolygon(self.g, b, poly, len(pts) + 2, 0)
        _gdip.GdipDeleteBrush(b)
        line = (PointF * len(pts))(*pts)
        pen = VP()
        _gdip.GdipCreatePen1(_argb(color, 235), F(1.6 * self.s), UNIT_PIXEL, ctypes.byref(pen))
        _gdip.GdipSetPenLineJoin(pen, 2)
        _gdip.GdipDrawLines(self.g, pen, line, len(pts))
        _gdip.GdipDeletePen(pen)


def paint_model(p, model: dict, width: int, height: int, opacity: int):
    s = p.s
    pad = 12 * s
    bg_alpha = int(min(245, 2.45 * opacity))
    p.round_rect(0.5, 0.5, width - 1, height - 1, 12 * s, fill=_argb(C_BG, bg_alpha),
                 stroke=_argb((255, 255, 255), 34), stroke_w=1.0)
    y = pad
    inner_w = width - pad * 2
    fps = model["fps"]
    if fps is not None:
        # encabezado con marca y nombre del juego
        p.round_rect(pad, y + 3 * s, 6 * s, 6 * s, 3 * s, fill=_argb(fps["color"] if fps["value"] else C_MUTED))
        p.text("VORTEX", p.font(9.5, True), _argb(C_MUTED), pad + 10 * s, y)
        if fps["app"]:
            p.text(fps["app"], p.font(10), _argb(C_MUTED), width - pad, y, "right")
        y += 14 * s
        # numero grande de fps
        big = str(fps["value"]) if fps["value"] else "--"
        bw = p.text(big, p.font(30, True, "Segoe UI Semibold"), _argb(fps["color"]), pad - 1 * s, y - 2 * s)
        p.text("FPS", p.font(10.5, True), _argb(C_MUTED), pad + bw + 5 * s, y + 21 * s)
        if fps["value"]:
            p.text(fps["frametime"] or "", p.font(13, True), _argb(C_TEXT), width - pad, y + 4 * s, "right")
            p.text(fps["low"] or "", p.font(10.5), _argb(C_MUTED), width - pad, y + 21 * s, "right")
        else:
            p.text(fps["note"] or "", p.font(11), _argb(C_MUTED), width - pad, y + 14 * s, "right")
        y += 38 * s
        # grafico de historial de fps
        chart_h = 20 * s
        p.rect(pad, y + chart_h, inner_w, max(1.0, s), _argb((255, 255, 255), 22))
        p.area_chart(fps["history"], pad, y, inner_w, chart_h, fps["color"] if fps["value"] else C_ACCENT)
        y += 24 * s
        if model["rows"]:
            p.rect(pad, y + 5 * s, inner_w, max(1.0, s), _argb((255, 255, 255), 26))
            y += 12 * s
    label_w = 38 * s
    for i, row in enumerate(model["rows"]):
        if i:
            y += 6 * s
        p.text(row["label"], p.font(10.5, True), _argb(C_ACCENT, 220), pad, y + 3 * s)
        vx = pad + label_w
        vw = p.text(row["value"], p.font(14, True), _argb(C_TEXT), vx, y - 1 * s)
        if row["extra"]:
            p.text(row["extra"], p.font(11), _argb(C_MUTED), vx + vw + 5 * s, y + 2.5 * s)
        if row["pill"]:
            ptxt, pcol = row["pill"]
            pf = p.font(11, True)
            tw, th = p.measure(ptxt, pf)
            pw, ph = tw + 14 * s, 18 * s
            px = width - pad - pw
            p.round_rect(px, y, pw, ph, ph / 2, fill=_argb(pcol, 40), stroke=_argb(pcol, 90))
            p.text(ptxt, pf, _argb(pcol), px + pw / 2, y + (ph - th) / 2 - 0.5 * s, "center")
        if row["bar"] is not None:
            by = y + 22 * s
            bh = 4 * s
            p.round_rect(vx, by, width - pad - vx, bh, bh / 2, fill=_argb((255, 255, 255), 24))
            fill_w = (width - pad - vx) * row["bar"]
            if fill_w >= bh:
                p.round_rect(vx, by, fill_w, bh, bh / 2, fill=_argb(row["bar_color"], 230))
            y += 30 * s
        else:
            y += 22 * s


class GameOverlay:
    def __init__(self, get_telemetry, fps_monitor=None, on_change=None):
        self.get_telemetry = get_telemetry
        self.fps = fps_monitor
        self.on_change = on_change
        self.config = load_config()
        self.hwnd = None
        self.hotkey_ok = False
        self.model = None
        self._size = (0, 0)
        self._wndproc = None
        self._gdip_token = None
        self._history = deque(maxlen=HISTORY_LEN)
        self._history_app = None
        self._misses = 0
        self._sync_fps()

    def start(self):
        if IS_WINDOWS and _gdip is not None:
            threading.Thread(target=self._run, daemon=True, name="vch-overlay").start()

    def get_config(self) -> dict:
        cfg = dict(self.config)
        cfg["hotkey"] = HOTKEY_LABEL
        cfg["hotkey_ok"] = self.hotkey_ok
        cfg["fps_available"] = bool(self.fps and self.fps.available)
        cfg["fps_error"] = getattr(self.fps, "error", None) if self.fps else None
        return cfg

    def update_config(self, data: dict) -> dict:
        self.config = sanitize_config(data, self.config)
        save_config(self.config)
        self._sync_fps()
        self._poke()
        return self.get_config()

    def toggle(self):
        self.update_config({"enabled": not self.config["enabled"]})
        if self.on_change:
            try:
                self.on_change(self.config["enabled"])
            except Exception:
                pass

    def _sync_fps(self):
        if not self.fps:
            return
        if self.config["enabled"] and "fps" in self.config["items"]:
            self.fps.start()
        else:
            self.fps.stop()

    def _poke(self):
        if self.hwnd:
            _user32.PostMessageW(self.hwnd, WM_APP_REFRESH, 0, 0)

    def _fps_note(self) -> str | None:
        if not self.fps or not self.fps.available:
            return "sin presentmon"
        if self.fps.error and "access" in self.fps.error.lower():
            return "requiere admin"
        return None

    def _track_history(self, fps):
        if fps and fps.get("fps"):
            if fps.get("app") != self._history_app:
                self._history.clear()
                self._history_app = fps.get("app")
            self._history.append(fps["fps"])
            self._misses = 0
        else:
            self._misses += 1
            if self._misses > 6:
                self._history.clear()
                self._history_app = None

    def _run(self):
        try:
            # dpi por monitor solo para las ventanas de este hilo
            _user32.SetThreadDpiAwarenessContext(VP(-4))
        except Exception:
            pass
        token = ctypes.c_size_t()
        inp = GdiplusStartupInput(1, None, False, False)
        if _gdip.GdiplusStartup(ctypes.byref(token), ctypes.byref(inp), None) != 0:
            return
        self._gdip_token = token
        hinst = _kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self._wnd_proc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "VCH_GameOverlay"
        _user32.RegisterClassExW(ctypes.byref(wc))
        ex = WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE
        self.hwnd = _user32.CreateWindowExW(ex, "VCH_GameOverlay", "VortexCore Overlay", WS_POPUP,
                                            0, 0, 10, 10, None, None, hinst, None)
        if not self.hwnd:
            return
        self.hotkey_ok = bool(_user32.RegisterHotKey(self.hwnd, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_F10))
        _user32.SetTimer(self.hwnd, TIMER_ID, 500, None)
        self._tick()
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _visible_wanted(self, fps) -> bool:
        if not self.config["enabled"] or not self.config["items"]:
            return False
        if self.config["only_games"] and self.fps and self.fps.available and not self.fps.error:
            return bool(fps)
        return True

    def _tick(self):
        fps = self.fps.snapshot() if (self.fps and self.config["enabled"]) else None
        self._track_history(fps)
        if not self._visible_wanted(fps):
            if _user32.IsWindowVisible(self.hwnd):
                _user32.ShowWindow(self.hwnd, SW_HIDE)
            return
        tel = self.get_telemetry() or {}
        self.model = build_model(tel, fps if "fps" in self.config["items"] else None,
                                 self.config["items"], self._fps_note(), self._history)
        if self.model["fps"] is None and not self.model["rows"]:
            _user32.ShowWindow(self.hwnd, SW_HIDE)
            return
        fg = _user32.GetForegroundWindow()
        mon = _user32.MonitorFromWindow(fg or self.hwnd, MONITOR_DEFAULTTOPRIMARY)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        _user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        try:
            dpi = _user32.GetDpiForWindow(self.hwnd) or 96
        except Exception:
            dpi = 96
        s = SIZES[self.config["size"]] * dpi / 96
        width = int(round(262 * s))
        height = model_height(self.model, s)
        self._size = (width, height)
        margin = int(16 * dpi / 96)
        r = mi.rcMonitor
        corner = self.config["corner"]
        x = r.left + margin if corner in ("tl", "bl") else r.right - width - margin
        y = r.top + margin if corner in ("tl", "tr") else r.bottom - height - margin
        self._render(x, y, width, height, s)
        _user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def _render(self, x, y, width, height, s):
        screen = _user32.GetDC(None)
        mdc = _gdi32.CreateCompatibleDC(screen)
        bih = BITMAPINFOHEADER()
        bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bih.biWidth = width
        bih.biHeight = -height
        bih.biPlanes = 1
        bih.biBitCount = 32
        bits = VP()
        dib = _gdi32.CreateDIBSection(mdc, ctypes.byref(bih), 0, ctypes.byref(bits), None, 0)
        old = _gdi32.SelectObject(mdc, dib)
        bmp, g = VP(), VP()
        try:
            _gdip.GdipCreateBitmapFromScan0(width, height, width * 4, PIXEL_FORMAT_32BPP_PARGB, bits, ctypes.byref(bmp))
            _gdip.GdipGetImageGraphicsContext(bmp, ctypes.byref(g))
            _gdip.GdipSetSmoothingMode(g, 4)
            _gdip.GdipSetTextRenderingHint(g, 4)
            _gdip.GdipGraphicsClear(g, 0)
            painter = _Painter(g, s)
            try:
                paint_model(painter, self.model, width, height, self.config["opacity"])
            finally:
                painter.close()
            _gdip.GdipDeleteGraphics(g)
            g = None
            blend = BLENDFUNCTION(0, 0, 255, 1)
            _user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wintypes.POINT(x, y)),
                                        ctypes.byref(SIZE(width, height)), mdc, ctypes.byref(wintypes.POINT(0, 0)),
                                        0, ctypes.byref(blend), ULW_ALPHA)
        finally:
            if g:
                _gdip.GdipDeleteGraphics(g)
            if bmp:
                _gdip.GdipDisposeImage(bmp)
            _gdi32.SelectObject(mdc, old)
            _gdi32.DeleteObject(dib)
            _gdi32.DeleteDC(mdc)
            _user32.ReleaseDC(None, screen)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TIMER or msg == WM_APP_REFRESH:
                self._tick()
                return 0
            if msg == WM_HOTKEY and wparam == HOTKEY_ID:
                self.toggle()
                return 0
        except Exception:
            pass
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)
