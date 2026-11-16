"""Pruebas de humo para las vistas del dashboard web Streamlit."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import api_client  # noqa: E402

WEB_APP_PATH = str(WEB_DIR / "app.py")


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

    def test_admin_view_renders_cleanly_for_funcionario(self):
        at = AppTest.from_file(WEB_APP_PATH, default_timeout=20)
        at.session_state["auth_token"] = "dummy-token"
        at.session_state["user_email"] = "admin@proevira.jalisco.gob.mx"
        at.session_state["user_role"] = "funcionario"
        at.session_state["user_uid"] = "usr_funcionario_001"
        at.run()
        self.assertEqual(len(at.exception), 0, f"Excepción inicial admin: {at.exception}")

        at.sidebar.radio[0].set_value("⛭   Administración").run()
        self.assertEqual(len(at.exception), 0, f"Excepción en Administración: {at.exception}")

    def test_alerts_filter_replaces_feed_without_stale_cards(self):
        guadalajara_alerts = [
            {
                "id": 1,
                "municipio_id": "14039",
                "municipio": "Guadalajara",
                "nivel": "crítico",
                "mensaje": "alerta de prueba 2",
                "ts": "2026-11-14T20:20:27",
                "activa": True,
            },
            {
                "id": 2,
                "municipio_id": "14039",
                "municipio": "Guadalajara",
                "nivel": "bajo",
                "mensaje": "alerta de prueba",
                "ts": "2026-11-14T20:19:36",
                "activa": True,
            },
        ]

        def fake_get_alerts(municipio_id=None, activa=True):
            if municipio_id in (None, "14039"):
                return guadalajara_alerts
            return []

        at = AppTest.from_file(WEB_APP_PATH, default_timeout=20)
        at.session_state["auth_token"] = "dummy-token"
        at.session_state["user_email"] = "medico@salud.jalisco.gob.mx"
        at.session_state["user_role"] = "medico"
        with (
            patch.object(api_client.api, "check_health", return_value=True),
            patch.object(api_client.api, "get_alerts", side_effect=fake_get_alerts),
            patch.object(api_client.api, "generate_predicted_alert_drafts", return_value={"success": True, "data": {}}),
            patch.object(api_client.api, "get_predicted_alert_drafts", return_value=[]),
        ):
            at.run()
            at.sidebar.radio[0].set_value("▲   Alertas").run()
            self.assertTrue(any("alerta de prueba 2" in m.value for m in at.markdown))

            filtro_mun = next(sb for sb in at.selectbox if sb.key == "al_filtro")
            filtro_mun.set_value("14120").run()
            self.assertTrue(any("Sin alertas activas" in info.value for info in at.info))
            self.assertFalse(any("alerta de prueba" in m.value for m in at.markdown))
            self.assertFalse(any(b.key and b.key.startswith("delete_alert_") for b in at.button))


if __name__ == "__main__":
    unittest.main()
