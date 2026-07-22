"""Upload/download de documentos no Portal do Cliente.

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from services.s3_storage import s3_service
from services.portal_assigned_users import get_all_assigned_user_ids as _get_all_assigned_user_ids
from services.portal_onboarding_advance import _trigger_onboarding_check
from services.notification_service import send_notification_with_preference_check
from services.redis_cache import invalidate_stats_cache

logger = logging.getLogger(__name__)


async def _create_document_record(
    doc_id: str,
    process_id: Optional[str],
    file_key: str,
    original_filename: str,
    category: str,
    file_size: int,
    content_type: str,
    now: str,
    custom_label: str = None,
    client_id: Optional[str] = None,
):
    """Cria um registo de documento na BD com status RECEIVED."""
    document = {
        "id": doc_id,
        "process_id": process_id,
        "filename": original_filename,
        "original_filename": original_filename,
        "category": category,
        "file_size": file_size,
        "content_type": content_type,
        "s3_path": file_key,
        "status": "RECEIVED",
        "uploaded_at": now,
        "uploaded_by": "portal_client",
        "source": "client_portal",
        "reviewed_by": "portal_client",
        "reviewed_at": now,
    }
    if client_id:
        document["client_id"] = client_id
    if custom_label:
        document["custom_label"] = custom_label
    await db.documents.insert_one(document)


async def _notify_assigned_team_upload(process: dict, filename: str, category: str):
    """Notifica TODOS os utilizadores atribuídos ao processo sobre um novo upload do cliente."""
    assigned_ids = _get_all_assigned_user_ids(process)
    if not assigned_ids:
        return

    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process.get("id", "")[:8]
    
    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if user:
                await send_notification_with_preference_check(
                    user.get("email"),
                    "Novo Documento Submetido",
                    f"O cliente {client_name} submeteu '{filename}' ({category}) no processo {process_ref} via Portal.",
                    notification_type="document_upload"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar utilizador {uid} sobre upload: {e}")


async def run_generate_portal_upload_url(data: dict, client_data: dict):
    """
    Gera uma pre-signed URL para upload direto ao S3.

    Suporta cliente sem processo (onboarding): usa pasta S3 do cliente.
    Com processo: usa pasta do processo. Categoria forçada a Index.
    """
    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Serviço de armazenamento indisponível. Contacte o seu consultor."
        )

    process = client_data.get("process")
    client = client_data.get("client") or {}
    client_id = client_data.get("client_id") or (process or {}).get("client_id")
    process_id = process["id"] if process else None

    filename = data.get("filename", "")
    content_type = data.get("content_type", "application/octet-stream")
    category = data.get("category", "Outros")

    if category != "Index":
        logger.info(
            f"[PORTAL-PACOTE-BL] generate_upload_url: categoria original "
            f"'{category}' forçada para 'Index'. ficheiro={filename}"
        )
    category = "Index"

    if not filename:
        raise HTTPException(status_code=400, detail="Nome do ficheiro é obrigatório")

    safe_filename = filename.replace(" ", "_").replace("/", "-").replace("\\", "-")

    if process:
        storage_id = process_id
        client_name = process.get("client_name") or client.get("nome") or "cliente"
        s3_folder = process.get("s3_folder")
    else:
        if not client_id:
            raise HTTPException(
                status_code=400,
                detail="Sem cliente associado. Não é possível fazer upload.",
            )
        storage_id = client_id
        client_name = client.get("nome") or "cliente"
        s3_folder = client.get("s3_folder")

    result = s3_service.generate_upload_presigned_url(
        client_id=storage_id,
        client_name=client_name,
        category=category,
        filename=safe_filename,
        content_type=content_type,
        s3_folder=s3_folder,
        expiration=300
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar link de upload. Tente novamente."
        )

    logger.info(
        f"[PORTAL] Upload URL gerada para {safe_filename} "
        f"(process={process_id or 'none'}, client={client_id}, cat: {category})"
    )

    return {
        "success": True,
        "upload_url": result["upload_url"],
        "file_key": result["file_key"],
        "expires_at": result["expires_at"],
        "expires_in_seconds": result["expires_in_seconds"],
        "method": "PUT",
        "headers": {"Content-Type": content_type},
    }


async def run_confirm_portal_upload(data: dict, client_data: dict):
    """
    Confirma upload para S3 e regista na base de dados.

    Sem processo: ancora ao client_id (órfão) até checklist completa criar o processo.
    Com processo: ancora ao process_id. Categoria forçada a Index.
    """
    import uuid

    process = client_data.get("process")
    client = client_data.get("client") or {}
    token_payload = client_data.get("token_payload", {})
    client_id = (
        client_data.get("client_id")
        or token_payload.get("client_id")
        or (process or {}).get("client_id")
        or client.get("id")
    )
    process_id = process["id"] if process else None

    file_key = data.get("file_key")
    original_filename = data.get("original_filename")
    category = data.get("category", "Outros")
    file_size = data.get("file_size")
    content_type = data.get("content_type", "application/octet-stream")
    document_id = data.get("document_id")
    custom_label = data.get("custom_label")

    original_category_from_client = category
    category = "Index"
    if original_category_from_client and original_category_from_client != "Index":
        logger.info(
            f"[PORTAL-PACOTE-BL] Upload forçado para Index "
            f"(original={original_category_from_client}, file={original_filename})"
        )

    ai_categorization_info = None

    if not file_key:
        raise HTTPException(status_code=400, detail="file_key é obrigatório")
    if not original_filename:
        raise HTTPException(status_code=400, detail="original_filename é obrigatório")
    if not client_id and not process_id:
        raise HTTPException(status_code=400, detail="Sem cliente/processo associado")

    if not s3_service.file_exists(file_key):
        raise HTTPException(
            status_code=400,
            detail="Ficheiro não encontrado. O upload pode ter falhado. Tente novamente."
        )

    now = datetime.now(timezone.utc).isoformat()

    # Satisfazer pedido REQUESTED (por process_id OU client_id)
    if document_id:
        match_q = {"id": document_id}
        if process_id:
            match_q["process_id"] = process_id
        elif client_id:
            match_q["client_id"] = client_id

        update_fields = {
            "status": "RECEIVED",
            "filename": original_filename,
            "original_filename": original_filename,
            "file_size": file_size,
            "content_type": content_type,
            "s3_path": file_key,
            # Mantém category do pedido (checklist); ficheiro físico está em Index via S3 path
            "storage_category": "Index",
            "uploaded_at": now,
            "uploaded_by": "portal_client",
            "reviewed_by": "portal_client",
            "reviewed_at": now,
            "updated_at": now,
        }
        if client_id:
            update_fields["client_id"] = client_id
        if process_id:
            update_fields["process_id"] = process_id

        update_result = await db.documents.update_one(match_q, {"$set": update_fields})

        if update_result.matched_count > 0:
            doc_id = document_id
            logger.info(f"[PORTAL] Doc REQUESTED → RECEIVED: {document_id}")
        else:
            doc_id = str(uuid.uuid4())
            await _create_document_record(
                doc_id, process_id, file_key, original_filename,
                category, file_size, content_type, now, client_id=client_id
            )
    else:
        doc_id = str(uuid.uuid4())
        await _create_document_record(
            doc_id, process_id, file_key, original_filename,
            category, file_size, content_type, now, custom_label, client_id=client_id
        )

    await invalidate_stats_cache()

    if process_id:
        try:
            from services.history import log_history
            client_name = (process or {}).get("client_name") or client.get("nome") or "Cliente"
            await log_history(
                process_id,
                user={"id": None, "name": f"{client_name} (Portal)", "role": "client_portal"},
                action="DOCUMENT_UPLOADED_BY_CLIENT",
                field="documento",
                old_value=None,
                new_value=f"{original_filename} [{category}]"
            )
        except Exception as e:
            logger.warning(f"[PORTAL] Erro ao registar histórico de upload: {e}")

        await _notify_assigned_team_upload(process, original_filename, category)

    temporary_url = s3_service.get_presigned_url(file_key) or ""

    # Gatilho onboarding (criar processo se checklist completa)
    try:
        if client_id:
            asyncio.create_task(_trigger_onboarding_check(client_id))
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao agendar verificação de onboarding: {e}")

    if process_id:
        try:
            from services.portal_documents_notify import check_and_notify_documents_complete
            company_id = process.get("company") or process.get("company_id")
            asyncio.create_task(check_and_notify_documents_complete(process_id, company_id))
        except Exception as e:
            logger.warning(f"[PORTAL] Erro ao agendar gatilho de documentação completa: {e}")

    logger.info(
        f"[PORTAL] Upload confirmado: {original_filename} "
        f"(process={process_id or 'none'}, client={client_id})"
    )

    return {
        "success": True,
        "document_id": doc_id,
        "filename": original_filename,
        "category": category,
        "s3_path": file_key,
        "temporary_url": temporary_url,
        "ai_categorization": ai_categorization_info,
        "process_id": process_id,
        "client_id": client_id,
    }


async def run_get_portal_download_url(file_key: str, client_data: dict):
    """
    Gera uma pre-signed URL para download de um documento do processo do cliente.

    SEGURANÇA:
    - Requer autenticação via token do portal
    - Valida que o ficheiro pertence ao processo do cliente (escopo do token)
    - URL temporária com validade de 1 hora
    - Bloqueia acesso a ficheiros de outros processos

    Query Params:
    - file_key: Caminho S3 do ficheiro (obrigatório)
    """
    if not file_key:
        raise HTTPException(status_code=400, detail="file_key é obrigatório.")

    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Serviço de armazenamento indisponível."
        )

    # ── Validação de segurança: o ficheiro deve pertencer ao processo do cliente ──
    process = client_data.get("process")
    if not process:
        raise HTTPException(
            status_code=403,
            detail="Sem processo associado. Não é possível descarregar documentos."
        )

    process_id = process["id"]

    # Verificar se o documento existe na BD e pertence a este processo
    doc = await db.documents.find_one(
        {"s3_path": file_key, "process_id": process_id},
        {"_id": 0, "id": 1, "s3_path": 1}
    )

    # Fallback: verificar por file_key se s3_path não existir
    if not doc:
        doc = await db.documents.find_one(
            {"file_key": file_key, "process_id": process_id},
            {"_id": 0, "id": 1, "s3_path": 1}
        )

    if not doc:
        # Tentativa de acesso a ficheiro de outro processo — negar
        logger.warning(
            f"[PORTAL DOWNLOAD] Acesso negado: file_key={file_key} "
            f"não pertence ao processo {process_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="Ficheiro não encontrado ou sem permissão de acesso."
        )

    # Verificar se o ficheiro existe no S3
    if not s3_service.file_exists(file_key):
        raise HTTPException(
            status_code=404,
            detail="Ficheiro não encontrado no armazenamento."
        )

    # Gerar URL pré-assinada (válida por 1 hora)
    presigned_url = s3_service.get_presigned_url(file_key, expiration=3600)

    if not presigned_url:
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar link de download."
        )

    logger.info(
        f"[PORTAL DOWNLOAD] Download autorizado: file_key={file_key} "
        f"para processo {process_id}"
    )

    return {
        "success": True,
        "url": presigned_url,
        "expires_in": 3600,
    }


