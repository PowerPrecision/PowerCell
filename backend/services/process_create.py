"""
Helpers para POST /processes/create-client.

Extraído de `routes/processes.py` (`create_client_process`) — resolução
de status inicial, carga do cliente, construção do doc, docs portal e
link cliente↔processo.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from models.auth import UserRole
from services.encryption import decrypt_client_data

logger = logging.getLogger(__name__)


async def resolve_initial_workflow_status(*, is_lead: bool) -> tuple[Optional[str], Optional[str]]:
    """
    Devolve (initial_status, default_status).

    Lead → (None, default). Caso contrário → (1ª fase do workflow, default).
    """
    first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
    default_status = first_status["name"] if first_status else None

    if is_lead:
        logger.info("[CREATE-PROCESS] is_lead=True → status vazio (Lead / Registos de Clientes)")
        return None, default_status

    if default_status:
        logger.info(f"[CREATE-PROCESS] status inicial = 1ª fase real do workflow: {default_status}")
    else:
        logger.warning(
            "[CREATE-PROCESS] workflow_statuses vazio — status inicial = None (sem fases configuradas)"
        )
    return default_status, default_status


async def load_existing_client_for_process(client_id: str) -> dict[str, Any]:
    """
    Carrega e desencripta o cliente. Exige email para o portal.

    Returns:
        dict com keys: client_id, client_name, client_email, client_phone, client_nif
    """
    existing_client = await db.clients.find_one({"id": client_id})
    if not existing_client:
        raise HTTPException(
            status_code=404,
            detail=f"Cliente com ID '{client_id}' não encontrado. "
                   "Verifique se o cliente existe na base de dados.",
        )

    decrypted = decrypt_client_data(existing_client)
    client_name = decrypted.get("nome", "") or ""
    client_email = decrypted.get("contacto", {}).get("email", "") or ""
    client_phone = decrypted.get("contacto", {}).get("telefone", "") or ""
    nif_val = decrypted.get("dados_pessoais", {}).get("nif", "")
    client_nif = nif_val if nif_val else None

    if not client_email or not str(client_email).strip():
        raise HTTPException(
            status_code=400,
            detail="O e-mail é obrigatório para a criação do Portal do Cliente. "
                   "Adicione um e-mail de contacto ao cliente antes de criar o processo.",
        )

    logger.info(f"Cliente existente usado via client_id: {client_id}")
    return {
        "client_id": existing_client["id"],
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "client_nif": client_nif,
    }


def build_staff_process_doc(
    *,
    process_id: str,
    process_number: str,
    now: str,
    client_id: str,
    client_name: str,
    client_email: str,
    client_phone: str,
    client_nif: Optional[str],
    process_type: Any,
    initial_status: Optional[str],
    is_lead: bool,
) -> dict[str, Any]:
    """Documento base do processo criado por staff (antes de 2º titular / role)."""
    return {
        "id": process_id,
        "process_number": process_number,
        "client_ids": [client_id] if client_id else [],
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "client_nif": client_nif,
        "process_type": process_type,
        "status": initial_status,
        "is_active": True,
        "real_estate_data": None,
        "credit_data": None,
        "created_at": now,
        "updated_at": now,
        "source": "lead" if is_lead else "staff_created",
    }


def apply_creator_role_assignment(process_doc: dict, user: dict) -> None:
    """Atribui mediador/consultor ao criador (mutação in-place)."""
    if user["role"] == UserRole.INTERMEDIARIO:
        process_doc["assigned_mediador_id"] = user["id"]
        process_doc["mediador_name"] = user["name"]
    elif user["role"] in [UserRole.CONSULTOR, UserRole.DIRETOR]:
        process_doc["assigned_consultor_id"] = user["id"]
        process_doc["consultor_name"] = user["name"]
        process_doc["consultor_id"] = user["id"]


async def attach_second_client_on_create(
    process_doc: dict,
    second_client_id: Optional[str],
    primary_client_id: str,
) -> Optional[str]:
    """
    Injeta 2º titular no process_doc se o cliente existir.
    Returns second_client_id ou None.
    """
    if not second_client_id:
        return None
    second_client_id_clean = second_client_id.strip()
    if not second_client_id_clean or second_client_id_clean == primary_client_id:
        return None

    second_client = await db.clients.find_one({"id": second_client_id_clean})
    if not second_client:
        logger.warning(
            f"[CREATE-PROCESS] second_client_id {second_client_id_clean} "
            f"não encontrado — a ignorar 2º titular na criação."
        )
        return None

    process_doc["second_client_id"] = second_client_id_clean
    process_doc["second_client_name"] = second_client.get("nome", "")
    if second_client_id_clean not in process_doc["client_ids"]:
        process_doc["client_ids"].append(second_client_id_clean)
    logger.info(
        f"[CREATE-PROCESS] 2º titular associado na criação: "
        f"{second_client_id_clean} ({second_client.get('nome', '')})"
    )
    return second_client_id_clean


async def create_default_portal_documents(process_id: str, requested_by: dict) -> int:
    """Cria pedidos de documentos padrão do portal. Returns count inserted."""
    try:
        from routes.portal import DEFAULT_PENDING_CATEGORIES, DOCUMENT_CATEGORY_MAP
        now_iso = datetime.now(timezone.utc).isoformat()
        default_docs = []
        for cat_key in DEFAULT_PENDING_CATEGORIES:
            default_docs.append({
                "id": str(uuid.uuid4()),
                "process_id": process_id,
                "category": cat_key,
                "label": DOCUMENT_CATEGORY_MAP.get(cat_key, {}).get("label", cat_key),
                "filename": None,
                "original_filename": None,
                "s3_key": None,
                "status": "REQUESTED",
                "notes": "",
                "source": "auto_default",
                "requested_by": requested_by["id"],
                "requested_by_name": requested_by.get("name", "Sistema"),
                "created_at": now_iso,
                "updated_at": now_iso,
            })
        if default_docs:
            await db.documents.insert_many(default_docs)
            logger.info(f"Criados {len(default_docs)} documentos padrão para processo {process_id}")
            return len(default_docs)
    except Exception as e:
        logger.warning(f"Erro ao criar documentos padrão para processo {process_id}: {e}")
    return 0


async def link_clients_after_process_create(
    process_id: str,
    client_id: str,
    second_client_id: Optional[str],
    *,
    is_lead: bool,
    now: str,
) -> None:
    """Actualiza process_ids (+ lead_status) do titular e do 2º titular."""
    if client_id:
        client_set = {"updated_at": now}
        client_set["lead_status"] = "new" if is_lead else "converted"
        await db.clients.update_one(
            {"id": client_id},
            {
                "$addToSet": {"process_ids": process_id},
                "$set": client_set,
            },
        )

    if not second_client_id:
        return
    try:
        await db.clients.update_one(
            {"id": second_client_id},
            {
                "$addToSet": {"process_ids": process_id},
                "$set": {"updated_at": now},
            },
        )
        logger.info(
            f"[CREATE-PROCESS] process_ids do 2º titular "
            f"{second_client_id} atualizado com processo {process_id}"
        )
    except Exception as e:
        logger.warning(
            f"[CREATE-PROCESS] Erro ao atualizar process_ids do 2º titular "
            f"{second_client_id}: {e}"
        )


def assert_can_create_staff_process(role: str) -> None:
    """Roles permitidos em POST /create-client."""
    allowed = [
        UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
        UserRole.INTERMEDIARIO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR,
    ]
    if role not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Não tem permissão para criar clientes/processos.",
        )


def assert_client_id_required(client_id: Optional[str]) -> None:
    """client_id obrigatório para criar processo staff."""
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "É obrigatório associar um cliente existente para criar um processo. "
                "Selecione um cliente na listagem antes de criar o processo."
            ),
        )


async def maybe_auto_assign_indexer_on_create(
    process_id: str,
    process_doc: dict,
    *,
    is_lead: bool,
    initial_status: Optional[str],
) -> None:
    """Auto-atribui indexador (excepto leads). Mutação opcional de process_doc."""
    try:
        if is_lead:
            logger.info(
                f"[CREATE-PROCESS] is_lead=True — a saltar auto-atribuição de "
                f"indexador para processo {process_id} (Lead)"
            )
            return
        from services.process_assignment import assign_to_indexer
        assign_success, assign_data, assign_msg = await assign_to_indexer(
            process_id, update_status=False,
        )
        if assign_success and assign_data.get("assigned"):
            logger.info(
                f"[CREATE-PROCESS] Indexador auto-atribuído: "
                f"{assign_data.get('indexacao_name')} para processo {process_id} "
                f"(status mantém: {initial_status})"
            )
            process_doc["assigned_indexacao_id"] = assign_data.get("assigned_indexacao_id")
            process_doc["indexacao_name"] = assign_data.get("indexacao_name")
        else:
            logger.warning(
                f"[CREATE-PROCESS] Sem indexador disponível para processo "
                f"{process_id}: {assign_msg} (status mantém: {initial_status})"
            )
    except Exception as e:
        logger.warning(
            f"[CREATE-PROCESS] Erro na auto-atribuição de indexador "
            f"para processo {process_id}: {e}"
        )


def build_create_broadcast_names(user: dict) -> tuple[list, list]:
    """Nomes consultor/mediador para broadcast PROCESS_CREATED."""
    consultor_names = (
        [user["name"]]
        if user["role"] in [UserRole.CONSULTOR, UserRole.DIRETOR]
        else []
    )
    mediador_names = (
        [user["name"]] if user["role"] == UserRole.INTERMEDIARIO else []
    )
    return consultor_names, mediador_names


def assert_is_cliente_role(role: str) -> None:
    """POST /processes (self-service) só para role CLIENTE."""
    if role != UserRole.CLIENTE:
        raise HTTPException(
            status_code=403,
            detail="Apenas clientes podem criar processos",
        )


async def load_client_doc_or_404(client_id: Optional[str]) -> dict[str, Any]:
    """Carrega cliente por id ou 404."""
    if not client_id:
        raise HTTPException(
            status_code=404,
            detail="Cliente com ID '' não encontrado. "
                   "O processo deve estar associado a um cliente existente.",
        )
    client_doc = await db.clients.find_one({"id": client_id})
    if not client_doc:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Cliente com ID '{client_id}' não encontrado. "
                "O processo deve estar associado a um cliente existente."
            ),
        )
    return client_doc


def build_client_self_process_doc(
    *,
    process_id: str,
    process_number: Any,
    client_id: str,
    process_type: Any,
    initial_status: Optional[str],
    now: str,
) -> dict[str, Any]:
    """Documento base do processo criado pelo próprio cliente."""
    return {
        "id": process_id,
        "process_number": process_number,
        "client_id": client_id,
        "process_type": process_type,
        "status": initial_status,
        "is_active": True,
        "real_estate_data": None,
        "credit_data": None,
        "assigned_consultor_id": None,
        "assigned_mediador_id": None,
        "created_at": now,
        "updated_at": now,
    }


async def link_single_client_to_process(
    process_id: str,
    client_id: str,
    *,
    now: str,
) -> None:
    """$addToSet process_ids no cliente após self-create."""
    await db.clients.update_one(
        {"id": client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {"updated_at": now},
        },
    )
    logger.info(
        f"Processo {process_id} criado e associado ao cliente {client_id}"
    )
