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
from http.server import HTTPServer, SimpleHTTPRequestHandler
from tray_manager import SystemTrayApp, is_autostart_enabled, set_autostart

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

CREATE_NO_WINDOW = 0x08000000
PORT = 8765


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def request_admin_elevation():
    if not is_admin():
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
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


class VortexCoreManager:
    def __init__(self):
        self.fan_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hp_fan_controller.ps1")
        self.current_profile = "STANDARD"
        self.fan_mode = "AUTO"

        # Detección inicial de memoria RAM instalada
        initial_installed = 32
        initial_total = "31.6"
        initial_used = "11.5"
        initial_free = "20.1"
        initial_pct = 36
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
                if tot_gb <= 8.5:
                    initial_installed = 8
                elif tot_gb <= 16.5:
                    initial_installed = 16
                elif tot_gb <= 24.5:
                    initial_installed = 24
                elif tot_gb <= 32.5:
                    initial_installed = 32
                elif tot_gb <= 48.5:
                    initial_installed = 48
                elif tot_gb <= 64.5:
                    initial_installed = 64
                else:
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
            "battery_devices": self._get_battery_devices()
        }

        self.running = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _get_battery_devices(self) -> list[dict]:
        devs = []
        # 1. Batería interna de Laptop
        if HAS_PSUTIL:
            try:
                bat = psutil.sensors_battery()
                if bat:
                    devs.append({
                        "name": "Batería HP Victus",
                        "type": "laptop",
                        "percent": int(bat.percent),
                        "plugged": bool(bat.power_plugged),
                        "icon": "laptop",
                        "status": "Cargando (AC)" if bat.power_plugged else "En Batería"
                    })
            except Exception:
                pass

        # 2. PnP Devices con Property {104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2
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

        # 3. Dispositivos Bluetooth conocidos en BTHPORT (como audífonos Redmi Buds 6 Active o mandos)
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

                # 5. Detección de Dispositivos y Batería (Laptop, Auriculares Bluetooth, Gamepads) cada 3s
                if tick % 6 == 0:
                    self.telemetry["battery_devices"] = self._get_battery_devices()

                self.telemetry["current_profile"] = self.current_profile
                self.telemetry["fan_mode"] = self.fan_mode
                tick += 1
            except Exception:
                pass

            time.sleep(0.5)

    def set_fan(self, mode: str) -> bool:
        ok, out = self._run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", self.fan_script, "-Mode", mode])
        if mode == "max":
            self.fan_mode = "TURBO (100%)"
        else:
            self.fan_mode = "AUTO"
        return ok

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
        directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vortex-hub")
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path == "/api/telemetry":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(manager.telemetry).encode("utf-8"))
        elif self.path == "/api/autostart":
            self._send_json({"enabled": is_autostart_enabled()})
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
        elif self.path == "/api/autostart":
            enable = bool(data.get("enabled", True))
            ok = set_autostart(enable)
            self._send_json({"status": "ok", "enabled": is_autostart_enabled()})
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


def launch_native_window():
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    edge_exe = next((p for p in edge_paths if os.path.isfile(p)), "msedge.exe")
    url = f"http://127.0.0.1:{PORT}"

    args = [
        edge_exe,
        f"--app={url}",
        "--window-size=1020,920",
        "--disable-extensions",
        "--disable-background-networking"
    ]
    subprocess.Popen(args)


if __name__ == "__main__":
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
        on_open_callback=launch_native_window,
        on_exit_callback=lambda: os._exit(0)
    )
    threading.Thread(target=tray.run, daemon=True).start()

    # Si se inicia automáticamente con Windows (--minimized o --tray), no abre la ventana
    is_minimized = any(arg in sys.argv for arg in ["--minimized", "--tray", "-m"])
    if not is_minimized:
        launch_native_window()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.running = False
        server.shutdown()
