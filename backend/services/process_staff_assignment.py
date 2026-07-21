"""
Helpers para atribuição staff multi-assignee (POST /processes/{id}/assign*).

Extraído de `routes/processes.py` — schema actual:
assigned_consultor_ids / assigned_mediador_ids (+ singulars de compat).

Nota: `process_assignment.py` ainda tem helpers legacy (`consultant_id` /
`mediador_id`) usados pelo auto-assign de indexação; este módulo cobre
os endpoints HTTP de atribuição manual.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from models.auth import UserRole

logger = logging.getLogger(__name__)

CLEAR_SENTINELS = ("", "null")


def normalize_compat_assignment_params(
    consultor_ids: Optional[str],
    mediador_ids: Optional[str],
    consultor_id: Optional[str],
    mediador_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Aplica fallback deprecated consultor_id/mediador_id → *_ids."""
    if consultor_id and not consultor_ids:
        consultor_ids = consultor_id
    if mediador_id and not mediador_ids:
        mediador_ids = mediador_id
    return consultor_ids, mediador_ids


def is_clear_assignment_value(value: Optional[str]) -> bool:
    """True se o parâmetro pede remoção de todos os assignees desse role."""
    return value in CLEAR_SENTINELS


def parse_assignment_ids_csv(value: str) -> list[str]:
    """Converte 'id1,id2' em lista limpa de IDs."""
    return [part.strip() for part in value.split(",") if part.strip()]


async def fetch_user_names(user_ids: list[str]) -> list[str]:
    """Resolve nomes pela ordem dos IDs (omite IDs inexistentes)."""
    names: list[str] = []
    for uid in user_ids:
        doc = await db.users.find_one({"id": uid}, {"name": 1})
        if doc:
            names.append(doc.get("name", ""))
    return names


def build_clear_consultor_fields() -> dict[str, Any]:
    return {
        "assigned_consultor_ids": [],
        "consultor_names": [],
        "assigned_consultor_id": None,
        "consultor_name": None,
    }


def build_clear_mediador_fields() -> dict[str, Any]:
    return {
        "assigned_mediador_ids": [],
        "mediador_names": [],
        "assigned_mediador_id": None,
        "mediador_name": None,
    }


def build_set_consultor_fields(ids: list[str], names: list[str]) -> dict[str, Any]:
    return {
        "assigned_consultor_ids": ids,
        "consultor_names": names,
        "assigned_consultor_id": ids[0],
        "consultor_name": names[0],
    }


def build_set_mediador_fields(ids: list[str], names: list[str]) -> dict[str, Any]:
    return {
        "assigned_mediador_ids": ids,
        "mediador_names": names,
        "assigned_mediador_id": ids[0],
        "mediador_name": names[0],
    }


def detect_newly_assigned(
    *,
    old_consultor_ids: list,
    old_mediador_ids: list,
    old_indexacao: Optional[str],
    old_parceiro: Optional[str],
    update_data: dict,
) -> dict[str, list[str]]:
    """IDs recém-atribuídos (para email automático)."""
    newly: dict[str, list[str]] = {
        "consultores": [],
        "mediadores": [],
        "indexacao": [],
        "parceiro": [],
    }
    new_consultor_list = update_data.get("assigned_consultor_ids")
    if new_consultor_list:
        old_set = set(old_consultor_ids or [])
        newly["consultores"] = [cid for cid in new_consultor_list if cid not in old_set]

    new_mediador_list = update_data.get("assigned_mediador_ids")
    if new_mediador_list:
        old_set = set(old_mediador_ids or [])
        newly["mediadores"] = [mid for mid in new_mediador_list if mid not in old_set]

    new_indexacao = update_data.get("assigned_indexacao_id")
    if new_indexacao and new_indexacao != old_indexacao:
        newly["indexacao"] = [new_indexacao]

    new_parceiro = update_data.get("assigned_parceiro_id")
    if new_parceiro and new_parceiro != old_parceiro:
        newly["parceiro"] = [new_parceiro]

    return newly


async def apply_consultor_ids_param(
    *,
    process_id: str,
    user: dict,
    update_data: dict,
    consultor_ids: str,
    old_consultor_ids: list,
) -> None:
    """Aplica parâmetro consultor_ids (clear ou set) + histórico."""
    from services.history import log_history

    if is_clear_assignment_value(consultor_ids):
        update_data.update(build_clear_consultor_fields())
        if old_consultor_ids:
            old_names = await fetch_user_names(list(old_consultor_ids))
            await log_history(
                process_id, user, "Removeu todos os consultores",
                "assigned_consultor_ids", ", ".join(old_names), None,
            )
        return

    new_ids = parse_assignment_ids_csv(consultor_ids)
    names: list[str] = []
    valid_ids: list[str] = []
    for cid in new_ids:
        doc = await db.users.find_one({"id": cid})
        if doc:
            valid_ids.append(cid)
            names.append(doc["name"])

    if not names:
        return

    update_data.update(build_set_consultor_fields(valid_ids, names))
    old_names = await fetch_user_names(list(old_consultor_ids or []))
    added = [n for n in names if n not in old_names]
    removed = [n for n in old_names if n not in names]
    if added or removed:
        await log_history(
            process_id, user, "Actualizou consultores",
            "assigned_consultor_ids",
            ", ".join(old_names), ", ".join(names),
        )


async def apply_mediador_ids_param(
    *,
    process_id: str,
    user: dict,
    update_data: dict,
    mediador_ids: str,
    old_mediador_ids: list,
) -> None:
    """Aplica parâmetro mediador_ids (clear ou set) + histórico."""
    from services.history import log_history

    if is_clear_assignment_value(mediador_ids):
        update_data.update(build_clear_mediador_fields())
        if old_mediador_ids:
            old_names = await fetch_user_names(list(old_mediador_ids))
            await log_history(
                process_id, user, "Removeu todos os intermediários",
                "assigned_mediador_ids", ", ".join(old_names), None,
            )
        return

    new_ids = parse_assignment_ids_csv(mediador_ids)
    names: list[str] = []
    valid_ids: list[str] = []
    for mid in new_ids:
        doc = await db.users.find_one({"id": mid})
        if doc:
            valid_ids.append(mid)
            names.append(doc["name"])

    if not names:
        return

    update_data.update(build_set_mediador_fields(valid_ids, names))
    old_names = await fetch_user_names(list(old_mediador_ids or []))
    added = [n for n in names if n not in old_names]
    removed = [n for n in old_names if n not in names]
    if added or removed:
        await log_history(
            process_id, user, "Actualizou intermediários",
            "assigned_mediador_ids",
            ", ".join(old_names), ", ".join(names),
        )


async def apply_single_assignee_param(
    *,
    process_id: str,
    user: dict,
    update_data: dict,
    param_value: str,
    old_id: Optional[str],
    id_field: str,
    name_field: str,
    clear_action: str,
    set_action: str,
) -> None:
    """Aplica indexação/parceiro (single assignee) + histórico."""
    from services.history import log_history

    if is_clear_assignment_value(param_value):
        update_data[id_field] = None
        update_data[name_field] = None
        if old_id:
            old_user = await db.users.find_one({"id": old_id}, {"name": 1})
            await log_history(
                process_id, user, clear_action, id_field,
                old_user.get("name") if old_user else old_id, None,
            )
        return

    target = await db.users.find_one({"id": param_value})
    if not target:
        return
    update_data[id_field] = param_value
    update_data[name_field] = target["name"]
    old_name = None
    if old_id:
        old_user = await db.users.find_one({"id": old_id}, {"name": 1})
        old_name = old_user.get("name") if old_user else None
    await log_history(
        process_id, user, set_action, id_field, old_name, target["name"],
    )


async def build_staff_assign_update(
    *,
    process: dict,
    process_id: str,
    user: dict,
    consultor_ids: Optional[str],
    mediador_ids: Optional[str],
    indexacao_id: Optional[str],
    parceiro_id: Optional[str],
    consultor_id: Optional[str] = None,
    mediador_id: Optional[str] = None,
) -> tuple[dict, dict[str, list[str]]]:
    """
    Monta `$set` + mapa de recém-atribuídos para POST /assign.

    Returns:
        (update_data, newly_assigned)
    """
    consultor_ids, mediador_ids = normalize_compat_assignment_params(
        consultor_ids, mediador_ids, consultor_id, mediador_id,
    )
    old_consultor_ids = process.get("assigned_consultor_ids") or []
    old_mediador_ids = process.get("assigned_mediador_ids") or []
    old_indexacao = process.get("assigned_indexacao_id")
    old_parceiro = process.get("assigned_parceiro_id")

    update_data: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if consultor_ids is not None:
        await apply_consultor_ids_param(
            process_id=process_id,
            user=user,
            update_data=update_data,
            consultor_ids=consultor_ids,
            old_consultor_ids=old_consultor_ids,
        )
    if mediador_ids is not None:
        await apply_mediador_ids_param(
            process_id=process_id,
            user=user,
            update_data=update_data,
            mediador_ids=mediador_ids,
            old_mediador_ids=old_mediador_ids,
        )
    if indexacao_id is not None:
        await apply_single_assignee_param(
            process_id=process_id,
            user=user,
            update_data=update_data,
            param_value=indexacao_id,
            old_id=old_indexacao,
            id_field="assigned_indexacao_id",
            name_field="indexacao_name",
            clear_action="Removeu indexação",
            set_action="Atribuiu indexação",
        )
    if parceiro_id is not None:
        await apply_single_assignee_param(
            process_id=process_id,
            user=user,
            update_data=update_data,
            param_value=parceiro_id,
            old_id=old_parceiro,
            id_field="assigned_parceiro_id",
            name_field="parceiro_name",
            clear_action="Removeu parceiro",
            set_action="Atribuiu parceiro",
        )

    newly = detect_newly_assigned(
        old_consultor_ids=old_consultor_ids,
        old_mediador_ids=old_mediador_ids,
        old_indexacao=old_indexacao,
        old_parceiro=old_parceiro,
        update_data=update_data,
    )
    return update_data, newly


def build_assign_me_update(process: dict, user: dict) -> tuple[dict, str]:
    """
    Campos para auto-atribuição (assign-me).

    Returns:
        (update_data, assignment_type)

    Raises:
        HTTPException(400/403)
    """
    from fastapi import HTTPException

    user_role = user.get("role", "")
    user_id = user["id"]
    user_name = user["name"]
    update_data: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    current_consultor_ids = process.get("assigned_consultor_ids") or []
    current_mediador_ids = process.get("assigned_mediador_ids") or []
    current_consultor_names = process.get("consultor_names") or []
    current_mediador_names = process.get("mediador_names") or []

    if UserRole.can_act_as_consultor(user_role):
        if user_id in current_consultor_ids:
            raise HTTPException(
                status_code=400,
                detail="Já está atribuído como consultor a este processo",
            )
        new_ids = list(current_consultor_ids) + [user_id]
        new_names = list(current_consultor_names) + [user_name]
        update_data.update(build_set_consultor_fields(new_ids, new_names))
        return update_data, "consultor"

    if UserRole.can_act_as_intermediario(user_role):
        if user_id in current_mediador_ids:
            raise HTTPException(
                status_code=400,
                detail="Já está atribuído como intermediário a este processo",
            )
        new_ids = list(current_mediador_ids) + [user_id]
        new_names = list(current_mediador_names) + [user_name]
        update_data.update(build_set_mediador_fields(new_ids, new_names))
        return update_data, "intermediario"

    raise HTTPException(
        status_code=403,
        detail="O seu papel não permite atribuir-se a processos",
    )


def build_unassign_me_update(process: dict, user: dict) -> tuple[dict, list[str]]:
    """
    Campos para remoção própria (unassign-me).

    Returns:
        (update_data, removed_from)

    Raises:
        HTTPException(400)
    """
    from fastapi import HTTPException

    user_id = user["id"]
    update_data: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    removed_from: list[str] = []

    current_consultor_ids = list(process.get("assigned_consultor_ids") or [])
    current_mediador_ids = list(process.get("assigned_mediador_ids") or [])
    current_consultor_names = list(process.get("consultor_names") or [])
    current_mediador_names = list(process.get("mediador_names") or [])

    if user_id in current_consultor_ids:
        idx = current_consultor_ids.index(user_id)
        new_ids = current_consultor_ids[:idx] + current_consultor_ids[idx + 1:]
        new_names = current_consultor_names[:idx] + current_consultor_names[idx + 1:]
        update_data["assigned_consultor_ids"] = new_ids
        update_data["consultor_names"] = new_names
        update_data["assigned_consultor_id"] = new_ids[0] if new_ids else None
        update_data["consultor_name"] = new_names[0] if new_names else None
        removed_from.append("consultor")

    if user_id in current_mediador_ids:
        idx = current_mediador_ids.index(user_id)
        new_ids = current_mediador_ids[:idx] + current_mediador_ids[idx + 1:]
        new_names = current_mediador_names[:idx] + current_mediador_names[idx + 1:]
        update_data["assigned_mediador_ids"] = new_ids
        update_data["mediador_names"] = new_names
        update_data["assigned_mediador_id"] = new_ids[0] if new_ids else None
        update_data["mediador_name"] = new_names[0] if new_names else None
        removed_from.append("intermediario")

    if not removed_from:
        raise HTTPException(status_code=400, detail="Não está atribuído a este processo")

    return update_data, removed_from
