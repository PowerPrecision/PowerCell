"""
Onboarding via SystemConfig `mandatory_documents` (sem listas hardcoded).

Fluxo desejado:
1. Registo público → cliente + pedidos REQUESTED (client_id, sem process_id)
2. Cliente carrega docs no portal → orphans em pasta Index
3. Quando não restam REQUESTED/PENDING do checklist → criar processo
   (copia titular2 do cliente) + ancorar docs + avançar para Index
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)


async def count_pending_mandatory_requests(
    *,
    client_id: Optional[str] = None,
    process_id: Optional[str] = None,
) -> int:
    """Conta pedidos REQUESTED/PENDING do checklist SystemConfig."""
    query: dict[str, Any] = {
        "source": "mandatory_checklist",
        "status": {"$in": ["REQUESTED", "PENDING", "requested", "pending"]},
    }
    if process_id:
        query["process_id"] = process_id
    elif client_id:
        query["client_id"] = client_id
        query["$or"] = [
            {"process_id": None},
            {"process_id": ""},
            {"process_id": {"$exists": False}},
        ]
    else:
        return 0
    return await db.documents.count_documents(query)


async def is_mandatory_checklist_complete(
    *,
    client_id: Optional[str] = None,
    process_id: Optional[str] = None,
) -> bool:
    """True quando não há pedidos obrigatórios pendentes (SystemConfig)."""
    # Sem pedidos gerados → não completo (evita criar processo sem checklist)
    gen_query: dict[str, Any] = {"source": "mandatory_checklist"}
    if process_id:
        gen_query["process_id"] = process_id
    elif client_id:
        gen_query["client_id"] = client_id
    else:
        return False

    total = await db.documents.count_documents(gen_query)
    if total == 0:
        return False
    pending = await count_pending_mandatory_requests(
        client_id=client_id, process_id=process_id
    )
    return pending == 0


async def create_process_from_client_onboarding(client_id: str) -> dict[str, Any]:
    """
    Cria processo após checklist SystemConfig completa.

    - Copia dados do cliente
    - Define 2.º titular a partir de `clients.titular2_data` (se existir)
    - Ancora docs órfãos (client_id, sem process_id) — mantém category Index
    - Marca lead_status=converted
    """
    from services.process_service import get_next_process_number
    from services.encryption import decrypt_client_data

    client = await db.clients.find_one({"id": client_id})
    if not client:
        return {"completed": False, "error": "client_not_found"}

    # Idempotência: se já tem processo activo de onboarding, não duplicar
    existing_ids = client.get("process_ids") or []
    if existing_ids:
        existing = await db.processes.find_one(
            {
                "id": {"$in": existing_ids},
                "is_deleted": {"$ne": True},
                "fonte": {"$in": ["public_form", "onboarding_auto"]},
            },
            {"_id": 0, "id": 1, "process_number": 1},
        )
        if existing:
            return {
                "completed": True,
                "already_existed": True,
                "process_id": existing["id"],
                "process_number": existing.get("process_number"),
                "anchored_docs": 0,
            }

    try:
        decrypted = decrypt_client_data(client)
    except Exception:
        decrypted = client

    now = datetime.now(timezone.utc).isoformat()
    process_id = str(uuid.uuid4())
    next_number = await get_next_process_number()

    client_name = decrypted.get("nome") or client.get("nome") or "Cliente"
    contacto = decrypted.get("contacto") or {}
    dados_pessoais = decrypted.get("dados_pessoais") or {}
    client_email = contacto.get("email") or dados_pessoais.get("email")
    client_phone = contacto.get("telefone") or dados_pessoais.get("telefone")

    personal_data = dict(dados_pessoais) if isinstance(dados_pessoais, dict) else {}
    if client_email and not personal_data.get("email"):
        personal_data["email"] = client_email
    if client_phone and not personal_data.get("telefone"):
        personal_data["telefone"] = client_phone
    if client_name and not personal_data.get("nome"):
        personal_data["nome"] = client_name

    s3_folder = client.get("s3_folder")
    pending_type = client.get("pending_process_type") or "credito_habitacao"
    titular2 = client.get("titular2_data") or {}

    process_doc: dict[str, Any] = {
        "id": process_id,
        "process_number": next_number,
        "client_id": client_id,
        "client_ids": [client_id],
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "process_type": pending_type,
        "type": pending_type,
        "status": None,  # Lead — avança após criação via portal_onboarding_advance
        "workflow_step": None,
        "is_active": True,
        "is_deleted": False,
        "personal_data": personal_data,
        "financial_data": client.get("dados_financeiros") or {},
        "real_estate_data": client.get("pending_real_estate_data")
        or client.get("dados_imobiliarios")
        or {},
        "credit_data": {},
        "s3_folder": s3_folder,
        "has_property": bool(client.get("has_property")),
        "fonte": "public_form",
        "source": "onboarding_auto",
        "created_at": now,
        "updated_at": now,
        "created_by": "onboarding_auto",
    }

    # 2.º titular: marcado no processo na criação (dados já no cliente desde o form)
    if isinstance(titular2, dict) and (
        titular2.get("name") or titular2.get("nome") or titular2.get("email")
    ):
        process_doc["titular2_data"] = titular2
        t2_name = titular2.get("name") or titular2.get("nome")
        if t2_name:
            process_doc["second_client_name"] = t2_name
        # Ligar second_client_id se já existir cliente criado para o 2.º titular
        second_id = client.get("pending_second_client_id") or titular2.get("client_id")
        if second_id:
            process_doc["second_client_id"] = second_id
            if second_id not in process_doc["client_ids"]:
                process_doc["client_ids"].append(second_id)

    await db.processes.insert_one(process_doc)

    # Ancorar docs órfãos + pedidos REQUESTED do cliente
    anchor_filter = {
        "client_id": client_id,
        "$or": [
            {"process_id": None},
            {"process_id": ""},
            {"process_id": {"$exists": False}},
        ],
    }
    anchor_result = await db.documents.update_many(
        anchor_filter,
        {"$set": {"process_id": process_id, "updated_at": now}},
    )
    anchored = anchor_result.modified_count if anchor_result else 0

    await db.clients.update_one(
        {"id": client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {
                "updated_at": now,
                "lead_status": "converted",
            },
        },
    )

    # Re-key portal_tokens para o process_id (links antigos continuam a resolver)
    try:
        await db.portal_tokens.update_many(
            {"client_id": client_id},
            {"$set": {"process_id": process_id, "updated_at": datetime.now(timezone.utc)}},
        )
    except Exception as e:
        logger.warning(f"[ONBOARDING-CFG] Falha ao actualizar portal_tokens: {e}")

    logger.info(
        f"[ONBOARDING-CFG] Processo {process_id} (PROC-{next_number:04d}) criado "
        f"para cliente {client_id}; {anchored} docs ancorados; "
        f"titular2={'yes' if process_doc.get('titular2_data') else 'no'}"
    )

    return {
        "completed": True,
        "process_id": process_id,
        "process_number": next_number,
        "anchored_docs": anchored,
        "has_titular2": bool(process_doc.get("titular2_data")),
    }
