"""Recovery-code navigation and password confirmation in Streamlit."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
WEB_DIR = str(Path(__file__).resolve().parents[1] / 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
import auth_ui
SOURCE = 'from auth_ui import render_auth_page\nrender_auth_page()'


class WebPasswordRecoveryTests(unittest.TestCase):
    def request_code(self):
        app = AppTest.from_string(SOURCE, default_timeout=15).run()
        app.button(key='forgot_password').click().run()
        app.text_input(key='recovery_email').set_value('medico@example.com')
        with patch.object(auth_ui.api, 'request_password_reset', return_value={'success': True, 'message': 'Code sent.'}):
            app.button[0].click().run()
        return app

    def test_request_code_verify_and_change_password(self):
        app = self.request_code()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        app.text_input(key='recovery_code').set_value('012345')
        with patch.object(auth_ui.api, 'verify_recovery_code', return_value={'success': True, 'reset_token': 'a' * 43}) as verify:
            app.button[0].click().run()
        verify.assert_called_once_with('medico@example.com', '012345')
        self.assertFalse(app.exception)
        app.text_input(key='reset_password').set_value('NewPassword123!')
        app.text_input(key='reset_confirmation').set_value('DifferentPassword')
        with patch.object(auth_ui.api, 'reset_password') as reset:
            app.button[0].click().run()
            self.assertTrue(app.warning)
            reset.assert_not_called()
        app.text_input(key='reset_confirmation').set_value('NewPassword123!')
        with patch.object(auth_ui.api, 'reset_password', return_value={'success': True}), patch.object(auth_ui.api, 'logout'):
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        self.assertFalse(app.session_state.get('_password_reset_token'))
        self.assertEqual(len(app.text_input), 2)

    def test_invalid_code_expiration_resend_and_change_email(self):
        app = self.request_code()
        app.text_input(key='recovery_code').set_value('12')
        with patch.object(auth_ui.api, 'verify_recovery_code') as verify:
            app.button[0].click().run()
            self.assertTrue(app.warning)
            verify.assert_not_called()
        app.text_input(key='recovery_code').set_value('999999')
        with patch.object(auth_ui.api, 'verify_recovery_code', return_value={'success': False, 'error': 'Code expired.'}):
            app.button[0].click().run()
        self.assertEqual(app.error[0].value, 'Code expired.')
        with patch.object(auth_ui.api, 'request_password_reset', return_value={'success': True}) as resend:
            app.button(key='resend_recovery_code').click().run()
        resend.assert_called_once_with('medico@example.com')
        self.assertFalse(app.exception)
        app.button(key='change_recovery_email').click().run()
        self.assertEqual(app.text_input[0].key, 'recovery_email')
        app.button(key='back_from_recovery').click().run()
        self.assertEqual(len(app.text_input), 2)

    def test_old_email_link_opens_code_request_even_with_session(self):
        app = AppTest.from_file(str(Path(WEB_DIR) / 'app.py'), default_timeout=20)
        app.session_state['auth_token'] = 'existing-session'
        app.query_params['reset_token'] = 'a' * 43
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input[0].key, 'recovery_email')
        self.assertFalse(app.sidebar.radio)
        self.assertNotIn('reset_token', app.query_params)
