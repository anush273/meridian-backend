import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from fastapi import WebSocket

from meridian_backend.voice.stt import fake_stt
from meridian_backend.voice.vad import FakeVAD, TurnEvent, VADEvent


class SessionState(StrEnum):
    IDLE = "IDLE"
    AGENT_SPEAKING = "AGENT_SPEAKING"
    USER_SPEAKING = "USER_SPEAKING"


async def fake_llm_task() -> None:
    await asyncio.sleep(30)


async def fake_tts_task() -> None:
    await asyncio.sleep(30)


async def fake_business_task() -> None:
    await asyncio.sleep(2)


@dataclass
class VoiceSession:
    session_id: UUID
    audio_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=5))
    stt_task: asyncio.Task[None] | None = None
    vad: FakeVAD = field(default_factory=FakeVAD)
    state: SessionState = field(default=SessionState.IDLE, init=False)
    # Incoming audio stays in audio_queue; only stale agent output is discarded.
    agent_audio_queue: asyncio.Queue[bytes] = field(default_factory=asyncio.Queue)
    llm_task: asyncio.Task[None] | None = field(default=None, init=False)
    tts_task: asyncio.Task[None] | None = field(default=None, init=False)
    business_task: asyncio.Task[None] | None = field(default=None, init=False)
    _turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _agent_output_cancelling: bool = field(default=False, init=False, repr=False)
    _agent_turn_succeeded: bool = field(default=True, init=False, repr=False)

    async def start_agent_turn(self) -> None:
        async with self._turn_lock:
            if self.state == SessionState.AGENT_SPEAKING:
                raise RuntimeError("An agent turn is already active")
            if self.state != SessionState.IDLE:
                raise RuntimeError("An agent turn requires IDLE state")
            if self._agent_output_cancelling:
                raise RuntimeError("Agent output cancellation is still in progress")
            self._agent_turn_succeeded = True
            self.llm_task = asyncio.create_task(
                self._run_agent_task(fake_llm_task), name="fake_llm_task"
            )
            self.tts_task = asyncio.create_task(
                self._run_agent_task(fake_tts_task), name="fake_tts_task"
            )
            # Also clear references if a task is cancelled before its coroutine starts.
            self.llm_task.add_done_callback(self._clear_finished_agent_task)
            self.tts_task.add_done_callback(self._clear_finished_agent_task)
            self.state = SessionState.AGENT_SPEAKING

    async def _run_agent_task(self, work: Callable[[], Awaitable[None]]) -> None:
        succeeded = False
        try:
            await work()
            succeeded = True
        finally:
            task = asyncio.current_task()
            async with self._turn_lock:
                # Detached tasks belong to an interrupted turn and cannot finish it.
                if task is not None and (task is self.llm_task or task is self.tts_task):
                    self._agent_turn_succeeded &= succeeded
                    self._clear_finished_agent_task(task)
                    if (
                        self.llm_task is None
                        and self.tts_task is None
                        and self._agent_turn_succeeded
                        and self.state == SessionState.AGENT_SPEAKING
                        and not self._agent_output_cancelling
                    ):
                        self.state = SessionState.IDLE

    def _clear_finished_agent_task(self, task: asyncio.Task[None]) -> None:
        # Identity checks keep an old callback from clearing a newer turn's task.
        if (task is self.llm_task or task is self.tts_task) and task.cancelled():
            self._agent_turn_succeeded = False
        if self.llm_task is task:
            self.llm_task = None
        if self.tts_task is task:
            self.tts_task = None

    def start_business_task(self) -> asyncio.Task[None]:
        """Business work has its own lifetime, independent of conversation turns."""
        if self.business_task is not None and not self.business_task.done():
            raise RuntimeError("A business task is already active")
        self.business_task = asyncio.create_task(fake_business_task(), name="fake_business_task")
        return self.business_task

    async def handle_vad_event(
        self, event: VADEvent | str, duration_ms: float = 0
    ) -> TurnEvent | None:
        """Accept fake VAD input, including an explicit speech_started notification."""
        cancelled_tasks: list[asyncio.Task[None]] | None = None
        async with self._turn_lock:
            vad_event = VADEvent.SPEECH if event == "speech_started" else VADEvent(event)
            result = self.vad.process_event(vad_event, duration_ms)
            if vad_event == VADEvent.SPEECH:
                if self.state == SessionState.AGENT_SPEAKING:
                    cancelled_tasks = [
                        task for task in (self.llm_task, self.tts_task) if task is not None
                    ]
                    self.llm_task = None
                    self.tts_task = None
                    self._agent_output_cancelling = True
                    for task in cancelled_tasks:
                        task.cancel()
                self.state = SessionState.USER_SPEAKING
            elif result == TurnEvent.USER_TURN_COMPLETE:
                self.state = SessionState.IDLE
        if cancelled_tasks is not None:
            await self._cancel_agent_output(cancelled_tasks)
        return result

    async def _cancel_agent_output(self, tasks: list[asyncio.Task[None]]) -> None:
        # Stop producers before draining so they cannot refill the output queue.
        # Cancellation handlers may acquire _turn_lock while this await runs.
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            async with self._turn_lock:
                while True:
                    try:
                        self.agent_audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    else:
                        self.agent_audio_queue.task_done()
                self._agent_output_cancelling = False

    async def receive_audio(
        self, websocket: WebSocket, audio_queue: asyncio.Queue[bytes] | None = None
    ) -> None:
        queue = self.audio_queue if audio_queue is None else audio_queue
        while True:
            chunk = await websocket.receive_bytes()
            await queue.put(chunk)

    async def process_audio(
        self,
        audio_queue: asyncio.Queue[bytes] | None = None,
        *,
        send_audio: Callable[[bytes], Awaitable[None]] = fake_stt,
    ) -> None:
        queue = self.audio_queue if audio_queue is None else audio_queue
        while True:
            chunk = await queue.get()
            try:
                await send_audio(chunk)
            finally:
                queue.task_done()
