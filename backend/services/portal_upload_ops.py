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


async def _create_document_record(doc_id: str, process_id: str, file_key: str, original_filename: str, category: str, file_size: int, content_type: str, now: str, custom_label: str = None):
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

    O cliente só pode fazer upload para o seu próprio processo.
    Usa a mesma lógica de S3 que o staff (s3_storage.py).

    Body:
    - filename: Nome original (obrigatório)
    - content_type: MIME type (obrigatório)
    - category: Categoria do documento (obrigatório)
    - document_id: ID do doc REQUESTED que este upload satisfaz (opcional)
    """
    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Serviço de armazenamento indisponível. Contacte o seu consultor."
        )

    process = client_data["process"]
    process_id = process["id"]

    filename = data.get("filename", "")
    content_type = data.get("content_type", "application/octet-stream")
    category = data.get("category", "Outros")

    # ====================================================================
    # PACOTE BL — CATEGORIA INDEX FORÇADA (PASTA COFRE)
    # ====================================================================
    # Override da categoria: todos os uploads do cliente vão para a pasta
    # cofre "Index", independentemente da categoria enviada pelo frontend.
    # Isto garante que o file_key no S3 também fica na pasta "Index",
    # consistente com o confirm-upload (que força a mesma categoria no
    # registo da BD).
    # ====================================================================
    if category != "Index":
        logger.info(
            f"[PORTAL-PACOTE-BL] generate_upload_url: categoria original "
            f"'{category}' forçada para 'Index' (pasta cofre). "
            f"Ficheiro: {filename}, processo: {process_id}"
        )
    category = "Index"

    if not filename:
        raise HTTPException(status_code=400, detail="Nome do ficheiro é obrigatório")

    # Bloquear categorias internas no portal do cliente
    # (Nota: "Index" está em PORTAL_HIDDEN_CATEGORIES, mas é EXATAMENTE a
    # categoria que queremos forçar aqui — o bloqueio abaixo foi desativado
    # para permitir o upload do cliente para a pasta cofre.)
    # if category in PORTAL_HIDDEN_CATEGORIES:
    #     raise HTTPException(status_code=403, detail="Categoria de documento não disponível no portal")

    # Normalizar nome
    safe_filename = filename.replace(" ", "_").replace("/", "-").replace("\\", "-")

    client_name = process.get("client_name", "cliente")
    s3_folder = process.get("s3_folder")

    result = s3_service.generate_upload_presigned_url(
        client_id=process_id,
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

    logger.info(f"[PORTAL] Upload URL gerada para {safe_filename} (processo {process_id}, cat: {category})")

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

    O documento fica com status=RECEIVED — ao carregar pelo portal, o documento
    é automaticamente marcado como Recebido tanto no portal como no CRM.
    Se for fornecido document_id (de um doc REQUESTED), esse registo é atualizado
    em vez de criar um novo.

    Body:
    - file_key: Caminho S3 (obrigatório)
    - original_filename: Nome original (obrigatório)
    - category: Categoria (obrigatório)
    - file_size: Tamanho em bytes (opcional)
    - content_type: MIME type (opcional)
    - document_id: ID do doc REQUESTED a satisfazer (opcional)
    """
    import uuid

    process = client_data["process"]
    process_id = process["id"]

    file_key = data.get("file_key")
    original_filename = data.get("original_filename")
    category = data.get("category", "Outros")
    file_size = data.get("file_size")
    content_type = data.get("content_type", "application/octet-stream")
    document_id = data.get("document_id")  # ID do doc REQUESTED a satisfazer
    custom_label = data.get("custom_label")  # Custom label for "Outros" category

    # ====================================================================
    # PACOTE BL — CATEGORIA INDEX FORÇADA E PRIVADA (PASTA COFRE)
    # ====================================================================
    # Todos os documentos enviados DIRETAMENTE pelo cliente através do
    # Portal recebem automaticamente category="Index" (pasta cofre),
    # ignorando qualquer categoria que venha do frontend do portal. Esta
    # categoria é tratada exclusivamente pela equipa de Indexação — os
    # outros roles não a veem no painel de documentos (filtro aplicado
    # no frontend UnifiedDocumentsPanel/S3FileManager).
    #
    # A categoria original (enviada pelo frontend) é preservada no log
    # para auditoria, mas o documento fica SEMPRE com category="Index".
    # Isto garante que o cliente não consiga classificar documentos em
    # categorias visíveis para consultores/mediadores, mantendo os docs
    # do cliente numa "pasta cofre" até a Indexação os classificar.
    #
    # NOTA: A triagem automática com IA (bloco abaixo) fica desativada
    # para uploads do cliente, porque a categoria já está definida ("Index").
    # A triagem IA só faria sentido se a categoria fosse "Outros"/"Auto",
    # o que já não acontece após este override.
    # ====================================================================
    original_category_from_client = category
    category = "Index"
    if original_category_from_client and original_category_from_client != "Index":
        logger.info(
            f"[PORTAL-PACOTE-BL] Upload do cliente com categoria original "
            f"'{original_category_from_client}' forçada para 'Index' (pasta cofre). "
            f"Ficheiro: {original_filename}, processo: {process_id}"
        )

    # ====================================================================
    # TRIAGEM AUTOMÁTICA COM IA: Se a categoria for 'Outros', 'Auto' ou vazia,
    # invocar IA para determinar a categoria correta com base no nome do
    # ficheiro e no conteúdo (se disponível).
    # ====================================================================
    ai_categorization_info = None
    if category.lower().strip() in ("outros", "auto", "", "other"):
        try:
            from services.document_categorization import (
                extract_text_from_pdf,
                categorize_document_with_ai,
            )

            # Tentar obter conteúdo do ficheiro do S3 para análise (offload de I/O bloqueante)
            file_content_for_ai = await asyncio.to_thread(s3_service.get_file_content, file_key)

            text_for_analysis = f"Ficheiro: {original_filename}"
            if file_content_for_ai and original_filename.lower().endswith('.pdf'):
                extracted = await asyncio.to_thread(extract_text_from_pdf, file_content_for_ai, max_chars=3000)
                if extracted:
                    text_for_analysis = extracted

            existing_categories = await db.document_metadata.distinct("ai_category")

            ai_result = await categorize_document_with_ai(
                text_content=text_for_analysis,
                filename=original_filename,
                existing_categories=existing_categories,
            )

            if ai_result.get("success") and ai_result.get("category"):
                ai_suggested = ai_result["category"]
                ai_categorization_info = {
                    "original_category": category or "Outros",
                    "ai_category": ai_suggested,
                    "ai_confidence": ai_result.get("confidence"),
                }
                category = ai_suggested
                logger.info(
                    f"[PORTAL-IA] Categoria IA: {ai_suggested} "
                    f"para {original_filename}"
                )
        except Exception as ai_err:
            logger.warning(f"[PORTAL-IA] Erro na triagem IA: {ai_err}")

    if not file_key:
        raise HTTPException(status_code=400, detail="file_key é obrigatório")
    if not original_filename:
        raise HTTPException(status_code=400, detail="original_filename é obrigatório")

    # Verificar que o ficheiro existe no S3
    if not s3_service.file_exists(file_key):
        raise HTTPException(
            status_code=400,
            detail="Ficheiro não encontrado. O upload pode ter falhado. Tente novamente."
        )

    now = datetime.now(timezone.utc).isoformat()

    # ── Se temos document_id, atualizar o registo REQUESTED ──
    if document_id:
        update_result = await db.documents.update_one(
            {"id": document_id, "process_id": process_id},
            {
                "$set": {
                    "status": "RECEIVED",
                    "filename": original_filename,
                    "original_filename": original_filename,
                    "file_size": file_size,
                    "content_type": content_type,
                    "s3_path": file_key,
                    "uploaded_at": now,
                    "uploaded_by": "portal_client",
                    "source": "client_portal",
                    "reviewed_by": "portal_client",
                    "reviewed_at": now,
                    "updated_at": now,
                }
            }
        )

        if update_result.matched_count > 0:
            doc_id = document_id
            logger.info(f"[PORTAL] Doc REQUESTED atualizado para RECEIVED: {document_id}")
        else:
            # document_id não encontrado — criar novo
            doc_id = str(uuid.uuid4())
            await _create_document_record(
                doc_id, process_id, file_key, original_filename,
                category, file_size, content_type, now
            )
    else:
        # Sem document_id — criar novo registo
        doc_id = str(uuid.uuid4())
        await _create_document_record(
            doc_id, process_id, file_key, original_filename,
            category, file_size, content_type, now, custom_label
        )

    # Invalidar cache de estatísticas
    await invalidate_stats_cache()

    # ── Audit Trail — registo de upload pelo cliente no histórico do processo ──
    try:
        from services.history import log_history
        client_name = process.get("client_name", "Cliente")
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

    # Obter URL temporária para preview
    temporary_url = s3_service.get_presigned_url(file_key) or ""

    # ── Notificar equipa atribuída ──
    await _notify_assigned_team_upload(process, original_filename, category)

    # ── Gatilho de Onboarding — verificar se o cliente completou os docs ──
    # Executar de forma assíncrona (não bloquear a resposta ao cliente)
    try:
        from services.onboarding_service import check_onboarding_completion
        # Determinar o client_id a partir do token ou do processo
        token_payload = client_data.get("token_payload", {})
        client_id = token_payload.get("client_id") or process.get("client_id")

        if client_id:
            # Verificar de forma assíncrona (fire-and-forget)
            asyncio.create_task(_trigger_onboarding_check(client_id))
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao agendar verificação de onboarding: {e}")

    # ── Pacote G — Gatilho: Documentação Completa ──────────────────────────
    # Verifica se TODOS os pedidos REQUESTED/PENDING foram satisfeitos.
    # Se sim, envia email automático de confirmação ao cliente em nome do
    # intermediário atribuído (com fallback para o SMTP geral da empresa).
    try:
        from services.portal_documents_notify import check_and_notify_documents_complete
        company_id = process.get("company") or process.get("company_id")
        asyncio.create_task(check_and_notify_documents_complete(process_id, company_id))
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao agendar gatilho de documentação completa: {e}")

    logger.info(
        f"[PORTAL] Upload confirmado: {original_filename} "
        f"({category}) para processo {process_id}"
    )

    return {
        "success": True,
        "document_id": doc_id,
        "filename": original_filename,
        "category": category,
        "s3_path": file_key,
        "temporary_url": temporary_url,
        "ai_categorization": ai_categorization_info,
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


