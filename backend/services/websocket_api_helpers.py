"""WebSocket route helpers.

Extraído de `routes/websocket.py`.
Do **not** overwrite services/websocket_manager.py.
"""
from __future__ import annotations

import logging
from typing import Optional

import jwt

from config import JWT_SECRET, JWT_ALGORITHM
from database import db
from models.auth import UserRole

logger = logging.getLogger(__name__)

# Campos mínimos para decidir se o utilizador pode entrar na room do processo.
PROCESS_ROOM_ACL_PROJECTION = {
    "_id": 0,
    "id": 1,
    "is_deleted": 1,
    "client_id": 1,
    "status": 1,
    "created_by": 1,
    "assigned_to": 1,
    "assigned_consultor_id": 1,
    "assigned_consultor_ids": 1,
    "assigned_mediador_id": 1,
    "assigned_mediador_ids": 1,
    "assigned_indexacao_id": 1,
}

# Gestores + administrativo: vêem todos os processos (igual à listagem global).
_PROCESS_ROOM_GLOBAL_ROLES = {
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
}


def process_room_name(process_id: str) -> str:
    """Nome canónico da room WebSocket de um processo."""
    return f"process_{process_id}"


def _roles_for_acl(user: dict) -> set[str]:
    """Role primário + additional_roles (multi-perfil)."""
    roles: set[str] = set()
    primary = (user.get("role") or "").strip().lower()
    if primary:
        roles.add(primary)
    extra = user.get("additional_roles") or []
    if isinstance(extra, list):
        for item in extra:
            if item:
                roles.add(str(item).strip().lower())
    # Legado: mediador → intermediario
    if UserRole.MEDIADOR in roles or "mediador" in roles:
        roles.add(UserRole.INTERMEDIARIO)
    return roles


def _user_id_matches(value, user_id: str) -> bool:
    if not user_id or value is None:
        return False
    if isinstance(value, list):
        return user_id in value
    return value == user_id


def user_can_join_process_room(user: Optional[dict], process: Optional[dict]) -> bool:
    """ACL de rooms de processo (C2).

    Quem pode entrar:
    - gestor (admin / ceo / diretor) e administrativo — qualquer processo
    - consultor atribuído (assigned_consultor_* / assigned_to)
    - intermediário atribuído (assigned_mediador_* / assigned_to)
    - indexação: atribuída, criadora, ou fila de espera
    - cliente: apenas o seu próprio processo

    Recusa processo inexistente, parceiro, e roles desconhecidos.
    """
    if not user or not process:
        return False

    user_id = user.get("id") or ""
    roles = _roles_for_acl(user)
    if not user_id or not roles:
        return False

    if roles <= {UserRole.PARCEIRO, "parceiro"}:
        return False

    if roles & _PROCESS_ROOM_GLOBAL_ROLES:
        return True

    if UserRole.CONSULTOR in roles and (
        _user_id_matches(process.get("assigned_consultor_ids"), user_id)
        or _user_id_matches(process.get("assigned_consultor_id"), user_id)
        or _user_id_matches(process.get("assigned_to"), user_id)
    ):
        return True

    if UserRole.INTERMEDIARIO in roles and (
        _user_id_matches(process.get("assigned_mediador_ids"), user_id)
        or _user_id_matches(process.get("assigned_mediador_id"), user_id)
        or _user_id_matches(process.get("assigned_to"), user_id)
    ):
        return True

    if UserRole.INDEXACAO in roles and (
        _user_id_matches(process.get("assigned_indexacao_id"), user_id)
        or _user_id_matches(process.get("assigned_to"), user_id)
        or process.get("created_by") == user.get("email")
        or process.get("status") == "fila_espera"
    ):
        return True

    if UserRole.CLIENTE in roles and process.get("client_id") == user_id:
        return True

    return False


async def load_process_for_room_acl(process_id: str) -> Optional[dict]:
    """Carrega o processo da BD para a decisão de ACL da room."""
    if not process_id:
        return None
    return await db.processes.find_one({"id": process_id}, PROCESS_ROOM_ACL_PROJECTION)


async def authorize_process_room_access(user: dict, process_id: str) -> bool:
    """True se o utilizador pode aceder à room ``process_{id}``."""
    process = await load_process_for_room_acl(process_id)
    return user_can_join_process_room(user, process)


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
