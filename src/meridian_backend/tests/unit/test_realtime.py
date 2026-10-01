from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from meridian_backend.api.routes import realtime
from meridian_backend.realtime.connection_manager import ConnectionManager


@pytest.fixture
def manager(monkeypatch):
    manager = ConnectionManager()
    monkeypatch.setattr(realtime, "manager", manager)
    return manager


def socket():
    websocket = AsyncMock(spec=WebSocket)
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
    manager.disconnect(connection_id)
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
