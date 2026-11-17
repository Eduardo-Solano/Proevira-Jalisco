"""Refresh continuity, inactivity, absolute expiry and explicit logout."""
import base64
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

WEB_DIR = str(Path(__file__).resolve().parents[1] / "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
import browser_session as sessions


class BrowserSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = {}
        self.cookies = {}
        for name, value in (("STORE_PATH", Path(self.temp.name) / "sessions.sqlite3"), ("IDLE_SECONDS", 1800)):
            mock = patch.object(sessions, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        for obj, name, value in ((sessions.st, "session_state", self.state), (sessions.st, "context", SimpleNamespace(cookies=self.cookies))):
            mock = patch.object(obj, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch.object(sessions, "_cookie")
        self.cookie_writer = mock.start()
        self.addCleanup(mock.stop)
        encoded = base64.urlsafe_b64encode(json.dumps({"exp": 10000}).encode()).decode().rstrip("=")
        self.payload = dict(auth_token="header." + encoded + ".signature", user_role="medico", user_email="medico@example.com", user_uid="med-1", municipio_id="14039")

    def test_refresh_restores_identity_and_resets_navigation(self):
        sid = sessions.create_session(self.payload, now=100)
        self.cookies[sessions.COOKIE_NAME] = sid
        self.state["main_navigation"] = "Predicciones"
        with patch.object(sessions.time, "time", return_value=200):
            sessions.restore_browser_session()
        self.assertEqual(self.state["auth_token"], self.payload["auth_token"])
        self.assertEqual(self.state["user_role"], "medico")
        self.assertNotIn("main_navigation", self.state)
        self.assertEqual(self.cookie_writer.call_args.kwargs["value"], sid)
        self.assertNotIn(self.payload["auth_token"], str(self.cookie_writer.call_args))

    def test_idle_expiration_and_timer_does_not_extend_session(self):
        sid = sessions.create_session(self.payload, now=100)
        self.assertIsNotNone(sessions.load_session(sid, touch=False, now=1800))
        self.assertIsNone(sessions.load_session(sid, now=1900))

    def test_interaction_extends_idle_window_but_not_token_expiry(self):
        sid = sessions.create_session(self.payload, now=100)
        for now in (1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000):
            self.assertIsNotNone(sessions.load_session(sid, now=now))
        self.assertIsNone(sessions.load_session(sid, now=10000))

    def test_logout_revokes_cookie_and_prevents_reuse(self):
        sid = sessions.create_session(self.payload, now=100)
        self.state.update(self.payload)
        self.state["_browser_session_id"] = sid
        self.cookies[sessions.COOKIE_NAME] = sid
        sessions.forget_login()
        with patch.object(sessions.time, "time", return_value=200):
            sessions.restore_browser_session()
        self.assertNotIn("auth_token", self.state)
        self.assertIsNone(sessions.load_session(sid, now=200))
        self.assertEqual(self.cookie_writer.call_args.kwargs["max_age"], 0)

    def test_new_login_rotates_identifier(self):
        sid = sessions.create_session(self.payload, now=100)
        self.cookies[sessions.COOKIE_NAME] = sid
        self.state.update(self.payload)
        with patch.object(sessions.time, "time", return_value=200):
            sessions.remember_login()
        self.assertNotEqual(self.state["_browser_session_id"], sid)
        self.assertIsNone(sessions.load_session(sid, now=200))

    def test_sessions_are_separate_and_cookie_cannot_change_role(self):
        first = sessions.create_session(self.payload, now=100)
        second = sessions.create_session({**self.payload, "user_uid": "other", "user_role": "funcionario"}, now=100)
        self.assertEqual(sessions.load_session(first, now=200)["user_role"], "medico")
        self.assertEqual(sessions.load_session(second, now=200)["user_uid"], "other")
        self.assertIsNone(sessions.load_session("forged", now=200))
        sessions.revoke_session(first)
        self.assertIsNotNone(sessions.load_session(second, now=200))

    def test_expired_cookie_returns_to_login(self):
        sid = sessions.create_session(self.payload, now=100)
        self.cookies[sessions.COOKIE_NAME] = sid
        with patch.object(sessions.time, "time", return_value=1900):
            sessions.restore_browser_session()
        self.assertNotIn("auth_token", self.state)
        self.assertTrue(self.state["_session_expired"])
        self.assertEqual(self.cookie_writer.call_args.kwargs["max_age"], 0)
