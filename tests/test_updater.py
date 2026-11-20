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


class NotesTests(unittest.TestCase):
    def test_skips_download_links(self):
        body = "\n".join([
            "# VortexCore Hub v7.11.0", "", "### Descargas Oficiales", "* **Instalador**: [`Setup.exe`](https://x)", "",
            "## Novedades en v7.11.0", "### Hub gaming", "- **Overlay en juego** con FPS", "- Ping al juego",
        ])
        self.assertEqual(updater.summarize_notes(body), ["Overlay en juego con FPS", "Ping al juego"])


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


NL = chr(10)


class InstallTests(unittest.TestCase):
    BASE = "https://github.com/Faundezz21/Vortex_Core/releases/download/v7.12.0/"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = (updater.state_path, updater._download)
        updater.state_path = lambda: os.path.join(self.tmp.name, "updates.json")
        self.payload = b"instalador de prueba"
        self.sums = updater.hashlib.sha256(self.payload).hexdigest().upper() + "  Vortex-core-hub-Setup.exe" + NL

        def fake_download(url, dest, progress=None, timeout=30):
            data = self.payload if url.endswith(".exe") else self.sums.encode()
            with open(dest, "wb") as f:
                f.write(data)
            if progress:
                progress(len(data), len(data))
        updater._download = fake_download

    def tearDown(self):
        updater.state_path, updater._download = self._orig
        self.tmp.cleanup()

    def checker(self, setup=None, sums=None):
        rel = dict(RELEASE, tag_name="v7.12.0", assets=[
            {"name": "Vortex-core-hub-Setup.exe", "browser_download_url": setup or self.BASE + "Vortex-core-hub-Setup.exe"},
            {"name": "checksums-sha256.txt", "browser_download_url": sums or self.BASE + "checksums-sha256.txt"},
        ])
        c = updater.UpdateChecker("7.11.0", fetch=lambda: ("ok", rel))
        c.check()
        return c

    def run_install(self, c):
        ready = []
        c.start_install(ready.append)
        for _ in range(200):
            if not c._installing:
                break
            updater.time.sleep(0.01)
        return ready

    def test_parse_checksums(self):
        text = "ABC  otro.zip" + NL + "A" * 64 + "  Vortex-core-hub-Setup.exe" + NL
        self.assertEqual(updater.parse_checksums(text, "Vortex-core-hub-Setup.exe"), "A" * 64)
        self.assertIsNone(updater.parse_checksums("hola", "Vortex-core-hub-Setup.exe"))

    def test_installs_when_hash_matches(self):
        c = self.checker()
        ready = self.run_install(c)
        self.assertEqual(len(ready), 1)
        self.assertTrue(os.path.isfile(ready[0]))
        self.assertEqual(c.get_state()["install"]["phase"], "installing")

    def test_rejects_tampered_installer(self):
        c = self.checker()
        self.payload = b"alterado"
        self.sums = "0" * 64 + "  Vortex-core-hub-Setup.exe" + NL
        ready = self.run_install(c)
        self.assertEqual(ready, [])
        self.assertEqual(c.get_state()["install"]["phase"], "error")
        self.assertEqual(os.listdir(updater.updates_dir()), [])

    def test_rejects_foreign_urls(self):
        c = self.checker(setup="https://evil.example/Vortex-core-hub-Setup.exe")
        ready = []
        st = c.start_install(ready.append)
        self.assertEqual(st["install"]["phase"], "error")
        self.assertEqual(ready, [])

    def test_no_install_without_update(self):
        c = updater.UpdateChecker("7.12.0", fetch=lambda: ("ok", dict(RELEASE, tag_name="v7.12.0")))
        c.check()
        self.assertEqual(c.start_install(lambda p: None)["install"]["phase"], "error")


class FallbackTests(unittest.TestCase):
    CHANGELOG = NL.join(["# Changelog", "", "## 7.14.0", "", "### Juego", "- **Modo juego** nuevo", "- Ping estable", "",
                         "## 7.13.0", "- viejo"])

    def fake_get(self, url):
        if url == updater.RELEASES_URL:
            return "https://github.com/Faundezz21/Vortex_Core/releases/tag/v7.14.0", "<html>"
        if url.endswith("/v7.14.0/CHANGELOG.md"):
            return url, self.CHANGELOG
        raise AssertionError(url)

    def test_builds_release_from_public_page(self):
        st, data = updater.fallback_release(self.fake_get)
        self.assertEqual(st, "ok")
        rel = updater.parse_release(data, "7.13.0")
        self.assertTrue(rel["update_available"])
        self.assertEqual(rel["latest"], "7.14.0")
        self.assertTrue(rel["setup_url"].startswith(updater.DOWNLOAD_PREFIX + "v7.14.0/"))
        self.assertTrue(rel["checksums_url"].endswith("/v7.14.0/checksums-sha256.txt"))
        self.assertEqual(rel["notes"], ["Modo juego nuevo", "Ping estable"])

    def test_no_releases_and_network_errors(self):
        none = lambda url: ("https://github.com/Faundezz21/Vortex_Core/releases", "")
        self.assertEqual(updater.fallback_release(none), ("none", None))

        def boom(url):
            raise OSError("sin red")
        self.assertEqual(updater.fallback_release(boom), ("error", None))


if __name__ == "__main__":
    unittest.main()
