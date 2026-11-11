"""
Pruebas del servidor REST local de VortexCore Hub.

Se ejecutan en Windows (CI) y también en Linux/macOS: si no hay APIs de Windows,
se inyectan stubs mínimos. El gestor de hardware real se reemplaza por uno falso,
así que estas pruebas NUNCA tocan ventiladores, energía ni el registro.

    python -m unittest discover -s tests -v
"""
import json
import os
import sys
import threading
import types
import unittest
import http.client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["VORTEXCORE_TEST_MODE"] = "1"

if sys.platform != "win32":
    import ctypes
    import mimetypes
    mimetypes.init()  # antes del stub de winreg (mimetypes lo usaría si existe)
    from unittest import mock

    class _AnyDll:
        def __getattr__(self, name):
            return _AnyDll()

        def __getitem__(self, item):
            return _AnyDll()

        def __call__(self, *a, **k):
            return 0

    ctypes.windll = _AnyDll()
    ctypes.WINFUNCTYPE = lambda *a, **k: (lambda f: f)
    sys.modules.setdefault("winreg", types.ModuleType("winreg"))
    _wr = sys.modules["winreg"]
    for _n in ("HKEY_CLASSES_ROOT", "HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE", "KEY_READ", "KEY_SET_VALUE", "REG_BINARY"):
        setattr(_wr, _n, 0)
    _wr.OpenKey = mock.MagicMock(side_effect=OSError)

import vortex_engine as ve  # noqa: E402


class FakeManager:
    def __init__(self):
        self.calls = []
        self.telemetry = {"cpu_temp": 50, "current_profile": "DEFAULT"}
        self.system_specs = {"is_hp": True}
        self.current_profile = "DEFAULT"
        self.fan_mode = "AUTO"
        self.manual_config = None

    def __getattr__(self, name):
        if name.startswith("set_") or name in ("clean_ram",):
            def _rec(*args, **kwargs):
                self.calls.append((name, args))
                return {"freed_mb": 0} if name == "clean_ram" else True
            return _rec
        raise AttributeError(name)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ve.manager = FakeManager()
        # Evitar efectos reales en endpoints que lanzan procesos
        ve.subprocess.Popen = lambda *a, **k: None
        ve.launch_or_focus_window = lambda: None
        cls.server = ve.ThreadingHTTPServer(("127.0.0.1", 0), ve.VortexHttpHandler)
        cls.port = cls.server.server_address[1]
        # Los orígenes permitidos dependen del puerto: ajustarlos al puerto de prueba
        ve.ALLOWED_HOSTS = {f"127.0.0.1:{cls.port}", f"localhost:{cls.port}"}
        ve.ALLOWED_ORIGINS = {f"http://127.0.0.1:{cls.port}", f"http://localhost:{cls.port}"}
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        ve.manager.calls.clear()

    def req(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Content-Type": "application/json"} if body is not None else {}
        h.update(headers or {})
        data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw
        return r.status, payload, dict(r.getheaders())

    # --- Funcionamiento normal ---
    def test_telemetry_same_origin(self):
        st, data, hdr = self.req("GET", "/api/telemetry")
        self.assertEqual(st, 200)
        self.assertEqual(data["cpu_temp"], 50)
        self.assertNotIn("Access-Control-Allow-Origin", hdr)

    def test_profile_ok(self):
        st, data, _ = self.req("POST", "/api/profile", {"profile": "ECO"},
                               {"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(st, 200)
        self.assertIn(("set_profile", ("ECO",)), ve.manager.calls)

    def test_post_without_body(self):
        st, data, _ = self.req("POST", "/api/clean_ram")
        self.assertEqual(st, 200)

    # --- Seguridad ---
    def test_cross_origin_post_blocked(self):
        st, _, _ = self.req("POST", "/api/manual_mode", {"gpu_tgp": 999},
                            {"Origin": "https://evil.example"})
        self.assertEqual(st, 403)
        self.assertEqual(ve.manager.calls, [])

    def test_cross_site_fetch_metadata_blocked(self):
        st, _, _ = self.req("POST", "/api/fan", {"mode": "max"}, {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(st, 403)

    def test_dns_rebinding_blocked(self):
        st, _, _ = self.req("GET", "/api/telemetry", headers={"Host": f"attacker.example:{self.port}"})
        self.assertEqual(st, 403)

    def test_form_content_type_blocked(self):
        st, _, _ = self.req("POST", "/api/fan", b"mode=max",
                            {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(st, 415)

    def test_preflight_rejected(self):
        st, _, _ = self.req("OPTIONS", "/api/fan", headers={"Origin": "https://evil.example"})
        self.assertEqual(st, 403)

    # --- Validación ---
    def test_invalid_json(self):
        st, _, _ = self.req("POST", "/api/profile", b"{no-json")
        self.assertEqual(st, 400)

    def test_unknown_profile(self):
        st, _, _ = self.req("POST", "/api/profile", {"profile": "HACK"})
        self.assertEqual(st, 400)

    def test_manual_mode_clamped(self):
        st, data, _ = self.req("POST", "/api/manual_mode", {
            "spl": 9999, "gpu_tgp": 9999, "gpu_temp": 5, "fan_curve": [500] * 8})
        self.assertEqual(st, 200)
        self.assertEqual(data["applied"]["spl"], 65)
        self.assertEqual(data["applied"]["gpu_tgp"], 175)
        self.assertEqual(ve.manager.manual_config["gpu_temp"], 60)
        self.assertEqual(ve.manager.manual_config["fan_curve"], [100] * 8)

    def test_cpu_limit_clamped_and_bad_value(self):
        st, data, _ = self.req("POST", "/api/set_cpu_limit", {"max_pct": "abc"})
        self.assertEqual(st, 200)
        self.assertEqual(data["cpu_limit"], 100)
        st, data, _ = self.req("POST", "/api/set_cpu_limit", {"max_pct": 10})
        self.assertEqual(data["cpu_limit"], 50)

    def test_fan_mode_validated(self):
        st, _, _ = self.req("POST", "/api/fan", {"mode": "; rm -rf"})
        self.assertEqual(st, 400)

    def test_unknown_endpoint(self):
        st, _, _ = self.req("POST", "/api/nope", {})
        self.assertEqual(st, 404)

    def test_cleanup_rejects_unknown_targets(self):
        st, _, _ = self.req("POST", "/api/cleanup/clean", {"targets": ["../../Windows/System32"]})
        self.assertEqual(st, 400)
        st, _, _ = self.req("POST", "/api/cleanup/clean", {"targets": "user_temp"})
        self.assertEqual(st, 400)

    def test_top_processes_returns_list_and_memory_mb(self):
        st, data, _ = self.req("GET", "/api/top_processes")
        self.assertEqual(st, 200)
        self.assertIn("processes", data)
        self.assertIsInstance(data["processes"], list)
        if data["processes"]:
            first = data["processes"][0]
            self.assertIn("pid", first)
            self.assertIn("name", first)
            self.assertIn("memory_mb", first)
            self.assertIn("mem_mb", first)


class HelperTests(unittest.TestCase):
    def test_clamp_int(self):
        self.assertEqual(ve._clamp_int("12.7", 0, 100, 5), 12)
        self.assertEqual(ve._clamp_int(None, 0, 100, 5), 5)
        self.assertEqual(ve._clamp_int(-3, 0, 100, 5), 0)

    def test_clamp_float_nan(self):
        self.assertEqual(ve._clamp_float(float("nan"), 0, 1, 0.5), 0.5)

    def test_curve(self):
        self.assertEqual(ve._sanitize_curve([1, 2], [0] * 8), [0] * 8)
        self.assertEqual(ve._sanitize_curve(["x"] + [50] * 7, [9] * 8), [9] + [50] * 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
