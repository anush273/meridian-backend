import logging
from uuid import uuid4
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from meridian_backend.realtime.connection_manager import ConnectionManager
from meridian_backend.schemas.realtime import RealtimeMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["realtime"])
manager = ConnectionManager()


@router.websocket("/ws")
async def realtime_socket(websocket: WebSocket) -> None:
    connection_id = uuid4()
    await manager.connect(connection_id, websocket)

    logger.info("websocket_connected", extra={"connection_id": str(connection_id)})
    logger.info("live_connections=%s", manager.connection_count, extra={"connection_count": manager.connection_count})

    try:
        await manager.send_json(
            connection_id,
            RealtimeMessage(
                type="connection.ready",
                sequence=0,
                data={"connection_id": str(connection_id)},
            ),
        )
        while True:
            try:
                payload = await asyncio.wait_for(websocket.receive_json(), timeout=30)
            except TimeoutError:
                logger.warning("websocket_heart_beat_timeout", extra={
                    "connection_id": str(
                        connection_id
                    )
                })
                await websocket.close(
                    code=400,
                    reason="heartbeat timeout"
                )
                break
            manager.mark_seen(connection_id)
            message = RealtimeMessage.model_validate(payload)
            logger.info(
                "websocket_message_received=%s", message,
                extra={"connection_id": str(connection_id), "message_type": message.type},
            )
            if message.type == "echo":
                response = RealtimeMessage(
                    type="echo.response", sequence=message.sequence, data=message.data
                )
            elif message.type == "ping":
                response = RealtimeMessage(
                    type="pong", sequence=message.sequence, data=message.data
                )
            else:
                response = RealtimeMessage(
                    type="error",
                    sequence=message.sequence,
                    data={
                        "code": "UNKNOWN_MESSAGE_TYPE",
                        "message": f"Unsupported message type: {message.type}",
                    },
                )
            await manager.send_json(connection_id, response)
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", extra={"connection_id": str(connection_id)})
        
    finally:
        manager.disconnect(connection_id)
        logger.info("live_connections=%s", manager.connection_count, extra={"connection_count": manager.connection_count})
