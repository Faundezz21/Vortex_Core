"""
Menú contextual GDI+ estilo Obsidian Glass 2026 para el icono de la bandeja de VortexCore Hub.
Reemplaza el menú nativo gris de Windows por tarjetas y píldoras interactivas de 1 clic.
"""

import ctypes
from ctypes import wintypes
import json
import os
import threading
import time

user32 = ctypes.WinDLL("user32")
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32")
gdiplus = ctypes.WinDLL("gdiplus")
try:
    dwmapi = ctypes.windll.dwmapi
except Exception:
    dwmapi = None

kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT), wintypes.BOOL]
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT]
user32.BeginPaint.restype = wintypes.HDC
user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.EndPaint.argtypes = [wintypes.HWND, ctypes.c_void_p]

gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateFontW.restype = wintypes.HFONT
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]

gdiplus.GdipCreateFromHDC.argtypes = [wintypes.HDC, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
gdiplus.GdipSetSmoothingMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipCreatePath.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeletePath.argtypes = [ctypes.c_void_p]
gdiplus.GdipClosePathFigure.argtypes = [ctypes.c_void_p]
gdiplus.GdipAddPathLine.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipAddPathArc.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipCreateSolidFill.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeleteBrush.argtypes = [ctypes.c_void_p]
gdiplus.GdipFillPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
gdiplus.GdipCreatePen1.argtypes = [ctypes.c_uint32, ctypes.c_float, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeletePen.argtypes = [ctypes.c_void_p]
gdiplus.GdipDrawPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

WS_POPUP = 0x80000000
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
WM_APP = 0x8000
WM_MENU_SHOW = WM_APP + 20
WA_INACTIVE = 0
VK_ESCAPE = 0x1B
SPI_GETWORKAREA = 0x0030
HWND_TOPMOST = -1
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

WNDPROC_TYPE = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC_TYPE),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC), ("fErase", wintypes.BOOL), ("rcPaint", wintypes.RECT),
        ("fRestore", wintypes.BOOL), ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32),
    ]


def _rgb(r: int, g: int, b: int) -> int:
    return r | (g << 8) | (b << 16)


def _argb(a: int, r: int, g: int, b: int) -> int:
    return ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)


COL_BG = _rgb(5, 6, 10)
COL_TEXT = _rgb(248, 250, 252)
COL_MUTED = _rgb(148, 163, 184)
COL_CYAN = _rgb(34, 211, 238)
COL_GREEN = _rgb(16, 185, 129)
COL_AMBER = _rgb(245, 158, 11)
COL_RED = _rgb(244, 63, 94)

ARGB_CARD = _argb(255, 13, 16, 25)
ARGB_CARD_ACTIVE = _argb(255, 17, 30, 46)
ARGB_BTN = _argb(255, 20, 24, 37)
ARGB_BTN_HOVER = _argb(255, 30, 37, 56)
ARGB_BORDER = _argb(255, 32, 39, 56)
ARGB_GLASS_TOP = _argb(26, 255, 255, 255)
ARGB_CYAN = _argb(255, 34, 211, 238)
ARGB_CYAN_DIM = _argb(140, 34, 211, 238)
ARGB_GREEN = _argb(255, 16, 185, 129)
ARGB_RED_BG = _argb(42, 244, 63, 94)
ARGB_RED_BD = _argb(140, 244, 63, 94)

_ACCENT_RGB = {
    "cyan": (34, 211, 238),
    "omen": (244, 63, 94),
    "violet": (168, 85, 247),
    "emerald": (16, 185, 129),
    "minimal": (226, 232, 240),
}


def _load_accent_palette():
    key = "cyan"
    try:
        p = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub", "accent.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                key = str((json.load(f) or {}).get("accent") or "cyan").lower()
    except Exception:
        pass
    r, g, b = _ACCENT_RGB.get(key, _ACCENT_RGB["cyan"])
    return {
        "col": _rgb(r, g, b),
        "argb": _argb(255, r, g, b),
        "dim": _argb(145, r, g, b),
        "soft": _argb(36, r, g, b),
        "card_active": _argb(255, min(255, 12 + r // 11), min(255, 15 + g // 11), min(255, 24 + b // 11)),
    }

_gdip_token = ctypes.c_ulonglong(0)


def _ensure_gdiplus():
    if _gdip_token.value == 0:
        inp = (ctypes.c_uint32 * 6)(1, 0, 0, 0, 0, 0)
        gdiplus.GdiplusStartup(ctypes.byref(_gdip_token), ctypes.byref(inp), None)


class TrayPopupMenu:
    """Menú rápido Obsidian Glass 2026 junto al icono de la bandeja."""

    def __init__(self, get_state_cb, on_action_cb):
        self.get_state_cb = get_state_cb
        self.on_action_cb = on_action_cb
        self.hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._wnd_proc_ref = None
        self._state = {}
        self._hit_regions = []
        self._hover_idx = -1
        self._win_w = 312
        self._win_h = 380
        self._dpi = 96
        self._last_show_ts = 0.0

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def show(self):
        self.start()
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_MENU_SHOW, 0, 0)

    def _s(self, px: float) -> int:
        return int(round(px * (self._dpi / 96.0)))

    def _run(self):
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass
        hinst = kernel32.GetModuleHandleW(None)
        cls_name = "VortexTrayMenu2026"
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
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW, cls_name, "VortexCore Menu", WS_POPUP,
            0, 0, 312, 380, None, None, hinst, None,
        )
        if self.hwnd and dwmapi:
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

    def _refresh_and_position(self):
        try:
            self._dpi = user32.GetDpiForWindow(self.hwnd) or 96
        except Exception:
            self._dpi = 96
        try:
            self._state = self.get_state_cb() or {}
        except Exception:
            self._state = {}
        s = self._s
        h = s(12) + s(24) + s(8) + s(32) + s(10)  # Header + Abrir Hub
        h += s(62) + s(8)  # Tarjeta Energía
        h += s(62) + s(8)  # Tarjeta Ventiladores
        h += s(104) + s(8)  # Tarjeta Switches (3 filas)
        h += s(32) + s(6) + s(30) + s(12)  # Liberar RAM + Salir

        self._win_w = s(316)
        self._win_h = h
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        wa = wintypes.RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
        x = max(wa.left + s(8), min(pt.x - self._win_w // 2, wa.right - self._win_w - s(8)))
        y = max(wa.top + s(8), min(pt.y - self._win_h - s(8), wa.bottom - self._win_h - s(8)))
        self._last_show_ts = time.monotonic()
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, int(x), int(y), self._win_w, self._win_h, 0x0040)
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        user32.InvalidateRect(self.hwnd, None, False)

    def _gp_round_rect(self, gp, x1, y1, x2, y2, r, fill_argb=None, border_argb=None, bw=1.0):
        cf = ctypes.c_float
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        d = max(1.0, float(r) * 2.0)
        path = ctypes.c_void_p()
        gdiplus.GdipCreatePath(0, ctypes.byref(path))
        if r <= 0:
            gdiplus.GdipAddPathLine(path, cf(x1), cf(y1), cf(x2), cf(y1))
            gdiplus.GdipAddPathLine(path, cf(x2), cf(y1), cf(x2), cf(y2))
            gdiplus.GdipAddPathLine(path, cf(x2), cf(y2), cf(x1), cf(y2))
        else:
            gdiplus.GdipAddPathArc(path, cf(x1), cf(y1), cf(d), cf(d), cf(180.0), cf(90.0))
            gdiplus.GdipAddPathArc(path, cf(x2 - d), cf(y1), cf(d), cf(d), cf(270.0), cf(90.0))
            gdiplus.GdipAddPathArc(path, cf(x2 - d), cf(y2 - d), cf(d), cf(d), cf(0.0), cf(90.0))
            gdiplus.GdipAddPathArc(path, cf(x1), cf(y2 - d), cf(d), cf(d), cf(90.0), cf(90.0))
        gdiplus.GdipClosePathFigure(path)
        if fill_argb is not None:
            br = ctypes.c_void_p()
            gdiplus.GdipCreateSolidFill(ctypes.c_uint32(fill_argb), ctypes.byref(br))
            gdiplus.GdipFillPath(gp, br, path)
            gdiplus.GdipDeleteBrush(br)
        if border_argb is not None:
            pen = ctypes.c_void_p()
            gdiplus.GdipCreatePen1(ctypes.c_uint32(border_argb), cf(bw), 2, ctypes.byref(pen))
            gdiplus.GdipDrawPath(gp, pen, path)
            gdiplus.GdipDeletePen(pen)
        gdiplus.GdipDeletePath(path)

    def _create_font(self, px, weight=FW_NORMAL):
        return gdi32.CreateFontW(-int(px), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")

    def _draw_text(self, hdc, text, x1, y1, x2, y2, color, font, flags=DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS):
        old_f = gdi32.SelectObject(hdc, font)
        gdi32.SetTextColor(hdc, color)
        r = wintypes.RECT(int(x1), int(y1), int(x2), int(y2))
        user32.DrawTextW(hdc, str(text), -1, ctypes.byref(r), flags)
        gdi32.SelectObject(hdc, old_f)

    def _paint(self, hwnd):
        _ensure_gdiplus()
        ps = PAINTSTRUCT()
        hdc_win = user32.BeginPaint(hwnd, ctypes.byref(ps))
        w, h = self._win_w, self._win_h
        hdc = gdi32.CreateCompatibleDC(hdc_win)
        bmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
        old_bmp = gdi32.SelectObject(hdc, bmp)
        gdi32.SetBkMode(hdc, TRANSPARENT)

        gp = ctypes.c_void_p()
        gdiplus.GdipCreateFromHDC(hdc, ctypes.byref(gp))
        gdiplus.GdipSetSmoothingMode(gp, 4)

        s = self._s
        f_title = self._create_font(s(12), FW_BOLD)
        f_sec = self._create_font(s(10), FW_BOLD)
        f_item = self._create_font(s(12), FW_SEMIBOLD)
        f_pill = self._create_font(s(11), FW_SEMIBOLD)

        br = gdi32.CreateSolidBrush(COL_BG)
        rect = wintypes.RECT(0, 0, w, h)
        user32.FillRect(hdc, ctypes.byref(rect), br)
        gdi32.DeleteObject(br)
        self._gp_round_rect(gp, 0, 0, w - 1, h - 1, s(12), None, ARGB_BORDER, 1.0)

        self._hit_regions = []
        pal = _load_accent_palette()
        col_acc = pal["col"]
        argb_acc = pal["argb"]
        argb_acc_dim = pal["dim"]
        argb_acc_soft = pal["soft"]
        argb_card_act = pal["card_active"]

        pad = s(12)
        cw = w - pad * 2
        y = s(12)

        def _add_btn(x1, y1, x2, y2, r, text, act, payload=None, active=False, danger=False):
            idx = len(self._hit_regions)
            hov = (idx == self._hover_idx)
            if danger:
                bg = ARGB_RED_BG if hov else ARGB_CARD
                bd = ARGB_RED_BD if hov else ARGB_BORDER
                fg = COL_RED if hov else COL_MUTED
            elif active:
                bg = argb_card_act
                bd = argb_acc
                fg = col_acc
            else:
                bg = ARGB_BTN_HOVER if hov else ARGB_BTN
                bd = argb_acc_dim if hov else ARGB_BORDER
                fg = COL_TEXT
            self._gp_round_rect(gp, x1, y1, x2, y2, r, bg, bd, 1.0)
            self._draw_text(hdc, text, x1 + s(3), y1, x2 - s(3), y2, fg, f_pill, DT_CENTER | DT_VCENTER | DT_SINGLELINE)
            self._hit_regions.append({"rect": (x1, y1, x2, y2), "action": act, "payload": payload})

        # 1. Cabecera estilo Inicio: Marca + Punto En vivo + Pastilla térmica CPU/GPU
        self._gp_round_rect(gp, pad + s(2), y + s(8), pad + s(9), y + s(15), s(3.5), ARGB_GREEN)
        self._draw_text(hdc, "VORTEXCORE", pad + s(14), y, pad + s(130), y + s(22), COL_TEXT, f_title)

        ct = self._state.get("cpu_temp")
        gt = self._state.get("gpu_temp")
        peak = max(int(ct or 0), int(gt or 0))
        t_col = COL_RED if peak >= 85 else (COL_AMBER if peak >= 70 else col_acc)
        temp_str = f"CPU {ct or '--'}° · GPU {gt or '--'}°"
        tw = s(122)
        self._gp_round_rect(gp, pad + cw - tw, y, pad + cw, y + s(23), s(7), ARGB_CARD, ARGB_BORDER, 1.0)
        self._draw_text(hdc, temp_str, pad + cw - tw + s(4), y, pad + cw - s(4), y + s(23), t_col, f_sec, DT_CENTER | DT_VCENTER | DT_SINGLELINE)
        y += s(31)

        # Botón Abrir Hub ancho completo
        _add_btn(pad, y, pad + cw, y + s(32), s(9), "Abrir VortexCore Hub  ↗", "open_hub", active=True)
        self._gp_round_rect(gp, pad + s(10), y + s(1), pad + cw - s(10), y + s(2), 0, ARGB_GLASS_TOP)
        y += s(42)

        # 2. Tarjeta Bento: Modo de energía
        self._gp_round_rect(gp, pad, y, pad + cw, y + s(62), s(11), ARGB_CARD, ARGB_BORDER, 1.0)
        self._gp_round_rect(gp, pad + s(10), y + s(1), pad + cw - s(10), y + s(2), 0, ARGB_GLASS_TOP)
        self._draw_text(hdc, "MODO DE ENERGÍA", pad + s(10), y + s(5), pad + cw - s(10), y + s(21), COL_MUTED, f_sec)
        prof = str(self._state.get("profile", "SILENT")).upper()
        modes = [("ECO", "Silencioso"), ("SILENT", "Equilibrado"), ("PERFORMANCE", "Rendimiento")]
        in_pad = pad + s(8)
        in_w = cw - s(16)
        pw = (in_w - s(10)) / 3.0
        for i, (k, lbl) in enumerate(modes):
            px = in_pad + i * (pw + s(5))
            act = (k == "SILENT" and prof in ("SILENT", "DEFAULT", "BALANCED")) or (prof == k)
            _add_btn(px, y + s(24), px + pw, y + s(54), s(8), lbl, "set_profile", k, active=act)
        y += s(70)

        # 3. Tarjeta Bento: Ventiladores
        self._gp_round_rect(gp, pad, y, pad + cw, y + s(62), s(11), ARGB_CARD, ARGB_BORDER, 1.0)
        self._gp_round_rect(gp, pad + s(10), y + s(1), pad + cw - s(10), y + s(2), 0, ARGB_GLASS_TOP)
        self._draw_text(hdc, "REFRIGERACIÓN", pad + s(10), y + s(5), pad + cw - s(10), y + s(21), COL_MUTED, f_sec)
        is_turbo = bool(self._state.get("fan_turbo"))
        fw = (in_w - s(6)) / 2.0
        _add_btn(in_pad, y + s(24), in_pad + fw, y + s(54), s(8), "Automático", "set_fan", "auto", active=not is_turbo)
        _add_btn(in_pad + fw + s(6), y + s(24), in_pad + in_w, y + s(54), s(8), "Máximo (100%)", "set_fan", "max", active=is_turbo)
        y += s(70)

        # 4. Tarjeta Bento: Switches rápidos
        self._gp_round_rect(gp, pad, y, pad + cw, y + s(104), s(11), ARGB_CARD, ARGB_BORDER, 1.0)
        self._gp_round_rect(gp, pad + s(10), y + s(1), pad + cw - s(10), y + s(2), 0, ARGB_GLASS_TOP)
        ry = y + s(6)

        def _add_switch_row(label, act, toggle, is_last=False):
            nonlocal ry
            idx = len(self._hit_regions)
            hov = (idx == self._hover_idx)
            if hov:
                self._gp_round_rect(gp, pad + s(4), ry, pad + cw - s(4), ry + s(30), s(7), ARGB_BTN_HOVER)
            self._draw_text(hdc, label, pad + s(12), ry, pad + cw - s(52), ry + s(30), COL_TEXT, f_item)
            sw_x1, sw_y1, sw_x2, sw_y2 = pad + cw - s(44), ry + s(7), pad + cw - s(12), ry + s(23)
            self._gp_round_rect(gp, sw_x1, sw_y1, sw_x2, sw_y2, s(8), argb_acc_soft if toggle else ARGB_BTN, argb_acc if toggle else ARGB_BORDER, 1.0)
            dot_x = sw_x2 - s(13) if toggle else sw_x1 + s(3)
            self._gp_round_rect(gp, dot_x, sw_y1 + s(3), dot_x + s(10), sw_y1 + s(13), s(5), argb_acc if toggle else _argb(255, 100, 116, 139))
            self._hit_regions.append({"rect": (pad + s(4), ry, pad + cw - s(4), ry + s(30)), "action": act, "payload": None})
            ry += s(31)
            if not is_last:
                self._gp_round_rect(gp, pad + s(12), ry, pad + cw - s(12), ry + s(1), 0, ARGB_BORDER)

        _add_switch_row("Overlay en juego", "toggle_overlay", bool(self._state.get("overlay_enabled")))
        _add_switch_row("Modo Juego automático", "toggle_gamemode", bool(self._state.get("gamemode_enabled")))
        _add_switch_row("Temperatura en bandeja", "toggle_temp_icon", bool(self._state.get("temp_icon")), is_last=True)
        y += s(112)

        # 5. Botones de acción inferiores (Liberar RAM + Salir)
        _add_btn(pad, y, pad + cw, y + s(32), s(9), "Liberar memoria RAM", "clean_ram")
        y += s(38)
        _add_btn(pad, y, pad + cw, y + s(30), s(9), "Salir de VortexCore", "exit_app", danger=True)

        gdiplus.GdipDeleteGraphics(gp)
        for f in (f_title, f_sec, f_item, f_pill):
            gdi32.DeleteObject(f)
        gdi32.BitBlt(hdc_win, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)
        gdi32.SelectObject(hdc, old_bmp)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(hdc)
        user32.EndPaint(hwnd, ctypes.byref(ps))

    def _hit_test(self, x, y):
        for i, r in enumerate(self._hit_regions):
            x1, y1, x2, y2 = r["rect"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return i, r
        return -1, None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_MENU_SHOW:
            self._refresh_and_position()
            return 0
        elif msg == WM_ACTIVATE:
            if (wparam & 0xFFFF) == WA_INACTIVE:
                if time.monotonic() - self._last_show_ts > 0.18:
                    user32.ShowWindow(hwnd, SW_HIDE)
            return 0
        elif msg == WM_KEYDOWN and wparam == VK_ESCAPE:
            user32.ShowWindow(hwnd, SW_HIDE)
            return 0
        elif msg == WM_ERASEBKGND:
            return 1
        elif msg == WM_PAINT:
            self._paint(hwnd)
            return 0
        elif msg == WM_MOUSEMOVE:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            idx, _ = self._hit_test(x, y)
            if idx != self._hover_idx:
                self._hover_idx = idx
                user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_LBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            _, reg = self._hit_test(x, y)
            user32.ShowWindow(hwnd, SW_HIDE)
            if reg and self.on_action_cb:
                self.on_action_cb(reg["action"], reg.get("payload"))
            return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
