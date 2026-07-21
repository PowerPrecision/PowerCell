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


def rebuild_client_ids_on_primary_reassign(
    current_client_ids: Optional[list],
    old_client_id: Optional[str],
    new_client_id: str,
) -> list:
    """Atualiza client_ids após troca do titular principal (novo no início)."""
    ids = list(current_client_ids or [])
    if old_client_id and old_client_id in ids:
        ids = [cid for cid in ids if cid != old_client_id]
    if new_client_id not in ids:
        ids.insert(0, new_client_id)
    return ids


def rebuild_client_ids_on_second_titular(
    current_client_ids: Optional[list],
    old_second_id: Optional[str],
    new_second_id: Optional[str],
) -> list:
    """Atualiza client_ids ao adicionar/remover 2º titular."""
    ids = list(current_client_ids or [])
    if old_second_id and old_second_id != new_second_id:
        ids = [cid for cid in ids if cid != old_second_id]
    if new_second_id and new_second_id not in ids:
        ids.append(new_second_id)
    return ids


async def reassign_process_primary_client(
    process: dict,
    process_id: str,
    new_client_id: str,
) -> dict[str, Any]:
    """
    Reatribui o titular principal: sincroniza process_ids e muta `process`.

    Returns:
        dict com old/new client info para histórico/auditoria na rota.

    Raises:
        HTTPException(404): cliente novo inexistente.
    """
    from fastapi import HTTPException
    from services.encryption import decrypt_client_data

    new_client_doc = await db.clients.find_one({"id": new_client_id})
    if not new_client_doc:
        raise HTTPException(
            status_code=404,
            detail=f"Cliente com ID '{new_client_id}' não encontrado.",
        )

    decrypted_new_client = decrypt_client_data(new_client_doc)
    new_client_name = decrypted_new_client.get("nome", "")
    new_client_email = decrypted_new_client.get("contacto", {}).get("email", "")
    new_client_phone = decrypted_new_client.get("contacto", {}).get("telefone", "")

    old_client_id = process.get("client_id")
    old_client_name = process.get("client_name", "")
    now_reassign = datetime.now(timezone.utc).isoformat()

    if old_client_id:
        await db.clients.update_one(
            {"id": old_client_id},
            {
                "$pull": {"process_ids": process_id},
                "$set": {"updated_at": now_reassign},
            },
        )

    await db.clients.update_one(
        {"id": new_client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {"updated_at": now_reassign},
        },
    )

    current_client_ids = rebuild_client_ids_on_primary_reassign(
        process.get("client_ids", []), old_client_id, new_client_id,
    )

    process["client_id"] = new_client_id
    process["client_name"] = new_client_name
    process["client_email"] = new_client_email
    process["client_phone"] = new_client_phone
    process["client_ids"] = current_client_ids

    return {
        "old_client_id": old_client_id,
        "old_client_name": old_client_name,
        "new_client_id": new_client_id,
        "new_client_name": new_client_name,
    }


async def sync_second_client_on_update(
    process: dict,
    process_id: str,
    new_second_id: Optional[str],
) -> dict[str, Any]:
    """
    Valida e sincroniza 2º titular (client_ids + process_ids nos clients).

    Args:
        new_second_id: ID limpo ou None (remoção).

    Returns:
        Campos a fazer merge em update_data.

    Raises:
        HTTPException(400): cliente inexistente ou igual ao titular principal.
    """
    from fastapi import HTTPException

    second_client = None
    if new_second_id:
        second_client = await db.clients.find_one({"id": new_second_id})
        if not second_client:
            raise HTTPException(
                status_code=400,
                detail=f"Cliente com ID {new_second_id} não encontrado",
            )
        if new_second_id == process.get("client_id"):
            raise HTTPException(
                status_code=400,
                detail="O 2º titular não pode ser o mesmo cliente que o titular principal",
            )

    update_fields: dict[str, Any] = {"second_client_id": new_second_id}
    old_second_id = process.get("second_client_id")

    if not new_second_id:
        update_fields["second_client_name"] = None
    else:
        update_fields["second_client_name"] = second_client.get("nome", "")

    update_fields["client_ids"] = rebuild_client_ids_on_second_titular(
        process.get("client_ids") or [], old_second_id, new_second_id,
    )

    now_iso_sync = datetime.now(timezone.utc).isoformat()
    if old_second_id and old_second_id != new_second_id:
        try:
            await db.clients.update_one(
                {"id": old_second_id},
                {
                    "$pull": {"process_ids": process_id},
                    "$set": {"updated_at": now_iso_sync},
                },
            )
            logger.info(
                f"[PACOTE-BP] Processo {process_id} removido do process_ids "
                f"do 2º titular antigo {old_second_id}"
            )
        except Exception as e:
            logger.warning(f"[PACOTE-BP] Erro ao remover process_ids do 2º titular antigo: {e}")

    if new_second_id:
        try:
            await db.clients.update_one(
                {"id": new_second_id},
                {
                    "$addToSet": {"process_ids": process_id},
                    "$set": {"updated_at": now_iso_sync},
                },
            )
            logger.info(
                f"[PACOTE-BP] Processo {process_id} adicionado ao process_ids "
                f"do 2º titular {new_second_id}"
            )
        except Exception as e:
            logger.warning(f"[PACOTE-BP] Erro ao adicionar process_ids ao 2º titular: {e}")

    return update_fields


def merge_field_metadata(existing: Optional[dict], incoming: dict) -> dict:
    """Merge seguro de field_metadata (não apaga keys não atualizadas)."""
    base = existing if isinstance(existing, dict) else {}
    return {**base, **incoming}
