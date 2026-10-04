import asyncio
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from meridian_backend.api.routes import realtime
from meridian_backend.realtime.connection_manager import ConnectionManager


@pytest.fixture
def manager(monkeypatch):
    manager = ConnectionManager()
    monkeypatch.setattr(realtime, "manager", manager)
    return manager


def socket():
    websocket = AsyncMock(spec=WebSocket)
    websocket.application_state = WebSocketState.CONNECTED
    websocket.client_state = WebSocketState.CONNECTED

    async def close(**kwargs):
        websocket.application_state = WebSocketState.DISCONNECTED

    websocket.close.side_effect = close
    websocket.receive_json.side_effect = WebSocketDisconnect()
    return websocket


@pytest.mark.asyncio
async def test_create_and_resume_session(manager):
    first = socket()
    await realtime.realtime_socket(first)
    ready = first.send_json.call_args.args[0]
    session_id = UUID(ready["data"]["session_id"])
    assert manager.connection_count == 0
    assert session_id in manager.sessions

    second = socket()
    await realtime.realtime_socket(second, session_id)
    resumed = second.send_json.call_args.args[0]
    assert resumed["data"]["session_id"] == str(session_id)
    assert resumed["data"]["connection_id"] != ready["data"]["connection_id"]
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_unknown_session_is_rejected(manager):
    websocket = socket()
    await realtime.realtime_socket(websocket, uuid4())
    websocket.close.assert_awaited_once_with(code=1008, reason="Session unavailable")
    websocket.accept.assert_not_awaited()
    assert not manager.sessions


@pytest.mark.asyncio
async def test_live_session_is_rejected(manager):
    connection_id = uuid4()
    session_id = manager.create_session(connection_id)
    await manager.connect(connection_id, socket())
    websocket = socket()
    await realtime.realtime_socket(websocket, session_id)
    websocket.accept.assert_not_awaited()
    assert manager.sessions[session_id].connection_id == connection_id


@pytest.mark.asyncio
async def test_heartbeat_timeout_closes_and_cleans_up(manager):
    websocket = socket()
    websocket.receive_json.side_effect = TimeoutError()
    await realtime.realtime_socket(websocket)
    websocket.close.assert_awaited_once_with(code=4000, reason="heartbeat timeout")
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_session_activity_and_expiration(manager, monkeypatch):
    monkeypatch.setattr("meridian_backend.realtime.connection_manager.monotonic", lambda: 100)
    connection_id = uuid4()
    session_id = manager.create_session(connection_id)
    await manager.connect(connection_id, socket())
    manager.mark_seen(connection_id)
    assert manager.sessions[session_id].last_seen == 100
    manager.expire_sessions()
    assert session_id in manager.sessions
    await manager.disconnect(connection_id)
    monkeypatch.setattr("meridian_backend.realtime.connection_manager.monotonic", lambda: 1900)
    assert not manager.resume_session(session_id, uuid4())
    assert session_id not in manager.sessions


@pytest.mark.asyncio
async def test_session_messages_are_isolated_and_acknowledged(manager):
    connection_id = uuid4()
    session_id = manager.create_session(connection_id)
    other_id = manager.create_session(uuid4())
    websocket = socket()
    await manager.connect(connection_id, websocket)
    await manager.send_session_message(session_id, "update", {"value": 1})
    await manager.send_session_message(session_id, "update", {"value": 2})
    websocket.send_json.assert_any_await({"type": "update", "sequence": 1, "data": {"value": 1}})
    assert not manager.sessions[other_id].pending_messages
    assert not manager.acknowledge(session_id, 3)
    assert not manager.acknowledge(session_id, -1)
    assert manager.acknowledge(session_id, 1)
    assert list(manager.sessions[session_id].pending_messages) == [2]
    assert manager.acknowledge(session_id, 0)
    assert manager.sessions[session_id].last_acked_sequence == 1


@pytest.mark.asyncio
async def test_reconnect_replays_unacknowledged_messages_and_handles_ack(manager):
    session_id = manager.create_session(uuid4())
    await manager.send_session_message(session_id, "update", {"value": 1})
    await manager.send_session_message(session_id, "update", {"value": 2})
    assert manager.acknowledge(session_id, 1)
    websocket = socket()
    websocket.receive_json.side_effect = [
        {"type": "ack", "sequence": 2, "data": {}},
        WebSocketDisconnect(),
    ]
    await realtime.realtime_socket(websocket, session_id)
    sent = [call.args[0] for call in websocket.send_json.await_args_list]
    assert [message["type"] for message in sent] == ["connection.ready", "update"]
    assert sent[1]["sequence"] == 2
    assert not manager.sessions[session_id].pending_messages


@pytest.mark.asyncio
async def test_pending_buffer_rejects_overflow_without_losing_messages():
    manager = ConnectionManager(max_pending_messages=1)
    session_id = manager.create_session(uuid4())
    await manager.send_session_message(session_id, "update", {})
    with pytest.raises(BufferError):
        await manager.send_session_message(session_id, "update", {})
    assert manager.sessions[session_id].next_server_sequence == 2
    assert list(manager.sessions[session_id].pending_messages) == [1]
    assert manager.acknowledge(session_id, 1)
    await manager.send_session_message(session_id, "update", {})
    assert list(manager.sessions[session_id].pending_messages) == [2]


@pytest.mark.asyncio
async def test_unknown_session_messages_fail_explicitly(manager):
    with pytest.raises(ValueError, match="Unknown session"):
        await manager.send_session_message(uuid4(), "update", {})
    with pytest.raises(ValueError, match="Unknown session"):
        await manager.replay_session_messages(uuid4())
    assert not manager.acknowledge(uuid4(), 0)


@pytest.mark.asyncio
async def test_failed_send_preserves_message_for_replay(manager):
    connection_id = uuid4()
    session_id = manager.create_session(connection_id)
    websocket = socket()
    await manager.connect(connection_id, websocket)
    websocket.send_json.side_effect = WebSocketDisconnect()
    with pytest.raises(WebSocketDisconnect):
        await manager.send_session_message(session_id, "update", {})
    assert list(manager.sessions[session_id].pending_messages) == [1]


@pytest.mark.asyncio
async def test_replay_skips_messages_through_last_acked_sequence(manager):
    connection_id = uuid4()
    session_id = manager.create_session(connection_id)
    for value in (1, 2, 3):
        await manager.send_session_message(session_id, "update", {"value": value})
    # Simulate a retained buffer that still contains an acknowledged message.
    manager.sessions[session_id].last_acked_sequence = 1
    websocket = socket()
    await manager.connect(connection_id, websocket)
    await manager.replay_session_messages(session_id)
    sent = [call.args[0] for call in websocket.send_json.await_args_list]
    assert [message["sequence"] for message in sent] == [2, 3]


@pytest.mark.asyncio
async def test_ack_one_disconnect_replay_two_three_then_ack_three(manager):
    first = socket()
    receives = 0

    async def receive_first():
        nonlocal receives
        receives += 1
        if receives > 1:
            raise WebSocketDisconnect()
        ready = first.send_json.await_args_list[0].args[0]
        session_id = UUID(ready["data"]["session_id"])
        for value in (1, 2, 3):
            await manager.send_session_message(session_id, "update", {"value": value})
        return {"type": "ack", "sequence": 1, "data": {}}

    first.receive_json.side_effect = receive_first
    await realtime.realtime_socket(first)
    sent = [call.args[0] for call in first.send_json.await_args_list]
    session_id = UUID(sent[0]["data"]["session_id"])
    assert [message["sequence"] for message in sent[1:]] == [1, 2, 3]
    session = manager.sessions[session_id]
    assert session.last_acked_sequence == 1
    assert list(session.pending_messages) == [2, 3]
    assert manager.connection_count == 0

    second = socket()

    async def receive_second():
        replayed = [call.args[0] for call in second.send_json.await_args_list]
        assert replayed[0]["data"]["session_id"] == str(session_id)
        assert replayed[0]["data"]["connection_id"] != sent[0]["data"]["connection_id"]
        assert replayed[1:] == sent[2:]
        assert list(session.pending_messages) == [2, 3]
        second.receive_json.side_effect = WebSocketDisconnect()
        return {"type": "ack", "sequence": 3, "data": {}}

    second.receive_json.side_effect = receive_second
    await realtime.realtime_socket(second, session_id)
    assert session.last_acked_sequence == 3
    assert session.pending_messages == {}
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_live_update_waits_for_replay(manager):
    session_id = manager.create_session(uuid4())
    await manager.send_session_message(session_id, "update", {"value": 1})
    await manager.send_session_message(session_id, "update", {"value": 2})
    connection_id = uuid4()
    assert manager.resume_session(session_id, connection_id)
    websocket = socket()
    started = asyncio.Event()
    release = asyncio.Event()
    sent = []

    async def send(payload):
        if payload["sequence"] == 1:
            started.set()
            await release.wait()
        sent.append(payload["sequence"])

    websocket.send_json.side_effect = send
    await manager.connect(connection_id, websocket)
    # Updates arriving before replay begins must also join the backlog.
    await manager.send_session_message(session_id, "update", {"value": 3})
    assert sent == []
    replay = asyncio.create_task(manager.replay_session_messages(session_id))
    await started.wait()
    live = asyncio.create_task(manager.send_session_message(session_id, "update", {"value": 4}))
    await asyncio.sleep(0)
    assert not live.done()
    release.set()
    await asyncio.gather(replay, live)
    assert sent == [1, 2, 3, 4]
    await manager.shutdown()


@pytest.mark.asyncio
async def test_disconnect_releases_inflight_and_queued_sends(manager):
    from meridian_backend.schemas.realtime import RealtimeMessage

    connection_id = uuid4()
    websocket = socket()
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def send(payload):
        started.set()
        await blocked.wait()

    websocket.send_json.side_effect = send
    await manager.connect(connection_id, websocket)
    state = manager.active_connections[connection_id]
    first = asyncio.create_task(
        manager.send_json(connection_id, RealtimeMessage(type="update", sequence=1))
    )
    await started.wait()
    second = asyncio.create_task(
        manager.send_json(connection_id, RealtimeMessage(type="update", sequence=2))
    )
    await asyncio.sleep(0)
    await manager.disconnect(connection_id)
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert all(isinstance(result, ConnectionError) for result in results)
    await asyncio.gather(state.sender_task, return_exceptions=True)
    assert state.sender_task.cancelled()
    websocket.close.assert_awaited_once()
    await state.outbound_queue.join()
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_sender_failure_disconnects_and_retains_pending(manager):
    connection_id = uuid4()
    session_id = manager.create_session(connection_id)
    websocket = socket()
    websocket.send_json.side_effect = RuntimeError("socket failed")
    await manager.connect(connection_id, websocket)
    with pytest.raises(RuntimeError, match="socket failed"):
        await manager.send_session_message(session_id, "update", {})
    assert manager.connection_count == 0
    assert list(manager.sessions[session_id].pending_messages) == [1]


@pytest.mark.asyncio
async def test_cleanup_loop_expires_sessions_without_new_connections(manager, monkeypatch):
    session_id = manager.create_session(uuid4())
    manager.sessions[session_id].last_seen = 0
    monkeypatch.setattr("meridian_backend.realtime.connection_manager.monotonic", lambda: 1900)
    expired = asyncio.Event()
    original = manager.expire_sessions

    def expire():
        original()
        expired.set()

    monkeypatch.setattr(manager, "expire_sessions", expire)
    task = asyncio.create_task(manager.cleanup_loop(interval=0.001))
    try:
        await asyncio.wait_for(expired.wait(), timeout=1)
        assert session_id not in manager.sessions
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_queue_overflow_disconnects_and_releases_waiters(manager):
    from meridian_backend.schemas.realtime import RealtimeMessage

    connection_id = uuid4()
    websocket = socket()
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def send(payload):
        started.set()
        await blocked.wait()

    websocket.send_json.side_effect = send
    await manager.connect(connection_id, websocket)
    state = manager.active_connections[connection_id]
    state.outbound_queue = asyncio.Queue(maxsize=1)
    payload = RealtimeMessage(type="update", sequence=1)
    first = asyncio.create_task(manager.send_json(connection_id, payload))
    await started.wait()
    second = asyncio.create_task(manager.send_json(connection_id, payload))
    await asyncio.sleep(0)
    with pytest.raises(BufferError, match="outbound queue is full"):
        await manager.send_json(connection_id, payload)
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert all(isinstance(result, ConnectionError) for result in results)
    await asyncio.gather(state.sender_task, return_exceptions=True)
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_concurrent_disconnects_wait_for_one_socket_close(manager):
    connection_id = uuid4()
    websocket = socket()
    close_started = asyncio.Event()
    release_close = asyncio.Event()

    async def close():
        close_started.set()
        await release_close.wait()
        websocket.application_state = WebSocketState.DISCONNECTED

    websocket.close.side_effect = close
    await manager.connect(connection_id, websocket)
    state = manager.active_connections[connection_id]
    first = asyncio.create_task(manager.disconnect(connection_id))
    await close_started.wait()
    second = asyncio.create_task(manager.disconnect(connection_id))
    await asyncio.sleep(0)
    assert not first.done()
    assert not second.done()
    release_close.set()
    await asyncio.gather(first, second)
    assert state.sender_task.done()
    websocket.close.assert_awaited_once()
    await manager.disconnect(connection_id)
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_waits_for_cleanup_after_disconnect_caller_cancelled(manager):
    connection_id = uuid4()
    websocket = socket()
    close_started = asyncio.Event()
    release_close = asyncio.Event()

    async def close():
        close_started.set()
        await release_close.wait()
        websocket.application_state = WebSocketState.DISCONNECTED

    websocket.close.side_effect = close
    await manager.connect(connection_id, websocket)
    disconnect = asyncio.create_task(manager.disconnect(connection_id))
    await close_started.wait()
    disconnect.cancel()
    with pytest.raises(asyncio.CancelledError):
        await disconnect
    shutdown = asyncio.create_task(manager.shutdown())
    await asyncio.sleep(0)
    assert not shutdown.done()
    release_close.set()
    await shutdown
    assert not manager._disconnect_tasks
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_does_not_close_already_disconnected_socket(manager):
    connection_id = uuid4()
    websocket = socket()
    await manager.connect(connection_id, websocket)
    websocket.client_state = WebSocketState.DISCONNECTED
    await manager.disconnect(connection_id)
    websocket.close.assert_not_awaited()
