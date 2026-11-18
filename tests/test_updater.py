# pruebas del aviso de nuevas versiones
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import updater  # noqa: E402

RELEASE = {
    "tag_name": "v7.11.0",
    "html_url": "https://github.com/Faundezz21/Vortex_Core/releases/tag/v7.11.0",
    "published_at": "2026-11-20T10:00:00Z",
    "body": "# VortexCore Hub v7.11.0\n\n## Novedades\n- **Overlay en juego** con FPS\n- Ping al [servidor](https://x.y) del juego\n* Red por app\n",
    "assets": [{"name": "VortexCoreHub-v7.11.0-Portable.zip", "browser_download_url": "https://x/zip"},
               {"name": "Vortex-core-hub-Setup.exe", "browser_download_url": "https://x/setup"}],
}


class VersionTests(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(updater.parse_version("v7.10.1"), (7, 10, 1))
        self.assertEqual(updater.parse_version("7.11"), (7, 11, 0))
        self.assertIsNone(updater.parse_version("dev"))
        self.assertTrue(updater.is_newer("v7.11.0", "7.10.1"))
        self.assertTrue(updater.is_newer("v7.10.10", "7.10.9"))
        self.assertFalse(updater.is_newer("v7.10.1", "7.10.1"))
        self.assertFalse(updater.is_newer("v7.9.9", "7.10.0"))
        self.assertFalse(updater.is_newer("v8.0.0", "dev"))

    def test_parse_release(self):
        r = updater.parse_release(RELEASE, "7.10.1")
        self.assertTrue(r["update_available"])
        self.assertEqual(r["latest"], "7.11.0")
        self.assertEqual(r["setup_url"], "https://x/setup")
        self.assertEqual(r["notes"], ["Overlay en juego con FPS", "Ping al servidor del juego", "Red por app"])


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = updater.state_path
        updater.state_path = lambda: os.path.join(self.tmp.name, "updates.json")
        self.notes = []

    def tearDown(self):
        updater.state_path = self._orig
        self.tmp.cleanup()

    def make(self, status="ok", data=RELEASE, current="7.10.1"):
        return updater.UpdateChecker(current, notify=lambda t, m: self.notes.append(m), fetch=lambda: (status, data))

    def test_notifies_once_per_version(self):
        c = self.make()
        self.assertEqual(c.check()["status"], "update")
        c.check()
        self.assertEqual(len(self.notes), 1)
        # una nueva instancia recuerda que ya aviso
        self.make().check()
        self.assertEqual(len(self.notes), 1)

    def test_dismiss_silences_version(self):
        c = self.make()
        c.check()
        self.assertTrue(c.dismiss()["dismissed"])
        self.notes.clear()
        c2 = self.make()
        self.assertTrue(c2.check()["dismissed"])
        self.assertEqual(self.notes, [])

    def test_up_to_date_and_errors(self):
        self.assertEqual(self.make(current="7.11.0").check()["status"], "current")
        self.assertEqual(self.make(status="none", data=None).check()["status"], "none")
        self.assertEqual(self.make(status="error", data=None).check()["status"], "error")
        self.assertEqual(self.notes, [])


if __name__ == "__main__":
    unittest.main()
