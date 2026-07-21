"""
Helpers para PUT /processes/{id}.

Extraído de `routes/processes.py` (`update_process`) — encriptação de
updates de cliente, merge de secções aninhadas e permissões por role.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from models.auth import UserRole
from services.encryption import generate_nif_hash, generate_email_hash

logger = logging.getLogger(__name__)


def prepare_encrypted_client_updates(client_updates: dict) -> dict:
    """
    Adiciona blind indexes e encripta campos sensíveis do update de cliente.

    Em falha de encriptação, devolve os updates originais (com hashes se
    gerados) — mesmo comportamento do endpoint original.
    """
    if "dados_pessoais.nif" in client_updates:
        nif_val = client_updates["dados_pessoais.nif"]
        nif_hash = generate_nif_hash(nif_val)
        if nif_hash:
            client_updates["dados_pessoais.nif_hash"] = nif_hash
    if "contacto.email" in client_updates:
        email_val = client_updates["contacto.email"]
        email_hash = generate_email_hash(email_val)
        if email_hash:
            client_updates["contacto.email_hash"] = email_hash

    try:
        from services.encryption import encrypt_client_data
        temp_client_update: dict[str, Any] = {}
        for k, v in client_updates.items():
            if k.startswith("dados_pessoais."):
                temp_client_update.setdefault("dados_pessoais", {})[
                    k.replace("dados_pessoais.", "")
                ] = v
            elif k.startswith("contacto."):
                temp_client_update.setdefault("contacto", {})[
                    k.replace("contacto.", "")
                ] = v
            else:
                temp_client_update[k] = v

        encrypted = encrypt_client_data(temp_client_update)
        final_client_updates: dict[str, Any] = {}
        for k, v in client_updates.items():
            if k.startswith("dados_pessoais.") and "dados_pessoais" in encrypted:
                field = k.replace("dados_pessoais.", "")
                final_client_updates[k] = encrypted["dados_pessoais"].get(field, v)
            elif k.startswith("contacto.") and "contacto" in encrypted:
                field = k.replace("contacto.", "")
                final_client_updates[k] = encrypted["contacto"].get(field, v)
            elif k in encrypted:
                final_client_updates[k] = encrypted[k]
            else:
                final_client_updates[k] = v

        if "dados_pessoais.nif_hash" in client_updates:
            final_client_updates["dados_pessoais.nif_hash"] = client_updates[
                "dados_pessoais.nif_hash"
            ]
        if "contacto.email_hash" in client_updates:
            final_client_updates["contacto.email_hash"] = client_updates[
                "contacto.email_hash"
            ]
        return final_client_updates
    except Exception as e:
        logger.warning(f"Erro ao encriptar dados do cliente: {e}")
        return client_updates


async def apply_client_personal_updates_from_process_put(
    client_id: str,
    client_updates: dict,
    process_id: str,
) -> None:
    """$set no cliente + cascade do nome para outros processos."""
    now_iso = datetime.now(timezone.utc).isoformat()
    client_updates = {**client_updates, "updated_at": now_iso}
    await db.clients.update_one({"id": client_id}, {"$set": client_updates})
    logger.info(
        f"Dados pessoais do cliente {client_id} atualizados via PUT processo: "
        f"{list(client_updates.keys())}"
    )

    updated_client_name = client_updates.get("nome")
    if not updated_client_name:
        return

    updated_client = await db.clients.find_one({"id": client_id}, {"process_ids": 1})
    all_process_ids = updated_client.get("process_ids", []) if updated_client else []
    other_process_ids = [pid for pid in all_process_ids if pid != process_id]
    if not other_process_ids:
        return

    cascade_sync = {
        "client_name": updated_client_name,
        "personal_data.nome": updated_client_name,
        "personal_data.name": updated_client_name,
    }
    await db.processes.update_many(
        {"id": {"$in": other_process_ids}},
        {"$set": cascade_sync},
    )
    logger.info(
        f"Sincronização inversa: nome '{updated_client_name}' propagado para "
        f"{len(other_process_ids)} processos do cliente {client_id}"
    )


def merge_nested_process_section(
    existing: Optional[dict],
    incoming: dict,
    *,
    drop_empty_strings: bool = False,
) -> dict:
    """
    Merge shallow de secções nested do processo.

    drop_empty_strings=True → financial_data (remove None e "").
    Caso contrário → só remove None (real_estate / credit).
    """
    base = existing if isinstance(existing, dict) else {}
    merged = {**base, **incoming}
    if drop_empty_strings:
        return {k: v for k, v in merged.items() if v is not None and v != ""}
    return {k: v for k, v in merged.items() if v is not None}


def build_role_update_permissions(role: str) -> dict[str, bool]:
    """Flags de permissão de edição por role no PUT do processo."""
    return {
        "can_update_personal": role in [
            UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
            UserRole.DIRETOR, UserRole.ADMINISTRATIVO,
        ],
        "can_update_financial": role in [
            UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO,
            UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO,
        ],
        "can_update_real_estate": UserRole.can_act_as_consultor(role),
        "can_update_credit": UserRole.can_act_as_intermediario(role),
        "can_update_status": role in [
            UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
            UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO,
        ],
    }
