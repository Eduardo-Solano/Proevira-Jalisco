import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.db.models import Alerta, AlertaPredictivaBorrador
from backend.schemas.alert import (
    AlertResponse,
    AlertCreateRequest,
    AlertCreateResponse,
    AlertPatchRequest,
    PredictiveAlertDraftResponse,
    PredictiveAlertDraftReviewRequest,
)
from backend.ws.manager import manager
from backend.core.security import require_roles, decode_token
from backend.core.inference import inference_engine

router = APIRouter(tags=["Alertas"])
NIVELES_ALERTA_PREDICTIVA = {"medio", "alto", "crítico"}
ROLES_EMISION_ALERTAS = ["funcionario", "medico", "admin", "administrador"]


def _utcnow_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _borrador_response(borrador: AlertaPredictivaBorrador) -> PredictiveAlertDraftResponse:
    return PredictiveAlertDraftResponse(
        id=borrador.id,
        municipio=borrador.municipio_id,
        semana=borrador.semana,
        enfermedad=borrador.enfermedad,
        nivel=borrador.nivel,
        casos_esperados=borrador.casos_esperados,
        mensaje=borrador.mensaje,
        estado=borrador.estado,
        created_at=borrador.created_at,
    )


@router.get("/alerts", response_model=List[AlertResponse])
def get_alerts(
    municipio: Optional[str] = Query(None, description="Filtrar por municipio"),
    activa: Optional[bool] = Query(True, description="Filtrar solo activas"),
    db: Session = Depends(get_db)
):
    """
    Lista de alertas epidemiológicas registradas en el sistema.
    """
    query = db.query(Alerta)
    if activa is not None:
        query = query.filter(Alerta.activa == activa)
    if municipio:
        m_id = str(municipio)
        if len(m_id) == 3:
            m_id = f"14{m_id}"
        query = query.filter((Alerta.municipio_id == m_id) | (Alerta.municipio_id == None))

    query = query.sort_values(Alerta.created_at.desc()) if hasattr(query, "sort_values") else query.order_by(Alerta.created_at.desc())
    alerts = query.all()

    return [
        AlertResponse(
            id=a.id,
            municipio=a.municipio_id,
            nivel=a.nivel,
            mensaje=a.mensaje,
            activa=a.activa,
            ts=a.created_at
        )
        for a in alerts
    ]


@router.post("/alerts", response_model=AlertCreateResponse)
async def create_alert(
    request: AlertCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_EMISION_ALERTAS))
):
    """
    Crea una nueva alerta epidemiológica (médico verificado o administrador/funcionario)
    y la emite inmediatamente en tiempo real vía WebSocket a todos los clientes.
    """
    m_id = request.municipio_id
    if m_id and len(str(m_id)) == 3:
        m_id = f"14{m_id}"

    nueva = Alerta(
        municipio_id=m_id,
        nivel=request.nivel,
        mensaje=request.mensaje,
        activa=True,
        created_at=_utcnow_naive()
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)

    alerta_resp = AlertResponse(
        id=nueva.id,
        municipio=nueva.municipio_id,
        nivel=nueva.nivel,
        mensaje=nueva.mensaje,
        activa=nueva.activa,
        ts=nueva.created_at
    )

    # Broadcast en tiempo real por WebSocket
    ws_payload = {
        "tipo": "alerta",
        "id": nueva.id,
        "municipio": nueva.municipio_id,
        "nivel": nueva.nivel,
        "mensaje": nueva.mensaje,
        "ts": nueva.created_at.isoformat()
    }
    await manager.broadcast(ws_payload)

    return AlertCreateResponse(
        id=nueva.id,
        emitida=True,
        mensaje="Alerta creada y transmitida por WebSocket en tiempo real",
        alerta=alerta_resp
    )


@router.post("/alerts/predictive-drafts/generate")
def generate_predictive_alert_drafts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_EMISION_ALERTAS)),
):
    """Genera borradores idempotentes para proyecciones municipales de riesgo medio o mayor."""
    inference_engine.load()
    municipios = sorted(inference_engine.municipios_info)
    if len(municipios) != 12:
        raise HTTPException(
            status_code=503,
            detail=f"Se esperaban 12 municipios de la Región Centro; se encontraron {len(municipios)}.",
        )

    forecast_weeks = {}
    eligible_forecasts = {}
    evaluated_pairs = 0

    for enfermedad in ("dengue", "influenza", "covid"):
        for municipio_id in municipios:
            history = inference_engine.get_history(
                municipio_id,
                enfermedad=enfermedad,
                semanas=4,
                horizonte=4,
            )
            points = history["prediccion"]
            if not points:
                continue

            evaluated_pairs += 1
            pair = (municipio_id, enfermedad)
            forecast_weeks[pair] = {point["semana"] for point in points}
            for point in points:
                if point["nivel"].lower() not in NIVELES_ALERTA_PREDICTIVA:
                    continue
                eligible_forecasts[(municipio_id, enfermedad, point["semana"])] = point

    if evaluated_pairs != len(municipios) * 3:
        raise HTTPException(
            status_code=503,
            detail="No se pudieron calcular proyecciones para los 12 municipios y las 3 enfermedades.",
        )

    existing_drafts = db.query(AlertaPredictivaBorrador).all()
    draft_by_key = {
        (draft.municipio_id, draft.enfermedad, draft.semana): draft
        for draft in existing_drafts
    }

    created = 0
    updated = 0
    obsolete = 0
    for draft in existing_drafts:
        if draft.estado != "pendiente":
            continue
        weeks = forecast_weeks.get((draft.municipio_id, draft.enfermedad))
        if weeks is None:
            continue
        if (
            draft.semana not in weeks
            or (draft.municipio_id, draft.enfermedad, draft.semana) not in eligible_forecasts
        ):
            draft.estado = "obsoleta"
            draft.reviewed_at = _utcnow_naive()
            draft.reviewed_by = None
            obsolete += 1

    for key, point in eligible_forecasts.items():
        municipio_id, enfermedad, semana = key
        fecha_semana = datetime.date.fromisocalendar(
            int(semana[:4]), int(semana[-2:]), 1
        ).strftime("%d/%m/%Y")
        mensaje = (
            f"Proyección para la semana que inicia el {fecha_semana}: "
            f"{point['casos']:.1f} casos estimados de {enfermedad}. "
            "Borrador predictivo; requiere revisión de un funcionario y no representa "
            "una alerta oficial ni casos confirmados."
        )
        draft = draft_by_key.get((municipio_id, enfermedad, semana))

        if draft is None:
            db.add(
                AlertaPredictivaBorrador(
                    municipio_id=municipio_id,
                    enfermedad=enfermedad,
                    semana=semana,
                    nivel=point["nivel"],
                    casos_esperados=point["casos"],
                    mensaje=mensaje,
                    estado="pendiente",
                )
            )
            created += 1
        elif draft.estado == "pendiente":
            if (
                draft.nivel != point["nivel"]
                or abs(float(draft.casos_esperados) - float(point["casos"])) >= 0.01
                or draft.mensaje != mensaje
            ):
                draft.nivel = point["nivel"]
                draft.casos_esperados = point["casos"]
                draft.mensaje = mensaje
                updated += 1

    db.commit()
    return {
        "municipios_evaluados": len(municipios),
        "borradores_creados": created,
        "borradores_actualizados": updated,
        "borradores_obsoletos": obsolete,
    }


@router.get(
    "/alerts/predictive-drafts",
    response_model=List[PredictiveAlertDraftResponse],
)
def get_predictive_alert_drafts(
    municipio: Optional[str] = Query(None, description="Filtrar por municipio"),
    estado: str = Query("pendiente"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_EMISION_ALERTAS)),
):
    if estado not in {"pendiente", "aprobada", "descartada", "obsoleta"}:
        raise HTTPException(status_code=400, detail="Estado de borrador no válido")

    query = db.query(AlertaPredictivaBorrador).filter(
        AlertaPredictivaBorrador.estado == estado
    )
    if municipio:
        municipio_id = f"14{municipio}" if len(municipio) == 3 else municipio
        query = query.filter(AlertaPredictivaBorrador.municipio_id == municipio_id)

    drafts = query.order_by(
        AlertaPredictivaBorrador.semana.asc(),
        AlertaPredictivaBorrador.nivel.desc(),
        AlertaPredictivaBorrador.id.asc(),
    ).all()
    return [_borrador_response(draft) for draft in drafts]


@router.patch(
    "/alerts/predictive-drafts/{draft_id}",
    response_model=PredictiveAlertDraftResponse,
)
async def review_predictive_alert_draft(
    draft_id: int,
    request: PredictiveAlertDraftReviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_EMISION_ALERTAS)),
):
    if request.decision not in {"aprobar", "descartar"}:
        raise HTTPException(status_code=400, detail="La decisión debe ser 'aprobar' o 'descartar'")

    draft = db.query(AlertaPredictivaBorrador).filter(
        AlertaPredictivaBorrador.id == draft_id
    ).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="Borrador predictivo no encontrado")
    if draft.estado != "pendiente":
        raise HTTPException(status_code=409, detail="El borrador ya fue revisado")

    draft.estado = "aprobada" if request.decision == "aprobar" else "descartada"
    draft.reviewed_at = _utcnow_naive()
    draft.reviewed_by = current_user.get("uid") or current_user.get("email")

    alerta = None
    if request.decision == "aprobar":
        alerta = Alerta(
            municipio_id=draft.municipio_id,
            nivel=draft.nivel,
            mensaje=draft.mensaje,
            activa=True,
            created_at=_utcnow_naive(),
        )
        db.add(alerta)
        db.flush()
        draft.alerta_id = alerta.id

    db.commit()
    db.refresh(draft)

    if alerta is not None:
        await manager.broadcast(
            {
                "tipo": "alerta",
                "id": alerta.id,
                "municipio": alerta.municipio_id,
                "nivel": alerta.nivel,
                "mensaje": alerta.mensaje,
                "ts": alerta.created_at.isoformat(),
            }
        )

    return _borrador_response(draft)


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: int,
    request: AlertPatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(ROLES_EMISION_ALERTAS))
):
    """
    Activa o desactiva una alerta existente.
    """
    alerta = db.query(Alerta).filter(Alerta.id == alert_id).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    alerta.activa = request.activa
    db.commit()

    return {"id": alerta.id, "activa": alerta.activa}


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket, token: Optional[str] = Query(None)):
    """
    Canal WebSocket para recepción en vivo de alertas push.
    Valida el token si se proporciona en la query string.
    """
    # Si viene token, intentar validar
    if token:
        try:
            decode_token(token)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(websocket)
    try:
        # Enviar mensaje de bienvenida y confirmación de conexión
        await manager.send_personal_message(
            {"tipo": "conexion", "mensaje": "Conectado al canal de alertas epidemiológicas de Jalisco"},
            websocket
        )
        while True:
            # Esperar mensajes del cliente (p.ej. ping o keepalive)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

