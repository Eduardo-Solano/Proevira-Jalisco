"""
Script de inicialización y carga de datos base (Seed).
Puebla:
1. Municipios (12 municipios de la Región Centro desde GeoJSON).
2. Catálogo CLUES (unidades médicas en operación).
3. Usuarios de prueba (funcionario, médico, paciente).
4. Predicciones base (última semana disponible y semana t+1).
5. Alerta preventiva inicial.

Uso:
  python backend/db/seed.py
"""
import os
import sys
import json
import uuid
import datetime
import pandas as pd

# Añadir la raíz del proyecto al sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from backend.config import settings
from backend.db.database import engine, SessionLocal, Base
from backend.db.models import Municipio, Clue, Prediccion, Alerta, Usuario
from backend.core.security import get_password_hash
from backend.core.inference import inference_engine


def seed_municipios(db):
    print("-> Cargando catálogo de Municipios...")
    geojson_path = os.path.join(settings.CLEAN_DATA_DIR, "municipios.geojson")
    if not os.path.exists(geojson_path):
        print(f"   [!] No se encontró {geojson_path}")
        return {}

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    municipios = {}
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        mid = str(props.get("municipio_id"))
        coords = feat.get("geometry", {}).get("coordinates", [0, 0])
        nombre = props.get("nombre", "")

        existing = db.query(Municipio).filter(Municipio.id == mid).first()
        if not existing:
            muni = Municipio(
                id=mid,
                nombre=nombre,
                lat=coords[1],
                lon=coords[0]
            )
            db.add(muni)
        municipios[mid] = nombre

    db.commit()
    print(f"   [OK] {len(municipios)} municipios cargados.")
    return municipios


def seed_clues(db, municipios_validos):
    print("-> Cargando catálogo CLUES...")
    clues_path = os.path.join(settings.CLEAN_DATA_DIR, "clues.csv")
    if not os.path.exists(clues_path):
        print(f"   [!] No se encontró {clues_path}")
        return

    df = pd.read_csv(clues_path, dtype=str)
    # Filtrar solo municipios válidos
    if municipios_validos:
        df = df[df["municipio_id"].isin(municipios_validos)]

    count = 0
    for _, row in df.iterrows():
        cid = str(row["clues"]).strip()
        existing = db.query(Clue).filter(Clue.clues == cid).first()
        if not existing:
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (ValueError, TypeError):
                continue

            clue = Clue(
                clues=cid,
                nombre=str(row["nombre"]).strip(),
                institucion=str(row.get("institucion", "")) if pd.notna(row.get("institucion")) else None,
                tipo=str(row.get("tipo", "")) if pd.notna(row.get("tipo")) else None,
                nivel_atencion=str(row.get("nivel_atencion", "")) if pd.notna(row.get("nivel_atencion")) else None,
                municipio_id=str(row["municipio_id"]),
                municipio=str(row.get("municipio", "")) if pd.notna(row.get("municipio")) else None,
                direccion=str(row.get("direccion", "")) if pd.notna(row.get("direccion")) else None,
                telefono=str(row.get("telefono", "")) if pd.notna(row.get("telefono")) else None,
                horario=str(row.get("horario", "")) if pd.notna(row.get("horario")) else None,
                lat=lat,
                lon=lon
            )
            db.add(clue)
            count += 1

    db.commit()
    print(f"   [OK] {count} unidades CLUES registradas.")


def seed_usuarios(db):
    print("-> Creando usuarios iniciales por rol...")
    usuarios_demo = [
        {
            "uid": "usr_funcionario_001",
            "email": "admin@proevira.jalisco.gob.mx",
            "password": "AdminPassword2026!",
            "role": "funcionario",
            "municipio_id": "14039",
            "institucion": "Secretaría de Salud Jalisco",
            "verificado": True
        },
        {
            "uid": "usr_medico_001",
            "email": "medico@salud.jalisco.gob.mx",
            "password": "MedicoPassword2026!",
            "role": "medico",
            "municipio_id": "14039",
            "institucion": "Hospital General de Occidente",
            "cedula": "MED-12345678",
            "verificado": True
        },
        {
            "uid": "usr_medico_pendiente",
            "email": "medico.pendiente@salud.jalisco.gob.mx",
            "password": "MedicoPassword2026!",
            "role": "medico",
            "municipio_id": "14120",
            "institucion": "Centro de Salud Zapopan Norte",
            "cedula": "MED-87654321",
            "verificado": False  # Para probar endpoint /auth/verify-medico
        },
        {
            "uid": "usr_paciente_001",
            "email": "paciente@ciudadano.mx",
            "password": "PacientePassword2026!",
            "role": "paciente",
            "municipio_id": "14039",
            "verificado": True
        }
    ]

    for u in usuarios_demo:
        existing = db.query(Usuario).filter(Usuario.email == u["email"]).first()
        if not existing:
            user = Usuario(
                uid=u["uid"],
                email=u["email"],
                hashed_password=get_password_hash(u["password"]),
                role=u["role"],
                municipio_id=u.get("municipio_id"),
                institucion=u.get("institucion"),
                cedula=u.get("cedula"),
                verificado=u.get("verificado", True),
                created_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            )
            db.add(user)

    db.commit()
    print("   [OK] Usuarios demo creados:")
    print("        - Funcionario: admin@proevira.jalisco.gob.mx / AdminPassword2026!")
    print("        - Médico:      medico@salud.jalisco.gob.mx / MedicoPassword2026!")
    print("        - Paciente:    paciente@ciudadano.mx / PacientePassword2026!")


def seed_predicciones(db, municipios_validos):
    print("-> Generando y almacenando predicciones base del modelo...")
    enfermedades = ["dengue", "influenza", "covid"]

    count = 0
    for enf in enfermedades:
        for mid in municipios_validos:
            try:
                res = inference_engine.predict_municipio(mid, enfermedad=enf)
                semana = res["semana"]

                # Reemplazar la predicción de esa semana (el seed puede re-ejecutarse tras reentrenar)
                db.query(Prediccion).filter(
                    Prediccion.municipio_id == mid,
                    Prediccion.semana == semana,
                    Prediccion.enfermedad == enf
                ).delete()
                existing = db.query(Prediccion).filter(
                    Prediccion.municipio_id == mid,
                    Prediccion.semana == semana,
                    Prediccion.enfermedad == enf
                ).first()

                if not existing:
                    pred = Prediccion(
                        municipio_id=mid,
                        semana=semana,
                        enfermedad=enf,
                        casos_esperados=res["casos_esperados"],
                        nivel_riesgo=res["nivel_riesgo"],
                        shap_top3=json.dumps(res["shap_top3"], ensure_ascii=False),
                        created_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                    )
                    db.add(pred)
                    count += 1
            except Exception as e:
                print(f"   [!] Error prediciendo {mid} {enf}: {e}")

    db.commit()
    print(f"   [OK] {count} predicciones base persistidas en base de datos.")


def seed_alertas(db):
    print("-> Creando alerta epidemiológica de inicio...")
    existing = db.query(Alerta).first()
    if not existing:
        alerta = Alerta(
            municipio_id="14039",  # Guadalajara o regional
            nivel="medio",
            mensaje="Vigilancia activa de Dengue en Región Centro ante temporada de transición estacional.",
            activa=True,
            created_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        )
        db.add(alerta)
        db.commit()
        print("   [OK] Alerta inicial activa registrada.")


def main():
    print("=== Inicializando Persistencia SQLite de Proevira Jalisco ===")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        municipios = seed_municipios(db)
        seed_clues(db, set(municipios.keys()))
        seed_usuarios(db)
        seed_predicciones(db, list(municipios.keys()))
        seed_alertas(db)
        print("=== Base de datos poblada exitosamente ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()

