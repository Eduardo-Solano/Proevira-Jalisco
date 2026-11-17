"""Avoid duplicate projections and clear the login during navigation."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

WEB_DIR = str(Path(__file__).resolve().parents[1] / "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
import auth_ui
from views import resumen
from streamlit.testing.v1 import AppTest


class DashboardLoadingTests(unittest.TestCase):
    def setUp(self):
        self.model = {"por_enfermedad": {c: {"semana_prediccion": "2026-W44"} for c in ("dengue", "influenza", "covid")}}
        self.projections = {c: [{"municipio": "14039", "nombre": "Guadalajara", "semana": "2026-W44", "enfermedad": c, "casos_esperados": 12, "nivel_riesgo": "medio"}] for c in self.model["por_enfermedad"]}

    def test_reuses_summary_projections_for_all_diseases(self):
        with patch.object(resumen.api, "get_predictions_bulk") as request:
            data = resumen._obtener_datos(self.model, "2026-W44", None, {"predicciones": self.projections})
        request.assert_not_called()
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["municipio_id"], "14039")
        self.assertEqual(data[0]["municipio"], "Guadalajara")
        self.assertEqual(self.projections["dengue"][0]["municipio"], "14039")

    def test_disease_filter_uses_only_matching_projections(self):
        with patch.object(resumen.api, "get_predictions_bulk") as request:
            data = resumen._obtener_datos(self.model, "2026-W44", "covid", {"predicciones": self.projections})
        request.assert_not_called()
        self.assertEqual([item["enfermedad"] for item in data], ["covid"])

    def test_older_backend_and_changed_week_fetch_projections(self):
        for summary in ({}, {"predicciones": {"dengue": [{**self.projections["dengue"][0], "semana": "2026-W43"}]}}):
            with self.subTest(summary=summary), patch.object(resumen.api, "get_predictions_bulk", return_value=[{"test": True}]) as request:
                self.assertEqual(resumen._obtener_datos(self.model, "2026-W44", "dengue", summary), [{"test": True}])
                request.assert_called_once_with(semana="2026-W44", enfermedad="dengue")

    def test_successful_login_clears_auth_placeholder(self):
        source = "import streamlit as st\nfrom auth_ui import render_auth_page\nslot = st.empty()\nwith slot.container():\n    render_auth_page(on_login=lambda: st.session_state.update(transition_cleared=True))"
        app = AppTest.from_string(source, default_timeout=15).run()
        app.text_input[0].set_value("medico@example.com")
        app.text_input[1].set_value("Password123!")
        with patch.object(auth_ui.api, "login", return_value={"success": True}):
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["transition_cleared"])
