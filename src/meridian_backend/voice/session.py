import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from uuid import UUID

from fastapi import WebSocket

from meridian_backend.voice.stt import FakeStreamingSTT
from meridian_backend.voice.vad import FakeVAD, TurnEvent, VADEvent

logger = logging.getLogger(__name__)


class SessionState(StrEnum):
    IDLE = "IDLE"
    AGENT_SPEAKING = "AGENT_SPEAKING"
    USER_SPEAKING = "USER_SPEAKING"


class TextStreamEnd(Enum):
    END_OF_STREAM = "end_of_stream"


class AudioStreamControl(Enum):
    AUDIO_TURN_END = "audio_turn_end"


AUDIO_TURN_END = AudioStreamControl.AUDIO_TURN_END

TEXT_END_OF_STREAM = TextStreamEnd.END_OF_STREAM


async def fake_streaming_llm(transcript: str) -> AsyncIterator[str]:
    """Yield a fixed fake response; the transcript is the simulated prompt."""
    for chunk in ("Your ", "order ", "was ", "shipped."):
        await asyncio.sleep(0.4)
        yield chunk


async def fake_streaming_tts(text: str) -> AsyncIterator[bytes]:
    """Simulate audio generation for a single text chunk."""
    await asyncio.sleep(0.4)
    yield text.encode("utf-8")


async def fake_business_task() -> None:
    await asyncio.sleep(2)


@dataclass
class VoiceSession:
    session_id: UUID
    audio_queue: asyncio.Queue[bytes | AudioStreamControl] = field(
        default_factory=lambda: asyncio.Queue(maxsize=5)
    )
    stt_task: asyncio.Task[None] | None = None
    vad: FakeVAD = field(default_factory=FakeVAD)
    state: SessionState = field(default=SessionState.IDLE, init=False)
    # Incoming audio stays in audio_queue; only stale agent output is discarded.
    agent_audio_queue: asyncio.Queue[bytes] = field(default_factory=asyncio.Queue)
    agent_audio_sender_task: asyncio.Task[None] | None = field(default=None, init=False)
    text_queue: asyncio.Queue[str | TextStreamEnd] = field(
        default_factory=lambda: asyncio.Queue(maxsize=10)
    )
    llm_task: asyncio.Task[None] | None = field(default=None, init=False)
    tts_task: asyncio.Task[None] | None = field(default=None, init=False)
    business_task: asyncio.Task[None] | None = field(default=None, init=False)
    _turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _agent_output_cancelling: bool = field(default=False, init=False, repr=False)
    _agent_turn_succeeded: bool = field(default=True, init=False, repr=False)

    async def start_agent_turn(self, transcript: str = "") -> None:
        async with self._turn_lock:
            if self.state == SessionState.AGENT_SPEAKING:
                raise RuntimeError("An agent turn is already active")
            if self.state != SessionState.IDLE:
                raise RuntimeError("An agent turn requires IDLE state")
            if self._agent_output_cancelling:
                raise RuntimeError("Agent output cancellation is still in progress")
            self._agent_turn_succeeded = True
            self.llm_task = asyncio.create_task(
                self._run_agent_task(lambda: self.run_llm(transcript)), name="fake_llm_task"
            )
            self.tts_task = asyncio.create_task(
                self._run_agent_task(self.run_tts), name="fake_tts_task"
            )
            # Also clear references if a task is cancelled before its coroutine starts.
            self.llm_task.add_done_callback(self._clear_finished_agent_task)
            self.tts_task.add_done_callback(self._clear_finished_agent_task)
            self.state = SessionState.AGENT_SPEAKING

    async def run_llm(self, transcript: str) -> None:
        async for text in fake_streaming_llm(transcript):
            await self.text_queue.put(text)
        # Only normal completion emits EOS. Cancellation must not block on a full queue.
        await self.text_queue.put(TEXT_END_OF_STREAM)

    async def run_tts(self) -> None:
        while True:
            text = await self.text_queue.get()
            try:
                if text is TEXT_END_OF_STREAM:
                    return
                if isinstance(text, str):
                    async for audio in fake_streaming_tts(text):
                        await self.agent_audio_queue.put(audio)
            finally:
                self.text_queue.task_done()

    async def _run_agent_task(self, work: Callable[[], Awaitable[None]]) -> None:
        succeeded = False
        try:
            await work()
            succeeded = True
        except Exception:
            # Consume and log provider errors so detached tasks do not leave
            # unobserved exceptions. CancelledError still propagates normally.
            task = asyncio.current_task()
            logger.exception(
                "Agent provider failure in session %s (%s)",
                self.session_id,
                task.get_name() if task is not None else "unknown task",
            )
            await self._handle_agent_failure()
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

    async def _handle_agent_failure(self) -> None:
        task = asyncio.current_task()
        async with self._turn_lock:
            if task is None or (task is not self.llm_task and task is not self.tts_task):
                # Barge-in or another failure already owns this turn's cleanup.
                return
            sibling = self.tts_task if task is self.llm_task else self.llm_task
            self._agent_turn_succeeded = False
            self._agent_output_cancelling = True
            self.llm_task = None
            self.tts_task = None
            # IDLE is safe, but starting output stays blocked until queues are drained.
            self.state = SessionState.IDLE
            if sibling is not None and not sibling.done():
                sibling.cancel()
        # Never await ourselves, or hold the lock while sibling cleanup runs.
        await self._cancel_agent_output([] if sibling is None else [sibling])

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
        if result == TurnEvent.USER_TURN_COMPLETE:
            await self.audio_queue.put(AUDIO_TURN_END)
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
                        self.text_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    else:
                        self.text_queue.task_done()
                while True:
                    try:
                        self.agent_audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    else:
                        self.agent_audio_queue.task_done()
                self._agent_output_cancelling = False

    async def send_agent_audio(
        self, send_audio: Callable[[bytes], Awaitable[None]]
    ) -> None:
        """Send queued agent audio for the session, independently of agent turns."""
        task = asyncio.current_task()
        if self.agent_audio_sender_task is not None and not self.agent_audio_sender_task.done():
            if self.agent_audio_sender_task is not task:
                raise RuntimeError("An agent audio sender is already active")
        self.agent_audio_sender_task = task
        try:
            while True:
                chunk = await self.agent_audio_queue.get()
                try:
                    await send_audio(chunk)
                finally:
                    self.agent_audio_queue.task_done()
        finally:
            if self.agent_audio_sender_task is task:
                self.agent_audio_sender_task = None

    async def receive_audio(
        self,
        websocket: WebSocket,
        audio_queue: asyncio.Queue[bytes | AudioStreamControl] | None = None,
    ) -> None:
        queue = self.audio_queue if audio_queue is None else audio_queue
        while True:
            chunk = await websocket.receive_bytes()
            await queue.put(chunk)

    async def process_audio(
        self,
        audio_queue: asyncio.Queue[bytes | AudioStreamControl] | None = None,
        *,
        stt: FakeStreamingSTT | None = None,
    ) -> None:
        queue = self.audio_queue if audio_queue is None else audio_queue
        stt = FakeStreamingSTT() if stt is None else stt
        while True:
            chunk = await queue.get()
            try:
                if chunk is AUDIO_TURN_END:
                    transcript = await stt.finalize()
                    await self.start_agent_turn(transcript)
                elif isinstance(chunk, bytes):
                    await stt.send_audio(chunk)
            finally:
                queue.task_done()
