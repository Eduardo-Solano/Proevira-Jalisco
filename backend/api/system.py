import os
import json
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.db.database import get_db
from backend.core.inference import inference_engine
from backend.config import settings

router = APIRouter(tags=["Sistema"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Healthcheck para monitoreo y plataformas como Render/Fly.io."""
    db_status = "error"
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "modelo_cargado": inference_engine.loaded,
        "db": db_status
    }


@router.get("/version")
def version_info():
    """Información de versión de API y modelo predictivo."""
    metricas_path = os.path.join(settings.MODEL_ARTIFACTS_DIR, "metricas.json")
    fecha_entrenamiento = None
    if os.path.exists(metricas_path):
        try:
            with open(metricas_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                fecha_entrenamiento = data.get("fecha_entrenamiento")
        except Exception:
            pass

    latest_week = None
    predicted_week = None
    if inference_engine.loaded and inference_engine.raw_data is not None:
        latest_date = inference_engine.raw_data["fecha_inicio_semana"].max()
        if not pd.isna(latest_date):
            latest_week = str(inference_engine.raw_data.loc[
                inference_engine.raw_data["fecha_inicio_semana"] == latest_date,
                "semana",
            ].iloc[0])
            next_week = (pd.Timestamp(latest_date) + pd.Timedelta(days=7)).isocalendar()
            predicted_week = f"{next_week.year}-W{next_week.week:02d}"

    return {
        "api": "1.0",
        "modelo": "rf-regresor-regional-v1",
        "fecha_entrenamiento": fecha_entrenamiento,
        "ultima_semana_datos": latest_week,
        "semana_prediccion": predicted_week,
        "sistema": settings.PROJECT_NAME
    }


@router.get("/model/metrics")
def model_metrics():
    """Publica las métricas de evaluación generadas por model/train.py."""
    metricas_path = os.path.join(settings.MODEL_ARTIFACTS_DIR, "metricas.json")
    if not os.path.exists(metricas_path):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se encontraron métricas de entrenamiento. Ejecuta model/train.py.",
        )

    try:
        with open(metricas_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudieron leer las métricas del modelo.",
        ) from error

    return {
        "fecha_entrenamiento": data.get("fecha_entrenamiento"),
        "split": data.get("split", {}),
        "test": data.get("test", {}),
    }
