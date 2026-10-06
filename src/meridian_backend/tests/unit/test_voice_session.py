import asyncio
from time import monotonic
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from meridian_backend.voice.session import SessionState, VoiceSession
from meridian_backend.voice.stt import fake_stt
from meridian_backend.voice.vad import FakeVAD, TurnEvent, VADState


def test_short_silence_and_resumed_speech():
    vad = FakeVAD()
    assert vad.state == VADState.IDLE
    assert vad.process_event("speech") is None
    assert vad.state == VADState.SPEAKING
    assert vad.process_event("silence", duration_ms=200) is None
    assert vad.state == VADState.POSSIBLE_END
    assert vad.process_event("speech") is None
    assert vad.state == VADState.SPEAKING
    assert vad.silence_ms == 0
    # The earlier pause must not count toward this new silence interval.
    assert vad.process_event("silence", duration_ms=300) is None
    assert vad.state == VADState.POSSIBLE_END


def test_long_silence_completes_user_turn_once():
    vad = FakeVAD()
    vad.process_event("speech")
    assert vad.process_event("silence", duration_ms=600) == TurnEvent.USER_TURN_COMPLETE
    assert vad.state == VADState.IDLE
    assert vad.process_event("silence", duration_ms=600) is None
    vad.process_event("speech")
    assert vad.state == VADState.SPEAKING
    assert vad.process_event("silence", duration_ms=500) == TurnEvent.USER_TURN_COMPLETE


def test_consecutive_silence_accumulates_to_threshold():
    vad = FakeVAD()
    for event in ("speech", "speech", "speech"):
        assert vad.process_event(event) is None
    assert vad.process_event("silence", duration_ms=200) is None
    assert vad.process_event("silence", duration_ms=299) is None
    assert vad.silence_ms == 499
    assert vad.process_event("silence", duration_ms=1) == TurnEvent.USER_TURN_COMPLETE


def test_initial_silence_does_not_complete_a_turn():
    vad = FakeVAD()
    assert vad.process_event("silence", duration_ms=1000) is None
    assert vad.state == VADState.IDLE
    assert vad.silence_ms == 0


def test_voice_sessions_have_independent_vad_state():
    first = VoiceSession(session_id=uuid4())
    second = VoiceSession(session_id=uuid4())
    first.vad.process_event("speech")
    assert second.vad.state == VADState.IDLE


def test_custom_endpoint_threshold():
    vad = FakeVAD(endpoint_threshold_ms=700)
    vad.process_event("speech")
    assert vad.process_event("silence", duration_ms=600) is None
    assert vad.process_event("silence", duration_ms=100) == TurnEvent.USER_TURN_COMPLETE


@pytest.mark.parametrize("duration_ms", [-1, float("inf"), float("nan")])
def test_invalid_duration_preserves_state(duration_ms):
    vad = FakeVAD()
    vad.process_event("speech")
    with pytest.raises(ValueError, match="duration_ms"):
        vad.process_event("silence", duration_ms=duration_ms)
    assert vad.state == VADState.SPEAKING
    assert vad.silence_ms == 0


@pytest.mark.parametrize("threshold", [0, -1, float("inf"), float("nan")])
def test_invalid_endpoint_threshold(threshold):
    with pytest.raises(ValueError, match="endpoint_threshold_ms"):
        FakeVAD(endpoint_threshold_ms=threshold)


def test_invalid_vad_event_preserves_state():
    vad = FakeVAD()
    with pytest.raises(ValueError):
        vad.process_event("noise")
    assert vad.state == VADState.IDLE


@pytest.mark.asyncio
async def test_fake_incoming_audio_backpressure():
    """Run with pytest -s to watch the fast producer and one-second STT worker."""
    session = VoiceSession(session_id=uuid4())
    chunks = [f"chunk-{number}".encode() for number in range(1, 9)]
    received = []
    processed = []
    queue_sizes = []
    sixth_arrived = asyncio.Event()
    websocket = AsyncMock(spec=WebSocket)

    async def receive_bytes():
        queue_sizes.append(session.audio_queue.qsize())
        if len(received) == len(chunks):
            raise WebSocketDisconnect()
        chunk = chunks[len(received)]
        received.append(chunk)
        print(f"producer: {chunk.decode()} (queued={session.audio_queue.qsize()})")
        if len(received) == 6:
            sixth_arrived.set()
        return chunk

    async def send_audio(chunk):
        queue_sizes.append(session.audio_queue.qsize())
        await fake_stt(chunk)
        processed.append(chunk)
        print(f"STT processed: {chunk.decode()}")

    websocket.receive_bytes.side_effect = receive_bytes
    producer = asyncio.create_task(session.receive_audio(websocket))
    consumer = None
    try:
        await asyncio.wait_for(sixth_arrived.wait(), timeout=1)
        assert session.audio_queue.maxsize == 5
        assert session.audio_queue.qsize() == 5
        assert received == chunks[:6]
        assert not producer.done()
        # With no consumer, the sixth put cannot finish or read chunk seven.
        await asyncio.sleep(0.05)
        assert received == chunks[:6]
        assert not producer.done()
        print("queue full: producer waits on chunk-6")

        started = monotonic()
        consumer = asyncio.create_task(session.process_audio(send_audio=send_audio))
        with pytest.raises(WebSocketDisconnect):
            await asyncio.wait_for(producer, timeout=5)
        producer_duration = monotonic() - started
        # Dequeuing frees space immediately. Chunks seven/eight then wait for
        # subsequent dequeues, paced by the one-second STT calls.
        assert producer_duration >= 2
        await asyncio.wait_for(session.audio_queue.join(), timeout=10)
        assert processed == chunks
        assert max(queue_sizes) == 5
        assert all(0 <= size <= 5 for size in queue_sizes)
        assert session.audio_queue.empty()
        print(f"verified: FIFO, maxsize=5, producer took {producer_duration:.2f}s")
    finally:
        tasks = [producer] if consumer is None else [producer, consumer]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_barge_in_after_one_second_preserves_business_work():
    session = VoiceSession(session_id=uuid4())
    await session.start_agent_turn()
    business = session.start_business_task()
    llm, tts = session.llm_task, session.tts_task
    assert llm is not None and tts is not None
    session.agent_audio_queue.put_nowait(b"stale-output-1")
    session.agent_audio_queue.put_nowait(b"stale-output-2")
    session.audio_queue.put_nowait(b"user-input")
    try:
        assert session.state == SessionState.AGENT_SPEAKING
        await asyncio.sleep(1)
        assert not llm.done() and not tts.done()
        await session.handle_vad_event("speech_started")
        assert llm.cancelled() and tts.cancelled()
        assert session.llm_task is None and session.tts_task is None
        assert session.agent_audio_queue.empty()
        await asyncio.wait_for(session.agent_audio_queue.join(), timeout=1)
        assert session.state == SessionState.USER_SPEAKING
        assert session.audio_queue.get_nowait() == b"user-input"
        session.audio_queue.task_done()
        assert not business.done()
        await asyncio.wait_for(asyncio.shield(business), timeout=3)
        assert not business.cancelled()
        assert business.exception() is None
        # Repeated speech notifications are harmless after the first interruption.
        await session.handle_vad_event("speech_started")
        assert session.state == SessionState.USER_SPEAKING
    finally:
        for task in (llm, tts, business):
            task.cancel()
        await asyncio.gather(llm, tts, business, return_exceptions=True)


@pytest.mark.asyncio
async def test_speech_input_interrupts_agent_and_allows_a_new_turn():
    session = VoiceSession(session_id=uuid4())
    await session.start_agent_turn()
    first_llm, first_tts = session.llm_task, session.tts_task
    await session.handle_vad_event("speech")
    assert first_llm.cancelled() and first_tts.cancelled()
    assert session.state == SessionState.USER_SPEAKING
    assert await session.handle_vad_event("silence", 600) == TurnEvent.USER_TURN_COMPLETE
    assert session.state == SessionState.IDLE
    await session.start_agent_turn()
    try:
        assert session.llm_task is not first_llm
        assert session.tts_task is not first_tts
        with pytest.raises(RuntimeError, match="already active"):
            await session.start_agent_turn()
        await session.handle_vad_event("silence", 100)
        assert session.state == SessionState.AGENT_SPEAKING
    finally:
        await session.handle_vad_event("speech_started")


@pytest.mark.asyncio
async def test_agent_turn_requires_idle():
    session = VoiceSession(session_id=uuid4())
    await session.handle_vad_event("speech")
    with pytest.raises(RuntimeError, match="requires IDLE"):
        await session.start_agent_turn()
    assert session.llm_task is None and session.tts_task is None


@pytest.mark.asyncio
async def test_cancellation_handler_can_acquire_turn_lock(monkeypatch):
    session = VoiceSession(session_id=uuid4())
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def llm():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            async with session._turn_lock:
                cleanup_started.set()
            await release_cleanup.wait()
            session.agent_audio_queue.put_nowait(b"last-stale-output")

    monkeypatch.setattr("meridian_backend.voice.session.fake_llm_task", llm)
    await session.start_agent_turn()
    old_llm, old_tts = session.llm_task, session.tts_task
    await started.wait()
    interruption = asyncio.create_task(session.handle_vad_event("speech_started"))
    try:
        await asyncio.wait_for(cleanup_started.wait(), timeout=1)
        assert session.state == SessionState.USER_SPEAKING
        assert session.llm_task is None and session.tts_task is None
        # Endpointing can advance while cleanup runs, but a new output producer
        # must not start until the old producers stop and their queue is drained.
        await session.handle_vad_event("silence", 600)
        with pytest.raises(RuntimeError, match="cancellation is still in progress"):
            await session.start_agent_turn()
        release_cleanup.set()
        await asyncio.wait_for(interruption, timeout=1)
        assert old_llm.cancelled() and old_tts.cancelled()
        assert session.agent_audio_queue.empty()
        await asyncio.wait_for(session.agent_audio_queue.join(), timeout=1)
        await session.start_agent_turn()
        await session.handle_vad_event("speech_started")
        assert session.llm_task is None and session.tts_task is None
    finally:
        release_cleanup.set()
        await asyncio.gather(interruption, return_exceptions=True)


@pytest.mark.asyncio
async def test_finished_agent_task_references_are_cleared(monkeypatch):
    async def finish():
        await asyncio.sleep(0)

    monkeypatch.setattr("meridian_backend.voice.session.fake_llm_task", finish)
    monkeypatch.setattr("meridian_backend.voice.session.fake_tts_task", finish)
    session = VoiceSession(session_id=uuid4())
    await session.start_agent_turn()
    await asyncio.gather(session.llm_task, session.tts_task)
    assert session.llm_task is None and session.tts_task is None


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["llm", "tts"])
async def test_normal_agent_completion_waits_for_both_tasks(monkeypatch, first):
    llm_release, tts_release = asyncio.Event(), asyncio.Event()

    async def llm():
        await llm_release.wait()

    async def tts():
        await tts_release.wait()

    monkeypatch.setattr("meridian_backend.voice.session.fake_llm_task", llm)
    monkeypatch.setattr("meridian_backend.voice.session.fake_tts_task", tts)
    session = VoiceSession(session_id=uuid4())
    await session.start_agent_turn()
    llm_task, tts_task = session.llm_task, session.tts_task
    first_release, first_task = (
        (llm_release, llm_task) if first == "llm" else (tts_release, tts_task)
    )
    try:
        first_release.set()
        await first_task
        assert session.state == SessionState.AGENT_SPEAKING
        llm_release.set()
        tts_release.set()
        await asyncio.gather(llm_task, tts_task)
        assert session.state == SessionState.IDLE
        assert session.llm_task is None and session.tts_task is None
        await session.start_agent_turn()
        await asyncio.gather(session.llm_task, session.tts_task)
        assert session.state == SessionState.IDLE
    finally:
        for task in (llm_task, tts_task):
            task.cancel()
        await asyncio.gather(llm_task, tts_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_interrupted_tasks_finishing_normally_cannot_reset_user_state(monkeypatch):
    started = asyncio.Event()

    async def suppress_cancellation():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

    monkeypatch.setattr("meridian_backend.voice.session.fake_llm_task", suppress_cancellation)
    monkeypatch.setattr("meridian_backend.voice.session.fake_tts_task", suppress_cancellation)
    session = VoiceSession(session_id=uuid4())
    await session.start_agent_turn()
    await started.wait()
    await session.handle_vad_event("speech_started")
    assert session.state == SessionState.USER_SPEAKING
    assert session.llm_task is None and session.tts_task is None
