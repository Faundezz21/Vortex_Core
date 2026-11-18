# consumo de red por app y servidor del juego leyendo eventos etw de microsoft-windows-kernel-network

import ctypes
import ipaddress
import socket
import struct
import sys
import threading
import time
import uuid
from collections import deque

IS_WINDOWS = sys.platform == "win32"
SESSION_NAME = "VortexCoreHubNet"
PROVIDER_GUID = "7dd42a49-5329-4832-8dfd-43d979153a88"
KEYWORDS = 0x10 | 0x20  # ipv4 e ipv6
WINDOW_S = 3
IDLE_STOP_S = 25

# id de evento -> (direccion, protocolo, ipv6)
EVENTS = {
    10: ("tx", "tcp", False), 11: ("rx", "tcp", False),
    42: ("tx", "udp", False), 43: ("rx", "udp", False),
    26: ("tx", "tcp", True), 27: ("rx", "tcp", True),
    58: ("tx", "udp", True), 59: ("rx", "udp", True),
}

# apps que mueven udp pero no son juegos (lista compartida con el medidor de fps)
from fps_monitor import NON_GAME_APPS as NOT_GAMES  # noqa: E402


def parse_payload(event_id: int, data: bytes):
    # devuelve (pid, bytes, direccion, protocolo, ip_remota, puerto_remoto) o none
    info = EVENTS.get(event_id)
    if info is None:
        return None
    direction, proto, v6 = info
    need = 42 if v6 else 18
    if len(data) < need:
        return None
    pid, size = struct.unpack_from("<II", data, 0)
    if v6:
        ip = socket.inet_ntop(socket.AF_INET6, data[8:24])
        port = struct.unpack_from(">H", data, 40)[0]
    else:
        ip = socket.inet_ntoa(data[8:12])
        port = struct.unpack_from(">H", data, 16)[0]
    # el trafico local entre programas no es uso de internet
    if ip.startswith("127.") or ip == "::1" or ip.startswith("::ffff:127."):
        return None
    return pid, size, direction, proto, ip, port


def is_public_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return not (a.is_private or a.is_loopback or a.is_multicast or a.is_link_local or a.is_unspecified or a.is_reserved)


class TrafficWindow:
    # acumula bytes por segundo y calcula tasas sobre los ultimos segundos completos

    def __init__(self, window_s: int = WINDOW_S):
        self.window_s = window_s
        self._lock = threading.Lock()
        self._buckets = deque()  # (segundo, {pid: [rx, tx]}, {(pid, proto, ip, port): [bytes, paquetes]})

    def add(self, sec: int, pid: int, size: int, direction: str, proto: str, ip: str, port: int):
        with self._lock:
            if not self._buckets or self._buckets[-1][0] != sec:
                self._buckets.append((sec, {}, {}))
                while self._buckets and self._buckets[0][0] < sec - self.window_s - 1:
                    self._buckets.popleft()
            _, procs, remotes = self._buckets[-1]
            pr = procs.get(pid)
            if pr is None:
                pr = procs[pid] = [0, 0]
            pr[0 if direction == "rx" else 1] += size
            key = (pid, proto, ip, port)
            rm = remotes.get(key)
            if rm is None:
                rm = remotes[key] = [0, 0]
            rm[0] += size
            rm[1] += 1

    def rates(self, now_sec: int):
        # usa solo segundos completos para no subestimar el actual
        lo, hi = now_sec - self.window_s, now_sec - 1
        procs, remotes = {}, {}
        with self._lock:
            for sec, p, r in self._buckets:
                if lo <= sec <= hi:
                    for pid, (rx, tx) in p.items():
                        acc = procs.setdefault(pid, [0, 0])
                        acc[0] += rx
                        acc[1] += tx
                    for key, (b, n) in r.items():
                        acc = remotes.setdefault(key, [0, 0])
                        acc[0] += b
                        acc[1] += n
        div = float(self.window_s)
        return ({pid: (rx / div, tx / div) for pid, (rx, tx) in procs.items()},
                {key: (b / div, n / div) for key, (b, n) in remotes.items()})


def group_by_app(proc_rates: dict, names: dict) -> list:
    apps = {}
    for pid, (rx, tx) in proc_rates.items():
        name = names.get(pid) or ("Sistema" if pid in (0, 4) else f"PID {pid}")
        a = apps.setdefault(name.lower(), {"name": name, "pids": [], "down_bps": 0.0, "up_bps": 0.0})
        a["pids"].append(pid)
        a["down_bps"] += rx
        a["up_bps"] += tx
    out = sorted(apps.values(), key=lambda a: a["down_bps"] + a["up_bps"], reverse=True)
    for a in out:
        a["down_bps"] = int(a["down_bps"])
        a["up_bps"] = int(a["up_bps"])
    return out


def pick_game_server(remote_rates: dict, names: dict, prefer_name: str | None = None):
    # elige el proceso con mas paquetes udp a una ip publica y su servidor principal
    if prefer_name and prefer_name.lower() in NOT_GAMES:
        prefer_name = None
    per_pid = {}
    for (pid, proto, ip, port), (bps, pps) in remote_rates.items():
        # 443 es quic de navegadores y 53 es dns, no trafico de juego
        if proto != "udp" or port in (53, 443) or not is_public_ip(ip):
            continue
        name = (names.get(pid) or "").lower()
        if not name or name in NOT_GAMES:
            continue
        entry = per_pid.setdefault(pid, {"pps": 0.0, "best": None})
        entry["pps"] += pps
        if entry["best"] is None or pps > entry["best"][3]:
            entry["best"] = (ip, port, bps, pps)
    if not per_pid:
        return None
    if prefer_name:
        preferred = {p: e for p, e in per_pid.items() if (names.get(p) or "").lower() == prefer_name.lower()}
        if preferred:
            per_pid = preferred
    pid, entry = max(per_pid.items(), key=lambda kv: kv[1]["pps"])
    if entry["pps"] < (2 if prefer_name else 5):
        return None
    ip, port, bps, pps = entry["best"]
    return {"pid": pid, "name": names.get(pid), "ip": ip, "port": port, "pps": round(pps, 1)}


IP_SUCCESS = 0
IP_TTL_EXPIRED_TRANSIT = 11013
PROXY_AFTER_FAILS = 4

if IS_WINDOWS:
    class IP_OPTION_INFORMATION(ctypes.Structure):
        _fields_ = [("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte),
                    ("OptionsSize", ctypes.c_ubyte), ("OptionsData", ctypes.c_void_p)]

    class ICMP_ECHO_REPLY(ctypes.Structure):
        _fields_ = [("Address", ctypes.c_ulong), ("Status", ctypes.c_ulong), ("RoundTripTime", ctypes.c_ulong),
                    ("DataSize", ctypes.c_ushort), ("Reserved", ctypes.c_ushort), ("Data", ctypes.c_void_p),
                    ("Options", IP_OPTION_INFORMATION)]

    _iph = ctypes.WinDLL("iphlpapi", use_last_error=True)
    _iph.IcmpCreateFile.restype = ctypes.c_void_p
    _iph.IcmpCloseHandle.argtypes = [ctypes.c_void_p]
    _iph.IcmpSendEcho.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ushort,
                                  ctypes.POINTER(IP_OPTION_INFORMATION), ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
    _iph.IcmpSendEcho.restype = ctypes.c_ulong


# envia un eco icmp ipv4 con un ttl dado: (estado, ip que respondio, ms) o none
def icmp_probe(ip: str, ttl: int = 128, timeout_ms: int = 1000):
    if not IS_WINDOWS:
        return None
    try:
        addr = int.from_bytes(socket.inet_aton(ip), "little")
    except OSError:
        return None
    handle = _iph.IcmpCreateFile()
    if not handle or handle == ctypes.c_void_p(-1).value:
        return None
    try:
        data = ctypes.create_string_buffer(b"vortexcore", 10)
        opts = IP_OPTION_INFORMATION(ttl, 0, 0, 0, None)
        buf = ctypes.create_string_buffer(ctypes.sizeof(ICMP_ECHO_REPLY) + 64)
        _iph.IcmpSendEcho(handle, addr, data, 10, ctypes.byref(opts), buf, len(buf), timeout_ms)
        reply = ICMP_ECHO_REPLY.from_buffer(buf)
        if not reply.Address:
            return None
        hop = socket.inet_ntoa(reply.Address.to_bytes(4, "little"))
        return reply.Status, hop, reply.RoundTripTime
    finally:
        _iph.IcmpCloseHandle(handle)


# elige el ultimo salto publico que responde antes del servidor
def pick_last_hop(probes: dict):
    hops = [(ttl, r[1], r[2]) for ttl, r in probes.items()
            if r and r[0] in (IP_SUCCESS, IP_TTL_EXPIRED_TRANSIT) and is_public_ip(r[1])]
    if not hops:
        return None
    ttl, ip, rtt = max(hops)
    return {"ip": ip, "ttl": ttl, "rtt": rtt}


# rastrea la ruta en paralelo (un eco por salto) para no tardar mas de un segundo
def find_last_hop(ip: str, max_hops: int = 24):
    probes = {}

    def run(ttl):
        probes[ttl] = icmp_probe(ip, ttl, 900)

    threads = [threading.Thread(target=run, args=(ttl,), daemon=True) for ttl in range(1, max_hops + 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(2)
    return pick_last_hop(probes)


# mide hasta el salto enviando al servidor con el ttl justo para que expire ahi (como mtr)
def ping_proxy(target_ip: str, hop: dict):
    r = icmp_probe(target_ip, hop["ttl"], 1000)
    if r and r[0] in (IP_SUCCESS, IP_TTL_EXPIRED_TRANSIT) and is_public_ip(r[1]):
        return r[2]
    return None


def ping_stats(samples) -> dict:
    samples = list(samples)
    ok = [s for s in samples if s is not None]
    if not samples:
        return {"ping_ms": None, "jitter_ms": None, "loss_pct": None, "responds": None}
    loss = round(100.0 * (len(samples) - len(ok)) / len(samples))
    if not ok:
        return {"ping_ms": None, "jitter_ms": None, "loss_pct": loss, "responds": False}
    recent = ok[-5:]
    jitter = sum(abs(a - b) for a, b in zip(ok[1:], ok[:-1])) / (len(ok) - 1) if len(ok) > 1 else 0.0
    return {"ping_ms": round(sum(recent) / len(recent)), "jitter_ms": round(jitter, 1),
            "loss_pct": loss, "responds": True}


if IS_WINDOWS:
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]

    def _guid(text: str) -> GUID:
        u = uuid.UUID(text)
        return GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))

    class WNODE_HEADER(ctypes.Structure):
        _fields_ = [("BufferSize", ctypes.c_ulong), ("ProviderId", ctypes.c_ulong),
                    ("HistoricalContext", ctypes.c_uint64), ("TimeStamp", ctypes.c_int64), ("Guid", GUID),
                    ("ClientContext", ctypes.c_ulong), ("Flags", ctypes.c_ulong)]

    class EVENT_TRACE_PROPERTIES(ctypes.Structure):
        _fields_ = [("Wnode", WNODE_HEADER), ("BufferSize", ctypes.c_ulong), ("MinimumBuffers", ctypes.c_ulong),
                    ("MaximumBuffers", ctypes.c_ulong), ("MaximumFileSize", ctypes.c_ulong),
                    ("LogFileMode", ctypes.c_ulong), ("FlushTimer", ctypes.c_ulong), ("EnableFlags", ctypes.c_ulong),
                    ("AgeLimit", ctypes.c_long), ("NumberOfBuffers", ctypes.c_ulong), ("FreeBuffers", ctypes.c_ulong),
                    ("EventsLost", ctypes.c_ulong), ("BuffersWritten", ctypes.c_ulong),
                    ("LogBuffersLost", ctypes.c_ulong), ("RealTimeBuffersLost", ctypes.c_ulong),
                    ("LoggerThreadId", ctypes.c_void_p), ("LogFileNameOffset", ctypes.c_ulong),
                    ("LoggerNameOffset", ctypes.c_ulong)]

    class PROPS(ctypes.Structure):
        _fields_ = [("p", EVENT_TRACE_PROPERTIES), ("name", ctypes.c_wchar * 256), ("file", ctypes.c_wchar * 256)]

    class EVENT_TRACE_HEADER(ctypes.Structure):
        _fields_ = [("Size", ctypes.c_ushort), ("FieldTypeFlags", ctypes.c_ushort), ("Version", ctypes.c_ulong),
                    ("ThreadId", ctypes.c_ulong), ("ProcessId", ctypes.c_ulong), ("TimeStamp", ctypes.c_int64),
                    ("Guid", GUID), ("ProcessorTime", ctypes.c_uint64)]

    class EVENT_TRACE(ctypes.Structure):
        _fields_ = [("Header", EVENT_TRACE_HEADER), ("InstanceId", ctypes.c_ulong),
                    ("ParentInstanceId", ctypes.c_ulong), ("ParentGuid", GUID), ("MofData", ctypes.c_void_p),
                    ("MofLength", ctypes.c_ulong), ("ClientContext", ctypes.c_ulong)]

    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ushort) for n in ("Y", "M", "DW", "D", "H", "Mi", "S", "Ms")]

    class TIME_ZONE_INFORMATION(ctypes.Structure):
        _fields_ = [("Bias", ctypes.c_long), ("StandardName", ctypes.c_wchar * 32), ("StandardDate", SYSTEMTIME),
                    ("StandardBias", ctypes.c_long), ("DaylightName", ctypes.c_wchar * 32),
                    ("DaylightDate", SYSTEMTIME), ("DaylightBias", ctypes.c_long)]

    class TRACE_LOGFILE_HEADER(ctypes.Structure):
        _fields_ = [("BufferSize", ctypes.c_ulong), ("Version", ctypes.c_ulong), ("ProviderVersion", ctypes.c_ulong),
                    ("NumberOfProcessors", ctypes.c_ulong), ("EndTime", ctypes.c_int64),
                    ("TimerResolution", ctypes.c_ulong), ("MaximumFileSize", ctypes.c_ulong),
                    ("LogFileMode", ctypes.c_ulong), ("BuffersWritten", ctypes.c_ulong), ("LogInstanceGuid", GUID),
                    ("LoggerName", ctypes.c_void_p), ("LogFileName", ctypes.c_void_p),
                    ("TimeZone", TIME_ZONE_INFORMATION), ("BootTime", ctypes.c_int64), ("PerfFreq", ctypes.c_int64),
                    ("StartTime", ctypes.c_int64), ("ReservedFlags", ctypes.c_ulong), ("BuffersLost", ctypes.c_ulong)]

    class EVENT_TRACE_LOGFILEW(ctypes.Structure):
        _fields_ = [("LogFileName", ctypes.c_wchar_p), ("LoggerName", ctypes.c_wchar_p),
                    ("CurrentTime", ctypes.c_int64), ("BuffersRead", ctypes.c_ulong),
                    ("ProcessTraceMode", ctypes.c_ulong), ("CurrentEvent", EVENT_TRACE),
                    ("LogfileHeader", TRACE_LOGFILE_HEADER), ("BufferCallback", ctypes.c_void_p),
                    ("BufferSize", ctypes.c_ulong), ("Filled", ctypes.c_ulong), ("EventsLost", ctypes.c_ulong),
                    ("EventRecordCallback", ctypes.c_void_p), ("IsKernelTrace", ctypes.c_ulong),
                    ("Context", ctypes.c_void_p)]

    _adv = ctypes.WinDLL("advapi32", use_last_error=True)
    _adv.StartTraceW.argtypes = [ctypes.POINTER(ctypes.c_uint64), wintypes.LPCWSTR, ctypes.c_void_p]
    _adv.StartTraceW.restype = ctypes.c_ulong
    _adv.ControlTraceW.argtypes = [ctypes.c_uint64, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_ulong]
    _adv.ControlTraceW.restype = ctypes.c_ulong
    _adv.EnableTraceEx2.argtypes = [ctypes.c_uint64, ctypes.POINTER(GUID), ctypes.c_ulong, ctypes.c_ubyte,
                                    ctypes.c_uint64, ctypes.c_uint64, ctypes.c_ulong, ctypes.c_void_p]
    _adv.EnableTraceEx2.restype = ctypes.c_ulong
    _adv.OpenTraceW.argtypes = [ctypes.POINTER(EVENT_TRACE_LOGFILEW)]
    _adv.OpenTraceW.restype = ctypes.c_uint64
    _adv.ProcessTrace.argtypes = [ctypes.POINTER(ctypes.c_uint64), ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
    _adv.ProcessTrace.restype = ctypes.c_ulong
    _adv.CloseTrace.argtypes = [ctypes.c_uint64]
    _adv.CloseTrace.restype = ctypes.c_ulong

    EVENT_RECORD_CALLBACK = ctypes.WINFUNCTYPE(None, ctypes.c_void_p)

INVALID_TRACE = 0xFFFFFFFFFFFFFFFF


def _new_props():
    props = PROPS()
    props.p.Wnode.BufferSize = ctypes.sizeof(PROPS)
    props.p.Wnode.Flags = 0x00020000  # wnode_flag_traced_guid
    props.p.Wnode.ClientContext = 1
    props.p.LogFileMode = 0x00000100  # event_trace_real_time_mode
    props.p.BufferSize = 64
    props.p.MinimumBuffers = 4
    props.p.MaximumBuffers = 32
    props.p.FlushTimer = 1
    props.p.LoggerNameOffset = ctypes.sizeof(EVENT_TRACE_PROPERTIES)
    props.p.LogFileNameOffset = ctypes.sizeof(EVENT_TRACE_PROPERTIES) + ctypes.sizeof(ctypes.c_wchar) * 256
    return props


def _process_names() -> dict:
    try:
        import psutil
        return {p.pid: p.info["name"] for p in psutil.process_iter(["name"])}
    except Exception:
        return {}


class NetMonitor:
    def __init__(self, ping_func=None, prefer_game=None):
        self.ping_func = ping_func
        self.prefer_game = prefer_game  # devuelve el nombre exe del juego detectado por fps
        self.window = TrafficWindow()
        self.error = None
        self._session = 0
        self._trace = 0
        self._cb = None
        self._lock = threading.Lock()
        self._running = False
        self._last_touch = 0.0
        self._names = {}
        self._names_at = 0.0
        self._target = None
        self._pings = deque(maxlen=20)
        self._proxy = None      # salto que responde cuando el servidor bloquea el ping
        self._proxy_for = None
        self._proxy_tried = None
        self._ping_thread = None
        self.events = 0

    @property
    def available(self) -> bool:
        return IS_WINDOWS

    @property
    def running(self) -> bool:
        return self._running

    def touch(self):
        self._last_touch = time.time()
        if not self._running:
            self.start()

    def start(self):
        with self._lock:
            if self._running or not IS_WINDOWS:
                return
            self.error = None
            stop_props = _new_props()
            _adv.ControlTraceW(0, SESSION_NAME, ctypes.byref(stop_props), 1)
            props = _new_props()
            handle = ctypes.c_uint64(0)
            rc = _adv.StartTraceW(ctypes.byref(handle), SESSION_NAME, ctypes.byref(props))
            if rc != 0:
                self.error = "requiere admin" if rc == 5 else f"etw {rc}"
                return
            self._session = handle.value
            guid = _guid(PROVIDER_GUID)
            rc = _adv.EnableTraceEx2(self._session, ctypes.byref(guid), 1, 5, KEYWORDS, 0, 0, None)
            if rc != 0:
                self.error = f"etw enable {rc}"
                self._stop_session()
                return
            self._cb = EVENT_RECORD_CALLBACK(self._on_event)
            lf = EVENT_TRACE_LOGFILEW()
            lf.LoggerName = SESSION_NAME
            lf.ProcessTraceMode = 0x00000100 | 0x10000000  # tiempo real y event_record
            lf.EventRecordCallback = ctypes.cast(self._cb, ctypes.c_void_p)
            self._logfile = lf
            trace = _adv.OpenTraceW(ctypes.byref(lf))
            if trace == INVALID_TRACE:
                self.error = "etw open"
                self._stop_session()
                return
            self._trace = trace
            self._running = True
            self._last_touch = time.time()
            threading.Thread(target=self._process, daemon=True, name="vch-net-etw").start()
            threading.Thread(target=self._supervise, daemon=True, name="vch-net-sup").start()

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_session()
            if self._trace:
                _adv.CloseTrace(self._trace)
                self._trace = 0
            self._target = None
            self._pings.clear()

    def _stop_session(self):
        props = _new_props()
        _adv.ControlTraceW(self._session or 0, None if self._session else SESSION_NAME, ctypes.byref(props), 1)
        self._session = 0

    def _process(self):
        h = ctypes.c_uint64(self._trace)
        try:
            _adv.ProcessTrace(ctypes.byref(h), 1, None, None)
        except Exception:
            pass

    def _supervise(self):
        while self._running:
            time.sleep(1.0)
            if time.time() - self._last_touch > IDLE_STOP_S:
                self.stop()
                return
            self._ping_once()

    def _on_event(self, rec):
        try:
            head = ctypes.string_at(rec, 104)
            event_id = struct.unpack_from("<H", head, 40)[0]
            if event_id not in EVENTS:
                return
            length = struct.unpack_from("<H", head, 86)[0]
            ptr = struct.unpack_from("<Q", head, 96)[0]
            if not ptr or length < 18:
                return
            parsed = parse_payload(event_id, ctypes.string_at(ptr, min(length, 44)))
            if parsed is None:
                return
            pid, size, direction, proto, ip, port = parsed
            self.events += 1
            self.window.add(int(time.monotonic()), pid, size, direction, proto, ip, port)
        except Exception:
            pass

    def _names_cached(self) -> dict:
        if time.time() - self._names_at > 3:
            self._names = _process_names()
            self._names_at = time.time()
        return self._names

    def _ping_once(self):
        target = self._target
        if not target or not self.ping_func:
            return
        ip = target["ip"]
        proxy = self._proxy if self._proxy_for == ip else None
        try:
            self._pings.append(ping_proxy(ip, proxy) if proxy else self.ping_func(ip))
        except Exception:
            self._pings.append(None)
        # si el servidor no contesta ningun ping se mide hasta el ultimo salto de la ruta
        recent = list(self._pings)[-PROXY_AFTER_FAILS:]
        if (not proxy and self._proxy_tried != ip and ":" not in ip
                and len(recent) == PROXY_AFTER_FAILS and all(p is None for p in recent)):
            self._proxy_tried = ip
            hop = find_last_hop(ip)
            if hop and self._target and self._target["ip"] == ip:
                self._proxy, self._proxy_for = hop, ip
                self._pings.clear()

    def snapshot(self, top: int = 6) -> dict:
        self.touch()
        if not self._running:
            return {"available": False, "error": self.error, "apps": [], "game": None}
        names = self._names_cached()
        procs, remotes = self.window.rates(int(time.monotonic()))
        apps = group_by_app(procs, names)
        prefer = None
        if self.prefer_game:
            try:
                prefer = self.prefer_game()
            except Exception:
                prefer = None
        game = pick_game_server(remotes, names, prefer)
        if game:
            if not self._target or self._target["ip"] != game["ip"]:
                self._pings.clear()
            self._target = game
            game.update(ping_stats(self._pings))
            proxy = self._proxy if self._proxy_for == game["ip"] else None
            game["approx"] = bool(proxy)
            game["via"] = proxy["ip"] if proxy else None
            if self._proxy_tried == game["ip"] and not proxy and not game.get("responds"):
                game["route_failed"] = True
        else:
            self._target = None
            self._pings.clear()
        return {
            "available": True,
            "error": None,
            "apps": [a for a in apps if a["down_bps"] + a["up_bps"] >= 1024][:top],
            "total_down_bps": int(sum(a["down_bps"] for a in apps)),
            "total_up_bps": int(sum(a["up_bps"] for a in apps)),
            "game": game,
        }
