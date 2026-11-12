from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class AlertCreateRequest(BaseModel):
    municipio_id: Optional[str] = None
    nivel: str  # "bajo", "medio", "alto", "crítico"
    mensaje: str


class AlertPatchRequest(BaseModel):
    activa: bool


class AlertResponse(BaseModel):
    id: int
    municipio: Optional[str] = None
    nivel: str
    mensaje: str
    activa: bool
    ts: datetime

    class Config:
        from_attributes = True


class AlertCreateResponse(BaseModel):
    id: int
    emitida: bool
    mensaje: str
    alerta: AlertResponse

