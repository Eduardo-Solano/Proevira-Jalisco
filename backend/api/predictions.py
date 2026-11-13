import os
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.db.models import Prediccion
from backend.schemas.prediction import (
    PredictionResponse,
    BulkPredictionItem,
    PredictionHistoryResponse,
    ExplainResponse,
    FeatureImportanceItem,
    ShapFeature
)
from backend.core.inference import inference_engine
from backend.core.security import get_current_user, require_roles
from backend.config import settings

router = APIRouter(prefix="/predictions", tags=["Predicciones"])


@router.get("", response_model=PredictionResponse)
def get_prediction(
    municipio: str = Query(..., description="Clave de municipio (p.ej. 14039 o 039)"),
    semana: Optional[str] = Query(None, description="Semana ISO (p.ej. 2026-W45). Si se omite, calcula t+1"),
    enfermedad: str = Query("dengue", description="dengue, influenza o covid"),
    db: Session = Depends(get_db)
):
    """
    Predicción de casos y nivel de riesgo para un municipio y enfermedad.
    Primero busca en la persistencia caché SQLite; si no existe, invoca al motor de inferencia.
    """
    enfermedad = enfermedad.lower()
    if enfermedad not in ["dengue", "influenza", "covid"]:
        raise HTTPException(status_code=400, detail="Enfermedad debe ser dengue, influenza o covid")

    m_id = str(municipio)
    if len(m_id) == 3:
        m_id = f"14{m_id}"

    # Si se pide una semana específica, buscar si ya está en BD
    if semana:
        cached = db.query(Prediccion).filter(
            Prediccion.municipio_id == m_id,
            Prediccion.semana == semana,
            Prediccion.enfermedad == enfermedad
        ).first()

        if cached:
            shap_list = []
            if cached.shap_top3:
                try:
                    raw_shap = json.loads(cached.shap_top3)
                    shap_list = [ShapFeature(**item) for item in raw_shap]
                except Exception:
                    pass

            return PredictionResponse(
                municipio=cached.municipio_id,
                municipio_nombre=inference_engine.municipios_coords.get(cached.municipio_id, {}).get("nombre"),
                semana=cached.semana,
                enfermedad=cached.enfermedad,
                casos_esperados=cached.casos_esperados,
                nivel_riesgo=cached.nivel_riesgo,
                shap_top3=shap_list
            )

    # Inferencia dinámica
    res = inference_engine.predict_municipio(m_id, semana=semana, enfermedad=enfermedad)
    return PredictionResponse(**res)


@router.get("/bulk", response_model=List[BulkPredictionItem])
def get_predictions_bulk(
    semana: Optional[str] = Query(None, description="Semana ISO"),
    enfermedad: str = Query("dengue", description="dengue, influenza o covid"),
    current_user: dict = Depends(require_roles(["funcionario", "medico"]))
):
    """
    Predicciones de todos los 12 municipios de la Región Centro (usado para mapas de calor).
    """
    enfermedad = enfermedad.lower()
    res = inference_engine.predict_bulk(semana=semana, enfermedad=enfermedad)
    return [BulkPredictionItem(**item) for item in res]


@router.get("/history", response_model=PredictionHistoryResponse)
def get_predictions_history(
    municipio: str = Query("14039", description="Clave municipio"),
    enfermedad: str = Query("dengue", description="dengue, influenza o covid"),
    semanas: int = Query(12, ge=4, le=52),
    horizonte: int = Query(1, ge=1, le=4, description="Número de semanas a proyectar"),
    current_user: dict = Depends(require_roles(["funcionario", "medico"]))
):
    """
    Serie histórica observada + proyección semanal recursiva para graficar tendencias en Streamlit o Móvil.
    """
    res = inference_engine.get_history(
        municipio,
        enfermedad=enfermedad,
        semanas=semanas,
        horizonte=horizonte,
    )
    return PredictionHistoryResponse(**res)


@router.get("/explain", response_model=ExplainResponse)
def get_prediction_explanation(
    municipio: str = Query("14039"),
    semana: Optional[str] = Query(None),
    enfermedad: str = Query("dengue"),
    current_user: dict = Depends(require_roles(["funcionario", "medico"]))
):
    """
    Explicabilidad SHAP local de la predicción municipal activa (con respaldo global por enfermedad).
    """
    try:
        res = inference_engine.explain_municipio(municipio, semana=semana, enfermedad=enfermedad)
        return ExplainResponse(**res)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error generando explicación SHAP: {str(e)}"
        )

