from __future__ import annotations

import logging
from typing import Any

from flask import Flask, request
from flask_socketio import SocketIO as BaseSocketIO, disconnect, emit, join_room, leave_room

from app.core.security import decode_token
from config import settings

logger = logging.getLogger("esim-ego")

USER_ROOM_PREFIX = "user:"


class SocketIO(BaseSocketIO):
    pass


socketio = SocketIO(
    async_mode="gevent",
    logger=False,
    engineio_logger=False,
)


def init_socketio(app: Flask) -> None:
    origins = settings.CORS_ORIGINS_LIST
    message_queue = settings.REDIS_URL
    socketio.init_app(
        app,
        cors_allowed_origins=origins if origins else "*",
        async_mode="gevent",
        message_queue=message_queue,
        logger=False,
        engineio_logger=False,
    )


def _get_user_id_from_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    payload = decode_token(token)
    if not payload:
        return None
    return payload.get("sub")


@socketio.on("connect")
def on_connect():
    user_id = _get_user_id_from_token()
    if not user_id:
        return False
    join_room(f"{USER_ROOM_PREFIX}{user_id}")
    logger.debug("SocketIO connect: user=%s sid=%s", user_id, request.sid)
    return True


@socketio.on("disconnect")
def on_disconnect():
    logger.debug("SocketIO disconnect: sid=%s", request.sid)


@socketio.on("join")
def on_join(data: dict[str, Any] | str):
    user_id = _get_user_id_from_token()
    if not user_id:
        disconnect()
        return
    room = data if isinstance(data, str) else data.get("room", "")
    if room:
        join_room(room)
        emit("joined", {"room": room})


@socketio.on("leave")
def on_leave(data: dict[str, Any] | str):
    room = data if isinstance(data, str) else data.get("room", "")
    if room:
        leave_room(room)
        emit("left", {"room": room})


def emit_to_user(user_id: str, event: str, data: dict[str, Any]) -> None:
    socketio.emit(event, data, room=f"{USER_ROOM_PREFIX}{user_id}")


def emit_order_update(user_id: str, order_id: str, status: str, **extra: Any) -> None:
    emit_to_user(user_id, "order_update", {
        "order_id": order_id,
        "status": status,
        **extra,
    })


def emit_wallet_update(user_id: str, balance: int, **extra: Any) -> None:
    emit_to_user(user_id, "wallet_update", {
        "balance": balance,
        **extra,
    })


def emit_push_received(user_id: str, title: str, body: str, data: dict[str, Any] | None = None) -> None:
    emit_to_user(user_id, "push", {
        "title": title,
        "body": body,
        "data": data or {},
    })
