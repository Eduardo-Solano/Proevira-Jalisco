import os
import json
from fastapi import APIRouter, Depends
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

    return {
        "api": "1.0",
        "modelo": "rf-regresor-regional-v1",
        "fecha_entrenamiento": fecha_entrenamiento,
        "sistema": settings.PROJECT_NAME
    }

