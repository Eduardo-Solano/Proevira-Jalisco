"""Pruebas End-to-End del backend FastAPI, inferencia ML, WebSockets y flujos móviles."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.core.inference import inference_engine
from backend.core.security import get_password_hash
from backend.db.database import Base, get_db
from backend.db.models import Clue, Municipio, Usuario
from backend.main import app
from scripts import limpieza


class EndToEndApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(cls._tmpdir.name)
        cls._clean_copy = tmp_path / "clean"
        shutil.copytree("data/clean", cls._clean_copy)
        cls._db_path = tmp_path / "e2e_test.db"

        cls._orig_clean = settings.CLEAN_DATA_DIR
        cls._orig_limpieza_clean = limpieza.CLEAN
        settings.CLEAN_DATA_DIR = str(cls._clean_copy)
        limpieza.CLEAN = str(cls._clean_copy)

        cls._engine = create_engine(
            f"sqlite:///{cls._db_path}",
            connect_args={"check_same_thread": False},
        )
        cls._SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls._engine)
        Base.metadata.create_all(bind=cls._engine)

        with cls._SessionLocal() as db:
            db.add_all(
                [
                    Municipio(id="14039", nombre="GUADALAJARA", lat=20.67647, lon=-103.347811),
                    Municipio(id="14120", nombre="ZAPOPAN", lat=20.716405, lon=-103.416947),
                    Municipio(id="14098", nombre="SAN PEDRO TLAQUEPAQUE", lat=20.610214, lon=-103.320670),
                    Clue(
                        clues="JCSSA001",
                        nombre="Centro de Salud Guadalajara Centro",
                        institucion="SSJ",
                        tipo="CONSULTA EXTERNA",
                        nivel_atencion="PRIMER NIVEL",
                        municipio_id="14039",
                        municipio="GUADALAJARA",
                        direccion="Calle Hospital 100",
                        telefono="3330000001",
                        horario="Lun-Vie 08:00-14:00",
                        lat=20.680,
                        lon=-103.348,
                    ),
                    Clue(
                        clues="JCSSA002",
                        nombre="Hospital General Zapopan",
                        institucion="SSJ",
                        tipo="HOSPITALIZACIÓN",
                        nivel_atencion="SEGUNDO NIVEL",
                        municipio_id="14120",
                        municipio="ZAPOPAN",
                        direccion="Av Laureles 500",
                        telefono="3330000002",
                        horario="Lun-Dom 00:00-23:59",
                        lat=20.720,
                        lon=-103.410,
                    ),
                    Usuario(
                        uid="usr_func_e2e",
                        email="funcionario.e2e@salud.jalisco.gob.mx",
                        hashed_password=get_password_hash("FuncPass2026!"),
                        role="funcionario",
                        municipio_id="14039",
                        verificado=True,
                    ),
                    Usuario(
                        uid="usr_med_e2e",
                        email="medico.e2e@salud.jalisco.gob.mx",
                        hashed_password=get_password_hash("MedPass2026!"),
                        role="medico",
                        municipio_id="14039",
                        verificado=True,
                    ),
                    Usuario(
                        uid="usr_pac_e2e",
                        email="paciente.e2e@jalisco.mx",
                        hashed_password=get_password_hash("PacPass2026!"),
                        role="paciente",
                        municipio_id="14039",
                        verificado=True,
                    ),
                ]
            )
            db.commit()

        def override_get_db():
            db = cls._SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        inference_engine.reload()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        settings.CLEAN_DATA_DIR = cls._orig_clean
        limpieza.CLEAN = cls._orig_limpieza_clean
        inference_engine.reload()
        cls._engine.dispose()
        cls._tmpdir.cleanup()

    def _login(self, email: str, password: str) -> dict:
        resp = self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_01_system_health_version_and_metrics(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertTrue(health.json()["modelo_cargado"])

        version = self.client.get("/version")
        self.assertEqual(version.status_code, 200)
        ver_data = version.json()
        self.assertEqual(ver_data["modelo"], "rf-municipal-v2")
        self.assertIn("dengue", ver_data["por_enfermedad"])

        metrics = self.client.get("/api/v1/model/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertIn("dengue", metrics.json()["test"]["municipal"])

    def test_02_medico_registration_verification_and_rbac(self):
        email = f"nuevo.med.{uuid.uuid4().hex[:6]}@hospital.org"
        reg = self.client.post(
            "/api/v1/auth/register-medico",
            json={
                "email": email,
                "password": "NuevoMed2026!",
                "institucion": "Centro de Salud Guadalajara 1",
                "cedula": "87654321",
                "municipio_id": "14039",
            },
        )
        self.assertEqual(reg.status_code, 200, reg.text)
        med_uid = reg.json()["uid"]
        self.assertFalse(reg.json()["verificado"])

        # Médico sin verificar no debe acceder a endpoints clínicos protegidos
        unverified_login = self._login(email, "NuevoMed2026!")
        blocked = self.client.get(
            "/api/v1/predictions/bulk?enfermedad=dengue",
            headers={"Authorization": f"Bearer {unverified_login['token']}"},
        )
        self.assertEqual(blocked.status_code, 403)

        # Funcionario aprueba al médico -> vuelve a iniciar sesión y ahora sí accede
        func_login = self._login("funcionario.e2e@salud.jalisco.gob.mx", "FuncPass2026!")
        verify = self.client.post(
            f"/api/v1/auth/verify-medico/{med_uid}",
            headers={"Authorization": f"Bearer {func_login['token']}"},
        )
        self.assertEqual(verify.status_code, 200, verify.text)
        self.assertTrue(verify.json()["verificado"])

        verified_login = self._login(email, "NuevoMed2026!")
        allowed = self.client.get(
            "/api/v1/predictions/bulk?enfermedad=dengue",
            headers={"Authorization": f"Bearer {verified_login['token']}"},
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(len(allowed.json()), 12)

    def test_03_municipal_predictions_horizon_explain_and_dashboard(self):
        med = self._login("medico.e2e@salud.jalisco.gob.mx", "MedPass2026!")
        headers = {"Authorization": f"Bearer {med['token']}"}

        hist = self.client.get(
            "/api/v1/predictions/history?municipio=14039&enfermedad=dengue&semanas=8&horizonte=4",
            headers=headers,
        )
        self.assertEqual(hist.status_code, 200, hist.text)
        hist_json = hist.json()
        self.assertEqual(len(hist_json["prediccion"]), 4)
        self.assertEqual(len(hist_json["historico"]), 8)

        explain = self.client.get(
            "/api/v1/predictions/explain?municipio=14039&enfermedad=dengue",
            headers=headers,
        )
        self.assertEqual(explain.status_code, 200, explain.text)
        self.assertGreater(len(explain.json()["feature_importance"]), 0)

        summary = self.client.get("/api/v1/dashboard/summary", headers=headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(len(summary.json()["por_municipio"]), 12)

        heatmap = self.client.get("/api/v1/dashboard/heatmap?enfermedad=dengue", headers=headers)
        self.assertEqual(heatmap.status_code, 200, heatmap.text)
        self.assertIn("geojson", heatmap.json())

    def test_04_alerts_web_to_websocket_realtime_and_drafts(self):
        func = self._login("funcionario.e2e@salud.jalisco.gob.mx", "FuncPass2026!")
        med = self._login("medico.e2e@salud.jalisco.gob.mx", "MedPass2026!")
        pac = self._login("paciente.e2e@jalisco.mx", "PacPass2026!")
        func_headers = {"Authorization": f"Bearer {func['token']}"}
        med_headers = {"Authorization": f"Bearer {med['token']}"}

        # Paciente no puede emitir alertas oficiales
        forbidden = self.client.post(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {pac['token']}"},
            json={"municipio_id": "14039", "nivel": "alto", "mensaje": "Intento no autorizado"},
        )
        self.assertEqual(forbidden.status_code, 403)

        # Médico verificado sí puede emitir alertas oficiales
        med_created = self.client.post(
            "/api/v1/alerts",
            headers=med_headers,
            json={"municipio_id": "14039", "nivel": "medio", "mensaje": "Alerta emitida por médico."},
        )
        self.assertEqual(med_created.status_code, 200, med_created.text)

        # Cliente móvil conectado por WebSocket recibe alerta emitida desde Web en tiempo real
        with self.client.websocket_connect(f"/ws/alerts?token={pac['token']}") as ws:
            welcome = json.loads(ws.receive_text())
            self.assertEqual(welcome["tipo"], "conexion")

            ws.send_text("ping")
            self.assertEqual(ws.receive_text(), "pong")

            created = self.client.post(
                "/api/v1/alerts",
                headers=func_headers,
                json={
                    "municipio_id": "14039",
                    "nivel": "alto",
                    "mensaje": "Reforzar control vectorial en Guadalajara.",
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            pushed = json.loads(ws.receive_text())
            self.assertEqual(pushed["tipo"], "alerta")
            self.assertEqual(pushed["municipio"], "14039")
            self.assertEqual(pushed["nivel"], "alto")

        drafts = self.client.post("/api/v1/alerts/predictive-drafts/generate", headers=func_headers)
        self.assertEqual(drafts.status_code, 200, drafts.text)
        listed_drafts = self.client.get("/api/v1/alerts/predictive-drafts?estado=pendiente", headers=func_headers)
        self.assertEqual(listed_drafts.status_code, 200)
        draft_items = listed_drafts.json()
        if draft_items:
            draft_id = draft_items[0]["id"]
            blank_msg = self.client.patch(
                f"/api/v1/alerts/predictive-drafts/{draft_id}",
                headers=func_headers,
                json={"decision": "aprobar", "nivel": "alto", "mensaje": "   "},
            )
            self.assertEqual(blank_msg.status_code, 400)

            bad_level = self.client.patch(
                f"/api/v1/alerts/predictive-drafts/{draft_id}",
                headers=func_headers,
                json={"decision": "aprobar", "nivel": "extremo", "mensaje": "Aviso válido"},
            )
            self.assertEqual(bad_level.status_code, 400)

            custom_msg = "Aviso personalizado: reforzar descacharrización en zona centro."
            approved = self.client.patch(
                f"/api/v1/alerts/predictive-drafts/{draft_id}",
                headers=func_headers,
                json={"decision": "aprobar", "nivel": "crítico", "mensaje": custom_msg},
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["nivel"], "crítico")
            self.assertEqual(approved.json()["mensaje"], custom_msg)

            all_alerts = self.client.get("/api/v1/alerts", params={"activa": True}).json()
            custom_alert = next((a for a in all_alerts if a["mensaje"] == custom_msg), None)
            self.assertIsNotNone(custom_alert)

            # Borrar alerta vinculada a un borrador predictivo no debe fallar por FK
            del_linked = self.client.delete(
                f"/api/v1/alerts/{custom_alert['id']}",
                headers=func_headers,
            )
            self.assertEqual(del_linked.status_code, 200, del_linked.text)

        # Paciente no puede eliminar alertas; funcionario sí puede eliminar alertas de prueba
        med_alert_id = med_created.json()["id"]
        pac_del = self.client.delete(
            f"/api/v1/alerts/{med_alert_id}",
            headers={"Authorization": f"Bearer {pac['token']}"},
        )
        self.assertEqual(pac_del.status_code, 403)

        func_del = self.client.delete(f"/api/v1/alerts/{med_alert_id}", headers=func_headers)
        self.assertEqual(func_del.status_code, 200, func_del.text)
        self.assertTrue(func_del.json()["eliminada"])

        remaining_ids = {a["id"] for a in self.client.get("/api/v1/alerts", params={"activa": True}).json()}
        self.assertNotIn(med_alert_id, remaining_ids)

        missing_del = self.client.delete("/api/v1/alerts/999999", headers=func_headers)
        self.assertEqual(missing_del.status_code, 404)

    def test_05_clues_nearest_and_offline_symptom_idempotency(self):
        pac = self._login("paciente.e2e@jalisco.mx", "PacPass2026!")
        headers = {"Authorization": f"Bearer {pac['token']}"}

        nearest = self.client.get("/api/v1/clues/nearest?lat=20.6765&lon=-103.3478&limit=2")
        self.assertEqual(nearest.status_code, 200, nearest.text)
        units = nearest.json()
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0]["clues"], "JCSSA001")
        self.assertLessEqual(units[0]["distancia_km"], units[1]["distancia_km"])

        detail = self.client.get("/api/v1/clues/JCSSA001")
        self.assertEqual(detail.status_code, 200)

        # Registro offline con id_local UUID y reenvío duplicado idempotente
        id_local = str(uuid.uuid4())
        payload = {
            "id_local": id_local,
            "municipio_id": "14039",
            "fiebre": True,
            "cefalea": True,
            "dolor_muscular": True,
            "dolor_articular": True,
            "dolor_retroocular": True,
            "tos": False,
            "dificultad_respiratoria": False,
            "dias_con_sintomas": 2,
            "temperatura": 38.7,
        }
        first = self.client.post("/api/v1/symptoms", headers=headers, json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["sospecha_sugerida"], "dengue")
        self.assertIn("NOM-004-SSA3-2012", first.json()["disclaimer_medico"])

        retry = self.client.post("/api/v1/symptoms", headers=headers, json=payload)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["id"], first.json()["id"])

        mine = self.client.get("/api/v1/symptoms/mine", headers=headers)
        self.assertEqual(mine.status_code, 200)
        matching = [item for item in mine.json() if item["id_local"] == id_local]
        self.assertEqual(len(matching), 1)

    def test_06_csv_import_validation_reload_and_history(self):
        med = self._login("medico.e2e@salud.jalisco.gob.mx", "MedPass2026!")
        headers = {"Authorization": f"Bearer {med['token']}"}

        invalid = self.client.post(
            "/api/v1/datasets/import",
            headers=headers,
            data={"enfermedad": "dengue", "fuente": "Test"},
            files={"file": ("invalido.csv", b"A,B\n1,2\n", "text/csv")},
        )
        self.assertEqual(invalid.status_code, 400)

        csv_bytes = (
            "FECHA_SIGN_SINTOMAS,MUNICIPIO_RES,ESTATUS_CASO,EDAD_ANOS,DEFUNCION\n"
            "2026-10-27,39,2,34,2\n"
            "2026-10-28,14120,1,21,2\n"
            "2026-10-28,002,2,45,2\n"
        ).encode("utf-8")
        imported = self.client.post(
            "/api/v1/datasets/import",
            headers=headers,
            data={"enfermedad": "dengue", "fuente": "SSJ E2E"},
            files={"file": ("dengue_e2e.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertEqual(imported.json()["filas_validas"], 2)
        self.assertEqual(imported.json()["filas_descartadas"], 1)
        self.assertEqual(imported.json()["ultima_semana"], "2026-W44")

        dup = self.client.post(
            "/api/v1/datasets/import",
            headers=headers,
            data={"enfermedad": "dengue", "fuente": "SSJ E2E"},
            files={"file": ("dengue_e2e.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(dup.status_code, 409)

        datasets = self.client.get("/api/v1/datasets", headers=headers)
        self.assertEqual(datasets.status_code, 200)
        self.assertEqual(len(datasets.json()["imports"]), 1)

    def test_07_paciente_registration_and_login(self):
        email = f"Nuevo.Pac.{uuid.uuid4().hex[:6]}@jalisco.mx"
        reg = self.client.post(
            "/api/v1/auth/register-paciente",
            json={
                "email": f"  {email} ",
                "password": "PacRegistro2026!",
                "municipio_id": "14120",
            },
        )
        self.assertEqual(reg.status_code, 201, reg.text)
        data = reg.json()
        self.assertEqual(data["role"], "paciente")
        self.assertEqual(data["email"], email.lower())
        self.assertEqual(data["municipio_id"], "14120")
        self.assertTrue(data["token"])

        me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {data['token']}"},
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["role"], "paciente")
        self.assertTrue(me.json()["verificado"])

        # Login posterior con el mismo correo
        logged = self._login(email.lower(), "PacRegistro2026!")
        self.assertEqual(logged["uid"], data["uid"])

        # Correo duplicado (insensible a mayúsculas)
        dup = self.client.post(
            "/api/v1/auth/register-paciente",
            json={"email": email.lower(), "password": "PacRegistro2026!"},
        )
        self.assertEqual(dup.status_code, 400)

        # Contraseña corta y municipio inválido
        short_pwd = self.client.post(
            "/api/v1/auth/register-paciente",
            json={"email": "otro.pac@jalisco.mx", "password": "123"},
        )
        self.assertEqual(short_pwd.status_code, 400)

        bad_muni = self.client.post(
            "/api/v1/auth/register-paciente",
            json={
                "email": "otro.pac@jalisco.mx",
                "password": "PacRegistro2026!",
                "municipio_id": "99999",
            },
        )
        self.assertEqual(bad_muni.status_code, 400)

    def test_08_admin_user_management_and_symptoms_summary(self):
        func = self._login("funcionario.e2e@salud.jalisco.gob.mx", "FuncPass2026!")
        med = self._login("medico.e2e@salud.jalisco.gob.mx", "MedPass2026!")
        pac = self._login("paciente.e2e@jalisco.mx", "PacPass2026!")
        func_headers = {"Authorization": f"Bearer {func['token']}"}
        med_headers = {"Authorization": f"Bearer {med['token']}"}
        pac_headers = {"Authorization": f"Bearer {pac['token']}"}

        # Médico y paciente no pueden listar ni crear usuarios desde administración
        self.assertEqual(self.client.get("/api/v1/auth/users", headers=med_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/auth/users", headers=pac_headers).status_code, 403)

        listed = self.client.get("/api/v1/auth/users", headers=func_headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertGreaterEqual(len(listed.json()), 3)

        created_email = f"admin.created.{uuid.uuid4().hex[:6]}@salud.jalisco.gob.mx"
        created = self.client.post(
            "/api/v1/auth/users",
            headers=func_headers,
            json={
                "email": created_email,
                "password": "TempUser2026!",
                "role": "medico",
                "municipio_id": "14120",
                "institucion": "Hospital Zapopan",
                "cedula": "MED-999111",
                "verificado": False,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        new_uid = created.json()["uid"]
        self.assertFalse(created.json()["verificado"])

        # Actualizar verificación y municipio
        updated = self.client.patch(
            f"/api/v1/auth/users/{new_uid}",
            headers=func_headers,
            json={"verificado": True, "municipio_id": "14039"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertTrue(updated.json()["verificado"])
        self.assertEqual(updated.json()["municipio_id"], "14039")

        # Funcionario no puede quitarse su propio rol ni auto-eliminarse
        self_demote = self.client.patch(
            f"/api/v1/auth/users/{func['uid']}",
            headers=func_headers,
            json={"role": "paciente"},
        )
        self.assertEqual(self_demote.status_code, 400)
        self_delete = self.client.delete(
            f"/api/v1/auth/users/{func['uid']}",
            headers=func_headers,
        )
        self.assertEqual(self_delete.status_code, 400)

        # Eliminar usuario creado
        deleted = self.client.delete(f"/api/v1/auth/users/{new_uid}", headers=func_headers)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertTrue(deleted.json()["eliminado"])

        # Resumen anonimizado de síntomas móviles
        self.assertEqual(self.client.get("/api/v1/symptoms/summary", headers=pac_headers).status_code, 403)
        sym_summary = self.client.get("/api/v1/symptoms/summary", headers=func_headers)
        self.assertEqual(sym_summary.status_code, 200, sym_summary.text)
        self.assertIn("total_reportes", sym_summary.json())
        self.assertIn("por_sospecha", sym_summary.json())


if __name__ == "__main__":
    unittest.main()

