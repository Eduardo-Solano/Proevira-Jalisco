import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from backend.db.database import get_db
from backend.db.models import Alerta
from backend.schemas.alert import (
    AlertResponse,
    AlertCreateRequest,
    AlertCreateResponse,
    AlertPatchRequest
)
from backend.ws.manager import manager
from backend.core.security import require_roles, decode_token

router = APIRouter(tags=["Alertas"])


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
    current_user: dict = Depends(require_roles(["funcionario"]))
):
    """
    Crea una nueva alerta epidemiológica (Exclusivo funcionario)
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
        created_at=datetime.datetime.utcnow()
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


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: int,
    request: AlertPatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["funcionario"]))
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

