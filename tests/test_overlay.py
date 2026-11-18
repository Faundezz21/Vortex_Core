# pruebas del parser de presentmon y de las filas del overlay en juego
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import fps_monitor  # noqa: E402
import game_overlay  # noqa: E402

# encabezado real de presentmon 2.6 con --v1_metrics
HEADER = ("Application,ProcessID,SwapChainAddress,Runtime,SyncInterval,PresentFlags,Dropped,"
          "TimeInSeconds,msInPresentAPI,msBetweenPresents,AllowsTearing")


class PresentMonParsingTests(unittest.TestCase):
    def test_header_and_row(self):
        h = fps_monitor.parse_header(HEADER)
        self.assertIsNotNone(h)
        row = fps_monitor.parse_row("game.exe,4242,0x1,DXGI,0,0,0,12.5,0.1,6.94,1", h)
        self.assertEqual(row, (4242, "game.exe", 12.5, 6.94))

    def test_utf16_stream(self):
        import io
        data = (HEADER + "\r\ngame.exe,1,0x1,DXGI,0,0,0,1.0,0.1,8.0,1\r\n").encode("utf-16")
        lines = list(fps_monitor._text_stream(io.BytesIO(data)))
        h = fps_monitor.parse_header(lines[0])
        self.assertEqual(fps_monitor.parse_row(lines[1], h), (1, "game.exe", 1.0, 8.0))

    def test_header_old_casing(self):
        h = fps_monitor.parse_header("Application,ProcessID,TimeInSeconds,MsBetweenPresents")
        self.assertEqual(h["ms"], 3)

    def test_header_without_metrics(self):
        self.assertIsNone(fps_monitor.parse_header("Application,ProcessID,FrameTime"))

    def test_bad_rows(self):
        h = fps_monitor.parse_header(HEADER)
        self.assertIsNone(fps_monitor.parse_row("game.exe,abc,0x1", h))
        self.assertIsNone(fps_monitor.parse_row("game.exe,1,0x1,DXGI,0,0,1,x,1.0,0,0.1", h))
        self.assertIsNone(fps_monitor.parse_row("game.exe,1,0x1,DXGI,0,0,1,x,1.0,5000,0.1", h))

    def test_stats(self):
        frames = [(i / 144, 1000 / 144) for i in range(144)]
        st = fps_monitor.compute_stats(frames)
        self.assertEqual(st["fps"], 144)
        self.assertEqual(st["frametime_ms"], 6.9)
        self.assertIsNone(fps_monitor.compute_stats([]))

    def test_low1_uses_worst_frames(self):
        frames = [(0, 10.0)] * 99 + [(0, 50.0)]
        st = fps_monitor.compute_stats(frames)
        self.assertEqual(st["low1_fps"], 20)

    def test_pick_pid_same_exe(self):
        apps = {10: "brave.exe", 20: "brave.exe", 30: "game.exe"}
        seen = {10: 99.0, 20: 99.5, 30: 99.9}
        self.assertEqual(fps_monitor.pick_pid(5, "Brave.exe", apps, seen, 100.0), 20)
        self.assertEqual(fps_monitor.pick_pid(30, "game.exe", apps, seen, 100.0), 30)
        self.assertEqual(fps_monitor.pick_pid(5, "otro.exe", apps, seen, 100.0), 5)

    def test_find_presentmon_missing(self):
        self.assertIsNone(fps_monitor.find_presentmon(os.path.join(ROOT, "no-existe")))


class OverlayRowsTests(unittest.TestCase):
    TEL = {"cpu_usage": 45, "cpu_temp": 82, "cpu_freq": "4.20", "gpu_usage": 97, "gpu_temp": 70,
           "gpu_power": "95.4", "gpu_freq_mhz": 2550, "ram_used": "12.1", "ram_total": "15.7",
           "ram_pct": 77, "fan1_rpm": 4100, "fan2_rpm": None}

    def test_model_full(self):
        fps = {"fps": 144, "frametime_ms": 6.9, "low1_fps": 101, "app": "Cyberpunk2077.exe"}
        m = game_overlay.build_model(self.TEL, fps, game_overlay.ITEMS, history=[140, 144])
        self.assertEqual(m["fps"]["value"], 144)
        self.assertEqual(m["fps"]["frametime"], "6.9 ms")
        self.assertEqual(m["fps"]["low"], "1% low 101")
        self.assertEqual(m["fps"]["app"], "Cyberpunk2077")
        self.assertEqual(m["fps"]["history"], [140, 144])
        rows = {r["label"]: r for r in m["rows"]}
        self.assertEqual((rows["CPU"]["value"], rows["CPU"]["extra"]), ("45%", "4.2 GHz"))
        self.assertEqual(rows["CPU"]["pill"], ("82°C", game_overlay.C_WARN))
        self.assertAlmostEqual(rows["CPU"]["bar"], 0.45)
        self.assertEqual(rows["GPU"]["extra"], "95 W · 2550 MHz")
        self.assertEqual(rows["GPU"]["bar_color"], game_overlay.C_ACCENT)
        self.assertEqual((rows["RAM"]["value"], rows["RAM"]["extra"]), ("12.1", "/ 16 GB"))
        self.assertEqual((rows["FAN"]["value"], rows["FAN"]["extra"], rows["FAN"]["bar"]), ("4100", "RPM", None))

    def test_model_missing_data(self):
        m = game_overlay.build_model({}, None, ["fps", "cpu", "fan"], fps_note="requiere admin")
        self.assertIsNone(m["fps"]["value"])
        self.assertEqual(m["fps"]["note"], "requiere admin")
        self.assertEqual(len(m["rows"]), 1)
        self.assertEqual((m["rows"][0]["value"], m["rows"][0]["pill"], m["rows"][0]["bar"]), ("--", None, None))
        self.assertEqual(game_overlay.build_model({}, None, ["fps"])["fps"]["note"], "sin juego activo")

    def test_model_height(self):
        m = game_overlay.build_model(self.TEL, None, game_overlay.ITEMS)
        self.assertEqual(game_overlay.model_height(m, 1.0), 24 + 76 + 12 + 30 * 3 + 22 * 2 + 6 * 4)
        only_fps = game_overlay.build_model({}, None, ["fps"])
        self.assertEqual(game_overlay.model_height(only_fps, 1.0), 24 + 76)

    def test_ping_row(self):
        row = lambda net: game_overlay.build_model({}, None, ["ping"], net=net)["rows"][0]
        self.assertEqual(row(None)["value"], "--")
        self.assertEqual(row({"available": False, "error": "requiere admin"})["extra"], "requiere admin")
        self.assertEqual(row({"available": True, "game": None})["extra"], "sin juego en línea")
        self.assertEqual(row({"available": True, "game": {"responds": False}})["extra"], "el servidor no responde ping")
        r = row({"available": True, "game": {"ping_ms": 34, "jitter_ms": 2.4, "loss_pct": 0, "responds": True}})
        self.assertEqual((r["value"], r["extra"]), ("34 ms", "± 2 · pérdida 0%"))
        self.assertEqual(r["pill"], ("Buena", game_overlay.C_OK))
        self.assertEqual(game_overlay.ping_quality(90, 5, 1), ("Regular", game_overlay.C_WARN))
        self.assertEqual(game_overlay.ping_quality(40, 5, 5), ("Mala", game_overlay.C_HOT))

    def test_sanitize_config(self):
        cfg = game_overlay.sanitize_config({"corner": "xx", "size": "l", "opacity": 5,
                                            "items": ["gpu", "bad", "fps"], "enabled": 1})
        self.assertEqual(cfg["corner"], "tl")
        self.assertEqual(cfg["size"], "l")
        self.assertEqual(cfg["opacity"], 30)
        self.assertEqual(cfg["items"], ["fps", "gpu"])
        self.assertTrue(cfg["enabled"])
        self.assertEqual(game_overlay.sanitize_config("x"), game_overlay.DEFAULT_CONFIG)


if __name__ == "__main__":
    unittest.main()
