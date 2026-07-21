"""
Helpers N:M cliente↔processo (add-client / remove-client).

Extraído de `routes/processes.py`.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException


def extract_client_contact_snapshot(client: dict) -> dict[str, Any]:
    """Snapshot nome/email/nif/phone a partir do doc cliente (como na rota original)."""
    contacto = client.get("contacto") or {}
    dados = client.get("dados_pessoais") or {}
    return {
        "name": client.get("nome"),
        "email": contacto.get("email"),
        "nif": dados.get("nif"),
        "phone": contacto.get("telefone"),
    }


def assert_client_not_on_process(client_ids: list, client_id: str) -> None:
    if client_id in client_ids:
        raise HTTPException(
            status_code=400,
            detail="Cliente já está associado a este processo",
        )


def assert_client_on_process(client_ids: list, client_id: str) -> None:
    if client_id not in client_ids:
        raise HTTPException(
            status_code=400,
            detail="Cliente não está associado a este processo",
        )


def assert_not_primary_client(process: dict, client_id: str) -> None:
    if client_id == process.get("client_id"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Não é possível remover o cliente principal. "
                "Apenas co-titulares podem ser removidos."
            ),
        )


def build_add_client_update(
    process: dict,
    client: dict,
    client_id: str,
    *,
    as_co_titular: bool,
    now: str,
) -> tuple[dict[str, Any], list]:
    """
    Constrói `$set` para add-client.

    Returns:
        (update_data, new_client_ids)
    """
    current_client_ids = list(process.get("client_ids") or [])
    assert_client_not_on_process(current_client_ids, client_id)
    current_client_ids.append(client_id)

    update_data: dict[str, Any] = {
        "updated_at": now,
        "client_ids": current_client_ids,
    }

    if as_co_titular:
        snap = extract_client_contact_snapshot(client)
        co_buyers = list(process.get("co_buyers") or [])
        co_buyers.append({
            **snap,
            "client_id": client_id,
            "relacao": "co-titular",
        })
        update_data["co_buyers"] = co_buyers
        if len(co_buyers) == 1:
            update_data["titular2_data"] = {
                "name": snap["name"],
                "email": snap["email"],
                "nif": snap["nif"],
                "phone": snap["phone"],
            }

    return update_data, current_client_ids


def build_remove_client_update(
    process: dict,
    client_id: str,
    *,
    now: str,
) -> tuple[dict[str, Any], list]:
    """
    Constrói `$set` para remove-client (inclui PACOTE BP second_client clear).

    Returns:
        (update_data, remaining_client_ids)
    """
    current_client_ids = list(process.get("client_ids") or [])
    assert_client_on_process(current_client_ids, client_id)
    assert_not_primary_client(process, client_id)

    current_client_ids.remove(client_id)
    co_buyers = [
        cb for cb in (process.get("co_buyers") or [])
        if cb.get("client_id") != client_id
    ]

    update_data: dict[str, Any] = {
        "client_ids": current_client_ids,
        "co_buyers": co_buyers if co_buyers else None,
        "updated_at": now,
    }

    if process.get("second_client_id") == client_id:
        update_data["second_client_id"] = None
        update_data["second_client_name"] = None

    if co_buyers:
        update_data["titular2_data"] = {
            "name": co_buyers[0].get("name"),
            "email": co_buyers[0].get("email"),
            "nif": co_buyers[0].get("nif"),
            "phone": co_buyers[0].get("phone"),
        }
    else:
        update_data["titular2_data"] = None

    return update_data, current_client_ids


def format_add_client_response(
    client_name: Optional[str],
    *,
    as_co_titular: bool,
    total_clients: int,
) -> dict[str, Any]:
    nome = client_name or ""
    return {
        "success": True,
        "message": f"Cliente {nome} adicionado ao processo",
        "total_clients": total_clients,
    }


def format_remove_client_response(
    client_name: str,
    *,
    total_clients: int,
) -> dict[str, Any]:
    return {
        "success": True,
        "message": f"Cliente {client_name} removido do processo",
        "total_clients": total_clients,
    }


def resolve_process_client_ids(process: dict) -> list:
    """client_ids com fallback para client_id singular."""
    client_ids = process.get("client_ids", []) or []
    if client_ids:
        return list(client_ids)
    if process.get("client_id"):
        return [process.get("client_id")]
    return []


def build_process_client_info_row(
    client: dict,
    *,
    process: dict,
    co_buyer_ids: set,
) -> dict[str, Any]:
    cid = client.get("id")
    return {
        "id": cid,
        "nome": client.get("nome"),
        "email": client.get("contacto", {}).get("email"),
        "telefone": client.get("contacto", {}).get("telefone"),
        "nif": client.get("dados_pessoais", {}).get("nif"),
        "is_main": cid == process.get("client_id"),
        "relacao": "co-titular" if cid in co_buyer_ids else "titular",
    }


def build_process_clients_payload(
    *,
    process: dict,
    clients: list[dict],
) -> dict[str, Any]:
    co_buyers = process.get("co_buyers", []) or []
    co_buyer_ids = {cb.get("client_id") for cb in co_buyers if cb.get("client_id")}
    result = [
        build_process_client_info_row(
            c, process=process, co_buyer_ids=co_buyer_ids,
        )
        for c in clients
    ]
    return {
        "clients": result,
        "total": len(result),
        "process_id": process.get("id"),
        "process_number": process.get("process_number"),
    }


async def run_add_client_to_process(
    process_id: str,
    client_id: str,
    user: dict,
    *,
    as_co_titular: bool,
    inject_cdc_fn,
    log_history_fn,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    from fastapi import HTTPException

    from database import db

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    client = await db.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    now = datetime.now(timezone.utc).isoformat()
    update_data, current_client_ids = build_add_client_update(
        process, client, client_id, as_co_titular=as_co_titular, now=now,
    )

    inject_cdc_fn(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    await db.clients.update_one(
        {"id": client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {"updated_at": now},
        },
    )
    await log_history_fn(
        process_id, user,
        f"Adicionou cliente {client.get('nome')} ao processo"
        + (" como co-titular" if as_co_titular else ""),
    )
    return format_add_client_response(
        client.get("nome"),
        as_co_titular=as_co_titular,
        total_clients=len(current_client_ids),
    )


async def run_remove_client_from_process(
    process_id: str,
    client_id: str,
    user: dict,
    *,
    inject_cdc_fn,
    log_history_fn,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    from fastapi import HTTPException

    from database import db

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    now = datetime.now(timezone.utc).isoformat()
    update_data, current_client_ids = build_remove_client_update(
        process, client_id, now=now,
    )

    inject_cdc_fn(update_data, user)
    await db.processes.update_one({"id": process_id}, {"$set": update_data})
    await db.clients.update_one(
        {"id": client_id},
        {
            "$pull": {"process_ids": process_id},
            "$set": {"updated_at": now},
        },
    )

    client = await db.clients.find_one({"id": client_id})
    client_name = client.get("nome") if client else client_id
    await log_history_fn(
        process_id, user, f"Removeu cliente {client_name} do processo",
    )
    return format_remove_client_response(
        client_name, total_clients=len(current_client_ids),
    )


async def run_get_process_clients(process_id: str) -> dict[str, Any]:
    from fastapi import HTTPException

    from database import db

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    client_ids = resolve_process_client_ids(process)
    if not client_ids:
        return {"clients": [], "total": 0}

    clients = await db.clients.find(
        {"id": {"$in": client_ids}},
        {"_id": 0},
    ).to_list(length=10)
    return build_process_clients_payload(process=process, clients=clients)
