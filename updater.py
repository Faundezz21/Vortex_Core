# aviso de nuevas versiones consultando el ultimo release publicado en github

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
    for line in (body or "").splitlines():
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
    return {
        "latest": tag.lstrip("vV") or None,
        "update_available": is_newer(tag, current),
        "url": data.get("html_url") or RELEASES_URL,
        "setup_url": setup,
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


def state_path() -> str:
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub")
    return os.path.join(base, "updates.json")


class UpdateChecker:
    def __init__(self, current_version: str, notify=None, fetch=fetch_latest):
        self.current = current_version
        self.notify = notify
        self.fetch = fetch
        self._lock = threading.Lock()
        self._state = {"status": "pending", "current": current_version, "checked_at": None}
        self._prefs = self._load_prefs()

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

    def get_state(self) -> dict:
        with self._lock:
            state = dict(self._state)
        state["dismissed"] = bool(state.get("latest")) and state.get("latest") == self._prefs.get("dismissed")
        state["releases_url"] = RELEASES_URL
        return state
