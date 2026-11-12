from typing import Optional
from pydantic import BaseModel


class ClueNearestItem(BaseModel):
    clues: str
    nombre: str
    institucion: Optional[str] = None
    nivel_atencion: Optional[str] = None
    direccion: Optional[str] = None
    distancia_km: float
    lat: float
    lon: float


class ClueDetailResponse(BaseModel):
    clues: str
    nombre: str
    institucion: Optional[str] = None
    tipo: Optional[str] = None
    nivel_atencion: Optional[str] = None
    municipio_id: str
    municipio: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    horario: Optional[str] = None
    lat: float
    lon: float

    class Config:
        from_attributes = True

