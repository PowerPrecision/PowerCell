"""
====================================================================
MAPEAMENTO S3 NA CRIAÇÃO — POWERCELL CRM (PACOTE 9)
====================================================================

Helpers que garantem que o mapeamento de pasta S3 (``s3_folder``) é
criado/recuperado e persistido **no momento exacto** em que um cliente
ou um processo nasce na base de dados.

CONTEXTO (bug reportado — Pacote 9):
- O hook FQ-3 cobria apenas o ``POST /clients`` (``client_crud.py``).
- O ``POST /processes/create-client`` (fluxo staff principal — todo o
  "Novo Cliente" passa por aqui) inseria o processo SEM qualquer
  mapeamento S3: a pasta só surgia de forma lazy no primeiro upload
  via Portal (``portal_upload_ops.py``).
- O ``POST /clients/{id}/assign`` gravava um ``s3_folder`` calculado
  com ``_get_client_base_path_for_upload`` — apenas uma string de path,
  SEM criar a estrutura de pastas no S3 (marcadores ``.keep``) e SEM
  verificar pastas existentes (risco de duplicados), e sem backfill do
  próprio documento do cliente.

Este módulo centraliza a garantia em três pontos de criação:

    1. ``run_create_client``            (client_crud.py)      — clientes
    2. ``persist_and_finalize_staff_create`` (process_create.py) — processos staff
    3. ``run_assign_client_to_user``    (client_assign.py)    — processos de atribuição

REGRAS:
- Reutiliza sempre ``s3_service.ensure_client_folder_mapping`` — a mesma
  função robusta (match fuzzy por nome / reutilização de pasta existente
  / criação idempotente) usada em produção e pelo script de backfill.
- Persistência via ``$set`` estrito na chave ``s3_folder`` — nunca
  substitui o documento inteiro.
- Degradação graciosa: qualquer falha S3 é logada (warning) e NUNCA
  rebenta o fluxo de criação (o cliente/processo é sempre criado).
- ``boto3`` é síncrono → chamado via ``asyncio.to_thread`` para não
  bloquear o event loop.

Nota: ``client_name``/``second_client_name`` NÃO são encriptados em
repouso (ver ``process_service.encrypt_sensitive_data`` — apenas
nif/documento_id/phone/etc.), pelo que podem ser lidos directamente
do documento do processo.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from database import db
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


async def ensure_s3_mapping_for_entity(
    *,
    collection,
    entity_id: str,
    client_name: str,
    second_client_name: Optional[str] = None,
    existing_s3_folder: Optional[str] = None,
    extra_set: Optional[dict] = None,
    label: str = "entidade",
) -> dict[str, Any]:
    """
    Garante e persiste o ``s3_folder`` de UMA entidade (cliente ou processo).

    Args:
        collection: colecção Mongo (``db.clients`` / ``db.processes``).
        entity_id: id do documento.
        client_name: nome do 1º titular (plain-text).
        second_client_name: nome do 2º titular (opcional, plain-text).
        existing_s3_folder: mapeamento já gravado na BD (se existir).
        extra_set: campos extra para o ``$set`` (ex.: auditoria de backfill).
        label: rótulo para os logs.

    Returns:
        dict: {"success": bool, "s3_folder": str|None, "created": bool,
               "reused_existing": bool, "persisted": bool}
    """
    result: dict[str, Any] = {
        "success": False,
        "s3_folder": None,
        "created": False,
        "reused_existing": False,
        "persisted": False,
    }

    if not client_name or not str(client_name).strip():
        logger.warning(
            "[S3-ON-CREATE] %s %s sem nome válido — não é possível mapear pasta S3.",
            label, entity_id,
        )
        return result

    try:
        s3_mapping = await asyncio.to_thread(
            s3_service.ensure_client_folder_mapping,
            entity_id,
            client_name,
            second_client_name,
            existing_s3_folder,
        )
    except Exception as e:  # degradação graciosa — nunca rebenta a criação
        logger.warning(
            "[S3-ON-CREATE] Erro ao chamar ensure_client_folder_mapping para %s %s: %s",
            label, entity_id, e,
        )
        return result

    if not (s3_mapping.get("success") and s3_mapping.get("s3_folder")):
        logger.warning(
            "[S3-ON-CREATE] Não foi possível criar/recuperar mapeamento S3 "
            "para %s %s (%s)",
            label, entity_id, client_name,
        )
        return result

    folder = s3_mapping["s3_folder"]
    result.update(
        success=True,
        s3_folder=folder,
        created=bool(s3_mapping.get("created")),
        reused_existing=bool(s3_mapping.get("reused_existing")),
    )

    set_payload = {"s3_folder": folder}
    if extra_set:
        set_payload.update(extra_set)

    try:
        await collection.update_one({"id": entity_id}, {"$set": set_payload})
        result["persisted"] = True
        logger.info(
            "[S3-ON-CREATE] Mapeamento S3 %s para %s %s: %s",
            "criado" if result["created"] else "recuperado",
            label, entity_id, folder,
        )
    except Exception as e:
        logger.warning(
            "[S3-ON-CREATE] Erro ao persistir s3_folder para %s %s: %s",
            label, entity_id, e,
        )

    return result


async def ensure_s3_mapping_on_process_create(
    *,
    process_id: str,
    client_id: Optional[str],
    client_name: str,
    second_client_name: Optional[str] = None,
    process_existing_s3_folder: Optional[str] = None,
    client_collection=None,
    process_collection=None,
) -> dict[str, Any]:
    """
    Garante o mapeamento S3 no momento da criação de um PROCESSO staff.

    Fluxo (Pacote 9 — bug "clientes não ficam mapeados no S3"):
    1. Resolve/cria a pasta S3 a partir do nome do titular (+ 2º titular).
    2. Persiste ``s3_folder`` no documento do PROCESSO (``db.processes``).
    3. Backfill: se o documento do CLIENTE ainda não tiver ``s3_folder``,
       persiste-o também (cliente e processo partilham a mesma pasta).

    Por defeito usa as colecções canónicas (``database.db``); recebe
    opcionalmente colecções alternativas para injecção em testes.

    Returns:
        dict: {"success", "s3_folder", "process_persisted", "client_backfilled"}
    """
    clients = client_collection if client_collection is not None else db.clients
    processes = process_collection if process_collection is not None else db.processes

    outcome: dict[str, Any] = {
        "success": False,
        "s3_folder": None,
        "process_persisted": False,
        "client_backfilled": False,
    }

    # 1+2) Mapeamento + persistência no processo
    process_result = await ensure_s3_mapping_for_entity(
        collection=processes,
        entity_id=process_id,
        client_name=client_name,
        second_client_name=second_client_name,
        existing_s3_folder=process_existing_s3_folder,
        label="processo",
    )
    outcome["s3_folder"] = process_result.get("s3_folder")

    if not process_result.get("success"):
        return outcome

    outcome["success"] = True
    outcome["process_persisted"] = process_result.get("persisted", False)

    # 3) Backfill do cliente (se aplicável) — cliente e processo partilham
    #    a mesma pasta de documentação.
    if not client_id:
        return outcome

    try:
        # Nota: o "id" TEM de estar na projecção — sem campos projectados o
        # Motor devolve "{}" (falsy) e o backfill nunca executava.
        client_doc = await clients.find_one(
            {"id": client_id}, {"_id": 0, "id": 1, "s3_folder": 1}
        )
    except Exception as e:
        logger.warning(
            "[S3-ON-CREATE] Erro ao carregar cliente %s para backfill: %s",
            client_id, e,
        )
        return outcome

    if not client_doc or not client_doc.get("id"):
        return outcome

    existing = (client_doc.get("s3_folder") or "").strip()
    if existing and existing.lower() not in ("undefined", "null", "none"):
        return outcome  # cliente já tem mapeamento válido

    try:
        await clients.update_one(
            {"id": client_id},
            {"$set": {"s3_folder": outcome["s3_folder"]}},
        )
        outcome["client_backfilled"] = True
        logger.info(
            "[S3-ON-CREATE] Backfill do mapeamento S3 do cliente %s: %s",
            client_id, outcome["s3_folder"],
        )
    except Exception as e:
        logger.warning(
            "[S3-ON-CREATE] Erro ao persistir backfill S3 do cliente %s: %s",
            client_id, e,
        )

    return outcome
