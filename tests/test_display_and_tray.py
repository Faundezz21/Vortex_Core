import sys
import unittest
from unittest.mock import patch

import dualsense_bridge
import display_manager
import tray_manager


class DisplayManagerTests(unittest.TestCase):
    def test_pick_default_ac_battery_hz(self):
        avail = [48, 60, 120, 144, 180]
        self.assertEqual(display_manager.pick_default_ac_battery_hz(avail, {}), (180, 60))
        self.assertEqual(
            display_manager.pick_default_ac_battery_hz(avail, {"ac_hz": 144, "battery_hz": 48}),
            (144, 48),
        )
        # Si un valor guardado ya no está disponible, vuelve al valor seguro
        self.assertEqual(
            display_manager.pick_default_ac_battery_hz(avail, {"ac_hz": 999, "battery_hz": 30}),
            (180, 60),
        )

    def test_auto_hz_watcher_switches_on_power_change(self):
        watcher = display_manager.AutoHzWatcher()
        watcher.config = {"auto_hz": True, "ac_hz": 165, "battery_hz": 60}
        watcher._last_ac = None

        fake_modes = {"supported": True, "available_hz": [60, 165], "current_hz": 165}
        with patch.object(display_manager, "IS_WINDOWS", True), \
             patch.object(display_manager, "get_display_modes", return_value=fake_modes), \
             patch.object(display_manager, "get_ac_plugged", side_effect=[False, False, True]), \
             patch.object(display_manager, "set_refresh_rate") as mock_set:
            watcher.tick()  # Batería -> 60 Hz
            mock_set.assert_called_once_with(60)

            mock_set.reset_mock()
            watcher.tick()  # Sigue en batería -> no hace nada
            mock_set.assert_not_called()

            fake_modes["current_hz"] = 60
            watcher.tick()  # Enchufado -> 165 Hz
            mock_set.assert_called_once_with(165)


class TrayIconTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Solo en Windows")
    def test_create_temp_hicon_all_ranges(self):
        import ctypes
        for temp in (42, 72, 88):
            hicon = tray_manager._create_temp_hicon(temp, 20)
            self.assertTrue(hicon)
            ctypes.windll.user32.DestroyIcon(hicon)


class DualSenseBridgeTests(unittest.TestCase):
    def test_dualsense_to_xusb_mapping(self):
        buf = bytearray(78)
        buf[0] = 0x31
        buf[2] = 255   # LX full right
        buf[3] = 0     # LY full up
        buf[6] = 200   # L2
        buf[7] = 150   # R2
        buf[9] = 0x20 | 0x00  # Cross (A) + D-pad Up
        buf[10] = 0x01 | 0x20  # L1 (LB) + Options (Start)
        rep = dualsense_bridge.dualsense_to_xusb_report(bytes(buf))
        self.assertIsNotNone(rep)
        self.assertEqual(rep.bLeftTrigger, 200)
        self.assertEqual(rep.bRightTrigger, 150)
        self.assertGreater(rep.sThumbLX, 30000)
        self.assertGreater(rep.sThumbLY, 30000)
        self.assertTrue(rep.wButtons & 0x1000)  # A
        self.assertTrue(rep.wButtons & 0x0001)  # D-pad Up
        self.assertTrue(rep.wButtons & 0x0100)  # LB
        self.assertTrue(rep.wButtons & 0x0010)  # Start
        self.assertIsNone(dualsense_bridge.dualsense_to_xusb_report(b"\x01" * 10))

    def test_dualsense_bt_and_usb_led_packets(self):
        bt_pkt = dualsense_bridge._build_bt_led_packet(
            168, 85, 247, light_out=False, mic_mute=True, player_leds="center", report_len=78
        )
        self.assertEqual(len(bt_pkt), 78)
        self.assertEqual(bt_pkt[0], 0x31)
        self.assertEqual(bt_pkt[4], 0x15)  # MIC | LIGHTBAR | PLAYER_INDICATOR
        self.assertEqual(bt_pkt[11], 0x01)
        self.assertEqual(bt_pkt[41], 0x01)  # LED_BRIGHTNESS_CONTROL_ENABLE only (no LIGHT_OUT)
        self.assertEqual(bt_pkt[44], 0x00)
        self.assertEqual(bt_pkt[46], 0x04)
        self.assertEqual((bt_pkt[47], bt_pkt[48], bt_pkt[49]), (168, 85, 247))

        usb_pkt = dualsense_bridge._build_usb_led_packet(
            0, 240, 255, light_out=False, mic_mute=False, player_leds="all",
            trigger_l2_mode="weapon", trigger_r2_mode="machine", trigger_force=90,
            report_len=48
        )
        self.assertEqual(len(usb_pkt), 48)
        self.assertEqual(usb_pkt[0], 0x02)
        self.assertEqual(usb_pkt[1] & 0x0C, 0x0C)  # R2 (0x04) | L2 (0x08) trigger motors enabled
        self.assertEqual(usb_pkt[2], 0x15)
        self.assertEqual(usb_pkt[11], 0x06)  # R2 mode = machine (0x06)
        self.assertEqual(usb_pkt[22], 0x02)  # L2 mode = weapon (0x02)
        self.assertEqual(usb_pkt[39], 0x01)
        self.assertEqual(usb_pkt[42], 0x00)
        self.assertEqual(usb_pkt[44], 0x1F)
        self.assertEqual((usb_pkt[45], usb_pkt[46], usb_pkt[47]), (0, 240, 255))

    def test_dualsensex_adaptive_triggers_and_udp_parser(self):
        self.assertEqual(dualsense_bridge.encode_adaptive_trigger("off")[0], 0x05)
        self.assertEqual(dualsense_bridge.encode_adaptive_trigger("continuous", 80)[0], 0x01)
        self.assertEqual(dualsense_bridge.encode_adaptive_trigger("weapon", 85)[0], 0x02)
        self.assertEqual(dualsense_bridge.encode_adaptive_trigger("machine", 90)[0], 0x06)
        self.assertEqual(dualsense_bridge.encode_adaptive_trigger("bow", 85)[0], 0x02)
        self.assertEqual(dualsense_bridge.encode_adaptive_trigger("hard", 100)[:3], bytes([0x01, 4, 255]))

        # Configuración automática por género de juego
        self.assertEqual(dualsense_bridge.resolve_auto_triggers(None)[:2], ("off", "off"))
        self.assertEqual(dualsense_bridge.resolve_auto_triggers("TslGame.exe")[:2], ("bow", "weapon"))
        self.assertEqual(dualsense_bridge.resolve_auto_triggers("RocketLeague.exe")[:2], ("continuous", "continuous"))
        self.assertEqual(dualsense_bridge.resolve_auto_triggers("eldenring.exe")[:2], ("bow", "weapon"))

        dsx_payload = b'''{
            "instructions": [
                {"type": 1, "parameters": [0, 1, 16, 35, 7]},
                {"type": 1, "parameters": [0, 2, 18, 25, 8]},
                {"type": 2, "parameters": [0, 34, 211, 238]},
                {"type": 3, "parameters": [0, false, true, true, true, false]},
                {"type": 5, "parameters": [0, 1]}
            ]
        }'''
        patch_cfg = dualsense_bridge.parse_dsx_udp_packet(dsx_payload)
        self.assertEqual(patch_cfg["trigger_l2_mode"], "weapon")
        self.assertEqual(patch_cfg["trigger_r2_mode"], "machine")
        self.assertEqual(patch_cfg["led_color"], "#22d3ee")
        self.assertEqual(patch_cfg["player_leds"], "three")
        self.assertTrue(patch_cfg["mic_mute"])


class LowBatteryAlertTests(unittest.TestCase):
    def test_notifies_once_and_resets_after_charge(self):
        import test_server  # noqa: F401
        import vortex_engine as ve

        mgr = ve.VortexCoreManager.__new__(ve.VortexCoreManager)
        mgr._low_battery_alerted = set()
        notices = []

        class FakeTray:
            def notify(self, title, msg):
                notices.append((title, msg))

        with patch.object(ve, "_tray_ref", FakeTray()):
            low_dev = [{"name": "Razer Barracuda X 2.4", "type": "headphone", "percent": 12, "plugged": False}]
            mgr._check_low_battery_alerts(low_dev)
            mgr._check_low_battery_alerts(low_dev)
            self.assertEqual(len(notices), 1)
            self.assertIn("12%", notices[0][1])

            # Al cargarse >= 30% se reinicia y puede volver a avisar después
            mgr._check_low_battery_alerts([{"name": "Razer Barracuda X 2.4", "type": "headphone", "percent": 40, "plugged": False}])
            mgr._check_low_battery_alerts(low_dev)
            self.assertEqual(len(notices), 2)


if __name__ == "__main__":
    unittest.main()
