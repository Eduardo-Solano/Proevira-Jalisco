"""Errores del servicio traducidos a mensajes seguros para el dashboard."""

import unittest
from unittest.mock import Mock, patch

import requests

from web import api_client


class WebErrorTests(unittest.TestCase):
    def setUp(self):
        self.state = patch.object(api_client.st, "session_state", {})
        self.state.start()
        self.addCleanup(self.state.stop)
        self.demo = patch.object(api_client, "DEMO_MODE", False)
        self.demo.start()
        self.addCleanup(self.demo.stop)
        self.client = api_client.ApiClient()

    @staticmethod
    def response(status):
        response = Mock(ok=False, status_code=status, text="HTTP error: secret internal detail")
        response.json.return_value = {"detail": "secret internal detail"}
        return response

    def test_http_errors_are_safe_for_reads_and_uploads(self):
        for status in (400, 401, 403, 404, 409, 413, 422, 429, 500, 502, 503):
            with self.subTest(status=status):
                response = self.response(status)
                with patch.object(api_client.requests, "request", return_value=response):
                    with self.assertRaises(api_client.ApiError) as caught:
                        self.client.get_datasets()
                with patch.object(api_client.requests, "post", return_value=response):
                    result = self.client.import_csv("dengue", "fuente", "datos.csv", b"a,b")
                self.assertFalse(result["success"])
                self.assertEqual(str(caught.exception), result["error"])
                for detail in (str(status), "HTTP", "secret", "/datasets"):
                    self.assertNotIn(detail, result["error"])
                self.assertFalse(api_client.st.session_state.get("_api_read_cache"))

    def test_login_distinguishes_bad_credentials_from_expired_session(self):
        with patch.object(api_client.requests, "request", return_value=self.response(401)):
            result = self.client.login("usuario@example.com", "incorrecta")
        self.assertFalse(result["success"])
        self.assertIn("correo o la contraseña", result["error"])
        self.assertNotIn("auth_token", api_client.st.session_state)
        self.assertIn("sesión venció", api_client._http_error_message(401, "/datasets"))

    def test_connection_errors_are_safe_in_both_transports(self):
        for error in (requests.Timeout("secret url"), requests.ConnectionError("secret url")):
            with self.subTest(error=type(error).__name__):
                with patch.object(api_client.requests, "request", side_effect=error):
                    with self.assertRaises(api_client.ApiError) as caught:
                        self.client.get_datasets()
                with patch.object(api_client.requests, "post", side_effect=error):
                    result = self.client.import_csv("dengue", "fuente", "datos.csv", b"a,b")
                self.assertEqual(str(caught.exception), result["error"])
                self.assertNotIn("secret", result["error"])

    def test_invalid_json_and_missing_login_token_are_handled(self):
        response = Mock(ok=True, status_code=200, content=b"invalid")
        response.json.side_effect = ValueError("secret parser detail")
        with patch.object(api_client.requests, "request", return_value=response):
            result = self.client.login("usuario@example.com", "password")
        self.assertFalse(result["success"])
        self.assertNotIn("secret", result["error"])
        response.json.side_effect = None
        for payload in (None, [], {}):
            response.json.return_value = payload
            with patch.object(api_client.requests, "request", return_value=response):
                self.assertFalse(self.client.login("usuario@example.com", "password")["success"])

    def test_successful_reads_still_use_cache(self):
        response = Mock(ok=True, status_code=200, content=b"{}")
        response.json.return_value = {"datasets": []}
        with patch.object(api_client.requests, "request", return_value=response) as request:
            self.assertEqual(self.client.get_datasets(), {"datasets": []})
            self.assertEqual(self.client.get_datasets(), {"datasets": []})
        request.assert_called_once()

    def test_health_bypasses_cache_and_detects_recovery(self):
        response = Mock(ok=True, status_code=200, content=b"{}")
        response.json.return_value = {"status": "ok"}
        with patch.object(api_client.requests, "request", side_effect=[
            response, requests.ConnectionError("offline"), response,
        ]) as request:
            self.assertTrue(self.client.check_health())
            self.assertFalse(self.client.check_health())
            self.assertTrue(self.client.check_health())
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args.kwargs["timeout"], (3.0, 5.0))

    def test_health_rejects_invalid_payload(self):
        with patch.object(self.client, "_request", return_value=None):
            self.assertFalse(self.client.check_health())


if __name__ == "__main__":
    unittest.main()
