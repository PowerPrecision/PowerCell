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
