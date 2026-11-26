"""
Pruebas de que la telemetría no inventa valores: sin sensor -> None ("N/D" en la interfaz).

    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["VORTEXCORE_TEST_MODE"] = "1"

import test_server  # noqa: E402,F401  (aplica los stubs de Windows si hace falta)
import hw_sensors  # noqa: E402
import vortex_engine as ve  # noqa: E402


class SensorParsingTests(unittest.TestCase):
    def test_nvidia_voltage_regex(self):
        sample = "    Voltage\n        Graphics                          : 712.500 mV\n"
        m = hw_sensors._VOLT_RE.search(sample)
        self.assertEqual(round(float(m.group(1))), 712)

    def test_nvidia_voltage_missing(self):
        self.assertIsNone(hw_sensors._VOLT_RE.search("    Voltage\n        Graphics : N/A\n"))

    def test_clean_bt_name(self):
        self.assertEqual(hw_sensors._clean_bt_name("Redmi Buds 6 Active Hands-Free AG"), "Redmi Buds 6 Active")
        self.assertEqual(hw_sensors._clean_bt_name("WH-1000XM4 Avrcp Transport"), "WH-1000XM4")

    def test_guid_roundtrip(self):
        g = hw_sensors.GUID.from_string("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}")
        self.assertEqual(str(g), "104ea319-6ee2-4701-bd47-8ddbf425bbe5")


@unittest.skipIf(sys.platform == "win32", "En Windows real los sensores sí devuelven valores")
class NoFakeTelemetryTests(unittest.TestCase):
    """Sin sensores disponibles, el gestor real no debe publicar números inventados."""

    @classmethod
    def setUpClass(cls):
        orig = ve.VortexCoreManager._monitor_loop
        ve.VortexCoreManager._monitor_loop = lambda self: None  # sin hilo de monitoreo
        try:
            cls.m = ve.VortexCoreManager()
        finally:
            ve.VortexCoreManager._monitor_loop = orig

    def test_sensor_fields_start_empty(self):
        t = self.m.telemetry
        for key in ("cpu_temp", "cpu_freq_mhz", "cpu_volt_mv", "gpu_temp", "gpu_volt_mv",
                    "gpu_mem_freq_mhz", "ram_speed_mts", "fan1_rpm", "fan2_rpm", "fan_dba"):
            self.assertIsNone(t[key], key)

    def test_battery_devices_have_no_invented_percent(self):
        for dev in self.m._get_battery_devices():
            if dev["type"] not in ("laptop",):
                self.assertIsNone(dev["percent"], dev)


class PeripheralClassificationTests(unittest.TestCase):
    """Detección genérica de periféricos USB: tipo por clase de Windows, nombre real."""

    def test_mouse_with_macro_keyboard_is_a_mouse(self):
        # Ratones gaming exponen también una interfaz de teclado para macros
        self.assertEqual(hw_sensors.classify_device({"Mouse", "Keyboard", "HIDClass"}, []), "mouse")

    def test_usb_headset_is_headphone(self):
        self.assertEqual(hw_sensors.classify_device({"MEDIA", "HIDClass"}, ["Dispositivo de control del consumidor"]), "headphone")

    def test_plain_keyboard(self):
        self.assertEqual(hw_sensors.classify_device({"Keyboard", "HIDClass"}, []), "keyboard")

    def test_game_controller(self):
        self.assertEqual(hw_sensors.classify_device({"HIDClass"}, ["HID-compliant game controller"]), "gamepad")
        self.assertEqual(hw_sensors.classify_device({"HIDClass"}, ["Controlador de juegos compatible con HID"]), "gamepad")
        self.assertEqual(hw_sensors.classify_device({"XnaComposite"}, []), "gamepad")

    def test_not_a_peripheral(self):
        self.assertIsNone(hw_sensors.classify_device({"Camera", "Image"}, []))
        self.assertIsNone(hw_sensors.classify_device({"HIDClass"}, ["Dispositivo definido por el proveedor"]))

    def test_names(self):
        self.assertEqual(hw_sensors.pretty_device_name("G502 HERO", "G502 HERO SE", "Logitech", "mouse"), "Logitech G502 HERO")
        self.assertEqual(hw_sensors.pretty_device_name("", "Razer Barracuda X 2.4", "(Controladora de host USB estándar)", "headphone"),
                         "Razer Barracuda X 2.4")
        self.assertEqual(hw_sensors.pretty_device_name("", "USB DEVICE", "(Controladora de host USB estándar)", "keyboard"), "Teclado USB")
        self.assertEqual(hw_sensors.pretty_device_name(None, None, None, "gamepad"), "Mando USB")

    def test_razer_barracuda_battery_parsing(self):
        raw = bytes.fromhex("01 80 11 50 49 01 ec 6e 05 3a 00 07 00 06 82 00 8d 0f") + b"\x00" * 46
        self.assertEqual(hw_sensors.parse_razer_barracuda_battery(raw), 76)
        self.assertIsNone(hw_sensors.parse_razer_barracuda_battery(b"\x00" * 64))


class BatteryHealthTests(unittest.TestCase):
    def test_missing_battery(self):
        self.assertEqual(hw_sensors.compute_battery_health(None, None), {"present": False})
        self.assertEqual(hw_sensors.compute_battery_health(0, 0), {"present": False})

    def test_healthy_and_worn_battery(self):
        ok = hw_sensors.compute_battery_health(70000, 64400, cycle_count=42, manufacturer="HP")
        self.assertTrue(ok["present"])
        self.assertEqual(ok["health_pct"], 92.0)
        self.assertEqual(ok["wear_pct"], 8.0)
        self.assertEqual(ok["cycle_count"], 42)
        self.assertEqual(ok["condition"], "Excelente")

        worn = hw_sensors.compute_battery_health(70000, 45500, cycle_count=410)
        self.assertEqual(worn["health_pct"], 65.0)
        self.assertEqual(worn["wear_pct"], 35.0)
        self.assertEqual(worn["condition"], "Desgastada")


class CoreAndNetworkTelemetryTests(unittest.TestCase):
    def test_parse_ping_ms(self):
        self.assertEqual(hw_sensors.parse_ping_ms("Respuesta desde 1.1.1.1: bytes=32 tiempo=14ms TTL=56"), 14)
        self.assertEqual(hw_sensors.parse_ping_ms("Reply from 1.1.1.1: bytes=32 time=22ms TTL=56"), 22)
        self.assertEqual(hw_sensors.parse_ping_ms("Reply from 1.1.1.1: bytes=32 time<1ms TTL=56"), 1)
        self.assertIsNone(hw_sensors.parse_ping_ms("Tiempo de espera agotado para esta solicitud."))
        self.assertIsNone(hw_sensors.parse_ping_ms(""))

    def test_select_primary_net_iface(self):
        import socket
        from types import SimpleNamespace
        stats = {
            "Loopback Pseudo-Interface 1": SimpleNamespace(isup=True, speed=1073),
            "Ethernet": SimpleNamespace(isup=False, speed=1000),
            "Wi-Fi": SimpleNamespace(isup=True, speed=433),
        }
        addrs = {
            "Wi-Fi": [SimpleNamespace(family=socket.AF_INET, address="192.168.1.55")],
        }
        io = {
            "Wi-Fi": SimpleNamespace(bytes_recv=204800, bytes_sent=40960),
        }
        sel = ve.select_primary_net_iface(stats, addrs, io)
        self.assertEqual(sel, {"name": "Wi-Fi", "link_mbps": 433, "ipv4": "192.168.1.55"})
        self.assertIsNone(ve.select_primary_net_iface({}, {}, {}))

    def test_core_and_network_defaults_are_real(self):
        orig = ve.VortexCoreManager._monitor_loop
        ve.VortexCoreManager._monitor_loop = lambda self: None
        try:
            m = ve.VortexCoreManager()
        finally:
            ve.VortexCoreManager._monitor_loop = orig
        self.assertEqual(m.telemetry["cpu_core_temps"], [])
        self.assertEqual(m.telemetry["cpu_acpi_zones"], [])
        self.assertIsNone(m.telemetry["cpu_temp_source"])
        self.assertIsNone(m.telemetry["network"]["ping_ms"])

    def test_parse_coretemp_bytes(self):
        import struct
        buf = bytearray(2688)
        struct.pack_into("<II", buf, 1536, 3, 1)  # 3 cores, 1 CPU
        struct.pack_into("<3f", buf, 1544, 52.5, 58.0, 49.0)
        struct.pack_into("<BB", buf, 2684, 0, 0)  # Celsius, not delta
        parsed = hw_sensors.parse_coretemp_bytes(bytes(buf))
        self.assertEqual(
            parsed,
            [
                {"name": "Core #1", "temp_c": 52.5},
                {"name": "Core #2", "temp_c": 58.0},
                {"name": "Core #3", "temp_c": 49.0},
            ],
        )

        # Fahrenheit conversion
        struct.pack_into("<II", buf, 1536, 1, 1)
        struct.pack_into("<1f", buf, 1544, 122.0)  # 50.0 C
        struct.pack_into("<BB", buf, 2684, 1, 0)
        self.assertEqual(hw_sensors.parse_coretemp_bytes(bytes(buf)), [{"name": "Core #1", "temp_c": 50.0}])

        # Delta-to-TjMax raw mode should not pretend to be absolute C
        struct.pack_into("<BB", buf, 2684, 0, 1)
        self.assertEqual(hw_sensors.parse_coretemp_bytes(bytes(buf)), [])

    def test_parse_hwinfo_bytes(self):
        import struct
        entry_off = 44
        entry_size = 324
        entry_cnt = 2
        buf = bytearray(entry_off + entry_cnt * entry_size)
        buf[0:4] = b"HWiS"
        struct.pack_into("<III", buf, 0x20, entry_off, entry_size, entry_cnt)

        # Entry 0: Core #0 temperature
        struct.pack_into("<III", buf, entry_off, 1, 0, 1)
        buf[entry_off + 0x0C:entry_off + 0x0C + 7] = b"Core #0"
        struct.pack_into("<d", buf, entry_off + 0x11C, 61.4)

        # Entry 1: Distance to TjMAX (must be excluded)
        off1 = entry_off + entry_size
        struct.pack_into("<III", buf, off1, 1, 0, 2)
        buf[off1 + 0x0C:off1 + 0x0C + 25] = b"Core #0 Distance to TjMAX"
        struct.pack_into("<d", buf, off1 + 0x11C, 39.0)

        self.assertEqual(hw_sensors.parse_hwinfo_bytes(bytes(buf)), [{"name": "Core #0", "temp_c": 61.4}])
        self.assertEqual(hw_sensors.parse_hwinfo_bytes(b"BAD!"), [])

    def test_extract_lhm_core_temps(self):
        items = [
            ("Core Max", 65.0),
            ("Core Average", 58.0),
            ("P-Core #1", 62.34),
            ("P-Core #1 Distance to TjMax", 38.0),
            ("E-Core #1", 54.0),
            ("CPU Package", 63.0),
            ("Bad Core", None),
            ("Frozen Core", 0.0),
        ]
        self.assertEqual(
            hw_sensors.extract_lhm_core_temps(items),
            [
                {"name": "P-Core #1", "temp_c": 62.3},
                {"name": "E-Core #1", "temp_c": 54.0},
            ],
        )
        self.assertIsInstance(hw_sensors.is_admin(), bool)
        self.assertIsInstance(hw_sensors.is_pawnio_installed(), bool)

    def test_acer_fan_control_and_fallback(self):
        orig = ve.VortexCoreManager._monitor_loop
        ve.VortexCoreManager._monitor_loop = lambda self: None
        try:
            m = ve.VortexCoreManager()
        finally:
            ve.VortexCoreManager._monitor_loop = orig

        m.system_specs = {"is_hp": False, "is_acer": True, "ram_gb": 16}
        m._acer_wmi_ok = True
        calls = []

        def fake_cmd(cmd):
            calls.append(cmd)
            if "-File" in cmd and "acer_fan_controller.ps1" in cmd[cmd.index("-File") + 1]:
                return (True, "OK: ACER_FAN_MAX")
            return (True, "")

        m._run_cmd = fake_cmd
        self.assertTrue(m.set_fan("max"))
        self.assertEqual(m.fan_mode, "TURBO (100% Nitro)")
        self.assertTrue(any("acer_fan_controller.ps1" in " ".join(c) and "max" in c for c in calls))

        # Si el modelo Acer no expone AcerGamingFunction, degrada a modo Universal sin romperse
        m._run_cmd = lambda cmd: (False, "NO_WMI: AcerGamingFunction no disponible")
        m.set_fan("max")
        self.assertFalse(m._acer_wmi_ok)
        self.assertEqual(m.fan_mode, "TURBO (Universal)")

    def test_parse_ping_stats(self):
        sample = "\n".join([
            "Respuesta desde 1.1.1.1: bytes=32 tiempo=10ms TTL=56",
            "Respuesta desde 1.1.1.1: bytes=32 tiempo=14ms TTL=56",
            "Respuesta desde 1.1.1.1: bytes=32 tiempo=12ms TTL=56",
            "Respuesta desde 1.1.1.1: bytes=32 tiempo=20ms TTL=56",
            "Tiempo de espera agotado para esta solicitud.",
        ])
        st = hw_sensors.parse_ping_stats(sample, sent=5)
        self.assertEqual(st["samples"], [10, 14, 12, 20])
        self.assertEqual(st["avg_ms"], 14.0)
        self.assertEqual(st["min_ms"], 10)
        self.assertEqual(st["max_ms"], 20)
        self.assertEqual(st["jitter_ms"], 4.7)
        self.assertEqual(st["loss_pct"], 20)

        empty = hw_sensors.parse_ping_stats("", sent=5)
        self.assertIsNone(empty["avg_ms"])
        self.assertEqual(empty["loss_pct"], 100)

    def test_multi_oem_fan_dispatch_and_fallback(self):
        orig = ve.VortexCoreManager._monitor_loop
        ve.VortexCoreManager._monitor_loop = lambda self: None
        try:
            m = ve.VortexCoreManager()
        finally:
            ve.VortexCoreManager._monitor_loop = orig

        for flag, brand_arg, expected_tag in (
            ("is_lenovo", "lenovo", "TURBO (LENOVO)"),
            ("is_asus", "asus", "TURBO (ASUS)"),
            ("is_dell", "dell", "TURBO (DELL)"),
        ):
            m.system_specs = {"is_hp": False, "is_acer": False, flag: True, "ram_gb": 16}
            m._oem_wmi_ok = True
            calls = []

            def fake_ok(cmd):
                calls.append(cmd)
                if "oem_fan_controller.ps1" in " ".join(cmd):
                    return (True, f"OK: {brand_arg.upper()}")
                return (True, "")

            m._run_cmd = fake_ok
            self.assertTrue(m.set_fan("max"))
            self.assertEqual(m.fan_mode, expected_tag)
            self.assertTrue(any("-Brand" in c and brand_arg in c for c in calls))

        # Si un modelo (p. ej. ThinkPad / ZenBook) no tiene WMI gaming, cae limpiamente a Universal
        m._run_cmd = lambda cmd: (False, "NO_WMI: no disponible")
        m.set_fan("max")
        self.assertFalse(m._oem_wmi_ok)
        self.assertEqual(m.fan_mode, "TURBO (Universal)")


class PowerShellQuotingTests(unittest.TestCase):
    """Los nombres que van a PowerShell entre comillas simples no pueden cerrar la cadena."""

    def test_all_single_quote_variants_are_doubled(self):
        for q in ("'", chr(0x2018), chr(0x2019), chr(0x201A), chr(0x201B)):
            self.assertEqual(hw_sensors.ps_quote(f"a{q}b"), f"a{q}{q}b")

    def test_newlines_removed(self):
        self.assertEqual(hw_sensors.ps_quote("Wi-Fi" + chr(10) + "x"), "Wi-Fi x")


class FanLogTests(unittest.TestCase):
    def test_logs_only_changes_and_reports_source(self):
        import tempfile
        log = ve.FanLog(os.path.join(tempfile.mkdtemp(), "v.log"))
        for out in ["FAN1_RPM=0"] * 3 + ["FAN1_RPM=3100"] + ["ERROR: x"] * 2:
            log.add("acer", "query", not out.startswith("ERROR"), out)
        lines = log.tail()
        self.assertEqual(len(lines), 3)
        self.assertIn("| acer query | fallo | ERROR: x", lines[-1])
        self.assertEqual(ve._fan_script_info(["-File", "C:/apps/acer_fan_controller.ps1", "-Mode", "diag"]), ("acer", "diag"))
        self.assertIsNone(ve._fan_script_info(["ping", "1.1.1.1"]))

    def test_issue_url_stays_short(self):
        rep = {"modelo": "Acer Nitro AN515-55", "registro": ["x" * 300] * 60}
        url = ve.fan_issue_url(rep)
        self.assertTrue(url.startswith(ve.ISSUES_URL))
        self.assertLessEqual(len(url), 7500)


def _smbios(structs):
    table = b"".join(structs) + bytes([127, 4, 0, 0, 0, 0])
    return bytes([0, 3, 2, 0]) + len(table).to_bytes(4, "little") + table


def _struct(stype, fields, strings):
    body = bytes([stype, 4 + len(fields), 0, 0]) + bytes(fields)
    return body + b"".join(s.encode() + b"\x00" for s in strings) + b"\x00"


class SmbiosTests(unittest.TestCase):
    def test_reads_firmware_brand_not_registry(self):
        raw = _smbios([
            _struct(0, [1, 2], ["Insyde Corp.", "V2.09"]),
            _struct(1, [1, 2, 0], ["Acer", "Nitro AN515-55"]),
            _struct(2, [1, 2], ["CML", "Stonic_CMS"]),
        ])
        self.assertEqual(hw_sensors.parse_smbios_system(raw),
                         {"manufacturer": "Acer", "product": "Nitro AN515-55", "board": "Stonic_CMS"})

    def test_bad_or_empty_tables(self):
        self.assertEqual(hw_sensors.parse_smbios_system(b""), {})
        self.assertEqual(hw_sensors.parse_smbios_system(_smbios([])), {})


class SpoofedBrandTests(unittest.TestCase):
    def test_firmware_wins_over_spoofed_registry(self):
        # registro modificado para parecer un samsung, como en el acer nitro reportado
        orig = hw_sensors.read_smbios_system
        hw_sensors.read_smbios_system = lambda: {"manufacturer": "Acer", "product": "Nitro AN515-55", "board": "Stonic_CMS"}
        try:
            specs = ve.get_system_specs()
        finally:
            hw_sensors.read_smbios_system = orig
        self.assertEqual(specs["model"], "Nitro AN515-55")
        self.assertTrue(specs["is_acer"])
        self.assertTrue(specs["fans_supported"])
        if specs["registry_brand"] and "nitro an515-55" not in specs["registry_brand"].lower():
            self.assertTrue(specs["brand_spoofed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
