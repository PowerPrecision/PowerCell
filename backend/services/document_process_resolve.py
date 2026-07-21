"""
Resolve ID flexível (processo OU cliente) → documento de processo.

Extraído da lógica duplicada em list/upload/download/delete de `routes/documents.py`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.document_constants import (
    ERROR_CLIENT_NOT_FOUND,
    ERROR_CLIENT_WITHOUT_PROCESS,
)

logger = logging.getLogger(__name__)


async def resolve_process_from_flexible_id(
    flexible_id: str,
    *,
    log_prefix: str = "[DOCS]",
    allow_client_without_process: bool = False,
    raise_on_client_without_process: bool = True,
    client_without_process_detail: Optional[str] = None,
) -> tuple[Optional[dict], Optional[str]]:
    """
    Resolve `flexible_id` para (process, effective_process_id).

    Ordem:
    1. processes.id
    2. clients.id → process_ids[0] / processes.client_id
    3. processes.client_id directo

    Returns:
        (process, effective_id)

    Raises:
        HTTPException(404) se não encontrado (ou cliente sem processo quando
        `raise_on_client_without_process` e não `allow_client_without_process`).

    Quando `allow_client_without_process=True` e o cliente existe sem processo:
        devolve (None, None) sem raise.
    """
    without_process_detail = (
        client_without_process_detail or ERROR_CLIENT_WITHOUT_PROCESS
    )

    process = await db.processes.find_one({"id": flexible_id})
    if process:
        logger.debug(f"{log_prefix} Encontrado processo por ID: {flexible_id}")
        return process, process["id"]

    client = await db.clients.find_one({"id": flexible_id})
    if client:
        logger.debug(f"{log_prefix} Encontrado cliente por ID: {flexible_id}")
        process_ids = client.get("process_ids", []) or []
        if process_ids:
            process = await db.processes.find_one({"id": process_ids[0]})
            if process:
                logger.debug(
                    f"{log_prefix} Processo encontrado via process_ids: {process['id']}"
                )
                return process, process["id"]

        process = await db.processes.find_one({"client_id": flexible_id})
        if process:
            logger.debug(
                f"{log_prefix} Processo encontrado via client_id: {process['id']}"
            )
            return process, process["id"]

        if allow_client_without_process:
            logger.info(
                f"{log_prefix} Cliente {flexible_id} existe mas sem processo associado"
            )
            return None, None

        if raise_on_client_without_process:
            raise HTTPException(status_code=404, detail=without_process_detail)

    process = await db.processes.find_one({"client_id": flexible_id})
    if process:
        logger.debug(
            f"{log_prefix} Processo encontrado via client_id (fallback): {process['id']}"
        )
        return process, process["id"]

    logger.warning(
        f"{log_prefix} Nenhum processo ou cliente encontrado para ID: {flexible_id}"
    )
    raise HTTPException(status_code=404, detail=ERROR_CLIENT_NOT_FOUND)


def extract_second_client_name(process: dict) -> Optional[str]:
    """Nome do 2º titular a partir do process doc."""
    titular2 = process.get("titular2_data") or {}
    return (
        process.get("second_client_name")
        or titular2.get("nome")
        or titular2.get("name")
    )


def assert_s3_file_belongs_to_process(file_path: str, process: dict) -> None:
    """
    Garante que `file_path` pertence ao prefixo S3 do processo.

    Raises:
        HTTPException(403) se o path estiver fora do scope do cliente/processo.
    """
    from services.s3_storage import sanitize_folder_name
    from services.document_constants import ERROR_FILE_ACCESS_DENIED

    s3_folder = process.get("s3_folder")
    if s3_folder:
        s3_prefix = s3_folder.rstrip("/")
        if not file_path.startswith(f"{s3_prefix}/"):
            raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)
        return

    client_name = process.get("client_name", "") or ""
    safe_name = sanitize_folder_name(client_name) if client_name else ""
    clean_name = client_name.strip() if client_name else ""
    valid_prefixes = [
        f"Documentação Clientes/{clean_name}",
        f"Documentação Clientes/{safe_name}",
    ]
    if not any(file_path.startswith(prefix) for prefix in valid_prefixes):
        raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)


def build_s3_valid_prefixes(process: dict) -> list[str]:
    """Prefixos S3 válidos para um processo (batch delete / list checks)."""
    from services.s3_storage import sanitize_folder_name

    s3_folder = process.get("s3_folder")
    if s3_folder:
        return [f"{s3_folder.rstrip('/')}/"]

    client_name = process.get("client_name", "") or ""
    safe_name = sanitize_folder_name(client_name) if client_name else ""
    clean_name = client_name.strip() if client_name else ""
    return [
        f"Documentação Clientes/{clean_name}",
        f"Documentação Clientes/{safe_name}",
    ]
