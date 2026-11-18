# pruebas del monitor de red por app y de la deteccion del servidor del juego
import os
import socket
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import net_monitor as nm  # noqa: E402


def v4_payload(pid, size, ip, port, extra=12):
    return struct.pack("<II", pid, size) + socket.inet_aton(ip) + socket.inet_aton("192.168.1.5") + \
        struct.pack(">HH", port, 50000) + b"\0" * extra


class PayloadTests(unittest.TestCase):
    def test_udp_v4(self):
        self.assertEqual(nm.parse_payload(42, v4_payload(10, 120, "45.7.1.2", 7777)),
                         (10, 120, "tx", "udp", "45.7.1.2", 7777))

    def test_tcp_v6(self):
        data = struct.pack("<II", 7, 1500) + socket.inet_pton(socket.AF_INET6, "2606:4700::1") + \
            socket.inet_pton(socket.AF_INET6, "fe80::1") + struct.pack(">HH", 443, 50001) + b"\0" * 8
        self.assertEqual(nm.parse_payload(27, data), (7, 1500, "rx", "tcp", "2606:4700::1", 443))

    def test_unknown_or_short(self):
        self.assertIsNone(nm.parse_payload(99, v4_payload(1, 1, "1.1.1.1", 1)))
        self.assertIsNone(nm.parse_payload(42, b"\0" * 10))

    def test_loopback_ignored(self):
        self.assertIsNone(nm.parse_payload(11, v4_payload(5, 900, "127.0.0.1", 8765)))

    def test_public_ip(self):
        self.assertTrue(nm.is_public_ip("45.7.1.2"))
        for ip in ("192.168.1.1", "10.0.0.1", "127.0.0.1", "239.255.255.250", "fe80::1", "nada"):
            self.assertFalse(nm.is_public_ip(ip), ip)


class WindowTests(unittest.TestCase):
    def test_rates_use_complete_seconds(self):
        w = nm.TrafficWindow(window_s=3)
        for sec in (97, 98, 99):
            w.add(sec, 1, 3000, "rx", "tcp", "1.1.1.1", 443)
            w.add(sec, 1, 300, "tx", "tcp", "1.1.1.1", 443)
        w.add(100, 1, 999999, "rx", "tcp", "1.1.1.1", 443)
        procs, remotes = w.rates(100)
        self.assertEqual(procs[1], (3000.0, 300.0))
        self.assertEqual(remotes[(1, "tcp", "1.1.1.1", 443)], (3300.0, 2.0))

    def test_group_by_app(self):
        apps = nm.group_by_app({1: (100.0, 10.0), 2: (50.0, 5.0), 3: (900.0, 0.0), 4: (1.0, 1.0)},
                               {1: "chrome.exe", 2: "Chrome.exe", 3: "steam.exe"})
        self.assertEqual([a["name"] for a in apps], ["steam.exe", "chrome.exe", "Sistema"])
        self.assertEqual(apps[1]["down_bps"], 150)
        self.assertEqual(sorted(apps[1]["pids"]), [1, 2])


class GameServerTests(unittest.TestCase):
    NAMES = {10: "VALORANT-Win64-Shipping.exe", 20: "Discord.exe", 30: "chrome.exe", 40: "RocketLeague.exe",
             50: "claude.exe"}

    def test_picks_udp_game_not_voice_chat(self):
        remotes = {
            (10, "udp", "45.7.1.2", 7777): (9000.0, 64.0),
            (10, "udp", "45.7.1.9", 7000): (100.0, 1.0),
            (20, "udp", "66.22.1.1", 50001): (20000.0, 100.0),
            (30, "udp", "142.250.1.1", 443): (90000.0, 300.0),
            (10, "udp", "192.168.1.1", 53): (50.0, 90.0),
        }
        g = nm.pick_game_server(remotes, self.NAMES)
        self.assertEqual((g["pid"], g["ip"], g["port"]), (10, "45.7.1.2", 7777))

    def test_prefer_name_and_threshold(self):
        remotes = {(40, "udp", "34.1.2.3", 7900): (2000.0, 3.0)}
        self.assertIsNone(nm.pick_game_server(remotes, self.NAMES))
        self.assertEqual(nm.pick_game_server(remotes, self.NAMES, "RocketLeague.exe")["pid"], 40)

    def test_non_game_preference_ignored(self):
        # el foco en claude o un navegador no debe convertirlo en juego
        remotes = {(50, "udp", "160.79.104.10", 443): (900.0, 3.0), (50, "udp", "160.79.104.10", 9000): (900.0, 9.0)}
        self.assertIsNone(nm.pick_game_server(remotes, self.NAMES, "claude.exe"))

    def test_quic_and_dns_ignored(self):
        remotes = {(40, "udp", "142.250.1.1", 443): (9000.0, 80.0), (40, "udp", "1.1.1.1", 53): (900.0, 30.0)}
        self.assertIsNone(nm.pick_game_server(remotes, self.NAMES))

    def test_ping_stats(self):
        self.assertEqual(nm.ping_stats([]), {"ping_ms": None, "jitter_ms": None, "loss_pct": None, "responds": None})
        st = nm.ping_stats([30, 34, None, 30, 32])
        self.assertEqual((st["ping_ms"], st["loss_pct"], st["responds"]), (32, 20, True))
        self.assertEqual(st["jitter_ms"], 3.3)
        self.assertEqual(nm.ping_stats([None, None])["responds"], False)


if __name__ == "__main__":
    unittest.main()
