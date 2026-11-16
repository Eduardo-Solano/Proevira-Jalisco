"""La desconexión y la recuperación conservan la sesión del usuario."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

WEB_DIR = str(Path(__file__).resolve().parents[1] / "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

import connection_ui


class ConnectionPanelTests(unittest.TestCase):
    def test_disconnect_retry_and_recover_without_losing_session(self):
        app = AppTest.from_string('''
import streamlit as st
from connection_ui import render_connection_status
render_connection_status()
if st.session_state.get("backend_offline"):
    st.stop()
st.write("Panel disponible")
''', default_timeout=15)
        app.session_state["auth_token"] = "session-token"
        with patch.object(connection_ui, "DEMO_MODE", False), patch.object(
            connection_ui.api, "check_health", return_value=True
        ) as health:
            app.run()
            self.assertFalse(app.exception)
            self.assertFalse(app.session_state["backend_offline"])
            health.return_value = False
            app.run()
            self.assertFalse(app.exception)
            self.assertIn("No podemos comunicarnos", app.error[0].value)
            self.assertFalse(app.markdown)
            self.assertEqual(app.button[0].label, "Reintentar conexión")
            self.assertEqual(app.session_state["auth_token"], "session-token")
            health.return_value = True
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertFalse(app.session_state["backend_offline"])
            self.assertEqual(app.markdown[0].value, "Panel disponible")
            self.assertEqual(app.session_state["auth_token"], "session-token")

    def test_demo_does_not_check_server(self):
        app = AppTest.from_string("from connection_ui import render_connection_status\nrender_connection_status()", default_timeout=15)
        with patch.object(connection_ui, "DEMO_MODE", True), patch.object(
            connection_ui.api, "check_health"
        ) as health:
            app.run()
        self.assertFalse(app.exception)
        health.assert_not_called()
