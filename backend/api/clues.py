from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.db.models import Clue
from backend.schemas.clue import ClueNearestItem, ClueDetailResponse
from backend.core.geo import rank_nearest_units
from backend.core.security import require_roles

router = APIRouter(prefix="/clues", tags=["CLUES / Geolocalización"])


@router.get("/nearest", response_model=List[ClueNearestItem])
def get_nearest_clues(
    lat: float = Query(..., ge=18.0, le=24.0, description="Latitud de origen"),
    lon: float = Query(..., ge=-106.0, le=-100.0, description="Longitud de origen"),
    limit: int = Query(5, ge=1, le=20, description="Cantidad máxima de unidades"),
    db: Session = Depends(get_db)
):
    """
    Busca las unidades de salud (CLUES) más cercanas a la coordenada indicada
    utilizando cálculo de distancia geodésica ortodrómica (Haversine).
    """
    all_clues = db.query(Clue).all()
    units_dict = [
        {
            "clues": c.clues,
            "nombre": c.nombre,
            "institucion": c.institucion,
            "nivel_atencion": c.nivel_atencion,
            "direccion": c.direccion,
            "lat": c.lat,
            "lon": c.lon
        }
        for c in all_clues
    ]

    nearest = rank_nearest_units(lat, lon, units_dict, limit=limit)
    return [ClueNearestItem(**item) for item in nearest]


@router.get("/{clues_id}", response_model=ClueDetailResponse)
def get_clue_detail(clues_id: str, db: Session = Depends(get_db)):
    """
    Obtiene la ficha técnica detallada de una unidad médica CLUES.
    """
    unit = db.query(Clue).filter(Clue.clues == clues_id.strip()).first()
    if not unit:
        raise HTTPException(status_code=404, detail=f"Unidad CLUES {clues_id} no encontrada")

    return ClueDetailResponse.from_orm(unit) if hasattr(ClueDetailResponse, "from_orm") else ClueDetailResponse(
        clues=unit.clues,
        nombre=unit.nombre,
        institucion=unit.institucion,
        tipo=unit.tipo,
        nivel_atencion=unit.nivel_atencion,
        municipio_id=unit.municipio_id,
        municipio=unit.municipio,
        direccion=unit.direccion,
        telefono=unit.telefono,
        horario=unit.horario,
        lat=unit.lat,
        lon=unit.lon
    )


@router.get("", response_model=List[ClueDetailResponse])
def get_clues_catalog(
    municipio_id: Optional[str] = Query(None, description="Filtrar por municipio"),
    limit: int = Query(100, ge=1, le=1500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["funcionario", "medico"]))
):
    """
    Catálogo completo de unidades médicas para administración y cartografía.
    """
    query = db.query(Clue)
    if municipio_id:
        m_id = str(municipio_id)
        if len(m_id) == 3:
            m_id = f"14{m_id}"
        query = query.filter(Clue.municipio_id == m_id)

    units = query.limit(limit).all()
    return [
        ClueDetailResponse(
            clues=u.clues,
            nombre=u.nombre,
            institucion=u.institucion,
            tipo=u.tipo,
            nivel_atencion=u.nivel_atencion,
            municipio_id=u.municipio_id,
            municipio=u.municipio,
            direccion=u.direccion,
            telefono=u.telefono,
            horario=u.horario,
            lat=u.lat,
            lon=u.lon
        )
        for u in units
    ]

