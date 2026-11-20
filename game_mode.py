# modo juego: pasa a rendimiento al detectar un juego y vuelve al perfil anterior al cerrarlo

import json
import os
import threading
import time

from fps_monitor import is_game

TARGET_PROFILE = "PERFORMANCE"
RESTORABLE = ("ECO", "SILENT", "DEFAULT")
GRACE_S = 90
TICK_S = 3


def config_path() -> str:
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VortexCoreHub")
    return os.path.join(base, "gamemode.json")


class GameMode:
    def __init__(self, get_profile, set_profile, get_snapshot, is_manual=lambda: False,
                 fps_start=None, fps_stop=None):
        self.get_profile = get_profile
        self.set_profile = set_profile
        self.get_snapshot = get_snapshot
        self.is_manual = is_manual
        self.fps_start = fps_start
        self.fps_stop = fps_stop
        self.enabled = self._load()
        self.active = False
        self.prev_profile = None
        self.game = None
        self._last_game = 0.0
        self._lock = threading.Lock()
        self._sync_fps()

    def _load(self) -> bool:
        try:
            with open(config_path(), encoding="utf-8") as f:
                return bool(json.load(f).get("enabled", False))
        except (OSError, ValueError, AttributeError):
            return False

    def _save(self):
        try:
            os.makedirs(os.path.dirname(config_path()), exist_ok=True)
            with open(config_path(), "w", encoding="utf-8") as f:
                json.dump({"enabled": self.enabled}, f)
        except OSError:
            pass

    def _sync_fps(self):
        # el medidor de fps es el que sabe si hay un juego en primer plano
        fn = self.fps_start if self.enabled else self.fps_stop
        if fn:
            try:
                fn()
            except Exception:
                pass

    def set_enabled(self, enabled: bool) -> dict:
        with self._lock:
            self.enabled = bool(enabled)
            self._save()
            if not self.enabled and self.active:
                self._restore()
        self._sync_fps()
        return self.state()

    def state(self) -> dict:
        return {"enabled": self.enabled, "active": self.active, "game": self.game,
                "prev_profile": self.prev_profile, "target": TARGET_PROFILE}

    def _restore(self):
        # solo vuelve atras si el usuario no cambio el perfil durante la partida
        if self.prev_profile and self.prev_profile != TARGET_PROFILE and self.get_profile() == TARGET_PROFILE:
            # un perfil desconocido (como el inicial) vuelve al modo windows por defecto
            self.set_profile(self.prev_profile if self.prev_profile in RESTORABLE else "DEFAULT")
        self.active = False
        self.prev_profile = None
        self.game = None

    def tick(self, now: float | None = None, snapshot=None):
        now = time.time() if now is None else now
        with self._lock:
            if not self.enabled:
                return
            snap = self.get_snapshot() if snapshot is None else snapshot
            if is_game(snap):
                self._last_game = now
                self.game = os.path.splitext(snap.get("app") or "")[0] or self.game
                if not self.active and not self.is_manual():
                    self.prev_profile = self.get_profile()
                    if self.prev_profile != TARGET_PROFILE:
                        self.set_profile(TARGET_PROFILE)
                    self.active = True
            elif self.active and now - self._last_game > GRACE_S:
                self._restore()

    def start(self):
        def loop():
            while True:
                time.sleep(TICK_S)
                try:
                    self.tick()
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True, name="vch-gamemode").start()
