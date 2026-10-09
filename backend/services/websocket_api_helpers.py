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
    """Verificar token JWT de STAFF para ligação WebSocket.

    A claim `type` é AUTORITATIVA desde o lote dos WebSockets externos.
    Antes, o que impedia um token do Portal de abrir este socket era uma
    **coincidência**: o `sub` de um token de Portal é um `process_id`, que não
    existe em `db.users`. Mesmo segredo, mesma função de decifra, zero
    verificações de tipo — e abrir o namespace aos clientes transformaria essa
    coincidência numa decisão de autorização por omissão.

    Um token de Portal (ou `gov_auth`) é agora recusado EXPLICITAMENTE, mesmo
    que o `sub` viesse a casar com um utilizador. Os clientes têm o seu
    endpoint próprio (`/ws/portal`), com o seu próprio verificador.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            return None

        from services.ws_client_identity import tipo_de_token_e_de_staff

        tipo = payload.get("type")
        if not tipo_de_token_e_de_staff(tipo):
            logger.warning(
                "[WS] Token de tipo '%s' recusado no socket de staff "
                "(sub=%s) — os clientes do Portal usam /ws/portal.",
                tipo, user_id,
            )
            return "invalid"

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


async def verify_portal_websocket_token(token: str):
    """Verificar token de CLIENTE do Portal para o socket `/ws/portal`.

    Lista de PERMISSÃO nos dois eixos, e nenhum deles é opcional:
      * `role` tem de ser `client_portal` (o mesmo que o `get_current_client`
        exige na API REST);
      * `type` tem de ser um dos TRÊS tipos que o `portal_security` emite.

    O `sub` de um token de Portal **é** o `process_id` — é dele que sai a sala,
    no servidor, e é por isso que o cliente nunca precisa (nem pode) pedir uma.

    Returns:
        ``(process_id, tipo)`` quando válido; ``"expired"`` / ``"invalid"``
        para o chamador fechar com o código certo; ``None`` se o processo não
        existir ou estiver eliminado.
    """
    from services.portal_security import PORTAL_ROLE
    from services.ws_client_identity import tipo_de_token_e_do_portal

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.info("[WS-PORTAL] Token expirado")
        return "expired"
    except jwt.PyJWTError as e:
        logger.warning(f"[WS-PORTAL] Token inválido — {e}")
        return "invalid"
    except Exception as e:
        logger.error(f"[WS-PORTAL] Erro inesperado — {type(e).__name__}: {e}")
        return "invalid"

    if payload.get("role") != PORTAL_ROLE:
        logger.warning(
            "[WS-PORTAL] Token com role '%s' recusado (esperado '%s') — "
            "um token de staff não entra por aqui.",
            payload.get("role"), PORTAL_ROLE,
        )
        return "invalid"

    tipo = payload.get("type")
    if not tipo_de_token_e_do_portal(tipo):
        logger.warning("[WS-PORTAL] Token de tipo '%s' recusado", tipo)
        return "invalid"

    process_id = payload.get("sub")
    if not process_id:
        return "invalid"

    # O processo tem de existir e não estar eliminado — a mesma verificação do
    # `get_current_client`. Um magic link continua válido depois de o processo
    # ser apagado, e sem isto o cliente entrava numa sala de um processo morto.
    processo = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, "id": 1, "is_deleted": 1, "status": 1}
    )
    if not processo or processo.get("is_deleted"):
        logger.warning(
            "[WS-PORTAL] Processo %s inexistente ou eliminado — ligação recusada",
            process_id,
        )
        return None

    # Bloco 3 (ponto 14): fase terminal = Portal bloqueado — também em tempo
    # real. Um socket recusado aqui fecha com 4002 («acesso inválido»), que o
    # cliente trata como veredicto e não reconecta.
    from services.portal_estado import processo_esta_inativo

    if await processo_esta_inativo(processo):
        logger.info(
            "[WS-PORTAL] Processo %s em fase terminal — ligação recusada",
            process_id,
        )
        return None

    return process_id, tipo
