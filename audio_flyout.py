"""
Flyout nativo estilo EarTrumpet para VortexCore Hub (renderizado con GDI+ anti-aliased).
Se abre con un solo clic izquierdo en el icono de la bandeja del sistema (System Tray),
justo encima del reloj, con iconos reales de cada app, barra de scroll y control de volumen.
"""

import ctypes
from ctypes import wintypes
import json
import os
import threading
import time

try:
    import psutil
except Exception:
    psutil = None

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
gdiplus = ctypes.windll.gdiplus
try:
    dwmapi = ctypes.windll.dwmapi
except Exception:
    dwmapi = None

# Tipos explícitos de 64 bits para evitar OverflowError en Win32 / GDI+
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON, ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
user32.DrawIconEx.restype = wintypes.BOOL
shell32.ExtractIconExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT]
shell32.ExtractIconExW.restype = wintypes.UINT

# Firmas GDI+ (64-bit safe)
gdiplus.GdiplusStartup.argtypes = [ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_void_p, ctypes.c_void_p]
gdiplus.GdiplusStartup.restype = ctypes.c_int
gdiplus.GdipCreateFromHDC.argtypes = [wintypes.HDC, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipCreateFromHDC.restype = ctypes.c_int
gdiplus.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeleteGraphics.restype = ctypes.c_int
gdiplus.GdipSetSmoothingMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipSetSmoothingMode.restype = ctypes.c_int
gdiplus.GdipCreateSolidFill.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipCreateSolidFill.restype = ctypes.c_int
gdiplus.GdipDeleteBrush.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeleteBrush.restype = ctypes.c_int
gdiplus.GdipCreatePen1.argtypes = [ctypes.c_uint32, ctypes.c_float, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipCreatePen1.restype = ctypes.c_int
gdiplus.GdipDeletePen.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeletePen.restype = ctypes.c_int
gdiplus.GdipCreatePath.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipCreatePath.restype = ctypes.c_int
gdiplus.GdipDeletePath.argtypes = [ctypes.c_void_p]
gdiplus.GdipDeletePath.restype = ctypes.c_int
gdiplus.GdipAddPathArc.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipAddPathArc.restype = ctypes.c_int
gdiplus.GdipAddPathLine.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipAddPathLine.restype = ctypes.c_int
gdiplus.GdipClosePathFigure.argtypes = [ctypes.c_void_p]
gdiplus.GdipClosePathFigure.restype = ctypes.c_int
gdiplus.GdipFillPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
gdiplus.GdipFillPath.restype = ctypes.c_int
gdiplus.GdipDrawPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
gdiplus.GdipDrawPath.restype = ctypes.c_int
gdiplus.GdipFillEllipse.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipFillEllipse.restype = ctypes.c_int
gdiplus.GdipDrawEllipse.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipDrawEllipse.restype = ctypes.c_int
gdiplus.GdipDrawLine.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipDrawLine.restype = ctypes.c_int
gdiplus.GdipDrawArc.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipDrawArc.restype = ctypes.c_int

WS_POPUP = 0x80000000
WS_CLIPCHILDREN = 0x02000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

SW_HIDE = 0
SW_SHOW = 5

WM_DESTROY = 0x0002
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_ACTIVATE = 0x0006
WM_KEYDOWN = 0x0100
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEWHEEL = 0x020A
WM_TIMER = 0x0113
WM_APP = 0x8000
WM_FLYOUT_TOGGLE = WM_APP + 10
WM_FLYOUT_HIDE = WM_APP + 11
ANIM_TIMER_ID = 1

WA_INACTIVE = 0
VK_ESCAPE = 0x1B
SPI_GETWORKAREA = 0x0030
HWND_TOPMOST = -1

SRCCOPY = 0x00CC0020
TRANSPARENT = 1
DT_LEFT = 0x00000000
DT_CENTER = 0x00000001
DT_RIGHT = 0x00000002
DT_VCENTER = 0x00000004
DT_SINGLELINE = 0x00000020
DT_END_ELLIPSIS = 0x00008000
FW_NORMAL = 400
FW_SEMIBOLD = 600
FW_BOLD = 700
DI_NORMAL = 0x0003

WNDPROC_TYPE = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC_TYPE),
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


def _rgb(r: int, g: int, b: int) -> int:
    return r | (g << 8) | (b << 16)


def _argb(a: int, r: int, g: int, b: int) -> int:
    return ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)


# Colores GDI (texto/fondo) y ARGB GDI+ (2026 Obsidian Glass)
COL_BG = _rgb(5, 6, 10)
COL_TEXT = _rgb(248, 250, 252)
COL_MUTED = _rgb(148, 163, 184)
COL_CYAN = _rgb(34, 211, 238)
COL_RED = _rgb(244, 63, 94)

ARGB_BG = _argb(255, 5, 6, 10)
ARGB_CARD = _argb(255, 13, 16, 25)
ARGB_CARD_ACTIVE = _argb(255, 17, 25, 40)
ARGB_SUBPANEL = _argb(255, 9, 11, 18)
ARGB_BORDER = _argb(255, 32, 39, 56)
ARGB_GLASS_TOP = _argb(28, 255, 255, 255)
ARGB_CYAN = _argb(255, 34, 211, 238)
ARGB_CYAN_DIM = _argb(150, 34, 211, 238)
ARGB_TRACK = _argb(255, 32, 39, 56)
ARGB_TEXT = _argb(255, 248, 250, 252)
ARGB_MUTED = _argb(255, 148, 163, 184)
ARGB_RED = _argb(255, 244, 63, 94)
ARGB_BTN = _argb(255, 20, 24, 37)
ARGB_SCROLL_TRACK = _argb(80, 36, 44, 62)
ARGB_SCROLL_THUMB = _argb(190, 120, 140, 170)

_ACCENT_RGB = {
    "cyan": (34, 211, 238),
    "omen": (244, 63, 94),
    "violet": (168, 85, 247),
    "emerald": (16, 185, 129),
    "minimal": (226, 232, 240),
}


def _apply_dynamic_accent():
    global COL_CYAN, ARGB_CYAN, ARGB_CYAN_DIM, ARGB_CARD_ACTIVE
    key = "cyan"
    try:
        p = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub", "accent.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                key = str((json.load(f) or {}).get("accent") or "cyan").lower()
    except Exception:
        pass
    r, g, b = _ACCENT_RGB.get(key, _ACCENT_RGB["cyan"])
    COL_CYAN = _rgb(r, g, b)
    ARGB_CYAN = _argb(255, r, g, b)
    ARGB_CYAN_DIM = _argb(145, r, g, b)
    ARGB_CARD_ACTIVE = _argb(255, min(255, 12 + r // 11), min(255, 15 + g // 11), min(255, 24 + b // 11))
    return _argb(36, r, g, b)


def _order_cfg_path() -> str:
    d = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "audio_order.json")


def _load_device_order() -> list[str]:
    try:
        with open(_order_cfg_path(), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return [str(x) for x in raw if x]
    except Exception:
        pass
    return []


def _save_device_order(order: list[str]) -> None:
    try:
        with open(_order_cfg_path(), "w", encoding="utf-8") as f:
            json.dump(order, f)
    except Exception:
        pass


def apply_device_order(devices: list[dict], order: list[str] | None = None) -> list[dict]:
    """Ordena los dispositivos según la preferencia guardada manteniendo los nuevos al final."""
    ord_list = order if order is not None else _load_device_order()
    if not ord_list or not devices:
        return list(devices)
    pos = {did: idx for idx, did in enumerate(ord_list)}
    return sorted(devices, key=lambda d: pos.get(str(d.get("id") or ""), len(ord_list)))

_gdip_token = ctypes.c_ulonglong(0)


def _ensure_gdiplus():
    if _gdip_token.value == 0:
        inp = (ctypes.c_uint32 * 6)(1, 0, 0, 0, 0, 0)
        gdiplus.GdiplusStartup(ctypes.byref(_gdip_token), ctypes.byref(inp), None)


class AudioFlyout:
    """Ventana emergente estilo EarTrumpet junto al reloj de Windows."""

    def __init__(self, get_data_cb, set_master_cb, set_app_cb, set_default_cb, on_open_hub_cb=None, set_mic_cb=None, set_eq_cb=None):
        self.get_data_cb = get_data_cb
        self.set_master_cb = set_master_cb
        self.set_app_cb = set_app_cb
        self.set_default_cb = set_default_cb
        self.on_open_hub_cb = on_open_hub_cb
        self.set_mic_cb = set_mic_cb
        self.set_eq_cb = set_eq_cb

        self.hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._wnd_proc_ref = None
        self._devices = []
        self._mic = None
        self._peripherals = []
        self._eq = {"enabled": True, "preset": "fps"}
        self._hit_regions = []
        self._dev_rects = []
        self._scroll_y = 0
        self._content_h = 200
        self._win_w = 376
        self._win_h = 260
        self._dpi = 96
        self._dragging = None
        self._drag_dev = None
        self._anim_offsets = {}
        self._last_send_ts = 0.0
        self._last_hide_ts = 0.0
        self._last_show_ts = 0.0
        self._icon_cache = {}  # exe_path -> HICON

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        _ensure_gdiplus()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def toggle(self):
        if not self.hwnd:
            self.start()
        if not self.hwnd:
            return
        if time.monotonic() - self._last_hide_ts < 0.25:
            return
        if user32.IsWindowVisible(self.hwnd):
            self.hide()
        else:
            user32.PostMessageW(self.hwnd, WM_FLYOUT_TOGGLE, 0, 0)

    def hide(self):
        if self.hwnd and user32.IsWindowVisible(self.hwnd):
            user32.PostMessageW(self.hwnd, WM_FLYOUT_HIDE, 0, 0)

    def _s(self, px: int) -> int:
        return int(round(px * self._dpi / 96.0))

    def _run_loop(self):
        if hasattr(user32, "SetThreadDpiAwarenessContext"):
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        hinst = kernel32.GetModuleHandleW(None)
        cls_name = "VortexAudioFlyoutClass"
        self._wnd_proc_ref = WNDPROC_TYPE(self._wnd_proc)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0x0003
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, 32512)
        wc.lpszClassName = cls_name
        user32.RegisterClassExW(ctypes.byref(wc))

        self.hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            cls_name,
            "VortexCore Audio",
            WS_POPUP | WS_CLIPCHILDREN,
            0, 0, 376, 260,
            None, None, hinst, None,
        )

        if dwmapi and self.hwnd:
            try:
                pref = ctypes.c_int(2)
                dwmapi.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(pref), 4)
            except Exception:
                pass

        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _refresh_data(self):
        try:
            data = self.get_data_cb() or {}
            devs = apply_device_order(list(data.get("devices") or []))
            for d in devs:
                raw_apps = d.get("apps") or []
                seen_names = set()
                dedup = []
                for ap in raw_apps:
                    nm = str(ap.get("display_name") or ap.get("name") or "App").strip().lower()
                    if nm in seen_names:
                        continue
                    seen_names.add(nm)
                    dedup.append(ap)
                d["apps"] = dedup
            self._devices = devs
            self._mic = data.get("mic")
            self._peripherals = list(data.get("peripherals") or [])
            self._eq = dict(data.get("eq") or {"enabled": True, "preset": "fps"})
        except Exception:
            self._devices = []
            self._mic = None
            self._peripherals = []

    def _get_app_hicon(self, pid: int):
        if not pid or not psutil:
            return None
        try:
            exe = psutil.Process(int(pid)).exe()
        except Exception:
            return None
        if not exe:
            return None
        if exe in self._icon_cache:
            return self._icon_cache[exe]
        h_large = wintypes.HICON()
        h_small = wintypes.HICON()
        cnt = shell32.ExtractIconExW(exe, 0, ctypes.byref(h_large), ctypes.byref(h_small), 1)
        hicon = None
        if cnt and cnt > 0:
            if h_large.value:
                hicon = h_large
                if h_small.value:
                    user32.DestroyIcon(h_small)
            elif h_small.value:
                hicon = h_small
        self._icon_cache[exe] = hicon
        return hicon

    def _layout_and_resize(self):
        try:
            if hasattr(user32, "GetDpiForWindow"):
                d = user32.GetDpiForWindow(self.hwnd)
                if d:
                    self._dpi = d
        except Exception:
            self._dpi = 96

        s = self._s
        wa = wintypes.RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
        max_h = max(s(220), (wa.bottom - wa.top) - s(24))
        self._win_w = s(376)

        y = s(42)
        if self._mic:
            y += s(75)
        if not self._devices:
            y += s(66)
        else:
            for dev in self._devices:
                y += s(66)
                apps = dev.get("apps") or []
                if apps:
                    y += s(8) + len(apps) * s(36) + s(6)
                y += s(8)
        if self.set_eq_cb:
            y += s(38)
        if self._peripherals:
            y += s(34)
        y += s(14)
        self._content_h = y
        self._win_h = min(self._content_h, max_h)
        max_scroll = max(0, self._content_h - self._win_h)
        self._scroll_y = max(0, min(self._scroll_y, max_scroll))

        x = wa.right - self._win_w - s(12)
        top = wa.bottom - self._win_h - s(10)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, top, self._win_w, self._win_h, 0x0040)

    def _show_flyout(self):
        self._scroll_y = 0
        self._dragging = None
        self._last_show_ts = time.monotonic()
        self._refresh_data()
        self._layout_and_resize()
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        user32.InvalidateRect(self.hwnd, None, False)

    def _hide_flyout(self):
        self._dragging = None
        self._last_hide_ts = time.monotonic()
        user32.ShowWindow(self.hwnd, SW_HIDE)

    def _create_font(self, pt_px: int, weight: int = FW_NORMAL):
        return gdi32.CreateFontW(-pt_px, 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")

    def _fill_rect_gdi(self, hdc, x1, y1, x2, y2, color):
        br = gdi32.CreateSolidBrush(color)
        r = wintypes.RECT(int(x1), int(y1), int(x2), int(y2))
        user32.FillRect(hdc, ctypes.byref(r), br)
        gdi32.DeleteObject(br)

    def _gp_round_rect(self, gp, x1, y1, x2, y2, radius, fill_argb, border_argb=None, border_w=1.0):
        w = float(x2 - x1)
        h = float(y2 - y1)
        if w <= 0 or h <= 0:
            return
        d = min(float(radius) * 2.0, w, h)
        path = ctypes.c_void_p()
        gdiplus.GdipCreatePath(0, ctypes.byref(path))
        if d > 0.5:
            gdiplus.GdipAddPathArc(path, float(x1), float(y1), d, d, 180.0, 90.0)
            gdiplus.GdipAddPathArc(path, float(x2) - d, float(y1), d, d, 270.0, 90.0)
            gdiplus.GdipAddPathArc(path, float(x2) - d, float(y2) - d, d, d, 0.0, 90.0)
            gdiplus.GdipAddPathArc(path, float(x1), float(y2) - d, d, d, 90.0, 90.0)
        else:
            gdiplus.GdipAddPathLine(path, float(x1), float(y1), float(x2), float(y1))
            gdiplus.GdipAddPathLine(path, float(x2), float(y1), float(x2), float(y2))
            gdiplus.GdipAddPathLine(path, float(x2), float(y2), float(x1), float(y2))
        gdiplus.GdipClosePathFigure(path)

        if fill_argb is not None:
            br = ctypes.c_void_p()
            gdiplus.GdipCreateSolidFill(fill_argb, ctypes.byref(br))
            gdiplus.GdipFillPath(gp, br, path)
            gdiplus.GdipDeleteBrush(br)
        if border_argb is not None:
            pen = ctypes.c_void_p()
            gdiplus.GdipCreatePen1(border_argb, ctypes.c_float(border_w), 2, ctypes.byref(pen))
            gdiplus.GdipDrawPath(gp, pen, path)
            gdiplus.GdipDeletePen(pen)
        gdiplus.GdipDeletePath(path)

    def _gp_speaker_icon(self, gp, cx, cy, size, muted: bool, color_argb: int):
        """Dibuja un icono vectorial nítido de altavoz con GDI+ anti-aliased."""
        u = float(size) / 16.0
        ox = float(cx) - 8.0 * u
        oy = float(cy) - 8.0 * u

        # Cuerpo del altavoz
        path = ctypes.c_void_p()
        gdiplus.GdipCreatePath(0, ctypes.byref(path))
        pts = [
            (ox + 2.0 * u, oy + 5.8 * u),
            (ox + 5.2 * u, oy + 5.8 * u),
            (ox + 9.0 * u, oy + 2.6 * u),
            (ox + 9.0 * u, oy + 13.4 * u),
            (ox + 5.2 * u, oy + 10.2 * u),
            (ox + 2.0 * u, oy + 10.2 * u),
        ]
        for idx in range(len(pts)):
            p1 = pts[idx]
            p2 = pts[(idx + 1) % len(pts)]
            gdiplus.GdipAddPathLine(path, p1[0], p1[1], p2[0], p2[1])
        gdiplus.GdipClosePathFigure(path)

        br = ctypes.c_void_p()
        gdiplus.GdipCreateSolidFill(color_argb, ctypes.byref(br))
        gdiplus.GdipFillPath(gp, br, path)
        gdiplus.GdipDeleteBrush(br)
        gdiplus.GdipDeletePath(path)

        pen = ctypes.c_void_p()
        gdiplus.GdipCreatePen1(color_argb, ctypes.c_float(max(1.3, 1.5 * u)), 2, ctypes.byref(pen))
        if muted:
            gdiplus.GdipDrawLine(gp, pen, ox + 11.2 * u, oy + 5.5 * u, ox + 14.8 * u, oy + 10.5 * u)
            gdiplus.GdipDrawLine(gp, pen, ox + 14.8 * u, oy + 5.5 * u, ox + 11.2 * u, oy + 10.5 * u)
        else:
            gdiplus.GdipDrawArc(gp, pen, ox + 7.2 * u, oy + 4.4 * u, 5.2 * u, 7.2 * u, -52.0, 104.0)
            gdiplus.GdipDrawArc(gp, pen, ox + 7.4 * u, oy + 2.2 * u, 8.2 * u, 11.6 * u, -52.0, 104.0)
        gdiplus.GdipDeletePen(pen)

    def _gp_mic_icon(self, gp, cx, cy, size, muted: bool, color_argb: int):
        """Dibuja un icono vectorial nítido de micrófono con GDI+ anti-aliased."""
        u = float(size) / 16.0
        ox = float(cx) - 8.0 * u
        oy = float(cy) - 8.0 * u
        self._gp_round_rect(gp, ox + 5.8 * u, oy + 1.8 * u, ox + 10.2 * u, oy + 9.2 * u, 2.2 * u, color_argb)

        pen = ctypes.c_void_p()
        gdiplus.GdipCreatePen1(color_argb, ctypes.c_float(max(1.3, 1.5 * u)), 2, ctypes.byref(pen))
        gdiplus.GdipDrawArc(gp, pen, ox + 4.0 * u, oy + 4.5 * u, 8.0 * u, 6.8 * u, 0.0, 180.0)
        gdiplus.GdipDrawLine(gp, pen, ox + 8.0 * u, oy + 11.3 * u, ox + 8.0 * u, oy + 14.0 * u)
        gdiplus.GdipDrawLine(gp, pen, ox + 5.5 * u, oy + 14.0 * u, ox + 10.5 * u, oy + 14.0 * u)
        if muted:
            gdiplus.GdipDrawLine(gp, pen, ox + 2.5 * u, oy + 2.5 * u, ox + 13.5 * u, oy + 13.5 * u)
        gdiplus.GdipDeletePen(pen)

    def _gp_slider(self, gp, x1, y_mid, x2, pct, muted, max_val: int = 100):
        s = self._s
        th = max(4, s(4))
        ty1 = y_mid - th / 2.0
        ty2 = ty1 + th
        self._gp_round_rect(gp, x1, ty1, x2, ty2, th / 2.0, ARGB_TRACK)

        pct_c = max(0, min(max_val, int(pct)))
        fill_w = (x2 - x1) * pct_c / float(max(1, max_val))
        col = ARGB_MUTED if muted else ARGB_CYAN
        if fill_w > 1:
            self._gp_round_rect(gp, x1, ty1, x1 + fill_w, ty2, th / 2.0, col)

        # Marca sutil al 100% cuando el slider permite boost hasta 200%
        if max_val > 100:
            mid_x = float(x1) + (x2 - x1) * (100.0 / float(max_val))
            self._gp_round_rect(gp, mid_x - 1.0, ty1 - 2.0, mid_x + 1.0, ty2 + 2.0, 1.0, ARGB_MUTED)

        r = float(max(5, s(6)))
        cx = float(x1) + fill_w
        br = ctypes.c_void_p()
        gdiplus.GdipCreateSolidFill(ARGB_TEXT if not muted else ARGB_MUTED, ctypes.byref(br))
        gdiplus.GdipFillEllipse(gp, br, cx - r, float(y_mid) - r, r * 2.0, r * 2.0)
        gdiplus.GdipDeleteBrush(br)

        pen = ctypes.c_void_p()
        gdiplus.GdipCreatePen1(col, ctypes.c_float(1.5), 2, ctypes.byref(pen))
        gdiplus.GdipDrawEllipse(gp, pen, cx - r, float(y_mid) - r, r * 2.0, r * 2.0)
        gdiplus.GdipDeletePen(pen)

    def _draw_text(self, hdc, text, x1, y1, x2, y2, color, font, flags=DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS):
        old_f = gdi32.SelectObject(hdc, font)
        gdi32.SetTextColor(hdc, color)
        r = wintypes.RECT(int(x1), int(y1), int(x2), int(y2))
        user32.DrawTextW(hdc, str(text), -1, ctypes.byref(r), flags)
        gdi32.SelectObject(hdc, old_f)

    def _paint(self, hwnd):
        _ensure_gdiplus()
        argb_acc_soft = _apply_dynamic_accent()
        ps = PAINTSTRUCT()
        hdc_win = user32.BeginPaint(hwnd, ctypes.byref(ps))
        w, h = self._win_w, self._win_h
        hdc = gdi32.CreateCompatibleDC(hdc_win)
        bmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
        old_bmp = gdi32.SelectObject(hdc, bmp)
        gdi32.SetBkMode(hdc, TRANSPARENT)

        gp = ctypes.c_void_p()
        gdiplus.GdipCreateFromHDC(hdc, ctypes.byref(gp))
        gdiplus.GdipSetSmoothingMode(gp, 4)  # SmoothingModeAntiAlias

        s = self._s
        f_title = self._create_font(s(12), FW_BOLD)
        f_dev = self._create_font(s(13), FW_SEMIBOLD)
        f_app = self._create_font(s(12), FW_NORMAL)
        f_num = self._create_font(s(13), FW_SEMIBOLD)
        f_small = self._create_font(s(11), FW_SEMIBOLD)

        self._fill_rect_gdi(hdc, 0, 0, w, h, COL_BG)
        self._hit_regions = []
        self._dev_rects = []

        has_scroll = self._content_h > self._win_h
        right_pad = s(14) if has_scroll else s(10)
        pad = s(10)
        card_w = w - pad - right_pad
        y = s(42) - self._scroll_y

        icon_draws = []  # diferir DrawIconEx para que quede nítido sobre el subpanel

        # Tarjeta compacta de micrófono (si hay entrada de audio activa)
        if self._mic:
            mic = self._mic
            mic_h = s(66)
            mic_muted = bool(mic.get("muted"))
            self._gp_round_rect(gp, pad, y, pad + card_w, y + mic_h, s(12), ARGB_CARD, ARGB_RED if mic_muted else ARGB_BORDER, 1.0)
            self._gp_round_rect(gp, pad + s(12), y + s(1), pad + card_w - s(12), y + s(2), 0, ARGB_GLASS_TOP)
            self._draw_text(hdc, mic.get("name", "Micrófono"), pad + s(13), y + s(7), pad + card_w - s(64), y + s(29), COL_TEXT, f_dev)
            self._draw_text(hdc, "SILENCIADO" if mic_muted else "MIC", pad + card_w - s(76), y + s(7), pad + card_w - s(12), y + s(29), COL_RED if mic_muted else COL_MUTED, f_small, DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

            row_y = y + s(31)
            mx1, my1, mx2, my2 = pad + s(10), row_y + s(2), pad + s(36), row_y + s(28)
            self._gp_round_rect(gp, mx1, my1, mx2, my2, s(8), ARGB_BTN)
            self._gp_mic_icon(gp, (mx1 + mx2) / 2.0, (my1 + my2) / 2.0, s(15), mic_muted, ARGB_RED if mic_muted else ARGB_TEXT)
            self._hit_regions.append({"rect": (mx1, my1, mx2, my2), "type": "mute_mic", "device_id": mic.get("id")})

            sl_x1 = pad + s(46)
            sl_x2 = pad + card_w - s(48)
            self._gp_slider(gp, sl_x1, row_y + s(15), sl_x2, mic.get("volume", 0), mic_muted, max_val=200)
            self._hit_regions.append({
                "rect": (sl_x1 - s(6), row_y, sl_x2 + s(6), row_y + s(30)),
                "type": "slider_mic",
                "x1": sl_x1,
                "x2": sl_x2,
                "max_val": 200,
                "device_id": mic.get("id"),
            })
            self._draw_text(hdc, str(mic.get("volume", 0)), sl_x2 + s(6), row_y, pad + card_w - s(10), row_y + s(30), COL_MUTED if mic_muted else COL_TEXT, f_num, DT_RIGHT | DT_VCENTER | DT_SINGLELINE)
            y += mic_h + s(9)

        if not self._devices:
            self._draw_text(hdc, "No hay dispositivos de audio activos", pad, y + s(12), w - right_pad, y + s(44), COL_MUTED, f_app)
        else:
            drag_id = self._drag_dev.get("device_id") if (self._drag_dev and self._drag_dev.get("moved")) else None
            slots = []
            for d_idx, dev in enumerate(self._devices):
                apps = dev.get("apps") or []
                apps_h = (s(8) + len(apps) * s(36) + s(6)) if apps else 0
                card_h = s(66) + apps_h
                slots.append((d_idx, dev, y, card_h))
                self._dev_rects.append((d_idx, y, y + card_h))
                y += card_h + s(8)

            def _render_card(d_idx, dev, cy, card_h, is_drag_card=False):
                apps = dev.get("apps") or []
                is_def = bool(dev.get("is_default"))
                if is_drag_card:
                    self._gp_round_rect(gp, pad + s(2), cy + s(6), pad + card_w + s(2), cy + card_h + s(6), s(14), _argb(120, 0, 0, 0))
                border = ARGB_CYAN if is_drag_card else (ARGB_CYAN_DIM if is_def else ARGB_BORDER)
                card_bg = ARGB_CARD_ACTIVE if (is_def or is_drag_card) else ARGB_CARD
                self._gp_round_rect(gp, pad, cy, pad + card_w, cy + card_h, s(13), card_bg, border, 1.4 if is_drag_card else 1.0)
                self._gp_round_rect(gp, pad + s(12), cy + s(1), pad + card_w - s(12), cy + s(2), 0, ARGB_GLASS_TOP)

                grip_x = pad + s(13)
                grip_y = cy + s(12)
                br_g = ctypes.c_void_p()
                gdiplus.GdipCreateSolidFill(ARGB_CYAN if is_drag_card else ARGB_MUTED, ctypes.byref(br_g))
                for gr in range(3):
                    for gc in range(2):
                        gdiplus.GdipFillEllipse(
                            gp, br_g,
                            ctypes.c_float(grip_x + gc * s(4.5)),
                            ctypes.c_float(grip_y + gr * s(4.5)),
                            ctypes.c_float(s(2.2)), ctypes.c_float(s(2.2)),
                        )
                gdiplus.GdipDeleteBrush(br_g)

                name_x1 = pad + s(27)
                name_x2 = pad + card_w - (s(66) if is_def else s(14))
                self._draw_text(hdc, dev.get("name", "Audio"), name_x1, cy + s(7), name_x2, cy + s(29), COL_TEXT, f_dev)

                if is_def:
                    ax1, ay1, ax2, ay2 = pad + card_w - s(60), cy + s(9), pad + card_w - s(10), cy + s(25)
                    self._gp_round_rect(gp, ax1, ay1, ax2, ay2, s(8), argb_acc_soft, ARGB_CYAN_DIM, 1.0)
                    self._draw_text(hdc, "ACTIVO", ax1, ay1, ax2, ay2, COL_CYAN, f_small, DT_CENTER | DT_VCENTER | DT_SINGLELINE)

                if not is_drag_card:
                    self._hit_regions.append({
                        "rect": (pad, cy, pad + card_w, cy + s(29)),
                        "type": "dev_header",
                        "device_idx": d_idx,
                        "device_id": dev["id"],
                    })

                row_y = cy + s(31)
                dev_muted = bool(dev.get("muted"))
                mx1, my1, mx2, my2 = pad + s(10), row_y + s(2), pad + s(36), row_y + s(28)
                self._gp_round_rect(gp, mx1, my1, mx2, my2, s(8), ARGB_BTN)
                self._gp_speaker_icon(gp, (mx1 + mx2) / 2.0, (my1 + my2) / 2.0, s(15), dev_muted, ARGB_RED if dev_muted else ARGB_TEXT)
                if not is_drag_card:
                    self._hit_regions.append({"rect": (mx1, my1, mx2, my2), "type": "mute_master", "device_idx": d_idx, "device_id": dev["id"]})

                sl_x1 = pad + s(46)
                sl_x2 = pad + card_w - s(48)
                self._gp_slider(gp, sl_x1, row_y + s(15), sl_x2, dev.get("volume", 0), dev_muted)
                if not is_drag_card:
                    self._hit_regions.append({
                        "rect": (sl_x1 - s(6), row_y, sl_x2 + s(6), row_y + s(30)),
                        "type": "slider_master",
                        "x1": sl_x1,
                        "x2": sl_x2,
                        "device_idx": d_idx,
                        "device_id": dev["id"],
                    })
                self._draw_text(hdc, str(dev.get("volume", 0)), sl_x2 + s(6), row_y, pad + card_w - s(10), row_y + s(30), COL_TEXT, f_num, DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

                if apps:
                    sy = cy + s(64)
                    self._gp_round_rect(gp, pad + s(4), sy, pad + card_w - s(4), cy + card_h - s(4), s(9), ARGB_SUBPANEL)
                    ay = sy + s(6)
                    for a_idx, app in enumerate(apps):
                        app_muted = bool(app.get("muted"))
                        am_x1, am_y1, am_x2, am_y2 = pad + s(10), ay + s(5), pad + s(34), ay + s(29)
                        self._gp_round_rect(gp, am_x1, am_y1, am_x2, am_y2, s(6), ARGB_BTN)
                        hicon = self._get_app_hicon(app.get("pid") or 0)
                        if hicon:
                            icon_draws.append((am_x1 + s(4), am_y1 + s(4), s(16), hicon, app_muted))
                        else:
                            self._gp_speaker_icon(gp, (am_x1 + am_x2) / 2.0, (am_y1 + am_y2) / 2.0, s(14), app_muted, ARGB_RED if app_muted else ARGB_MUTED)
                        if not is_drag_card:
                            self._hit_regions.append({
                                "rect": (am_x1, am_y1, am_x2, am_y2),
                                "type": "mute_app",
                                "device_idx": d_idx,
                                "app_idx": a_idx,
                                "device_id": dev["id"],
                                "pid": app.get("pid"),
                                "name": app.get("name"),
                            })
                        app_label = app.get("display_name") or app.get("name") or "App"
                        self._draw_text(hdc, app_label, pad + s(42), ay, pad + s(164), ay + s(34), COL_TEXT if not app_muted else COL_MUTED, f_app)
                        as_x1 = pad + s(170)
                        as_x2 = pad + card_w - s(48)
                        self._gp_slider(gp, as_x1, ay + s(17), as_x2, app.get("volume", 0), app_muted)
                        if not is_drag_card:
                            self._hit_regions.append({
                                "rect": (as_x1 - s(6), ay, as_x2 + s(6), ay + s(34)),
                                "type": "slider_app",
                                "x1": as_x1,
                                "x2": as_x2,
                                "device_idx": d_idx,
                                "app_idx": a_idx,
                                "device_id": dev["id"],
                                "pid": app.get("pid"),
                                "name": app.get("name"),
                            })
                        self._draw_text(hdc, str(app.get("volume", 0)), as_x2 + s(6), ay, pad + card_w - s(10), ay + s(34), COL_MUTED if app_muted else COL_TEXT, f_num, DT_RIGHT | DT_VCENTER | DT_SINGLELINE)
                        ay += s(36)

            floating = None
            for d_idx, dev, slot_y, card_h in slots:
                if drag_id and dev.get("id") == drag_id:
                    self._gp_round_rect(gp, pad + s(2), slot_y + s(2), pad + card_w - s(2), slot_y + card_h - s(2), s(13), _argb(26, 34, 211, 238), _argb(95, 34, 211, 238), 1.0)
                    off_y = self._drag_dev["cur_y"] - self._drag_dev["anchor_y"]
                    floating = (d_idx, dev, slot_y + off_y, card_h)
                else:
                    anim_y = self._anim_offsets.get(str(dev.get("id") or ""), 0.0)
                    _render_card(d_idx, dev, slot_y + anim_y, card_h, is_drag_card=False)
            if floating:
                _render_card(*floating, is_drag_card=True)

        # Selector rápido de perfil EQ en el flyout
        if self.set_eq_cb:
            eq_presets = [("fps", "FPS"), ("bass", "Bass"), ("music", "Música"), ("movie", "Cine"), ("flat", "Plano")]
            active_p = (self._eq.get("preset") or "flat") if self._eq.get("enabled", True) else "flat"
            gap = s(6)
            pw = (card_w - gap * (len(eq_presets) - 1)) / float(len(eq_presets))
            px = float(pad)
            for key, lbl in eq_presets:
                is_act = (active_p == key)
                self._gp_round_rect(gp, px, y, px + pw, y + s(28), s(8), ARGB_CARD_ACTIVE if is_act else ARGB_BTN, ARGB_CYAN if is_act else ARGB_BORDER, 1.0)
                self._draw_text(hdc, lbl, px, y, px + pw, y + s(28), COL_CYAN if is_act else COL_MUTED, f_small, DT_CENTER | DT_VCENTER | DT_SINGLELINE)
                self._hit_regions.append({"rect": (px, y, px + pw, y + s(28)), "type": "set_eq", "preset": key})
                px += pw + gap
            y += s(36)

        # Batería de periféricos inalámbricos
        if self._peripherals:
            parts = []
            for pdev in self._peripherals[:2]:
                pname = str(pdev.get("name") or "Dispositivo").split("(")[0].strip()
                if len(pname) > 18:
                    pname = pname[:17] + "…"
                parts.append(f"{pname}: {pdev.get('percent')}%")
            bat_text = "  •  ".join(parts)
            self._gp_round_rect(gp, pad, y, pad + card_w, y + s(26), s(8), ARGB_SUBPANEL, ARGB_BORDER, 1.0)
            self._draw_text(hdc, bat_text, pad + s(10), y, pad + card_w - s(10), y + s(26), COL_TEXT, f_small, DT_CENTER | DT_VCENTER | DT_SINGLELINE)
            y += s(32)

        # Dibujar iconos reales de apps (.exe) sobre el DC
        for ix, iy, isize, hicon, is_muted in icon_draws:
            if iy + isize > s(36) and iy < h:
                user32.DrawIconEx(hdc, int(ix), int(iy), hicon, int(isize), int(isize), 0, 0, DI_NORMAL)
                if is_muted:
                    self._gp_round_rect(gp, ix + isize - s(5), iy + isize - s(5), ix + isize + s(1), iy + isize + s(1), s(3), ARGB_RED)

        # Cabecera fija superior estilo Inicio
        self._fill_rect_gdi(hdc, 0, 0, w, s(36), COL_BG)
        self._gp_round_rect(gp, 0, s(35), w, s(36), 0, ARGB_BORDER)
        self._gp_round_rect(gp, s(12), s(15), s(18), s(21), s(3), ARGB_CYAN)
        self._draw_text(hdc, "VORTEX AUDIO", s(24), 0, s(190), s(35), COL_TEXT, f_title)
        hub_x1, hub_y1, hub_x2, hub_y2 = w - s(110), s(6), w - s(10), s(29)
        self._gp_round_rect(gp, hub_x1, hub_y1, hub_x2, hub_y2, s(8), argb_acc_soft, ARGB_CYAN_DIM)
        self._draw_text(hdc, "Abrir Hub ↗", hub_x1, hub_y1, hub_x2, hub_y2, COL_CYAN, f_small, DT_CENTER | DT_VCENTER | DT_SINGLELINE)
        self._hit_regions.append({"rect": (hub_x1, hub_y1, hub_x2, hub_y2), "type": "open_hub"})

        # Barra de scroll visual a la derecha cuando hay contenido extra
        if has_scroll:
            sb_x1 = w - s(7)
            sb_x2 = w - s(3)
            sb_top = s(42)
            sb_bot = h - s(8)
            track_h = max(1, sb_bot - sb_top)
            self._gp_round_rect(gp, sb_x1, sb_top, sb_x2, sb_bot, s(2), ARGB_SCROLL_TRACK)
            thumb_h = max(s(26), int(track_h * (self._win_h / float(self._content_h))))
            max_scroll = max(1, self._content_h - self._win_h)
            thumb_y = sb_top + int((track_h - thumb_h) * (self._scroll_y / float(max_scroll)))
            self._gp_round_rect(gp, sb_x1, thumb_y, sb_x2, thumb_y + thumb_h, s(2), ARGB_SCROLL_THUMB)

        # Borde exterior sutil anti-aliased
        self._gp_round_rect(gp, 0.5, 0.5, w - 1.5, h - 1.5, s(8), None, ARGB_BORDER, 1.0)

        gdiplus.GdipDeleteGraphics(gp)
        gdi32.BitBlt(hdc_win, 0, 0, w, h, hdc, 0, 0, SRCCOPY)

        for f in (f_title, f_dev, f_app, f_num, f_small):
            gdi32.DeleteObject(f)
        gdi32.SelectObject(hdc, old_bmp)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(hdc)
        user32.EndPaint(hwnd, ctypes.byref(ps))

    def _hit_test(self, x: int, y: int):
        for reg in reversed(self._hit_regions):
            x1, y1, x2, y2 = reg["rect"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return reg
        return None

    def _apply_slider_x(self, reg: dict, x: int, force_send: bool = False):
        x1, x2 = reg["x1"], reg["x2"]
        max_val = int(reg.get("max_val", 100))
        pct = int(round(max(0.0, min(1.0, (x - x1) / max(1, x2 - x1))) * max_val))
        if reg["type"] == "slider_mic":
            if not self._mic:
                return
            self._mic["volume"] = pct
            if pct > 0 and self._mic.get("muted"):
                self._mic["muted"] = False
        else:
            d_idx = reg["device_idx"]
            if d_idx >= len(self._devices):
                return
            dev = self._devices[d_idx]
            if reg["type"] == "slider_master":
                dev["volume"] = pct
                if pct > 0 and dev.get("muted"):
                    dev["muted"] = False
            else:
                a_idx = reg["app_idx"]
                apps = dev.get("apps") or []
                if a_idx < len(apps):
                    apps[a_idx]["volume"] = pct
                    if pct > 0 and apps[a_idx].get("muted"):
                        apps[a_idx]["muted"] = False

        user32.InvalidateRect(self.hwnd, None, False)
        now = time.monotonic()
        if force_send or now - self._last_send_ts >= 0.04:
            self._last_send_ts = now
            self._dispatch_slider(reg, pct)

    def _dispatch_slider(self, reg: dict, pct: int):
        if reg["type"] == "slider_mic":
            if self.set_mic_cb:
                self.set_mic_cb(volume=pct, muted=False if pct > 0 else None, device_id=reg.get("device_id"))
        elif reg["type"] == "slider_master":
            self.set_master_cb(volume=pct, muted=False if pct > 0 else None, device_id=reg["device_id"])
        else:
            self.set_app_cb(pid=reg["pid"], name=reg["name"], volume=pct, muted=False if pct > 0 else None, device_id=reg["device_id"])

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_FLYOUT_TOGGLE:
            self._show_flyout()
            return 0
        elif msg == WM_FLYOUT_HIDE:
            self._hide_flyout()
            return 0
        elif msg == WM_ACTIVATE:
            if (wparam & 0xFFFF) == WA_INACTIVE:
                if time.monotonic() - self._last_show_ts > 0.18:
                    self._hide_flyout()
            return 0
        elif msg == WM_KEYDOWN:
            if wparam == VK_ESCAPE:
                self._hide_flyout()
            return 0
        elif msg == WM_ERASEBKGND:
            return 1
        elif msg == WM_PAINT:
            self._paint(hwnd)
            return 0
        elif msg == WM_LBUTTONDOWN:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            reg = self._hit_test(x, y)
            if not reg:
                return 0
            rtype = reg["type"]
            if rtype in ("slider_master", "slider_app", "slider_mic"):
                self._dragging = reg
                user32.SetCapture(hwnd)
                self._apply_slider_x(reg, x, force_send=True)
            elif rtype == "mute_mic":
                if self._mic and self.set_mic_cb:
                    new_m = not bool(self._mic.get("muted"))
                    self._mic["muted"] = new_m
                    self.set_mic_cb(muted=new_m, device_id=reg.get("device_id"))
                    user32.InvalidateRect(hwnd, None, False)
            elif rtype == "mute_master":
                dev = self._devices[reg["device_idx"]]
                new_m = not bool(dev.get("muted"))
                dev["muted"] = new_m
                self.set_master_cb(muted=new_m, device_id=reg["device_id"])
                user32.InvalidateRect(hwnd, None, False)
            elif rtype == "mute_app":
                app = self._devices[reg["device_idx"]]["apps"][reg["app_idx"]]
                new_m = not bool(app.get("muted"))
                app["muted"] = new_m
                self.set_app_cb(pid=reg["pid"], name=reg["name"], muted=new_m, device_id=reg["device_id"])
                user32.InvalidateRect(hwnd, None, False)
            elif rtype == "dev_header":
                self._drag_dev = {
                    "idx": reg["device_idx"],
                    "device_id": reg["device_id"],
                    "start_y": y,
                    "anchor_y": y,
                    "cur_y": y,
                    "moved": False,
                }
                user32.SetCapture(hwnd)
            elif rtype == "set_eq":
                if self.set_eq_cb:
                    self._eq = self.set_eq_cb(reg["preset"]) or {"enabled": reg["preset"] != "flat", "preset": reg["preset"]}
                    user32.InvalidateRect(hwnd, None, False)
            elif rtype == "open_hub":
                self._hide_flyout()
                if self.on_open_hub_cb:
                    threading.Thread(target=self.on_open_hub_cb, daemon=True).start()
            return 0
        elif msg == WM_MOUSEMOVE:
            if self._dragging:
                x = ctypes.c_short(lparam & 0xFFFF).value
                self._apply_slider_x(self._dragging, x, force_send=False)
            elif self._drag_dev:
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                self._drag_dev["cur_y"] = y
                if not self._drag_dev["moved"] and abs(y - self._drag_dev["start_y"]) > self._s(6):
                    self._drag_dev["moved"] = True
                if self._drag_dev["moved"]:
                    idx = self._drag_dev["idx"]
                    gap = self._s(8)
                    if idx > 0 and idx < len(self._dev_rects):
                        _, top_prev, bot_prev = self._dev_rects[idx - 1]
                        if y < bot_prev - self._s(24):
                            step = (bot_prev - top_prev) + gap
                            disp_id = str(self._devices[idx - 1].get("id") or "")
                            self._devices[idx], self._devices[idx - 1] = self._devices[idx - 1], self._devices[idx]
                            self._drag_dev["idx"] = idx - 1
                            self._drag_dev["anchor_y"] -= step
                            if disp_id:
                                self._anim_offsets[disp_id] = self._anim_offsets.get(disp_id, 0.0) + step
                                user32.SetTimer(hwnd, ANIM_TIMER_ID, 16, None)
                    elif idx < len(self._devices) - 1 and idx + 1 < len(self._dev_rects):
                        _, top_next, bot_next = self._dev_rects[idx + 1]
                        if y > top_next + self._s(24):
                            step = (bot_next - top_next) + gap
                            disp_id = str(self._devices[idx + 1].get("id") or "")
                            self._devices[idx], self._devices[idx + 1] = self._devices[idx + 1], self._devices[idx]
                            self._drag_dev["idx"] = idx + 1
                            self._drag_dev["anchor_y"] += step
                            if disp_id:
                                self._anim_offsets[disp_id] = self._anim_offsets.get(disp_id, 0.0) - step
                                user32.SetTimer(hwnd, ANIM_TIMER_ID, 16, None)
                    user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_LBUTTONUP:
            if self._dragging:
                x = ctypes.c_short(lparam & 0xFFFF).value
                self._apply_slider_x(self._dragging, x, force_send=True)
                self._dragging = None
                user32.ReleaseCapture()
            elif self._drag_dev:
                dd = self._drag_dev
                self._drag_dev = None
                user32.ReleaseCapture()
                if dd["moved"]:
                    _save_device_order([str(d.get("id") or "") for d in self._devices if d.get("id")])
                    drop_off = dd["cur_y"] - dd["anchor_y"]
                    if abs(drop_off) > 1.0 and dd.get("device_id"):
                        self._anim_offsets[str(dd["device_id"])] = drop_off
                        user32.SetTimer(hwnd, ANIM_TIMER_ID, 16, None)
                    user32.InvalidateRect(hwnd, None, False)
                else:
                    self.set_default_cb(dd["device_id"])
                    self._refresh_data()
                    self._layout_and_resize()
                    user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_TIMER:
            if wparam == ANIM_TIMER_ID:
                nxt = {}
                for k, v in self._anim_offsets.items():
                    nv = v * 0.68
                    if abs(nv) >= 0.6:
                        nxt[k] = nv
                self._anim_offsets = nxt
                if not self._anim_offsets:
                    user32.KillTimer(hwnd, ANIM_TIMER_ID)
                user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_MOUSEWHEEL:
            delta = ctypes.c_short((wparam >> 16) & 0xFFFF).value
            pt = wintypes.POINT(
                ctypes.c_short(lparam & 0xFFFF).value,
                ctypes.c_short((lparam >> 16) & 0xFFFF).value,
            )
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            reg = self._hit_test(pt.x, pt.y)
            if reg and reg["type"] in ("slider_master", "slider_app", "slider_mic"):
                step = 2 if delta > 0 else -2
                if reg["type"] == "slider_mic":
                    if self._mic and self.set_mic_cb:
                        pct = max(0, min(200, int(self._mic.get("volume", 0)) + (5 if delta > 0 else -5)))
                        self._mic["volume"] = pct
                        self.set_mic_cb(volume=pct, device_id=reg.get("device_id"))
                elif reg["type"] == "slider_master":
                    dev = self._devices[reg["device_idx"]]
                    pct = max(0, min(100, int(dev.get("volume", 0)) + step))
                    dev["volume"] = pct
                    self.set_master_cb(volume=pct, device_id=reg["device_id"])
                else:
                    app = self._devices[reg["device_idx"]]["apps"][reg["app_idx"]]
                    pct = max(0, min(100, int(app.get("volume", 0)) + step))
                    app["volume"] = pct
                    self.set_app_cb(pid=reg["pid"], name=reg["name"], volume=pct, device_id=reg["device_id"])
                user32.InvalidateRect(hwnd, None, False)
            else:
                max_scroll = max(0, self._content_h - self._win_h)
                if max_scroll > 0:
                    self._scroll_y = max(0, min(max_scroll, self._scroll_y - (self._s(36) if delta > 0 else -self._s(36))))
                    user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
