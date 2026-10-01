from uuid import UUID
from dataclasses import dataclass, field
from time import monotonic
from fastapi import WebSocket

from meridian_backend.schemas.realtime import RealtimeMessage


@dataclass
class ConnectionState:
    websocket: WebSocket
    last_seen: float = field(default_factory=monotonic)

@dataclass
class SessionState:
    session_id: UUID
    connection_id: UUID
    last_seen: float = field(default_factory=monotonic)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[UUID, ConnectionState] = {}
        self.sessions: dict[UUID, SessionState] = {}

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)

    async def connect(self, connection_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[connection_id] = (ConnectionState(websocket))

    def disconnect(self, connection_id: UUID) -> None:
        self.active_connections.pop(connection_id, None)

    async def send_json(self, connection_id: UUID, payload: RealtimeMessage) -> None:
        connection = self.active_connections.get(connection_id)

        if connection is None:
            return

        await connection.websocket.send_json(payload.model_dump(mode="json"))
    
    def mark_seen(self, connection_id: UUID) -> None:
        connection = self.active_connections.get(connection_id)
        if connection is not None:
            connection.last_seen = monotonic()
