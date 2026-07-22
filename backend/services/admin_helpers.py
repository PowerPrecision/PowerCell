"""Helpers partilhados do admin (_safe_float, _audit_log).

Extraído de `routes/admin.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from database import db

logger = logging.getLogger(__name__)


def _safe_float(val):
    """Converte valor para float de forma segura (helper local)."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


async def _audit_log(action: str, entity: str, entity_id: str, performed_by: dict, details: dict = None):
    """Regista uma ação crítica no audit log para rastreabilidade.

    O audit log é usado para manter um histórico permanente de
    operações sensíveis (criação/eliminação de utilizadores,
    restauros de BD, reset de permissões, etc.).

    Este método é tolerante a falhas: se a escrita no audit log
    falhar (ex: problema de conexão à BD), o erro é registado no
    logger mas NÃO é propagado — evitando que uma falha de auditoria
    bloqueie a operação principal.

    Args:
        action: Identificador da ação (ex: "user_created", "user_deleted",
            "restore_dev_from_backup", "permissions_reset").
        entity: Tipo de entidade afetada (ex: "user", "database").
        entity_id: ID da entidade afetada.
        performed_by: Dicionário do utilizador que executou a ação
            (deve conter "id", "name", "email").
        details: Dicionário opcional com metadados adicionais sobre
            a ação executada.
    """
    try:
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "performed_by_id": performed_by.get("id"),
            "performed_by_name": performed_by.get("name"),
            "performed_by_email": performed_by.get("email"),
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.warning(f"Audit log falhou: {e}")


