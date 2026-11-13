from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class ShapFeature(BaseModel):
    feature: str
    valor: float


class PredictionResponse(BaseModel):
    municipio: str
    municipio_nombre: Optional[str] = None
    semana: str
    enfermedad: str
    casos_esperados: float
    casos_esperados_redondeados: Optional[int] = None
    umbrales: Optional[List[float]] = None  # cortes [bajo/medio, medio/alto, alto/crítico] del municipio
    prediccion_regional: Optional[float] = None
    participacion_pct: Optional[float] = None
    nivel_riesgo: str
    shap_top3: List[ShapFeature] = []


class BulkPredictionItem(BaseModel):
    municipio: str
    nombre: Optional[str] = None
    lat: float
    lon: float
    semana: str
    enfermedad: str
    casos_esperados: float
    casos_esperados_redondeados: Optional[int] = None
    nivel_riesgo: str


class HistoryPoint(BaseModel):
    semana: str
    casos: int


class ForecastPoint(BaseModel):
    semana: str
    casos: float
    nivel: str


class PredictionHistoryResponse(BaseModel):
    municipio: str
    enfermedad: str
    historico: List[HistoryPoint]
    prediccion: List[ForecastPoint]


class RegionForecastPoint(BaseModel):
    semana: str
    casos: float


class RegionPredictionHistoryResponse(BaseModel):
    region: str
    enfermedad: str
    municipios_incluidos: int
    historico: List[HistoryPoint]
    prediccion: List[RegionForecastPoint]


class FeatureImportanceItem(BaseModel):
    feature: str
    shap: float


class ExplainResponse(BaseModel):
    municipio: str
    semana: str
    enfermedad: str
    casos_esperados: float
    nivel_riesgo: str
    base_value: float
    feature_importance: List[FeatureImportanceItem]

