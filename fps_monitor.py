# medidor de fps por proceso leyendo el csv de presentmon por stdout

import ctypes
import io
import os
import subprocess
import sys
import threading
import time
from collections import deque

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000
SESSION_NAME = "VortexCoreHubFps"
WINDOW_S = 1.0
STALE_S = 2.0

# procesos del sistema que presentan frames pero no son juegos
_IGNORED_APPS = {"dwm.exe", "explorer.exe", "searchhost.exe", "shellexperiencehost.exe",
                 "startmenuexperiencehost.exe", "textinputhost.exe", "applicationframehost.exe"}

# apps que dibujan frames pero no son juegos (navegadores, chat, lanzadores, herramientas)
NON_GAME_APPS = {
    "system", "svchost.exe", "chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe", "opera_gx.exe",
    "vivaldi.exe", "arc.exe", "discord.exe", "teams.exe", "ms-teams.exe", "zoom.exe", "slack.exe", "spotify.exe",
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "epicwebhelper.exe", "battle.net.exe",
    "riotclientservices.exe", "riotclientux.exe", "eadesktop.exe", "ubisoftconnect.exe", "upc.exe",
    "galaxyclient.exe", "obs64.exe", "nvcontainer.exe", "nvidia share.exe", "nvidia app.exe", "whatsapp.exe",
    "telegram.exe", "msedgewebview2.exe", "parsecd.exe", "lghub_agent.exe", "lghub.exe", "onedrive.exe",
    "dropbox.exe", "qbittorrent.exe", "utorrent.exe", "python.exe", "pythonw.exe", "vortexcorehub.exe",
    "claude.exe", "code.exe", "cursor.exe", "notepad.exe", "notepad++.exe", "winword.exe", "excel.exe",
    "powerpnt.exe", "outlook.exe", "olk.exe", "acrobat.exe", "acrord32.exe", "vlc.exe", "mpc-hc64.exe",
    "photos.exe", "windowsterminal.exe", "cmd.exe", "powershell.exe", "taskmgr.exe", "systemsettings.exe",
    "notion.exe", "figma.exe", "obsidian.exe", "postman.exe", "phpstorm64.exe", "idea64.exe", "devenv.exe",
    "hp.omenhub.exe", "omen gaming hub.exe", "armoury crate.exe", "msiafterburner.exe", "rtss.exe",
}
GAME_MIN_FPS = 15


# un proceso cuenta como juego si dibuja de forma continua y no es una app conocida
def is_game(stats: dict | None) -> bool:
    if not stats or not stats.get("fps"):
        return False
    return (stats.get("app") or "").lower() not in NON_GAME_APPS and stats["fps"] >= GAME_MIN_FPS


def find_presentmon(app_dir: str) -> str | None:
    for rel in (("tools", "PresentMon.exe"), ("PresentMon.exe",)):
        path = os.path.join(app_dir, *rel)
        if os.path.isfile(path):
            return path
    return None


def parse_header(line: str) -> dict | None:
    cols = [c.strip() for c in line.strip().split(",")]
    # presentmon cambia mayusculas entre versiones (msbetweenpresents)
    idx = {name.lower(): i for i, name in enumerate(cols)}
    if "processid" not in idx or "timeinseconds" not in idx or "msbetweenpresents" not in idx:
        return None
    return {
        "app": idx.get("application"),
        "pid": idx["processid"],
        "t": idx["timeinseconds"],
        "ms": idx["msbetweenpresents"],
        "n": len(cols),
    }


def parse_row(line: str, header: dict) -> tuple | None:
    parts = line.rstrip("\r\n").split(",")
    if len(parts) < header["n"]:
        return None
    try:
        pid = int(parts[header["pid"]])
        t = float(parts[header["t"]])
        ms = float(parts[header["ms"]])
    except ValueError:
        return None
    if ms <= 0 or ms > 1000:
        return None
    app = parts[header["app"]] if header["app"] is not None else ""
    return pid, app, t, ms


def compute_stats(frames) -> dict | None:
    # frames: iterable de (t, ms) del ultimo segundo
    frames = list(frames)
    if not frames:
        return None
    avg_ms = sum(ms for _, ms in frames) / len(frames)
    worst = sorted(ms for _, ms in frames)[-max(1, len(frames) // 100):]
    low_ms = sum(worst) / len(worst)
    return {
        "fps": round(1000.0 / avg_ms) if avg_ms > 0 else None,
        "frametime_ms": round(avg_ms, 1),
        "low1_fps": round(1000.0 / low_ms) if low_ms > 0 else None,
    }


_job_handle = None


# asocia el proceso a un job que lo mata cuando la app se cierra o se cae
def _bind_to_job(proc) -> None:
    global _job_handle
    if not IS_WINDOWS:
        return
    try:
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        if _job_handle is None:

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class EXTENDED(ctypes.Structure):
                _fields_ = [("Basic", BASIC), ("Io", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            job = k32.CreateJobObjectW(None, None)
            info = EXTENDED()
            info.Basic.LimitFlags = 0x2000  # job_object_limit_kill_on_job_close
            k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
            _job_handle = job
        k32.AssignProcessToJobObject(_job_handle, wintypes.HANDLE(int(proc._handle)))
    except Exception:
        pass


# presentmon escribe en utf-16 con bom; se detecta para no depender de la version
def _text_stream(raw):
    buf = raw if isinstance(raw, io.BufferedReader) else io.BufferedReader(raw)
    head = buf.peek(2)[:2]
    if head in (b"\xff\xfe", b"\xfe\xff"):
        return io.TextIOWrapper(buf, encoding="utf-16", errors="replace", newline=None)
    return io.TextIOWrapper(buf, encoding="utf-8-sig", errors="replace", newline=None)


if IS_WINDOWS:
    from ctypes import wintypes as _wt
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _u32.GetForegroundWindow.restype = _wt.HWND
    _u32.GetWindowThreadProcessId.argtypes = [_wt.HWND, ctypes.POINTER(_wt.DWORD)]
    _k32.OpenProcess.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
    _k32.OpenProcess.restype = _wt.HANDLE
    _k32.QueryFullProcessImageNameW.argtypes = [_wt.HANDLE, _wt.DWORD, _wt.LPWSTR, ctypes.POINTER(_wt.DWORD)]
    _k32.CloseHandle.argtypes = [_wt.HANDLE]


def foreground_pid() -> int | None:
    if not IS_WINDOWS:
        return None
    try:
        hwnd = _u32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong(0)
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value or None
    except Exception:
        return None


def process_exe_name(pid: int) -> str | None:
    if not IS_WINDOWS or not pid:
        return None
    try:
        h = _k32.OpenProcess(0x1000, False, pid)  # process_query_limited_information
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = _wt.DWORD(len(buf))
            if not _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return None
            return os.path.basename(buf.value)
        finally:
            _k32.CloseHandle(h)
    except Exception:
        return None


# si el proceso con foco no dibuja (navegadores, lanzadores) usa otro del mismo exe
def pick_pid(fg_pid: int, fg_exe: str | None, apps: dict, last_seen: dict, now: float) -> int:
    if now - last_seen.get(fg_pid, 0) <= STALE_S or not fg_exe:
        return fg_pid
    target = fg_exe.lower()
    best, best_ts = fg_pid, 0.0
    for pid, app in apps.items():
        ts = last_seen.get(pid, 0)
        if (app or "").lower() == target and now - ts <= STALE_S and ts > best_ts:
            best, best_ts = pid, ts
    return best


class FpsMonitor:
    def __init__(self, exe_path: str | None):
        self.exe_path = exe_path
        self._lock = threading.Lock()
        self._frames = {}      # pid -> deque[(t, ms)]
        self._apps = {}        # pid -> nombre exe
        self._last_seen = {}   # pid -> reloj local del ultimo frame
        self._proc = None
        self._wanted = False
        self._owners = set()  # quienes lo usan: el hud y el modo juego
        self._last_start = 0.0
        self.error = None
        self.last_game = None  # (exe, instante) del ultimo juego con foco

    @property
    def available(self) -> bool:
        return bool(self.exe_path) and IS_WINDOWS

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, owner: str = "overlay"):
        self._owners.add(owner)
        self._wanted = True
        self._ensure_running()

    # solo se detiene cuando ya nadie lo necesita
    def stop(self, owner: str = "overlay"):
        self._owners.discard(owner)
        if self._owners:
            return
        self._wanted = False
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                pass
        # cierra la sesion etw por si quedo abierta
        if self.available:
            try:
                subprocess.run([self.exe_path, "--terminate_existing_session", "--session_name", SESSION_NAME],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=CREATE_NO_WINDOW, timeout=5)
            except Exception:
                pass
        with self._lock:
            self._frames.clear()
            self._apps.clear()
            self._last_seen.clear()

    def _ensure_running(self):
        if not self._wanted or not self.available or self.running:
            return
        # evita relanzar en bucle si presentmon falla al iniciar
        if time.time() - self._last_start < 10:
            return
        self._last_start = time.time()
        args = [self.exe_path, "--output_stdout", "--no_console_stats", "--v1_metrics",
                "--no_track_input", "--no_track_gpu", "--no_track_display",
                "--session_name", SESSION_NAME, "--stop_existing_session"]
        for name in _IGNORED_APPS:
            args += ["--exclude", name]
        try:
            self._proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
            self.error = None
        except Exception as e:
            self._proc = None
            self.error = str(e)
            return
        proc = self._proc
        _bind_to_job(proc)
        threading.Thread(target=self._reader, args=(proc,), daemon=True).start()
        threading.Thread(target=self._stderr_reader, args=(proc,), daemon=True).start()

    def _stderr_reader(self, proc):
        try:
            for line in _text_stream(proc.stderr):
                if "error" in line.lower():
                    self.error = line.strip()[:200]
        except Exception:
            pass

    def _reader(self, proc):
        header = None
        try:
            for line in _text_stream(proc.stdout):
                if header is None:
                    header = parse_header(line)
                    continue
                row = parse_row(line, header)
                if row is None:
                    continue
                pid, app, t, ms = row
                now = time.time()
                with self._lock:
                    dq = self._frames.get(pid)
                    if dq is None:
                        dq = self._frames[pid] = deque()
                        self._apps[pid] = app
                    dq.append((t, ms))
                    while dq and dq[0][0] < t - WINDOW_S:
                        dq.popleft()
                    self._last_seen[pid] = now
        except Exception:
            pass

    # nombre del ultimo juego visto con foco en el ultimo minuto
    def recent_game(self) -> str | None:
        if self.last_game and time.time() - self.last_game[1] < 60:
            return self.last_game[0]
        return None

    # fps del proceso indicado o del que tiene el foco
    def snapshot(self, pid: int | None = None) -> dict | None:
        self._ensure_running()
        fg_exe = None
        if pid is None:
            pid = foreground_pid()
            if pid is None:
                return None
            fg_exe = process_exe_name(pid)
        now = time.time()
        with self._lock:
            # limpia procesos que dejaron de presentar
            for old in [p for p, ts in self._last_seen.items() if now - ts > 30]:
                self._frames.pop(old, None)
                self._apps.pop(old, None)
                self._last_seen.pop(old, None)
            if fg_exe:
                pid = pick_pid(pid, fg_exe, self._apps, self._last_seen, now)
            if now - self._last_seen.get(pid, 0) > STALE_S:
                return None
            stats = compute_stats(self._frames.get(pid, ()))
            if stats is None:
                return None
            stats["app"] = self._apps.get(pid, "")
            stats["pid"] = pid
            if fg_exe and is_game(stats):
                self.last_game = (stats["app"], now)
            return stats
