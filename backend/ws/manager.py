import json
import logging
from typing import List, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger("proevira.ws")


class ConnectionManager:
    def __init__(self):
        # Lista de WebSockets activos
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket conectado. Total activos: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket desconectado. Total activos: {len(self.active_connections)}")

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        try:
            await websocket.send_text(json.dumps(message, ensure_ascii=False, default=str))
        except Exception as e:
            logger.error(f"Error enviando mensaje personal: {e}")

    async def broadcast(self, message: Dict[str, Any]):
        """Envía el mensaje en tiempo real a todos los clientes conectados."""
        logger.info(f"Emitiendo broadcast a {len(self.active_connections)} clientes...")
        dead_connections = []
        payload = json.dumps(message, ensure_ascii=False, default=str)

        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"Error enviando a cliente WebSocket, marcando para remover: {e}")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


# Instancia única del gestor de conexiones
manager = ConnectionManager()

