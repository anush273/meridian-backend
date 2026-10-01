from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

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

    next_server_sequence: int = 1
    last_acked_sequence: int = 0
    pending_messages: dict[int, RealtimeMessage] = field(default_factory=dict[int, RealtimeMessage])


class ConnectionManager:
    def __init__(self, session_timeout: float = 1800, max_pending_messages: int = 1000) -> None:
        if max_pending_messages < 1:
            raise ValueError("max_pending_messages must be positive")
        self.max_pending_messages = max_pending_messages
        self.session_timeout = session_timeout
        self.active_connections: dict[UUID, ConnectionState] = {}
        self.sessions: dict[UUID, SessionState] = {}

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)

    async def connect(self, connection_id: UUID, websocket: WebSocket) -> None:
        self.active_connections[connection_id] = ConnectionState(websocket)
        try:
            await websocket.accept()
        except BaseException:
            self.disconnect(connection_id)
            raise

    def disconnect(self, connection_id: UUID) -> None:
        self.active_connections.pop(connection_id, None)
        for session in self.sessions.values():
            if session.connection_id == connection_id:
                session.last_seen = monotonic()

    async def send_json(self, connection_id: UUID, payload: RealtimeMessage) -> None:
        connection = self.active_connections.get(connection_id)

        if connection is None:
            return

        await connection.websocket.send_json(payload.model_dump(mode="json"))

    def mark_seen(self, connection_id: UUID) -> None:
        connection = self.active_connections.get(connection_id)
        if connection is not None:
            connection.last_seen = monotonic()
            for session in self.sessions.values():
                if session.connection_id == connection_id:
                    session.last_seen = connection.last_seen

    def expire_sessions(self) -> None:
        now = monotonic()
        expired = [
            session_id
            for session_id, session in self.sessions.items()
            if session.connection_id not in self.active_connections
            and now - session.last_seen >= self.session_timeout
        ]
        for session_id in expired:
            del self.sessions[session_id]

    def create_session(self, connection_id: UUID) -> UUID:
        self.expire_sessions()
        session_id = uuid4()

        self.sessions[session_id] = SessionState(session_id=session_id, connection_id=connection_id)

        return session_id

    def resume_session(self, session_id: UUID, connection_id: UUID) -> bool:
        self.expire_sessions()
        session = self.sessions.get(session_id)
        if session is None or session.connection_id in self.active_connections:
            return False
        session.connection_id = connection_id
        session.last_seen = monotonic()
        return True

    async def send_session_message(
        self,
        session_id: UUID,
        message_type: str,
        data: dict[str, Any],
    ) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError("Unknown session")
        if len(session.pending_messages) >= self.max_pending_messages:
            raise BufferError("Session pending message buffer is full")
        sequence = session.next_server_sequence
        payload = RealtimeMessage(type=message_type, sequence=sequence, data=data)
        session.next_server_sequence += 1
        session.pending_messages[sequence] = payload
        await self.send_json(session.connection_id, payload)

    def acknowledge(self, session_id: UUID, sequence: int) -> bool:
        """Acknowledge all session messages through sequence, inclusive."""
        session = self.sessions.get(session_id)
        if session is None or sequence < 0 or sequence >= session.next_server_sequence:
            return False
        if sequence <= session.last_acked_sequence:
            return True
        session.last_acked_sequence = sequence
        for pending_sequence in list(session.pending_messages):
            if pending_sequence <= sequence:
                del session.pending_messages[pending_sequence]
        return True

    async def replay_session_messages(self, session_id: UUID) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError("Unknown session")
        connection_id = session.connection_id
        for sequence, payload in list(session.pending_messages.items()):
            if session.connection_id != connection_id:
                return
            if sequence in session.pending_messages:
                await self.send_json(connection_id, payload)
