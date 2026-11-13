import os
import json
import pandas as pd
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.db.models import Prediccion, Alerta, Municipio
from backend.core.inference import inference_engine
from backend.core.security import get_current_user, require_roles
from backend.config import settings

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/mobile-incidence")
def get_mobile_incidence(
    enfermedad: str = Query("dengue"),
    semanas: int = Query(8, ge=4, le=12),
    current_user: dict = Depends(get_current_user),
):
    """Incidencia histórica agregada para el mapa informativo de pacientes."""
    enfermedad = enfermedad.strip().lower()
    if enfermedad not in {"dengue", "influenza", "covid"}:
        raise HTTPException(
            status_code=400,
            detail="Enfermedad debe ser dengue, influenza o covid",
        )

    raw = inference_engine.raw_data
    if raw is None or raw.empty:
        return {
            "enfermedad": enfermedad,
            "semanas": [],
            "puntos": [],
        }

    series = raw[
        raw["enfermedad"].astype(str).str.strip().str.lower() == enfermedad
    ].copy()
    if series.empty:
        return {
            "enfermedad": enfermedad,
            "semanas": [],
            "puntos": [],
        }
    series["fecha_inicio_semana"] = pd.to_datetime(
        series["fecha_inicio_semana"], errors="coerce"
    )
    series = series.dropna(subset=["fecha_inicio_semana"])
    if series.empty:
        return {
            "enfermedad": enfermedad,
            "semanas": [],
            "puntos": [],
        }
    latest = series["fecha_inicio_semana"].max()
    selected_weeks = sorted(
        series.loc[
            series["fecha_inicio_semana"]
            >= latest - pd.Timedelta(weeks=semanas - 1),
            "fecha_inicio_semana",
        ].unique()
    )
    series = series[series["fecha_inicio_semana"].isin(selected_weeks)]
    grouped = (
        series.groupby("municipio_id", as_index=False)
        .agg(
            casos=("casos", "sum"),
            ultima_semana=("fecha_inicio_semana", "max"),
        )
    )

    points = []
    for row in grouped.to_dict("records"):
        municipio_id = str(row["municipio_id"]).zfill(5)
        info = inference_engine.municipios_coords.get(municipio_id, {})
        nombre = info.get("nombre") or row.get("municipio") or municipio_id
        points.append(
            {
                "municipio": municipio_id,
                "nombre": nombre,
                "lat": info.get("lat"),
                "lon": info.get("lon"),
                "casos": int(row["casos"]),
                "promedio_semanal": round(float(row["casos"]) / semanas, 1),
                "ultima_semana": str(row["ultima_semana"].date()),
            }
        )

    return {
        "enfermedad": enfermedad,
        "semanas": [str(item.date()) for item in selected_weeks],
        "puntos": [point for point in points if point["lat"] and point["lon"]],
    }


@router.get("/summary")
def get_dashboard_summary(
    semana: Optional[str] = Query(None, description="Semana ISO"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["funcionario", "medico"]))
):
    """
    Totales proyectados por patología, tendencia agregada y desglose por municipio.
    """
    bulk_dengue = inference_engine.predict_bulk(semana=semana, enfermedad="dengue")
    bulk_flu = inference_engine.predict_bulk(semana=semana, enfermedad="influenza")
    bulk_covid = inference_engine.predict_bulk(semana=semana, enfermedad="covid")

    total_dengue = sum(item["casos_esperados"] for item in bulk_dengue)
    total_flu = sum(item["casos_esperados"] for item in bulk_flu)
    total_covid = sum(item["casos_esperados"] for item in bulk_covid)

    # Agrupar por municipio
    por_municipio = []
    for item in bulk_dengue:
        mid = item["municipio"]
        flu_item = next((x for x in bulk_flu if x["municipio"] == mid), {})
        covid_item = next((x for x in bulk_covid if x["municipio"] == mid), {})

        por_municipio.append({
            "municipio_id": mid,
            "nombre": item["nombre"],
            "lat": item["lat"],
            "lon": item["lon"],
            "dengue_casos": item["casos_esperados"],
            "dengue_riesgo": item["nivel_riesgo"],
            "influenza_casos": flu_item.get("casos_esperados", 0.0),
            "covid_casos": covid_item.get("casos_esperados", 0.0)
        })

    # Serie histórica regional agregada (últimas 12 semanas)
    tendencia = []
    try:
        raw = inference_engine.raw_data
        ultimas_sem = raw["fecha_inicio_semana"].sort_values().unique()[-12:]
        sub = raw[raw["fecha_inicio_semana"].isin(ultimas_sem)]
        agg = sub.groupby(["semana", "enfermedad"])["casos"].sum().unstack(fill_value=0)
        for sem_name, row in agg.iterrows():
            tendencia.append({
                "semana": sem_name,
                "dengue": int(row.get("dengue", 0)),
                "influenza": int(row.get("influenza", 0)),
                "covid": int(row.get("covid", 0))
            })
    except Exception:
        pass

    return {
        "semana": bulk_dengue[0]["semana"] if bulk_dengue else semana,
        "totales": {
            "dengue": round(total_dengue, 1),
            "influenza": round(total_flu, 1),
            "covid": round(total_covid, 1)
        },
        "tendencia": tendencia,
        "por_municipio": por_municipio
    }


@router.get("/kpis")
def get_dashboard_kpis(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["funcionario", "medico"]))
):
    """
    Indicadores clave de desempeño (KPIs) para la toma de decisiones sanitarias.
    """
    bulk = inference_engine.predict_bulk(enfermedad="dengue")
    casos_semana = sum(item["casos_esperados"] for item in bulk)
    municipios_altos = sum(1 for item in bulk if item["nivel_riesgo"] in ["alto", "crítico"])
    alertas_activas = db.query(Alerta).filter(Alerta.activa == True).count()
    hosp_estimadas = round(casos_semana * 0.08, 1)  # Estimación basada en tasa del 8% de dengue con signos de alarma

    return {
        "casos_semana": round(casos_semana, 1),
        "municipios_riesgo_alto": municipios_altos,
        "alertas_activas": alertas_activas,
        "hospitalizaciones_est": hosp_estimadas
    }


@router.get("/heatmap")
def get_dashboard_heatmap(
    semana: Optional[str] = Query(None),
    enfermedad: str = Query("dengue"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["funcionario", "medico"]))
):
    """
    Retorna el GeoJSON y los valores de riesgo por municipio listos para renderizar
    en Folium o MapBox.
    """
    geojson_path = os.path.join(settings.CLEAN_DATA_DIR, "municipios.geojson")
    geo_data = {}
    if os.path.exists(geojson_path):
        with open(geojson_path, "r", encoding="utf-8") as f:
            geo_data = json.load(f)

    bulk = inference_engine.predict_bulk(semana=semana, enfermedad=enfermedad)
    valores = {
        item["municipio"]: {
            "nombre": item["nombre"],
            "casos_esperados": item["casos_esperados"],
            "nivel_riesgo": item["nivel_riesgo"],
            "lat": item["lat"],
            "lon": item["lon"]
        }
        for item in bulk
    }

    return {
        "semana": bulk[0]["semana"] if bulk else semana,
        "enfermedad": enfermedad,
        "geojson": geo_data,
        "valores": valores
    }

