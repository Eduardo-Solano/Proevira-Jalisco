"""Recovery codes, attempt limits and single-use password changes."""
import datetime
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.api.auth import router
from backend.config import settings
from backend.core import password_recovery as recovery
from backend.core.security import get_password_hash
from backend.db.database import Base, get_db
from backend.db.models import PasswordRecoveryCode, PasswordResetToken, Usuario


class PasswordRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with self.sessions() as db:
            db.add(Usuario(uid='test-user', email='medico@example.com', hashed_password=get_password_hash('OldPassword123!'), role='medico'))
            db.commit()
        app = FastAPI()
        app.include_router(router, prefix='/api/v1')
        def override_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        for obj, attr, value in (
            (settings, 'SMTP_HOST', 'smtp.example.com'),
            (settings, 'SMTP_FROM_EMAIL', 'acceso@example.com'),
            (settings, 'SMTP_USE_SSL', False),
            (settings, 'SMTP_STARTTLS', True),
            (recovery, 'SessionLocal', self.sessions),
        ):
            p = patch.object(obj, attr, value)
            p.start()
            self.addCleanup(p.stop)
        self.send_mail_impl = recovery.send_reset_email
        p = patch.object(recovery, 'send_reset_email')
        self.mail = p.start()
        self.addCleanup(p.stop)
        p = patch.object(recovery.secrets, 'randbelow', side_effect=range(123450, 123499))
        p.start()
        self.addCleanup(p.stop)

    def request_code(self, email='medico@example.com'):
        return self.client.post('/api/v1/auth/forgot-password', json={'email': email})

    def verify(self, code, email='medico@example.com'):
        return self.client.post('/api/v1/auth/verify-recovery-code', json={'email': email, 'code': code})

    def reset(self, token, password='NewPassword123!'):
        return self.client.post('/api/v1/auth/reset-password', json={'token': token, 'password': password})

    def test_complete_flow_and_single_use(self):
        response = self.request_code('  MEDICO@example.com ')
        self.assertEqual(response.status_code, 202)
        email, code = self.mail.call_args.args
        self.assertRegex(code, r'^[0-9]{6}$')
        self.assertNotIn(code, response.text)
        with self.sessions() as db:
            record = db.get(PasswordRecoveryCode, 'test-user')
            self.assertEqual(record.code_hash, recovery._code_digest('test-user', code))
            self.assertNotEqual(record.code_hash, code)
        verified = self.verify(code)
        self.assertEqual(verified.status_code, 200)
        token = verified.json()['reset_token']
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertEqual(self.client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code, 401)
        self.assertEqual(self.reset(token).status_code, 200)
        self.assertEqual(self.reset(token).status_code, 400)
        for password, expected in (('OldPassword123!', 401), ('NewPassword123!', 200)):
            r = self.client.post('/api/v1/auth/login', json={'email': email, 'password': password})
            self.assertEqual(r.status_code, expected)

    def test_unknown_email_and_cooldown_have_same_response(self):
        known = self.request_code()
        self.assertEqual(known.json(), self.request_code('unknown@example.com').json())
        self.assertEqual(known.json(), self.request_code().json())
        self.assertIn('C\u00f3digo de recuperaci\u00f3n enviado', known.json()['message'])
        self.assertEqual(self.mail.call_count, 1)

    def test_expired_and_replaced_codes_fail(self):
        self.request_code()
        first = self.mail.call_args.args[1]
        with self.sessions() as db:
            record = db.get(PasswordRecoveryCode, 'test-user')
            record.expires_at = recovery._now() - datetime.timedelta(seconds=1)
            record.requested_at = recovery._now() - datetime.timedelta(days=1)
            db.commit()
        self.assertEqual(self.verify(first).status_code, 400)
        self.request_code()
        second = self.mail.call_args.args[1]
        self.assertNotEqual(first, second)
        self.assertEqual(self.verify(first).status_code, 400)
        self.assertEqual(self.verify(second).status_code, 200)

    def test_five_wrong_attempts_block_even_correct_code(self):
        self.request_code()
        code = self.mail.call_args.args[1]
        for _ in range(5):
            self.assertEqual(self.verify('999999').status_code, 400)
        self.assertEqual(self.verify(code).status_code, 400)
        with self.sessions() as db:
            self.assertEqual(db.get(PasswordRecoveryCode, 'test-user').attempts, 5)
            self.assertIsNone(db.get(PasswordResetToken, 'test-user'))

    def test_correct_code_on_fifth_attempt_and_bound_to_email(self):
        self.request_code()
        code = self.mail.call_args.args[1]
        self.assertEqual(self.verify(code, 'other@example.com').status_code, 400)
        for _ in range(4):
            self.assertEqual(self.verify('999999').status_code, 400)
        self.assertEqual(self.verify(code).status_code, 200)

    def test_password_validation_does_not_consume_grant(self):
        self.request_code()
        token = self.verify(self.mail.call_args.args[1]).json()['reset_token']
        self.assertEqual(self.reset(token, 'short').status_code, 422)
        self.assertEqual(self.reset(token, '\u00e1' * 40).status_code, 400)
        self.assertEqual(self.reset('X' * 43).status_code, 400)
        self.assertEqual(self.reset(token).status_code, 200)

    def test_password_changed_elsewhere_invalidates_code(self):
        self.request_code()
        code = self.mail.call_args.args[1]
        with self.sessions() as db:
            db.get(Usuario, 'test-user').hashed_password = get_password_hash('OtherPassword123!')
            db.commit()
        self.assertEqual(self.verify(code).status_code, 400)

    def test_new_request_revokes_grant_and_expired_grant_fails(self):
        self.request_code()
        token = self.verify(self.mail.call_args.args[1]).json()['reset_token']
        with self.sessions() as db:
            db.get(PasswordResetToken, 'test-user').expires_at = recovery._now() - datetime.timedelta(seconds=1)
            db.get(PasswordRecoveryCode, 'test-user').requested_at = recovery._now() - datetime.timedelta(days=1)
            db.commit()
        self.assertEqual(self.reset(token).status_code, 400)
        self.request_code()
        with self.sessions() as db:
            self.assertIsNone(db.get(PasswordResetToken, 'test-user'))
        self.assertEqual(self.verify(self.mail.call_args.args[1]).status_code, 200)

    def test_invalid_email_and_missing_configuration(self):
        self.assertEqual(self.request_code('invalid').status_code, 400)
        with patch.object(settings, 'SMTP_HOST', ''):
            self.assertEqual(self.request_code().status_code, 503)
            self.assertEqual(self.request_code('unknown@example.com').status_code, 503)
        self.mail.assert_not_called()

    def test_mail_failure_expires_code_without_exposing_details(self):
        self.mail.side_effect = OSError('private provider detail')
        response = self.request_code()
        self.assertEqual(response.status_code, 202)
        self.assertNotIn('private', response.text)
        self.assertEqual(self.verify(self.mail.call_args.args[1]).status_code, 400)

    def test_email_contains_code_without_links_and_uses_tls(self):
        with patch.object(recovery.smtplib, 'SMTP') as transport:
            self.send_mail_impl('medico@example.com', '012345')
        smtp = transport.return_value.__enter__.return_value
        smtp.starttls.assert_called_once()
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message['To'], 'medico@example.com')
        plain = message.get_body(preferencelist=('plain',)).get_content()
        html = message.get_body(preferencelist=('html',)).get_content()
        self.assertIn('012345', plain)
        self.assertIn('012345', html)
        self.assertNotIn('http', plain)
        self.assertNotIn('href=', html)
