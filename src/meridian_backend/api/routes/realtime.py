import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from meridian_backend.schemas.realtime import RealtimeMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["realtime"])

@router.websocket("/ws")
async def realtime_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("websocket_connected")
    try:
        while True:
            payload = await websocket.receive_json()
            message = RealtimeMessage.model_validate(payload)
            logger.info("websocket_message_received", extra={"message_type": message.type})
            if(message.type == "echo"):
                await websocket.send_json(
                    {
                        "type": "echo.response",
                        "sequence": message.sequence,
                        "data": message.data
                    }
                )
            elif(message.type == "ping"):
                await websocket.send_json(
                    {
                        "type": "pong",
                        "sequence": message.sequence,
                        "data": message.data
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "sequence": message.sequence,
                        "data": {
                            "code": "UNKNOWN_MESSAGE_TYPE",
                            "message": f"Unsupported message type: {message.type}",
                        },
                    }
                )
    except WebSocketDisconnect:
        logger.info("webscoket_disconnected")
