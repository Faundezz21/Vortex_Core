"""
================================================================================
  VortexCore Hub // Tray Manager & Windows Autostart
  - Icono nativo en la Bandeja del Sistema (System Tray / junto al reloj)
  - Menú contextual rápido para conmutar perfiles y turbina
  - Gestión de Auto-Inicio con Windows (Startup Folder)
  - Desarrollado por Faundezz21
================================================================================
"""

import os
import sys
import ctypes
import subprocess
import tempfile
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

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
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
NIN_BALLOONUSERCLICK = WM_USER + 5

TPM_BOTTOMALIGN = 0x0020
TPM_RIGHTALIGN = 0x0008

MF_STRING = 0x0000
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


class SystemTrayApp:
    def __init__(self, manager, on_open_callback, on_exit_callback):
        self.manager = manager
        self.on_open = on_open_callback
        self.on_exit = on_exit_callback
        self.hwnd = None
        self.nid = None
        self._pending_notice = None

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

        # Message loop
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))

    def _show_context_menu(self):
        try:
            if uxtheme:
                fn_flush_themes = ctypes.cast(uxtheme[136], ctypes.WINFUNCTYPE(None))
                fn_flush_themes()
        except Exception:
            pass

        menu = user32.CreatePopupMenu()

        user32.AppendMenuW(menu, MF_STRING, CMD_OPEN, "Abrir VortexCore Hub")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        curr_prof = getattr(self.manager, "current_profile", "DEFAULT").upper()
        user32.AppendMenuW(menu, (MF_CHECKED if curr_prof == "ECO" else MF_UNCHECKED) | MF_STRING, CMD_ECO, "Modo Silencioso")
        user32.AppendMenuW(menu, (MF_CHECKED if curr_prof in ("DEFAULT", "BALANCED") else MF_UNCHECKED) | MF_STRING, CMD_BALANCED, "Modo Windows (por defecto)")
        user32.AppendMenuW(menu, (MF_CHECKED if curr_prof == "PERFORMANCE" else MF_UNCHECKED) | MF_STRING, CMD_TURBO, "Modo Rendimiento")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        fan_mode = str(getattr(self.manager, "fan_mode", "auto")).lower()
        is_turbo = "max" in fan_mode or "turbo" in fan_mode
        user32.AppendMenuW(menu, (MF_CHECKED if is_turbo else MF_UNCHECKED) | MF_STRING, CMD_FAN_MAX, "Ventiladores al 100%")
        user32.AppendMenuW(menu, (MF_CHECKED if not is_turbo else MF_UNCHECKED) | MF_STRING, CMD_FAN_AUTO, "Ventiladores en automático")
        user32.AppendMenuW(menu, MF_STRING, CMD_PURGE_RAM, "Liberar memoria RAM")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        autostart_state = MF_CHECKED if is_autostart_enabled() else MF_UNCHECKED
        user32.AppendMenuW(menu, autostart_state | MF_STRING, CMD_AUTOSTART, "Iniciar con Windows al encender")
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
            if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                import time
                now = time.time()
                # Debounce de clics: ignora pulsaciones repetidas o ráfagas de doble-clic
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
            elif cmd == CMD_EXIT:
                if self.nid:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
                user32.PostQuitMessage(0)
                if self.on_exit:
                    self.on_exit()
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
