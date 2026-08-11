"""WebSocket route helpers.

Extraído de `routes/websocket.py`.
Do **not** overwrite services/websocket_manager.py.
"""
from __future__ import annotations

import logging

import jwt

from config import JWT_SECRET, JWT_ALGORITHM
from database import db

logger = logging.getLogger(__name__)


async def verify_websocket_token(token: str):
    """Verificar token JWT para ligação WebSocket."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            return None

        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})

        if not user or user.get("is_active") == False:
            return None

        return user
    except jwt.ExpiredSignatureError:
        logger.warning("JWT WebSocket: Token expirado (Signature has expired)")
        return "expired"
    except jwt.PyJWTError as e:
        logger.error(f"JWT WebSocket: Token inválido — {e}")
        return "invalid"
    except Exception as e:
        logger.error(f"JWT WebSocket: Erro inesperado — {type(e).__name__}: {e}")
        return None


def is_disconnect_error(error: Exception) -> bool:
    """Verifica se o erro indica desconexão do cliente."""
    error_str = str(error).lower()
    error_type = type(error).__name__

    disconnect_indicators = [
        "disconnect",
        "closed",
        "connection reset",
        "broken pipe",
        "cannot call receive",
    ]

    for indicator in disconnect_indicators:
        if indicator in error_str:
            return True

    if error_type in ["WebSocketDisconnect", "ConnectionClosed", "RuntimeError"]:
        return True

    return False
