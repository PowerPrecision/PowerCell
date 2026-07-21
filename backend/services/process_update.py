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


TERMINAL_PROCESS_STATUSES = ("eliminados", "desistencias", "concluidos")
FINANCE_RELEVANT_STATUSES = ("concluidos", "escritura", "escritura_agendada")
VALID_PRIORIDADES = ("baixa", "media", "alta")


def assert_process_editable_for_role(status: Optional[str], role: str) -> None:
    """
    Bloqueia edição em estados terminais (exceto admin/CEO).

    Raises:
        HTTPException(403)
    """
    from fastapi import HTTPException

    is_admin_or_ceo = role in [UserRole.ADMIN, UserRole.CEO]
    if status in TERMINAL_PROCESS_STATUSES and not is_admin_or_ceo:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Não é possível editar um processo em estado terminal ({status})."
            ),
        )


def seed_update_data(
    *,
    process: dict,
    client_id_before: Optional[str],
    new_client_id: Optional[str],
    raw_client_email: Any,
    raw_client_phone: Any,
) -> dict:
    """Monta o `$set` base: timestamp + contactos + campos de reatribuição."""
    update_data: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if raw_client_email is not None:
        update_data["client_email"] = raw_client_email
    if raw_client_phone is not None:
        update_data["client_phone"] = raw_client_phone

    if new_client_id and new_client_id != client_id_before:
        update_data["client_id"] = process["client_id"]
        update_data["client_name"] = process["client_name"]
        update_data["client_email"] = process["client_email"]
        update_data["client_phone"] = process["client_phone"]
        update_data["client_ids"] = process["client_ids"]
    return update_data


def maybe_copy_owner_to_vendedor(
    merged_re: Optional[dict],
    existing_vendedor: Optional[dict],
    *,
    vendedor_explicit: bool,
) -> Optional[dict]:
    """
    Se vendedor.nome vazio e sem update explícito, copia proprietário/owner.
    """
    existing = existing_vendedor if isinstance(existing_vendedor, dict) else {}
    if not merged_re or existing.get("nome") or vendedor_explicit:
        return None
    owner_name = merged_re.get("proprietario_nome") or merged_re.get("owner_name") or ""
    owner_contact = (
        merged_re.get("proprietario_contacto") or merged_re.get("owner_phone") or ""
    )
    if not owner_name:
        return None
    return {**existing, "nome": owner_name, "contacto": owner_contact}


def sanitize_party_dict_names(d: dict) -> None:
    """Sanitiza nome/email/telefone/url em dicts de vendedor/mediador (in-place)."""
    from utils.input_sanitization import (
        sanitize_email, sanitize_name, sanitize_phone,
        sanitize_string, sanitize_url,
    )
    name_fields = ["nome", "name", "nome_completo", "full_name"]
    email_fields = ["email", "e_mail"]
    phone_fields = ["telefone", "phone", "telemovel", "mobile"]
    url_fields = ["url", "website", "link"]
    for key in list(d.keys()):
        if key in name_fields and d[key] is not None:
            d[key] = sanitize_name(str(d[key]))
        elif key in email_fields and d[key] is not None:
            d[key] = sanitize_email(str(d[key]))
        elif key in phone_fields and d[key] is not None:
            d[key] = sanitize_phone(str(d[key]))
        elif key in url_fields and d[key] is not None:
            d[key] = sanitize_url(str(d[key]))
        elif isinstance(d[key], str) and d[key]:
            d[key] = sanitize_string(d[key], max_length=500)


def apply_cpcv_and_metadata_fields(update_data: dict, data: Any) -> None:
    """
    Aplica co_buyers / vendedor / mediador / notes / prioridade / labels.

    Raises:
        HTTPException(400): prioridade inválida.
    """
    from fastapi import HTTPException

    if data.co_buyers is not None:
        update_data["co_buyers"] = data.co_buyers
    if data.co_applicants is not None:
        update_data["co_applicants"] = data.co_applicants
    if data.vendedor is not None:
        sanitize_party_dict_names(data.vendedor)
        update_data["vendedor"] = data.vendedor
    if data.mediador is not None:
        sanitize_party_dict_names(data.mediador)
        update_data["mediador"] = data.mediador
    if data.monitored_emails is not None:
        update_data["monitored_emails"] = data.monitored_emails
    if data.notes is not None:
        update_data["notes"] = data.notes
    if data.prioridade is not None:
        if data.prioridade not in VALID_PRIORIDADES:
            raise HTTPException(
                status_code=400,
                detail="Prioridade inválida. Valores aceites: baixa, media, alta",
            )
        update_data["prioridade"] = data.prioridade
    if data.labels is not None:
        update_data["labels"] = data.labels


async def apply_staff_business_updates(
    *,
    process: dict,
    process_id: str,
    data: Any,
    raw_body: dict,
    update_data: dict,
    user: dict,
    request: Any,
    audit_reason: Optional[str],
    ai_suggested: bool,
    perms: dict[str, bool],
    valid_statuses: list,
) -> None:
    """
    Merge de secções de negócio (RE/crédito/financeiro/2º titular/CPCV/status).

    Mutação in-place de `update_data`. Side-effects de histórico/audit/email
    ficam aqui para a rota permanecer fina.
    """
    from services.history import log_history, log_data_changes
    from services.audit_trail_service import log_audit_event
    from services.notification_service import send_notification_with_preference_check

    can_update_financial = perms["can_update_financial"]
    can_update_real_estate = perms["can_update_real_estate"]
    can_update_credit = perms["can_update_credit"]
    can_update_status = perms["can_update_status"]
    ai_approved_by = user.get("id") if ai_suggested else None

    if data.real_estate_data and can_update_real_estate:
        incoming_re = data.real_estate_data.model_dump(exclude_unset=True)
        _re = process.get("real_estate_data")
        existing_re = _re if isinstance(_re, dict) else {}
        merged_re = merge_nested_process_section(existing_re, incoming_re)
        await log_data_changes(
            process_id, user, existing_re, incoming_re, "dados imobiliários",
        )
        await log_audit_event(
            process_id, user, "Alterou dados imobiliários",
            request=request, source="web",
            audit_reason=audit_reason, ai_suggested=ai_suggested,
            ai_approved_by=ai_approved_by,
        )
        update_data["real_estate_data"] = merged_re

    merged_re = update_data.get("real_estate_data")
    _vd = process.get("vendedor")
    existing_vendedor = _vd if isinstance(_vd, dict) else {}
    synced_vendedor = maybe_copy_owner_to_vendedor(
        merged_re, existing_vendedor, vendedor_explicit=data.vendedor is not None,
    )
    if synced_vendedor is not None:
        update_data["vendedor"] = synced_vendedor

    if data.credit_data and can_update_credit:
        incoming_credit = data.credit_data.model_dump(exclude_unset=True)
        _cd = process.get("credit_data")
        existing_credit = _cd if isinstance(_cd, dict) else {}
        merged_credit = merge_nested_process_section(existing_credit, incoming_credit)
        await log_data_changes(
            process_id, user, existing_credit, incoming_credit, "dados de crédito",
        )
        await log_audit_event(
            process_id, user, "Alterou dados de crédito",
            request=request, source="web",
            audit_reason=audit_reason, ai_suggested=ai_suggested,
            ai_approved_by=ai_approved_by,
        )
        update_data["credit_data"] = merged_credit

    if can_update_financial:
        incoming_fd = raw_body.get("financial_data")
        if isinstance(incoming_fd, dict):
            _fd = process.get("financial_data")
            existing_fd = _fd if isinstance(_fd, dict) else {}
            merged_fd = merge_nested_process_section(
                existing_fd, incoming_fd, drop_empty_strings=True,
            )
            await log_data_changes(
                process_id, user, existing_fd, incoming_fd, "dados financeiros",
            )
            await log_audit_event(
                process_id, user, "Alterou dados financeiros",
                request=request, source="web",
                audit_reason=audit_reason, ai_suggested=ai_suggested,
                ai_approved_by=ai_approved_by,
            )
            update_data["financial_data"] = merged_fd

    if data.second_client_id is not None:
        new_second_id = data.second_client_id.strip() if data.second_client_id else None
        second_fields = await sync_second_client_on_update(
            process, process_id, new_second_id,
        )
        update_data.update(second_fields)

    apply_cpcv_and_metadata_fields(update_data, data)

    if data.status and can_update_status and (
        data.status in valid_statuses or not valid_statuses
    ):
        await log_history(
            process_id, user, "Alterou estado",
            "status", process["status"], data.status,
        )
        await log_audit_event(
            process_id, user, "Alterou estado",
            field="status", old_value=process["status"], new_value=data.status,
            request=request, source="web",
            audit_reason=audit_reason, ai_suggested=ai_suggested,
            ai_approved_by=ai_approved_by,
        )
        update_data["status"] = data.status
        if process.get("client_email"):
            await send_notification_with_preference_check(
                process["client_email"],
                "Estado do Processo Atualizado",
                f"O estado do seu processo foi atualizado para: {data.status}",
                notification_type="status_change",
            )


def encrypt_process_update_payload(update_data: dict, process_id: str) -> dict:
    """
    Encripta campos sensíveis do `$set` com diagnóstico TypeError.

    Raises:
        HTTPException(500)
    """
    from fastapi import HTTPException
    from services.process_service import encrypt_sensitive_data

    try:
        return encrypt_sensitive_data(update_data)
    except TypeError as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(
            f"TypeError em encrypt_sensitive_data para processo {process_id}: {e}\n{tb}"
        )
        for k, v in update_data.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    if not isinstance(sv, (str, int, float, bool, type(None), list)):
                        logger.error(
                            f"  Suspeito: update_data[{k}][{sk}] = "
                            f"{type(sv).__name__}: {repr(sv)[:100]}"
                        )
            elif not isinstance(v, (str, int, float, bool, type(None), list, dict)):
                logger.error(
                    f"  Suspeito root: update_data[{k}] = "
                    f"{type(v).__name__}: {repr(v)[:100]}"
                )
        raise HTTPException(
            status_code=500,
            detail=(
                f"TypeError em encrypt: {e} | "
                f"{tb.split(chr(10))[-3] if tb else 'no traceback'}"
            ),
        )


def attach_field_metadata_if_present(
    update_data: dict,
    process: dict,
    raw_body: dict,
) -> None:
    """Merge field_metadata do raw body (se dict)."""
    field_metadata_cs = raw_body.get("field_metadata")
    if field_metadata_cs and isinstance(field_metadata_cs, dict):
        update_data["field_metadata"] = merge_field_metadata(
            process.get("field_metadata"), field_metadata_cs,
        )


async def run_process_update_side_effects(
    *,
    process: dict,
    process_id: str,
    data: Any,
    updated: dict,
    user: dict,
    can_update_status: bool,
    broadcast_fn,
    ensure_finance_snapshot_fn,
    decrypt_fn,
) -> None:
    """
    Pós-persist: Trello, snapshot financeiro, cache, WS, workflow automation.
    """
    import asyncio
    from services.trello_service import sync_process_to_trello
    from services.redis_cache import invalidate_stats_cache
    from services.websocket_manager import WSEventType

    if data.status and data.status != process.get("status"):
        asyncio.create_task(
            sync_process_to_trello(updated, action="move", new_status=data.status)
        )
    else:
        asyncio.create_task(sync_process_to_trello(updated, action="update"))

    current_status = updated.get("status", "")
    if current_status in FINANCE_RELEVANT_STATUSES:
        try:
            decrypted_for_finance = decrypt_fn(updated)
        except Exception:
            decrypted_for_finance = updated
        try:
            await ensure_finance_snapshot_fn(decrypted_for_finance, user)
        except Exception as snap_err:
            logger.warning(
                f"Falha na sincronização financeira retroativa "
                f"para processo {process_id}: {snap_err}"
            )

    if data.status:
        await invalidate_stats_cache(user_id=user.get("id"))

    await broadcast_fn(
        event_type=WSEventType.PROCESS_UPDATED,
        process_id=process_id,
        process_number=updated.get("process_number"),
        client_name=updated.get("client_name"),
        status=updated.get("status"),
        old_status=process.get("status") if data.status else None,
        priority=updated.get("prioridade") or updated.get("priority"),
        prioridade=updated.get("prioridade"),
        updated_at=updated.get("updated_at"),
    )

    if data.status and can_update_status:
        try:
            from services.workflow_engine import process_trigger
            await process_trigger("process_status_changed", {
                "process_id": process_id,
                "old_status": process.get("status"),
                "new_status": data.status,
                "client_name": process.get("client_name", ""),
            })
        except Exception as e:
            logger.warning(f"Erro ao processar automações: {e}")


def parse_update_request_meta(raw_body: Optional[dict]) -> tuple[dict, Any, bool]:
    """Extrai raw_body seguro + audit_reason + ai_suggested."""
    body = raw_body if isinstance(raw_body, dict) else {}
    return body, body.get("audit_reason"), bool(body.get("ai_suggested", False))


def assert_can_reassign_primary_client(role: str) -> None:
    from fastapi import HTTPException
    if role not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]:
        raise HTTPException(
            status_code=403,
            detail=(
                "Apenas administradores, CEO ou directores podem reatribuir "
                "o cliente de um processo."
            ),
        )


def assert_cliente_owns_process(process: dict, user: dict) -> None:
    """CLIENTE só edita o próprio processo (client_id == user.id)."""
    from fastapi import HTTPException
    if user.get("role") != UserRole.CLIENTE:
        return
    if process.get("client_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Acesso negado")


def decrypt_process_doc_or_500(process: dict, process_id: str, decrypt_fn) -> dict:
    from fastapi import HTTPException
    try:
        return decrypt_fn(process)
    except Exception as e:
        logger.error(f"Erro ao desencriptar processo {process_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                f"Erro interno ao desencriptar dados do processo: "
                f"{type(e).__name__}"
            ),
        )


def build_process_response_or_500(updated: dict, process_id: str):
    """Serializa ProcessResponse ou HTTP 500."""
    from fastapi import HTTPException
    from models.process import ProcessResponse
    try:
        return ProcessResponse(**updated)
    except Exception as e:
        logger.error(f"Erro ao serializar resposta do processo {process_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao serializar dados do processo: {str(e)[:200]}",
        )


async def load_valid_workflow_status_names() -> list[str]:
    statuses = await db.workflow_statuses.find(
        {}, {"name": 1, "_id": 0},
    ).to_list(100)
    return [s["name"] for s in statuses]


async def maybe_reassign_primary_client_with_audit(
    *,
    process: dict,
    process_id: str,
    new_client_id: Optional[str],
    role: str,
    user: dict,
    request: Any,
    log_history_fn,
    log_audit_event_fn,
) -> None:
    """
    Se new_client_id difere do actual: valida role, reatribui e regista histórico.
    """
    if not new_client_id or new_client_id == process.get("client_id"):
        return
    assert_can_reassign_primary_client(role)
    reassign_info = await reassign_process_primary_client(
        process, process_id, new_client_id,
    )
    msg = (
        f"Reatribuiu cliente de '{reassign_info['old_client_name']}' "
        f"para '{reassign_info['new_client_name']}'"
    )
    await log_history_fn(process_id, user, msg)
    await log_audit_event_fn(
        process_id, user, msg, request=request, source="web",
    )
    logger.info(
        f"Processo {process_id} reatribuído de cliente "
        f"{reassign_info['old_client_id']} ({reassign_info['old_client_name']}) "
        f"para cliente {reassign_info['new_client_id']} "
        f"({reassign_info['new_client_name']}) por {user.get('email')}"
    )


async def decrypt_and_populate_updated_process(
    updated: dict,
    process_id: str,
    *,
    decrypt_fn,
    populate_fn,
) -> dict:
    """Desencripta + popula cliente após PUT (ou 500)."""
    from fastapi import HTTPException
    try:
        updated = decrypt_fn(updated)
    except Exception as e:
        logger.error(f"Erro ao desencriptar dados do processo {process_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao desencriptar dados do processo",
        )
    return await populate_fn(updated)
