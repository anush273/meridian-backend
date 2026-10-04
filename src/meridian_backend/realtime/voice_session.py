from dataclasses import dataclass,field
from uuid import UUID
import asyncio
from fastapi import WebSocket



@dataclass
class VoiceSeesion:
    session_id: UUID
    audio_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=50))
    stt_task: asyncio.Task[None] | None


    async def receive_audio(self,websocket: WebSocket, audio_queue: asyncio.Queue[bytes]) -> None:
        while True:
            chunk = await websocket.receive_bytes()
            await audio_queue.put(chunk)