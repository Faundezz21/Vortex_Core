"""
La versión de la interfaz debe coincidir con el archivo VERSION.

Los recursos se cargan como style.css?v=X / app.js?v=X para que la ventana de Edge
no reutilice CSS/JS de una versión anterior guardados en su caché. Si al publicar
se olvida actualizar index.html, esta prueba falla.

    python -m unittest discover -s tests -v
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class VersionConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.version = read("VERSION").strip()
        self.html = read("vortex-hub", "index.html")

    def test_version_format(self):
        self.assertRegex(self.version, r"^\d+\.\d+\.\d+$")

    def test_assets_are_versioned(self):
        self.assertIn(f'href="style.css?v={self.version}"', self.html)
        self.assertIn(f'src="app.js?v={self.version}"', self.html)

    def test_no_stale_versions_in_ui(self):
        # Los <svg> en línea tienen coordenadas que parecen versiones (p. ej. "1.12.61")
        html_sin_svg = re.sub(r"<svg\b.*?</svg>", "", self.html, flags=re.S)
        found = set(re.findall(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])", html_sin_svg))
        self.assertEqual(found, {self.version}, f"index.html menciona otras versiones: {found}")
        js_versions = set(re.findall(r"v(\d+\.\d+\.\d+)", read("vortex-hub", "app.js")))
        self.assertTrue(js_versions <= {self.version}, f"app.js menciona otras versiones: {js_versions}")


if __name__ == "__main__":
    unittest.main()
