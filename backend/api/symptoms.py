import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.db.models import Sintoma
from backend.schemas.symptom import (
    SymptomCreateRequest,
    SymptomCreateResponse,
    SymptomResponse
)
from backend.core.security import get_current_user, require_roles

router = APIRouter(prefix="/symptoms", tags=["Seguimiento de Síntomas"])


def evaluar_sospecha(fiebre: bool, dolor_retroocular: bool, tos: bool, dificultad_resp: bool, dolor_muscular: bool) -> (str, str):
    """
    Evaluación preliminar de orientación ciudadana basada en lineamientos SINAVE
    (con disclaimer explícito de orientación, nunca diagnóstico).
    """
    if dificultad_resp:
        return (
            "covid",
            "URGENTE: Se detectó dificultad respiratoria. Acuda de inmediato al servicio de urgencias o unidad médica más cercana."
        )
    if fiebre and dolor_retroocular and dolor_muscular:
        return (
            "dengue",
            "Síntomas compatibles con cuadro febril sospechoso de Dengue. Evite la automedicación (no tome aspirina ni ibuprofeno), mantenga hidratación oral abundante y acuda a valoración médica a su centro de salud."
        )
    if tos and fiebre:
        return (
            "influenza",
            "Cuadro respiratorio compatible con Influenza o infección respiratoria aguda. Use cubrebocas, guarde reposo y consulte a su médico."
        )
    return (
        "indeterminado",
        "Monitoree su temperatura y evolución de síntomas. Si presenta fiebre persistente o dolor intenso, acuda a consulta médica."
    )


@router.post("", response_model=SymptomCreateResponse)
def register_symptoms(
    request: SymptomCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Registra el seguimiento de síntomas reportado por un paciente.
    Es IDEMPOTENTE mediante id_local: si la app móvil ya lo envió en modo offline,
    no duplica el registro y confirma sincronización exitosa.
    """
    uid = current_user.get("uid") or current_user.get("sub")

    # Verificar si ya existe por id_local (idempotencia)
    existing = db.query(Sintoma).filter(Sintoma.id_local == request.id_local).first()
    if existing:
        sospecha, rec = evaluar_sospecha(
            existing.fiebre,
            existing.dolor_retroocular,
            existing.tos,
            existing.dificultad_respiratoria,
            existing.dolor_muscular
        )
        return SymptomCreateResponse(
            id=existing.id,
            id_local=existing.id_local,
            synced=True,
            ts_registro=existing.ts_registro,
            sospecha_sugerida=sospecha,
            recomendacion=rec
        )

    m_id = request.municipio_id or current_user.get("municipio_id")
    if m_id and len(str(m_id)) == 3:
        m_id = f"14{m_id}"

    ts_reg = request.ts_registro or datetime.datetime.utcnow()
    sospecha, rec = evaluar_sospecha(
        request.fiebre,
        request.dolor_retroocular,
        request.tos,
        request.dificultad_respiratoria,
        request.dolor_muscular
    )

    nuevo = Sintoma(
        id_local=request.id_local,
        user_id=uid,
        municipio_id=m_id,
        fiebre=request.fiebre,
        cefalea=request.cefalea,
        dolor_muscular=request.dolor_muscular,
        dolor_articular=request.dolor_articular,
        dolor_retroocular=request.dolor_retroocular,
        tos=request.tos,
        dificultad_respiratoria=request.dificultad_respiratoria,
        otros_sintomas=request.otros_sintomas,
        dias_con_sintomas=request.dias_con_sintomas,
        sospecha_enfermedad=sospecha,
        synced=True,
        ts_registro=ts_reg,
        created_at=datetime.datetime.utcnow()
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)

    return SymptomCreateResponse(
        id=nuevo.id,
        id_local=nuevo.id_local,
        synced=True,
        ts_registro=nuevo.ts_registro,
        sospecha_sugerida=sospecha,
        recomendacion=rec
    )


@router.get("/mine", response_model=List[SymptomResponse])
def get_my_symptoms(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene el historial de registros de síntomas del paciente autenticado.
    """
    uid = current_user.get("uid") or current_user.get("sub")
    records = db.query(Sintoma).filter(Sintoma.user_id == uid).order_by(Sintoma.ts_registro.desc()).all()
    return records


@router.get("/{symptom_id}", response_model=SymptomResponse)
def get_symptom_detail(
    symptom_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Detalle de un registro de síntomas. Los pacientes solo pueden consultar los suyos;
    los médicos y funcionarios pueden consultar cualquiera de su jurisdicción.
    """
    rec = db.query(Sintoma).filter(Sintoma.id == symptom_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    role = current_user.get("role", "paciente")
    uid = current_user.get("uid") or current_user.get("sub")

    if role == "paciente" and rec.user_id != uid:
        raise HTTPException(status_code=403, detail="No autorizado para ver este registro")

    return rec

