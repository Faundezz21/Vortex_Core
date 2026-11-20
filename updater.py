# aviso de nuevas versiones consultando el ultimo release publicado en github

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

REPO = "Faundezz21/Vortex_Core"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
CHECK_EVERY_S = 6 * 3600
FIRST_DELAY_S = 20
USER_AGENT = "VortexCoreHub-Updater"


def parse_version(text) -> tuple | None:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", str(text or ""))
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def is_newer(latest, current) -> bool:
    lv, cv = parse_version(latest), parse_version(current)
    if lv is None:
        return False
    if cv is None:
        # una version de desarrollo sin numero no se compara
        return False
    return lv > cv


def summarize_notes(body: str, limit: int = 6) -> list:
    # extrae las primeras vinetas de las notas del release para mostrarlas en la app
    items = []
    lines = (body or "").splitlines()
    # las notas traen primero las descargas; se leen solo desde la seccion de novedades
    start = next((i for i, l in enumerate(lines) if l.lstrip("# ").lower().startswith("novedades")), -1)
    for line in lines[start + 1:]:
        line = line.strip()
        if line.startswith(("- ", "* ")):
            text = re.sub(r"\*\*|`|\[([^\]]+)\]\([^)]+\)", lambda m: m.group(1) or "", line[2:]).strip()
            if text:
                items.append(text[:160])
        if len(items) >= limit:
            break
    return items


def parse_release(data: dict, current: str) -> dict:
    tag = data.get("tag_name") or ""
    assets = data.get("assets") or []
    setup = next((a.get("browser_download_url") for a in assets
                  if str(a.get("name", "")).lower().endswith("setup.exe")), None)
    sums = next((a.get("browser_download_url") for a in assets
                 if str(a.get("name", "")).lower() == "checksums-sha256.txt"), None)
    return {
        "latest": tag.lstrip("vV") or None,
        "update_available": is_newer(tag, current),
        "url": data.get("html_url") or RELEASES_URL,
        "setup_url": setup,
        "checksums_url": sums,
        "published_at": data.get("published_at"),
        "notes": summarize_notes(data.get("body") or ""),
    }


def fetch_latest(timeout: int = 8) -> tuple:
    req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "ok", json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return ("none" if e.code == 404 else "error"), None
    except Exception:
        return "error", None


DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
SETUP_NAME = "Vortex-core-hub-Setup.exe"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


# busca el hash publicado para un archivo en checksums-sha256.txt
def parse_checksums(text: str, name: str) -> str | None:
    for line in (text or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name and re.fullmatch(r"[0-9A-Fa-f]{64}", parts[0]):
            return parts[0].upper()
    return None


def _download(url: str, dest: str, progress=None, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done, total)


def updates_dir() -> str:
    return os.path.join(os.path.dirname(state_path()), "updates")


def state_path() -> str:
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub")
    return os.path.join(base, "updates.json")


class UpdateChecker:
    def __init__(self, current_version: str, notify=None, fetch=fetch_latest):
        self.current = current_version
        self.notify = notify
        self.fetch = fetch
        self._lock = threading.RLock()  # reentrante: start_install consulta el estado con el candado tomado
        self._state = {"status": "pending", "current": current_version, "checked_at": None}
        self._prefs = self._load_prefs()
        self.install = {"phase": "idle", "progress": 0, "message": ""}
        self._installing = False

    def _load_prefs(self) -> dict:
        try:
            with open(state_path(), encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_prefs(self):
        try:
            os.makedirs(os.path.dirname(state_path()), exist_ok=True)
            with open(state_path(), "w", encoding="utf-8") as f:
                json.dump(self._prefs, f)
        except OSError:
            pass

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="vch-updater").start()

    def _loop(self):
        time.sleep(FIRST_DELAY_S)
        while True:
            self.check()
            time.sleep(CHECK_EVERY_S)

    def check(self) -> dict:
        status, data = self.fetch()
        state = {"status": status, "current": self.current, "checked_at": int(time.time())}
        if status == "ok" and data:
            state.update(parse_release(data, self.current))
            state["status"] = "update" if state["update_available"] else "current"
        with self._lock:
            self._state = state
        self._maybe_notify(state)
        return self.get_state()

    def _maybe_notify(self, state: dict):
        latest = state.get("latest")
        if state.get("status") != "update" or not latest:
            return
        # avisa una sola vez por version y nunca si el usuario la omitio
        if latest in (self._prefs.get("dismissed"), self._prefs.get("notified")):
            return
        self._prefs["notified"] = latest
        self._save_prefs()
        if self.notify:
            try:
                self.notify("Nueva versión de VortexCore Hub",
                            f"La versión {latest} está disponible (tienes la {self.current}). Haz clic para verla.")
            except Exception:
                pass

    def dismiss(self) -> dict:
        with self._lock:
            latest = self._state.get("latest")
        if latest:
            self._prefs["dismissed"] = latest
            self._save_prefs()
        return self.get_state()

    # descarga el instalador, verifica su sha-256 y entrega la ruta lista para ejecutar
    def start_install(self, on_ready) -> dict:
        with self._lock:
            state = dict(self._state)
            if self._installing:
                return self.get_state()
            setup, sums = state.get("setup_url"), state.get("checksums_url")
            if state.get("status") != "update" or not setup or not sums:
                self.install = {"phase": "error", "progress": 0, "message": "No hay una versión nueva con instalador publicado."}
                return self.get_state()
            if not (setup.startswith(DOWNLOAD_PREFIX) and sums.startswith(DOWNLOAD_PREFIX)):
                self.install = {"phase": "error", "progress": 0, "message": "El instalador no viene del repositorio oficial."}
                return self.get_state()
            self._installing = True
            self.install = {"phase": "downloading", "progress": 0, "message": "Descargando…"}
        threading.Thread(target=self._install_worker, args=(state, on_ready), daemon=True, name="vch-update").start()
        return self.get_state()

    def _install_worker(self, state, on_ready):
        latest = state.get("latest") or "nueva"
        dest = os.path.join(updates_dir(), f"VortexCoreHub-{latest}-Setup.exe")
        try:
            os.makedirs(updates_dir(), exist_ok=True)

            def progress(done, total):
                self.install = {"phase": "downloading", "progress": int(done * 100 / total),
                                "message": f"Descargando {done / 1048576:.1f} de {total / 1048576:.1f} MB"}

            _download(state["setup_url"], dest, progress)
            self.install = {"phase": "verifying", "progress": 100, "message": "Verificando el instalador…"}
            sums_path = dest + ".sha256.txt"
            _download(state["checksums_url"], sums_path)
            with open(sums_path, encoding="utf-8", errors="replace") as f:
                expected = parse_checksums(f.read(), SETUP_NAME)
            os.remove(sums_path)
            if not expected or sha256_file(dest) != expected:
                os.remove(dest)
                self.install = {"phase": "error", "progress": 0,
                                "message": "El instalador descargado no coincide con el publicado; no se instaló nada."}
                return
            self.install = {"phase": "installing", "progress": 100,
                            "message": "Instalando… VortexCore se cerrará y volverá a abrirse sola."}
            on_ready(dest)
        except Exception as e:
            self.install = {"phase": "error", "progress": 0, "message": f"No se pudo actualizar: {e}"}
        finally:
            self._installing = False

    def get_state(self) -> dict:
        with self._lock:
            state = dict(self._state)
        state["install"] = dict(self.install)
        state["dismissed"] = bool(state.get("latest")) and state.get("latest") == self._prefs.get("dismissed")
        state["releases_url"] = RELEASES_URL
        return state
