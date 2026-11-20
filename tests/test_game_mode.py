# pruebas del modo juego, del medidor compartido, del atajo y de la bateria del dualsense
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import fps_monitor  # noqa: E402
import game_mode  # noqa: E402
import game_overlay  # noqa: E402
import hw_sensors  # noqa: E402

GAME = {"fps": 144, "app": "RocketLeague.exe"}


class GameModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = game_mode.config_path
        game_mode.config_path = lambda: os.path.join(self.tmp.name, "gamemode.json")
        self.profile = "SILENT"
        self.calls = []

    def tearDown(self):
        game_mode.config_path = self._orig
        self.tmp.cleanup()

    def make(self, manual=False):
        def set_profile(p):
            self.calls.append(p)
            self.profile = p
        gm = game_mode.GameMode(lambda: self.profile, set_profile, lambda: None, is_manual=lambda: manual)
        gm.set_enabled(True)
        return gm

    def test_switches_and_restores_previous_profile(self):
        gm = self.make()
        gm.tick(now=100, snapshot=GAME)
        self.assertEqual(self.profile, "PERFORMANCE")
        self.assertEqual(gm.state()["game"], "RocketLeague")
        # pantallas de carga o alt+tab breves no lo devuelven
        gm.tick(now=150, snapshot=None)
        self.assertEqual(self.profile, "PERFORMANCE")
        gm.tick(now=100 + game_mode.GRACE_S + 1, snapshot=None)
        self.assertEqual(self.profile, "SILENT")
        self.assertFalse(gm.active)

    def test_respects_manual_change_during_game(self):
        gm = self.make()
        gm.tick(now=0, snapshot=GAME)
        self.profile = "ECO"  # el usuario cambio a mano
        gm.tick(now=game_mode.GRACE_S + 5, snapshot=None)
        self.assertEqual(self.profile, "ECO")

    def test_unknown_profile_restores_windows_default(self):
        self.profile = "STANDARD"
        gm = self.make()
        gm.tick(now=0, snapshot=GAME)
        gm.tick(now=game_mode.GRACE_S + 5, snapshot=None)
        self.assertEqual(self.profile, "DEFAULT")

    def test_ignores_non_games_manual_mode_and_disabled(self):
        gm = self.make()
        gm.tick(now=0, snapshot={"fps": 120, "app": "brave.exe"})
        self.assertEqual(self.calls, [])
        gm_manual = self.make(manual=True)
        gm_manual.tick(now=0, snapshot=GAME)
        self.assertEqual(self.calls, [])
        gm.set_enabled(False)
        gm.tick(now=0, snapshot=GAME)
        self.assertEqual(self.calls, [])

    def test_disabling_mid_game_restores(self):
        gm = self.make()
        gm.tick(now=0, snapshot=GAME)
        gm.set_enabled(False)
        self.assertEqual(self.profile, "SILENT")

    def test_enabled_is_saved(self):
        self.make()
        again = game_mode.GameMode(lambda: "DEFAULT", lambda p: None, lambda: None)
        self.assertTrue(again.enabled)


class SharedFpsMonitorTests(unittest.TestCase):
    def test_stops_only_when_nobody_needs_it(self):
        m = fps_monitor.FpsMonitor(None)
        m.start("overlay")
        m.start("gamemode")
        m.stop("overlay")
        self.assertTrue(m._wanted)
        m.stop("gamemode")
        self.assertFalse(m._wanted)


class SoloKeyTests(unittest.TestCase):
    def test_solo_keys_allowed(self):
        for vk in (0x2D, 0x24, 0x13, 0x91, 0x67, 0x77):
            self.assertEqual(game_overlay.sanitize_hotkey({"mods": 0, "vk": vk}), {"mods": 0, "vk": vk})
        self.assertIsNone(game_overlay.sanitize_hotkey({"mods": 0, "vk": 0x48}))
        self.assertEqual(game_overlay.hotkey_label({"mods": 0, "vk": 0x2D}), "Insert")


class DualSenseTests(unittest.TestCase):
    def report(self, rid, size, offset, status):
        data = bytearray(size)
        data[0] = rid
        data[offset] = status
        return bytes(data)

    def test_bluetooth_full_report(self):
        r = hw_sensors.parse_dualsense_report(self.report(0x31, 78, 54, 0x06))
        self.assertEqual(r, {"mode": "full", "percent": 65, "charging": False, "full": False})

    def test_usb_charging_and_full(self):
        self.assertTrue(hw_sensors.parse_dualsense_report(self.report(0x01, 64, 53, 0x13))["charging"])
        self.assertEqual(hw_sensors.parse_dualsense_report(self.report(0x01, 64, 53, 0x2A))["percent"], 100)

    def test_simple_mode_and_bad_data(self):
        self.assertEqual(hw_sensors.parse_dualsense_report(self.report(0x01, 10, 5, 0)), {"mode": "simple"})
        # reporte simple por bluetooth rellenado con ceros hasta 78 bytes, como lo entrega windows
        padded = bytes.fromhex("01837f827d0800380000") + bytes(68)
        self.assertEqual(hw_sensors.parse_dualsense_report(padded, bluetooth=True), {"mode": "simple"})
        self.assertIsNone(hw_sensors.parse_dualsense_report(self.report(0x31, 78, 54, 0xFF)))
        self.assertIsNone(hw_sensors.parse_dualsense_report(b""))


if __name__ == "__main__":
    unittest.main()
