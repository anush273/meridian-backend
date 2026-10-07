import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from meridian_backend.schemas.realtime import RealtimeMessage


class OutBoundFrameType(StrEnum):
    JSON = "json"
    BINARY = "binary"


@dataclass
class OutboundMessage:
    frame_type: OutBoundFrameType
    payload: dict[str, Any] | bytes
    completion: asyncio.Future[None]


@dataclass
class ConnectionState:
    websocket: WebSocket
    last_seen: float = field(default_factory=monotonic)
    outbound_queue: asyncio.Queue[OutboundMessage] = field(
        default_factory=lambda: asyncio.Queue(maxsize=100)
    )
    sender_task: asyncio.Task[None] | None = None


@dataclass
class SessionState:
    session_id: UUID
    connection_id: UUID
    last_seen: float = field(default_factory=monotonic)

    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    replay_required: bool = False
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
        self._disconnect_tasks: dict[UUID, asyncio.Task[None]] = {}

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)

    async def connect(self, connection_id: UUID, websocket: WebSocket) -> None:
        if connection_id in self.active_connections or connection_id in self._disconnect_tasks:
            raise ValueError("Connection already exists")
        state = ConnectionState(websocket)
        self.active_connections[connection_id] = state
        try:
            await websocket.accept()
        except BaseException:
            await self.disconnect(connection_id)
            raise
        state.sender_task = asyncio.create_task(self._sender_loop(connection_id, state))

    async def disconnect(self, connection_id: UUID) -> None:
        """Wait for sender termination and socket closure; concurrent calls share cleanup."""
        task = self._start_disconnect(connection_id)
        if task is not None:
            # Caller cancellation must not abandon resource cleanup.
            await asyncio.shield(task)

    def _start_disconnect(self, connection_id: UUID) -> asyncio.Task[None] | None:
        existing = self._disconnect_tasks.get(connection_id)
        if existing is not None:
            return existing
        state = self.active_connections.pop(connection_id, None)
        if state is None:
            return None
        for session in self.sessions.values():
            if session.connection_id == connection_id:
                session.last_seen = monotonic()
        self._fail_queued_messages(state)
        sender = state.sender_task
        if sender is not None and sender is not asyncio.current_task():
            sender.cancel()
        task = asyncio.create_task(self._cleanup_connection(state))
        self._disconnect_tasks[connection_id] = task
        task.add_done_callback(lambda _: self._disconnect_tasks.pop(connection_id, None))
        return task

    async def _cleanup_connection(self, state: ConnectionState) -> None:
        try:
            if state.sender_task is not None:
                await asyncio.gather(state.sender_task, return_exceptions=True)
        finally:
            self._fail_queued_messages(state)
            if (
                state.websocket.application_state != WebSocketState.DISCONNECTED
                and state.websocket.client_state != WebSocketState.DISCONNECTED
            ):
                # The peer may have closed while the sender was stopping.
                with suppress(WebSocketDisconnect, OSError, RuntimeError):
                    await state.websocket.close()

    async def send_json(self, connection_id: UUID, payload: RealtimeMessage) -> None:
        await self._enqueue_frame(
            connection_id, OutBoundFrameType.JSON, payload.model_dump(mode="json")
        )

    async def send_bytes(self, connection_id: UUID, payload: bytes) -> None:
        await self._enqueue_frame(connection_id, OutBoundFrameType.BINARY, payload)

    async def _enqueue_frame(
        self, connection_id: UUID, frame_type: OutBoundFrameType, payload: dict[str, Any] | bytes
    ) -> None:
        connection = self.active_connections.get(connection_id)

        if connection is None:
            return

        completion = asyncio.get_running_loop().create_future()
        item = OutboundMessage(
            frame_type=frame_type,
            payload=payload,
            completion=completion,
        )
        try:
            connection.outbound_queue.put_nowait(item)
        except asyncio.QueueFull as exc:
            # Stop live delivery so retained session messages can replay in order.
            await self.disconnect(connection_id)
            raise BufferError("Connection outbound queue is full") from exc
        await completion

    async def send_session_audio(self, session_id: UUID, payload: bytes) -> None:
        """Send live audio without sequence numbers, retention, or replay."""
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError("Unknown session")
        async with session.send_lock:
            # Never deliver audio ahead of ready/backlog on a resumed connection.
            if session.replay_required:
                return
            await self.send_bytes(session.connection_id, payload)

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
        session.replay_required = True
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
        async with session.send_lock:
            if len(session.pending_messages) >= self.max_pending_messages:
                raise BufferError("Session pending message buffer is full")
            sequence = session.next_server_sequence
            payload = RealtimeMessage(type=message_type, sequence=sequence, data=data)
            session.next_server_sequence += 1
            session.pending_messages[sequence] = payload
            # A resumed connection must send ready and its backlog before live updates.
            if not session.replay_required:
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
        async with session.send_lock:
            connection_id = session.connection_id
            for sequence, payload in list(session.pending_messages.items()):
                if session.connection_id != connection_id:
                    return
                if sequence > session.last_acked_sequence and sequence in session.pending_messages:
                    await self.send_json(connection_id, payload)
            if session.connection_id == connection_id:
                session.replay_required = False

    @staticmethod
    def _fail_queued_messages(state: ConnectionState) -> None:
        while not state.outbound_queue.empty():
            item = state.outbound_queue.get_nowait()
            if not item.completion.done():
                item.completion.set_exception(ConnectionError("Connection closed before send"))
            state.outbound_queue.task_done()

    async def _sender_loop(self, connection_id: UUID, state: ConnectionState) -> None:
        try:
            while True:
                message = await state.outbound_queue.get()
                try:
                    if message.frame_type == OutBoundFrameType.JSON:
                        if not isinstance(message.payload, dict):
                            raise TypeError("JSON frames require a dictionary payload")
                        await state.websocket.send_json(message.payload)
                    elif message.frame_type == OutBoundFrameType.BINARY:
                        if not isinstance(message.payload, bytes):
                            raise TypeError("Binary frames require a bytes payload")
                        await state.websocket.send_bytes(message.payload)
                    else:
                        raise ValueError("Unsupported outbound frame type")
                except asyncio.CancelledError:
                    if not message.completion.done():
                        message.completion.set_exception(
                            ConnectionError("Connection closed during send")
                        )
                    raise
                except Exception as exc:
                    if not message.completion.done():
                        message.completion.set_exception(exc)
                    return
                else:
                    if not message.completion.done():
                        message.completion.set_result(None)
                finally:
                    state.outbound_queue.task_done()
        finally:
            if self.active_connections.get(connection_id) is state:
                # Cleanup awaits this sender, so the sender must not await cleanup.
                self._start_disconnect(connection_id)
            else:
                self._fail_queued_messages(state)

    async def cleanup_loop(self, interval: float = 60) -> None:
        """Remove expired disconnected sessions even when there are no new connections."""
        if interval <= 0:
            raise ValueError("Cleanup interval must be positive")
        while True:
            await asyncio.sleep(interval)
            self.expire_sessions()

    async def shutdown(self) -> None:
        """Cancel and await all connection sender tasks on application shutdown."""
        for connection_id in list(self.active_connections):
            self._start_disconnect(connection_id)
        tasks = list(self._disconnect_tasks.values())
        if tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tasks))
