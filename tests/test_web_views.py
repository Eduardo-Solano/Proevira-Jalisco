"""Pruebas de humo para las vistas del dashboard web Streamlit."""

from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

WEB_APP_PATH = str(Path(__file__).resolve().parents[1] / "web" / "app.py")


class WebViewsSmokeTests(unittest.TestCase):
    def test_auth_screen_renders_without_token(self):
        at = AppTest.from_file(WEB_APP_PATH, default_timeout=15)
        at.run()
        self.assertEqual(len(at.exception), 0, f"Excepción en login: {at.exception}")

    def test_all_sidebar_views_render_cleanly(self):
        secciones = [
            "◫   Panorama",
            "⌖   Mapa epidemiológico",
            "↗   Predicciones",
            "▤   Gestión de datos",
            "▧   Reportes",
            "▲   Alertas",
        ]
        at = AppTest.from_file(WEB_APP_PATH, default_timeout=20)
        at.session_state["auth_token"] = "dummy-token"
        at.session_state["user_email"] = "medico@salud.jalisco.gob.mx"
        at.session_state["user_role"] = "medico"
        at.run()
        self.assertEqual(len(at.exception), 0, f"Excepción inicial: {at.exception}")

        for seccion in secciones:
            with self.subTest(seccion=seccion):
                at.sidebar.radio[0].set_value(seccion).run()
                self.assertEqual(len(at.exception), 0, f"Excepción en {seccion}: {at.exception}")


if __name__ == "__main__":
    unittest.main()
