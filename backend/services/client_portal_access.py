"""POST /clients/{id}/resend-portal-access.

Extraído de `routes/clients.py`.
"""
from __future__ import annotations

import uuid
import logging
import asyncio
import copy
import re
import os
import unicodedata
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from database import db
from models.client import (
    Client, ClientCreate, ClientUpdate,
    ClientContact, ClientPersonalData,
    find_or_create_client_key,
    generate_portal_access_code,
)
from services.auth import get_effective_role
from models.auth import UserRole
from services.encryption import (
    encryption_service,
    encrypt_client_data,
    decrypt_client_data,
    decrypt_clients_list,
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
)
from services.process_service import get_next_process_number
from services.s3_storage import s3_service
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, sanitize_url, log_sanitization_rejection,
)
from utils.search_filters import create_accent_insensitive_regex, build_multiword_search_filter

logger = logging.getLogger(__name__)

async def run_resend_portal_access(
    client_id: str,
    request: Request,
    user: dict
):
    """
    Reenvia o email de acesso ao Portal para o cliente.

    Fluxo:
    1. Valida que o cliente existe e tem email.
    2. Encontra o primeiro processo ativo (não eliminado) do cliente.
    3. Delega para send_magic_link_email (processes.py) que:
       - Gera/refresh portal_access_code no cliente
       - Gera novo short_id + JWT
       - Envia email com magic link + Código de Acesso
    4. Devolve {portal_access_code, magic_link, short_id, process_id}.
    """
    from routes.processes import send_magic_link_email

    client = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    client_email = ""
    contacto = client.get("contacto") or {}
    if isinstance(contacto, dict):
        client_email = contacto.get("email", "")
    if not client_email:
        raise HTTPException(
            status_code=400,
            detail="Cliente não tem email associado — não é possível reenviar o acesso ao Portal."
        )

    process_ids = client.get("process_ids") or []
    if not process_ids:
        raise HTTPException(
            status_code=400,
            detail="Cliente não tem processo associado — crie um processo primeiro."
        )

    active_process = await db.processes.find_one(
        {"id": {"$in": process_ids}, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1}
    )
    if not active_process:
        raise HTTPException(
            status_code=404,
            detail="Cliente não tem processo ativo — todos foram eliminados."
        )

    process_id = active_process["id"]

    result = await send_magic_link_email(process_id=process_id, request=request, user=user)

    logger.info(
        f"[PACOTE-DC] Reenvio de acesso ao Portal para cliente {client_id} "
        f"(processo {process_id}) por {user.get('email')}"
    )

    return {
        "success": True,
        "process_id": process_id,
        "portal_access_code": result.get("portal_access_code") if isinstance(result, dict) else None,
        "magic_link": result.get("magic_link") if isinstance(result, dict) else None,
        "short_id": result.get("short_id") if isinstance(result, dict) else None,
        "message": "Email de acesso ao Portal reenviado com sucesso.",
    }
