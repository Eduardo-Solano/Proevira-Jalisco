from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class SymptomCreateRequest(BaseModel):
    id_local: str = Field(..., description="UUID generado en el dispositivo para garantizar idempotencia offline")
    municipio_id: Optional[str] = None
    fiebre: bool = False
    cefalea: bool = False
    dolor_muscular: bool = False
    dolor_articular: bool = False
    dolor_retroocular: bool = False
    tos: bool = False
    dificultad_respiratoria: bool = False
    otros_sintomas: Optional[str] = None
    dias_con_sintomas: int = 1
    sospecha_enfermedad: Optional[str] = None
    ts_registro: Optional[datetime] = None


class SymptomResponse(BaseModel):
    id: int
    id_local: str
    user_id: Optional[str] = None
    municipio_id: Optional[str] = None
    fiebre: bool
    cefalea: bool
    dolor_muscular: bool
    dolor_articular: bool
    dolor_retroocular: bool
    tos: bool
    dificultad_respiratoria: bool
    otros_sintomas: Optional[str] = None
    dias_con_sintomas: int
    sospecha_enfermedad: Optional[str] = None
    synced: bool
    ts_registro: datetime
    created_at: datetime
    disclaimer_medico: str = "Esta aplicación es un asistente orientador y no sustituye el diagnóstico médico profesional (NOM-004-SSA3-2012)."

    class Config:
        from_attributes = True


class SymptomCreateResponse(BaseModel):
    id: int
    id_local: str
    synced: bool = True
    ts_registro: datetime
    sospecha_sugerida: Optional[str] = None
    recomendacion: str
    disclaimer_medico: str = "Esta aplicación es un asistente orientador y no sustituye el diagnóstico médico profesional (NOM-004-SSA3-2012)."

