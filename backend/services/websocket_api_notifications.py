"""WebSocket notifications endpoint handler.

Extraído de `routes/websocket.py`.
Do **not** overwrite services/websocket_manager.py.
"""
from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from database import db
from services.websocket_manager import manager, WSEventType, create_ws_message
from services.websocket_api_helpers import verify_websocket_token, is_disconnect_error

logger = logging.getLogger(__name__)


async def run_websocket_notifications(websocket: WebSocket, token: str) -> None:
    """Endpoint WebSocket para receber notificações em tempo real."""
    user = await verify_websocket_token(token)

    if user == "expired":
        await websocket.close(code=4001, reason="Token expirado")
        return

    if user == "invalid" or user is None:
        await websocket.close(code=4002, reason="Token inválido")
        return

    user_id = user["id"]
    connected = True

    try:
        await manager.connect(websocket, user_id)

        await websocket.send_json(create_ws_message(
            WSEventType.CONNECTION_STATUS,
            {
                "status": "connected",
                "user_id": user_id,
                "user_name": user.get("name", ""),
                "connected_users": len(manager.get_connected_users())
            }
        ))

        if user.get("role") in ["admin", "ceo"]:
            await manager.broadcast(
                create_ws_message(
                    WSEventType.USER_ONLINE,
                    {"user_id": user_id, "user_name": user.get("name", "")}
                ),
                exclude_user=user_id
            )

        while connected:
            try:
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    logger.debug(f"Cliente {user_id} desconectou normalmente")
                    connected = False
                    break

                if message.get("type") == "websocket.receive":
                    text = message.get("text")
                    if text:
                        try:
                            data = json.loads(text)
                        except json.JSONDecodeError:
                            logger.warning(f"JSON inválido de {user_id}")
                            continue
                    else:
                        continue
                else:
                    continue

                msg_type = data.get("type")

                if msg_type == "ping":
                    try:
                        await websocket.send_json(create_ws_message(
                            WSEventType.HEARTBEAT,
                            {"status": "pong"}
                        ))
                    except Exception:
                        connected = False
                        break

                elif msg_type == "mark_notification_read":
                    notification_id = data.get("notification_id")
                    if notification_id:
                        await db.notifications.update_one(
                            {"id": notification_id, "user_id": user_id},
                            {"$set": {"read": True}}
                        )
                        try:
                            await websocket.send_json(create_ws_message(
                                WSEventType.NOTIFICATION_READ,
                                {"notification_id": notification_id}
                            ))
                        except Exception:
                            connected = False
                            break

                elif msg_type == "mark_all_read":
                    await db.notifications.update_many(
                        {"user_id": user_id, "read": False},
                        {"$set": {"read": True}}
                    )
                    try:
                        await websocket.send_json(create_ws_message(
                            WSEventType.ALL_NOTIFICATIONS_READ,
                            {"status": "success"}
                        ))
                    except Exception:
                        connected = False
                        break

                elif data.get("type") == "process_locked":
                    lock_message = create_ws_message(
                        WSEventType.PROCESS_LOCKED,
                        {
                            "process_id": data.get("process_id"),
                            "user_id": str(user.get("id", "")),
                            "user_name": user.get("name", "Unknown"),
                        }
                    )
                    await manager.broadcast(lock_message, exclude_user=str(user.get("id", "")))

                elif data.get("type") == "process_unlocked":
                    unlock_message = create_ws_message(
                        WSEventType.PROCESS_UNLOCKED,
                        {
                            "process_id": data.get("process_id"),
                            "user_id": str(user.get("id", "")),
                            "user_name": user.get("name", "Unknown"),
                        }
                    )
                    await manager.broadcast(unlock_message, exclude_user=str(user.get("id", "")))

                elif msg_type == "join_process_room":
                    process_id = data.get("process_id")
                    if process_id:
                        room_name = f"process_{process_id}"
                        manager.join_room(room_name, user_id)
                        try:
                            await websocket.send_json(create_ws_message(
                                "room_joined",
                                {"room": room_name, "process_id": process_id}
                            ))
                        except Exception:
                            connected = False
                            break
                        logger.info(f"[ROOM] Utilizador {user_id} juntou-se à room '{room_name}'")

                elif msg_type == "leave_process_room":
                    process_id = data.get("process_id")
                    if process_id:
                        room_name = f"process_{process_id}"
                        manager.leave_room(room_name, user_id)
                        try:
                            await websocket.send_json(create_ws_message(
                                "room_left",
                                {"room": room_name, "process_id": process_id}
                            ))
                        except Exception:
                            connected = False
                            break
                        logger.info(f"[ROOM] Utilizador {user_id} saiu da room '{room_name}'")

            except WebSocketDisconnect:
                logger.debug(f"WebSocketDisconnect: {user_id}")
                connected = False
                break

            except RuntimeError as e:
                if is_disconnect_error(e):
                    logger.debug(f"Conexão fechada (RuntimeError): {user_id}")
                    connected = False
                    break
                logger.warning(f"RuntimeError inesperado WebSocket {user_id}: {e}")
                connected = False
                break

            except Exception as e:
                if is_disconnect_error(e):
                    logger.debug(f"Conexão fechada: {user_id}")
                    connected = False
                    break
                logger.warning(f"Erro WebSocket {user_id}: {type(e).__name__}: {e}")
                connected = False
                break

    except WebSocketDisconnect:
        logger.debug(f"WebSocket desconectado (outer): {user_id}")

    except Exception as e:
        if not is_disconnect_error(e):
            logger.error(f"Erro WebSocket (outer) {user_id}: {type(e).__name__}: {e}")

    finally:
        manager.disconnect(websocket)

        if user.get("role") in ["admin", "ceo"]:
            try:
                await manager.broadcast(
                    create_ws_message(
                        WSEventType.USER_OFFLINE,
                        {"user_id": user_id, "user_name": user.get("name", "")}
                    ),
                    exclude_user=user_id
                )
            except Exception:
                pass
