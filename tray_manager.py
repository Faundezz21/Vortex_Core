"""
================================================================================
  VortexCore Hub // Tray Manager & Windows Autostart
  - Icono nativo en la Bandeja del Sistema (System Tray / junto al reloj)
  - Menú contextual rápido para conmutar perfiles y turbina
  - Gestión de Auto-Inicio con Windows (Startup Folder)
  - Desarrollado por Faundezz21
================================================================================
"""

import json
import os
import sys
import ctypes
import subprocess
import tempfile
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32

# Definición precisa de tipos Win64 para evitar desbordamientos y fallos en WNDPROC
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_longlong

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL

user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, wintypes.LPCVOID
]
user32.TrackPopupMenu.restype = wintypes.BOOL

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL

# Handles de 64 bits: sin restype explícito ctypes los trunca a int de 32 bits
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.RegisterClassExW.restype = wintypes.ATOM
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

# Habilitar soporte de Modo Oscuro nativo de Windows 11 (uxtheme)
try:
    uxtheme = ctypes.windll.uxtheme
    fn_set_app_mode = ctypes.cast(uxtheme[135], ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int))
    fn_set_app_mode(2)  # 2 = ForceDark
    fn_flush_themes = ctypes.cast(uxtheme[136], ctypes.WINFUNCTYPE(None))
    fn_flush_themes()
except Exception:
    uxtheme = None

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
NIF_INFO = 16

NIIF_INFO = 1
NIIF_WARNING = 2

WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
NIN_BALLOONUSERCLICK = WM_USER + 5

TPM_BOTTOMALIGN = 0x0020
TPM_RIGHTALIGN = 0x0008

MF_STRING = 0x0000
MF_POPUP = 0x0010
MF_SEPARATOR = 0x0800
MF_CHECKED = 0x0008
MF_UNCHECKED = 0x0000

# IDs de menú
CMD_OPEN = 1001
CMD_ECO = 1002
CMD_BALANCED = 1003
CMD_TURBO = 1004
CMD_FAN_MAX = 1005
CMD_FAN_AUTO = 1006
CMD_PURGE_RAM = 1007
CMD_AUTOSTART = 1008
CMD_EXIT = 1009
CMD_TEMP_ICON = 1010
CMD_AUDIO_BASE = 2000
CMD_HZ_BASE = 2100

try:
    import audio_devices
except Exception:
    audio_devices = None

try:
    import display_manager
except Exception:
    display_manager = None

try:
    import tray_menu
except Exception:
    tray_menu = None

# Ubicaciones antiguas de auto-inicio (versiones <= 7.8.6). Se migran a la tarea programada.
STARTUP_FILE = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VortexCoreHub.vbs")
LEGACY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LEGACY_RUN_VALUE = "VortexCoreHub"

# Auto-inicio real: tarea programada "Al iniciar sesión" con privilegios más altos.
# (Una app que requiere Administrador lanzada desde Run/Inicio muestra UAC en cada arranque
#  o Windows directamente la bloquea; la tarea programada evita ambos problemas.)
TASK_NAME = "VortexCoreHub"
CREATE_NO_WINDOW = 0x08000000


def get_app_dir() -> str:
    """Retorna el directorio base de la aplicación (compatible con PyInstaller y script estándar)."""
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _launch_command() -> tuple:
    """(ejecutable, argumentos) para arrancar VortexCore Hub minimizado en la bandeja."""
    if getattr(sys, 'frozen', False):
        return sys.executable, "--minimized"
    script_path = os.path.abspath(os.path.join(get_app_dir(), "vortex_engine.py"))
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = sys.executable
    return pythonw, f'"{script_path}" --minimized'


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))


def _task_xml() -> str:
    exe, args = _launch_command()
    workdir = os.path.dirname(exe) if getattr(sys, 'frozen', False) else get_app_dir()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>Faundezz21</Author>
    <Description>Inicia VortexCore Hub en la bandeja del sistema al iniciar sesion.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT10S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml_escape(exe)}</Command>
      <Arguments>{_xml_escape(args)}</Arguments>
      <WorkingDirectory>{_xml_escape(workdir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(args: list) -> bool:
    try:
        res = subprocess.run(["schtasks"] + args, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW, timeout=15)
        return res.returncode == 0
    except Exception:
        return False


def _remove_legacy_autostart():
    try:
        if os.path.isfile(STARTUP_FILE):
            os.remove(STARTUP_FILE)
    except Exception:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LEGACY_RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, LEGACY_RUN_VALUE)
    except Exception:
        pass


def is_autostart_enabled() -> bool:
    return _schtasks(["/Query", "/TN", TASK_NAME])


def set_autostart(enable: bool) -> bool:
    """Activa/desactiva el auto-inicio. Requiere privilegios de Administrador (la app ya los tiene)."""
    _remove_legacy_autostart()
    if not enable:
        if not is_autostart_enabled():
            return True
        return _schtasks(["/Delete", "/TN", TASK_NAME, "/F"])

    xml_path = os.path.join(tempfile.gettempdir(), f"vortexcore_task_{os.getpid()}.xml")
    try:
        with open(xml_path, "w", encoding="utf-16") as f:
            f.write(_task_xml())
        return _schtasks(["/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"])
    except Exception:
        return False
    finally:
        try:
            os.remove(xml_path)
        except Exception:
            pass


def migrate_legacy_autostart():
    """Si una versión anterior dejó el auto-inicio en Run/Inicio, lo convierte en tarea programada."""
    legacy = os.path.isfile(STARTUP_FILE)
    if not legacy:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LEGACY_RUN_KEY, 0, winreg.KEY_READ) as k:
                winreg.QueryValueEx(k, LEGACY_RUN_VALUE)
                legacy = True
        except Exception:
            pass
    if legacy:
        set_autostart(True)


class GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', wintypes.DWORD),
        ('Data2', wintypes.WORD),
        ('Data3', wintypes.WORD),
        ('Data4', ctypes.c_byte * 8)
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('hWnd', wintypes.HWND),
        ('uID', wintypes.UINT),
        ('uFlags', wintypes.UINT),
        ('uCallbackMessage', wintypes.UINT),
        ('hIcon', wintypes.HICON),
        ('szTip', ctypes.c_wchar * 128),
        ('dwState', wintypes.DWORD),
        ('dwStateMask', wintypes.DWORD),
        ('szInfo', ctypes.c_wchar * 256),
        ('uTimeoutOrVersion', wintypes.UINT),
        ('szInfoTitle', ctypes.c_wchar * 64),
        ('dwInfoFlags', wintypes.DWORD),
        ('guidItem', GUID),
        ('hBalloonIcon', wintypes.HICON)
    ]


def tray_config_path() -> str:
    return os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "VortexCoreHub",
        "tray.json",
    )


def load_tray_config() -> dict:
    cfg = {"temp_icon": False}
    try:
        with open(tray_config_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "temp_icon" in data:
            cfg["temp_icon"] = bool(data["temp_icon"])
    except (OSError, ValueError):
        pass
    return cfg


def save_tray_config(cfg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(tray_config_path()), exist_ok=True)
        with open(tray_config_path(), "w", encoding="utf-8") as f:
            json.dump({"temp_icon": bool(cfg.get("temp_icon", False))}, f, indent=2)
    except OSError:
        pass


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def _create_temp_hicon(temp_c: float, size: int = 16) -> int:
    """Dibuja la temperatura de CPU en un HICON GDI nativo para la bandeja."""
    try:
        val = max(0, min(99, int(round(float(temp_c)))))
        text = str(val)
    except (TypeError, ValueError):
        val = 0
        text = "--"

    # COLORREF es 0x00BBGGRR
    if val >= 82:
        bg_color, border_color = 0x001B1B6B, 0x004444EF
    elif val >= 65:
        bg_color, border_color = 0x000B3B5C, 0x000B9EF5
    else:
        bg_color, border_color = 0x0033240D, 0x00FFCC00

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32

    bits = ctypes.c_void_p()
    hbm_color = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    hbm_mask = gdi32.CreateBitmap(size, size, 1, 1, None)
    if not hbm_color or not hbm_mask:
        if hbm_color:
            gdi32.DeleteObject(hbm_color)
        if hbm_mask:
            gdi32.DeleteObject(hbm_mask)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        return 0

    old_bmp = gdi32.SelectObject(hdc_mem, hbm_color)
    brush = gdi32.CreateSolidBrush(bg_color)
    pen = gdi32.CreatePen(0, 1, border_color)
    old_brush = gdi32.SelectObject(hdc_mem, brush)
    old_pen = gdi32.SelectObject(hdc_mem, pen)

    radius = max(3, size // 4)
    gdi32.RoundRect(hdc_mem, 0, 0, size, size, radius, radius)

    font_h = -int(size * 0.72)
    hfont = gdi32.CreateFontW(
        font_h, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 4, 0, "Segoe UI"
    )
    old_font = gdi32.SelectObject(hdc_mem, hfont)
    gdi32.SetBkMode(hdc_mem, 1)  # TRANSPARENT
    gdi32.SetTextColor(hdc_mem, 0x00FFFFFF)
    rc = wintypes.RECT(0, 0, size, size)
    user32.DrawTextW(hdc_mem, text, -1, ctypes.byref(rc), 0x00000025)  # DT_CENTER | DT_VCENTER | DT_SINGLELINE

    # Forzar alfa opaco (0xFF) en todos los píxeles del DIB 32bpp
    if bits.value:
        buf_type = ctypes.c_uint32 * (size * size)
        px = buf_type.from_address(bits.value)
        for i in range(size * size):
            px[i] |= 0xFF000000

    gdi32.SelectObject(hdc_mem, old_font)
    gdi32.SelectObject(hdc_mem, old_pen)
    gdi32.SelectObject(hdc_mem, old_brush)
    gdi32.SelectObject(hdc_mem, old_bmp)

    ii = _ICONINFO()
    ii.fIcon = True
    ii.hbmMask = hbm_mask
    ii.hbmColor = hbm_color
    hicon = user32.CreateIconIndirect(ctypes.byref(ii))

    gdi32.DeleteObject(hfont)
    gdi32.DeleteObject(pen)
    gdi32.DeleteObject(brush)
    gdi32.DeleteObject(hbm_color)
    gdi32.DeleteObject(hbm_mask)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)
    return hicon


class SystemTrayApp:
    def __init__(self, manager, on_open_callback, on_exit_callback, on_flyout_callback=None):
        self.manager = manager
        self.on_open = on_open_callback
        self.on_exit = on_exit_callback
        self.on_flyout = on_flyout_callback
        self.hwnd = None
        self.nid = None
        self._pending_notice = None
        self._base_hicon = 0
        self._dyn_hicon = 0
        self._icon_size = user32.GetSystemMetrics(49) or 16
        self._last_drawn = None
        self.temp_icon_enabled = load_tray_config()["temp_icon"]
        self._tray_menu = tray_menu.TrayPopupMenu(self._get_menu_state, self._handle_menu_action) if tray_menu else None

    def set_temp_icon(self, enabled: bool) -> None:
        self.temp_icon_enabled = bool(enabled)
        save_tray_config({"temp_icon": self.temp_icon_enabled})
        self._last_drawn = None
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_TIMER, 1, 0)

    def _update_tray_visual(self) -> None:
        if not self.nid:
            return
        tel = getattr(self.manager, "telemetry", {}) or {}
        cpu_t = tel.get("cpu_temp")
        gpu_t = tel.get("gpu_temp")

        tip = "VortexCore Hub"
        if isinstance(cpu_t, (int, float)) and cpu_t > 0:
            tip += f" — CPU {int(round(cpu_t))}°C"
        if isinstance(gpu_t, (int, float)) and gpu_t > 0:
            tip += f" | GPU {int(round(gpu_t))}°C"
        self.nid.szTip = tip[:127]

        new_hicon = None
        if self.temp_icon_enabled and isinstance(cpu_t, (int, float)) and cpu_t > 0:
            rounded = int(round(cpu_t))
            bucket = (rounded, "r" if rounded >= 82 else "a" if rounded >= 65 else "c")
            if bucket != self._last_drawn:
                created = _create_temp_hicon(rounded, self._icon_size)
                if created:
                    new_hicon = created
                    self._last_drawn = bucket
        elif self._dyn_hicon:
            new_hicon = self._base_hicon
            self._last_drawn = None

        if new_hicon:
            self.nid.hIcon = new_hicon
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

        if new_hicon:
            if self._dyn_hicon and self._dyn_hicon != new_hicon:
                user32.DestroyIcon(self._dyn_hicon)
            self._dyn_hicon = new_hicon if new_hicon != self._base_hicon else 0

    # muestra una notificacion de windows desde el icono de la bandeja
    def notify(self, title: str, message: str):
        if not self.nid:
            self._pending_notice = (title, message)
            return
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
        self.nid.szInfoTitle = title[:63]
        self.nid.szInfo = message[:255]
        self.nid.dwInfoFlags = NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP

    def run(self):
        # Registrar ventana oculta para recibir mensajes de la bandeja (Win64 LRESULT)
        wndproc = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)(self._wnd_proc)
        self._wndproc = wndproc

        hinstance = kernel32.GetModuleHandleW(None)
        class_name = "VCH_TrayMsgClass"

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.UINT),
                ('style', wintypes.UINT),
                ('lpfnWndProc', ctypes.c_void_p),
                ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HINSTANCE),
                ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HANDLE),
                ('hbrBackground', wintypes.HBRUSH),
                ('lpszMenuName', wintypes.LPCWSTR),
                ('lpszClassName', wintypes.LPCWSTR),
                ('hIconSm', wintypes.HICON)
            ]

        # Cargar icono personalizado de VortexCore Hub
        icon_path = os.path.abspath(os.path.join(get_app_dir(), "vortex_icon.ico"))
        hicon = 0
        if os.path.isfile(icon_path):
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.LoadImageW.restype = wintypes.HANDLE
            # Tamaño de icono pequeño del sistema (16/20/24 px según DPI): el .ico trae esas
            # versiones dibujadas a medida, así la bandeja no reduce el de 32 px y se ve nítido
            sm_cx = user32.GetSystemMetrics(49) or 16  # SM_CXSMICON
            sm_cy = user32.GetSystemMetrics(50) or 16  # SM_CYSMICON
            hicon = user32.LoadImageW(0, icon_path, 1, sm_cx, sm_cy, 0x00000010)  # IMAGE_ICON, LR_LOADFROMFILE
        if not hicon:
            hicon = user32.LoadIconW(None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR))  # IDI_APPLICATION

        wndclass = WNDCLASSEXW()
        wndclass.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wndclass.style = 0
        wndclass.lpfnWndProc = ctypes.cast(wndproc, ctypes.c_void_p)
        wndclass.cbClsExtra = 0
        wndclass.cbWndExtra = 0
        wndclass.hInstance = hinstance
        wndclass.hIcon = hicon
        wndclass.hCursor = 0
        wndclass.hbrBackground = 0
        wndclass.lpszMenuName = None
        wndclass.lpszClassName = class_name
        wndclass.hIconSm = hicon

        user32.RegisterClassExW(ctypes.byref(wndclass))

        self.hwnd = user32.CreateWindowExW(
            0, class_name, "VCH_TrayMsgWindow", 0,
            0, 0, 0, 0, 0, 0, hinstance, None
        )

        # Aplicar tema oscuro nativo de Windows 11 al HWND de la bandeja
        try:
            if uxtheme:
                fn_allow_dark = ctypes.cast(uxtheme[133], ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_bool))
                fn_allow_dark(self.hwnd, True)
                uxtheme.SetWindowTheme(self.hwnd, "DarkMode_Explorer", None)
        except Exception:
            pass

        # Crear icono en la bandeja del sistema con el logo oficial
        self._base_hicon = hicon
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.uCallbackMessage = WM_TRAYICON
        self.nid.hIcon = hicon
        self.nid.szTip = "VortexCore Hub // Por Faundezz21"

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
        if self._pending_notice:
            self.notify(*self._pending_notice)
            self._pending_notice = None

        user32.SetTimer(self.hwnd, 1, 2500, None)
        self._update_tray_visual()

        # Message loop
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup
        user32.KillTimer(self.hwnd, 1)
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
        if self._dyn_hicon:
            user32.DestroyIcon(self._dyn_hicon)
            self._dyn_hicon = 0

    def _get_menu_state(self) -> dict:
        tel = getattr(self.manager, "telemetry", {}) or {}
        fan_mode = str(getattr(self.manager, "fan_mode", "auto")).lower()
        ov = getattr(self.manager, "_overlay_ref", None)
        gm = getattr(self.manager, "_gamemode_ref", None)
        ov_on = bool(ov.get_config().get("enabled")) if ov and hasattr(ov, "get_config") else False
        gm_on = bool(getattr(gm, "enabled", False)) if gm else False
        return {
            "cpu_temp": tel.get("cpu_temp"),
            "gpu_temp": tel.get("gpu_temp"),
            "profile": getattr(self.manager, "current_profile", "DEFAULT"),
            "fan_turbo": ("max" in fan_mode or "turbo" in fan_mode),
            "overlay_enabled": ov_on,
            "gamemode_enabled": gm_on,
            "temp_icon": self.temp_icon_enabled,
        }

    def _handle_menu_action(self, action: str, payload=None):
        if action == "open_hub":
            if self.on_open:
                threading.Thread(target=self.on_open, daemon=True).start()
        elif action == "set_audio" and audio_devices is not None and payload:
            audio_devices.set_default_output_device(payload)
        elif action == "set_profile" and payload:
            self.manager.set_profile(payload)
        elif action == "set_fan" and payload:
            self.manager.set_fan(payload)
        elif action == "set_hz" and display_manager is not None and payload:
            display_manager.set_refresh_rate(payload)
        elif action == "clean_ram":
            self.manager.clean_ram()
        elif action == "toggle_overlay":
            ov = getattr(self.manager, "_overlay_ref", None)
            if ov and hasattr(ov, "get_config") and hasattr(ov, "update_config"):
                ov.update_config({"enabled": not bool(ov.get_config().get("enabled"))})
        elif action == "toggle_gamemode":
            gm = getattr(self.manager, "_gamemode_ref", None)
            if gm and hasattr(gm, "set_enabled"):
                gm.set_enabled(not bool(getattr(gm, "enabled", False)))
        elif action == "toggle_autostart":
            set_autostart(not is_autostart_enabled())
        elif action == "toggle_temp_icon":
            self.set_temp_icon(not self.temp_icon_enabled)
        elif action == "exit_app":
            if self.nid:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            if self.hwnd:
                user32.PostMessageW(self.hwnd, 0x0012, 0, 0)
            if self.on_exit:
                self.on_exit()

    def _show_context_menu(self):
        if self._tray_menu is not None:
            user32.SetForegroundWindow(self.hwnd)
            self._tray_menu.show()
            return
        try:
            if uxtheme:
                fn_flush_themes = ctypes.cast(uxtheme[136], ctypes.WINFUNCTYPE(None))
                fn_flush_themes()
        except Exception:
            pass

        menu = user32.CreatePopupMenu()

        user32.AppendMenuW(menu, MF_STRING, CMD_OPEN, "Abrir VortexCore Hub")
        try:
            user32.SetMenuDefaultItem(menu, 0, True)
        except Exception:
            pass
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        # Salidas de audio en primer nivel (cambio en 1 clic, estilo EarTrumpet)
        self._audio_menu_ids = {}
        if audio_devices is not None:
            devs = audio_devices.list_output_devices()[:20]
            if devs:
                for idx, dev in enumerate(devs):
                    cmd_id = CMD_AUDIO_BASE + idx
                    self._audio_menu_ids[cmd_id] = dev["id"]
                    chk = MF_CHECKED if dev["is_default"] else MF_UNCHECKED
                    user32.AppendMenuW(menu, chk | MF_STRING, cmd_id, dev["name"])
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        # Submenú: Modo de energía
        curr_prof = getattr(self.manager, "current_profile", "DEFAULT").upper()
        prof_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(prof_menu, (MF_CHECKED if curr_prof == "ECO" else MF_UNCHECKED) | MF_STRING, CMD_ECO, "Silencioso (Eco)")
        user32.AppendMenuW(prof_menu, (MF_CHECKED if curr_prof in ("DEFAULT", "BALANCED") else MF_UNCHECKED) | MF_STRING, CMD_BALANCED, "Equilibrado (Windows)")
        user32.AppendMenuW(prof_menu, (MF_CHECKED if curr_prof == "PERFORMANCE" else MF_UNCHECKED) | MF_STRING, CMD_TURBO, "Rendimiento")
        user32.AppendMenuW(menu, MF_POPUP, int(prof_menu), "Modo de energía")

        # Submenú: Ventiladores
        fan_mode = str(getattr(self.manager, "fan_mode", "auto")).lower()
        is_turbo = "max" in fan_mode or "turbo" in fan_mode
        fan_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(fan_menu, (MF_CHECKED if not is_turbo else MF_UNCHECKED) | MF_STRING, CMD_FAN_AUTO, "Automático")
        user32.AppendMenuW(fan_menu, (MF_CHECKED if is_turbo else MF_UNCHECKED) | MF_STRING, CMD_FAN_MAX, "Al 100% (Máximo)")
        user32.AppendMenuW(menu, MF_POPUP, int(fan_menu), "Ventiladores")

        # Submenú: Pantalla (Hz)
        self._hz_menu_ids = {}
        if display_manager is not None:
            disp = display_manager.get_display_modes()
            hz_list = disp.get("available_hz") or []
            if hz_list:
                hz_menu = user32.CreatePopupMenu()
                for idx, hz in enumerate(hz_list[:20]):
                    cmd_id = CMD_HZ_BASE + idx
                    self._hz_menu_ids[cmd_id] = hz
                    chk = MF_CHECKED if hz == disp.get("current_hz") else MF_UNCHECKED
                    user32.AppendMenuW(hz_menu, chk | MF_STRING, cmd_id, f"{hz} Hz")
                user32.AppendMenuW(menu, MF_POPUP, int(hz_menu), f"Pantalla ({disp.get('current_hz', '--')} Hz)")

        user32.AppendMenuW(menu, MF_STRING, CMD_PURGE_RAM, "Liberar memoria RAM")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        # Submenú: Opciones de bandeja
        opts_menu = user32.CreatePopupMenu()
        autostart_state = MF_CHECKED if is_autostart_enabled() else MF_UNCHECKED
        user32.AppendMenuW(opts_menu, autostart_state | MF_STRING, CMD_AUTOSTART, "Iniciar con Windows al encender")
        temp_state = MF_CHECKED if self.temp_icon_enabled else MF_UNCHECKED
        user32.AppendMenuW(opts_menu, temp_state | MF_STRING, CMD_TEMP_ICON, "Mostrar temperatura en lugar del logo")
        user32.AppendMenuW(menu, MF_POPUP, int(opts_menu), "Opciones de bandeja")

        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_EXIT, "Salir de VortexCore")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        user32.SetForegroundWindow(self.hwnd)
        user32.TrackPopupMenu(menu, TPM_RIGHTALIGN | TPM_BOTTOMALIGN, pt.x, pt.y, 0, self.hwnd, 0)
        user32.PostMessageW(self.hwnd, 0, 0, 0)
        user32.DestroyMenu(menu)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_LBUTTONUP:
                if self.on_flyout:
                    self.on_flyout()
                elif self.on_open:
                    import time
                    now = time.time()
                    if now - getattr(self, "_last_click_time", 0) > 0.7:
                        self._last_click_time = now
                        self.on_open()
            elif lparam == WM_LBUTTONDBLCLK:
                import time
                now = time.time()
                if now - getattr(self, "_last_click_time", 0) > 0.7:
                    self._last_click_time = now
                    if self.on_open:
                        self.on_open()
            elif lparam == WM_RBUTTONUP:
                self._show_context_menu()
            elif lparam == NIN_BALLOONUSERCLICK and self.on_open:
                self.on_open()
            return 0

        elif msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == CMD_OPEN:
                if self.on_open:
                    self.on_open()
            elif cmd == CMD_ECO:
                self.manager.set_profile("ECO")
            elif cmd == CMD_BALANCED:
                self.manager.set_profile("DEFAULT")
            elif cmd == CMD_TURBO:
                self.manager.set_profile("PERFORMANCE")
            elif cmd == CMD_FAN_MAX:
                self.manager.set_fan("max")
            elif cmd == CMD_FAN_AUTO:
                self.manager.set_fan("auto")
            elif cmd == CMD_PURGE_RAM:
                self.manager.clean_ram()
            elif cmd == CMD_AUTOSTART:
                set_autostart(not is_autostart_enabled())
            elif cmd == CMD_TEMP_ICON:
                self.set_temp_icon(not self.temp_icon_enabled)
            elif cmd in getattr(self, "_audio_menu_ids", {}) and audio_devices is not None:
                audio_devices.set_default_output_device(self._audio_menu_ids[cmd])
            elif cmd in getattr(self, "_hz_menu_ids", {}) and display_manager is not None:
                display_manager.set_refresh_rate(self._hz_menu_ids[cmd])
            elif cmd == CMD_EXIT:
                if self.nid:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
                user32.PostQuitMessage(0)
                if self.on_exit:
                    self.on_exit()
            return 0

        elif msg == WM_TIMER:
            self._update_tray_visual()
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
