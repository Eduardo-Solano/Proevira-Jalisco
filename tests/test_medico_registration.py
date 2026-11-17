"""Registro público, revisión administrativa y acceso tras aprobación."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.api.auth import router
from backend.core.security import create_access_token
from backend.db.database import Base, get_db
from backend.db.models import Municipio, Usuario

WEB_DIR = str(Path(__file__).resolve().parents[1] / "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
import auth_ui
from streamlit.testing.v1 import AppTest


class MedicoRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions() as db:
            db.add(Municipio(id="14039", nombre="Guadalajara", lat=20.67, lon=-103.35))
            db.add(Usuario(uid="admin-test", email="admin@example.com", role="funcionario", verificado=True))
            db.commit()
        app = FastAPI()
        app.include_router(router)
        def override_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + create_access_token({"sub": "admin-test", "uid": "admin-test", "role": "funcionario", "verificado": True})}
        self.payload = dict(email="  MEDICO@example.com ", password="Password123!", institucion="Hospital", cedula="1234567", municipio_id="14039")

    def test_registration_reaches_admin_and_requires_approval(self):
        response = self.client.post("/auth/register-medico", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        uid = response.json()["uid"]
        users = self.client.get("/auth/users", headers=self.headers, params={"verificado": False}).json()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["uid"], uid)
        for field in ("institucion", "cedula", "municipio_id"):
            self.assertEqual(users[0][field], self.payload[field])
        self.assertNotIn("hashed_password", users[0])
        credentials = dict(email="medico@example.com", password=self.payload["password"])
        self.assertEqual(self.client.post("/auth/login", json=credentials).status_code, 403)
        self.assertEqual(self.client.post("/auth/verify-medico/" + uid).status_code, 401)
        self.assertEqual(self.client.post("/auth/verify-medico/" + uid, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.post("/auth/login", json=credentials).status_code, 200)
        self.assertEqual(self.client.post("/auth/register-medico", json=self.payload).status_code, 400)

    def test_invalid_registration_is_not_saved(self):
        for changes in ({"institucion": " "}, {"cedula": " "}, {"municipio_id": "99999"}, {"password": "short"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post("/auth/register-medico", json={**self.payload, **changes}).status_code, 400)
        with self.sessions() as db:
            self.assertEqual(db.query(Usuario).filter(Usuario.role == "medico").count(), 0)

    def test_login_links_and_registration_form(self):
        app = AppTest.from_string("from auth_ui import render_auth_page\nrender_auth_page()", default_timeout=15).run()
        self.assertTrue(any('href="?auth=recovery"' in m.value for m in app.markdown))
        self.assertFalse(any(b.key == "forgot_password" for b in app.button))
        app.query_params["auth"] = "register"
        app.run()
        for key, value in (("register_email", "medico@example.com"), ("register_institucion", "Hospital"), ("register_cedula", "1234567"), ("register_password", "Password123!"), ("register_confirmation", "different")):
            app.text_input(key=key).set_value(value)
        with patch.object(auth_ui.api, "register_medico", return_value={"success": True}) as register:
            app.button[0].click().run()
            register.assert_not_called()
            app.text_input(key="register_confirmation").set_value("Password123!")
            app.button[0].click().run()
            register.assert_called_once()
            self.assertEqual(register.call_args.kwargs["municipio_id"], "14039")
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        self.assertFalse(app.text_input)
