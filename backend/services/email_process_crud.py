"""Search/timeline, emails por processo, send, CRUD e monitored.

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import HTTPException, BackgroundTasks, Request

from database import db
from models.email import (
    EmailCreate, EmailUpdate, EmailResponse, EmailDirection, EmailStatus,
    EmailFilter, EmailSendRequest,
)
from services.auth import get_effective_role
from services.email_enrich import enrich_email
from services.email_service import (
    sync_emails_for_process,
    send_email,
    imap_delete_message,
    imap_move_to_trash,
    _get_email_account_for_email,
)
from utils.input_sanitization import (
    sanitize_string, sanitize_name, sanitize_email, sanitize_html, sanitize_url,
    log_sanitization_rejection,
)

logger = logging.getLogger(__name__)

# Shared in-memory sync status (single object — do not duplicate)
_sync_status: dict = {}

async def run_advanced_email_search(filters: EmailFilter, current_user: dict, page: int = 1, limit: int = 20):
    """
    Pesquisa avançada de emails com filtros.
    
    Suporta:
    - Filtro por processo
    - Filtro por direção (enviado/recebido)
    - Filtro por conta (precision/power)
    - Filtro por marcações (importante, lido, estrela)
    - Filtro por anexos
    - Filtro por intervalo de datas
    - Pesquisa por texto
    - Filtro por etiquetas
    """
    query = {}
    
    # Filtro por processo
    if filters.process_id:
        query["process_id"] = filters.process_id
    
    # Filtro por direcção
    if filters.direction:
        query["direction"] = filters.direction.value
    
    # Filtro por conta
    if filters.account:
        query["account"] = filters.account
    
    # Filtros de marcação
    if filters.is_important is not None:
        query["is_important"] = filters.is_important
    if filters.is_read is not None:
        query["is_read"] = filters.is_read
    if filters.is_starred is not None:
        query["is_starred"] = filters.is_starred
    if filters.is_archived is not None:
        query["is_archived"] = filters.is_archived
    
    # Filtro por anexos
    if filters.has_attachments is not None:
        if filters.has_attachments:
            query["attachments.0"] = {"$exists": True}
        else:
            query["attachments"] = {"$size": 0}
    
    # Filtro por datas
    if filters.date_from or filters.date_to:
        date_query = {}
        if filters.date_from:
            date_query["$gte"] = filters.date_from
        if filters.date_to:
            date_query["$lte"] = filters.date_to
        query["sent_at"] = date_query
    
    # Pesquisa por texto
    if filters.search_term:
        query["$or"] = [
            {"subject": {"$regex": filters.search_term, "$options": "i"}},
            {"body": {"$regex": filters.search_term, "$options": "i"}},
            {"from_email": {"$regex": filters.search_term, "$options": "i"}},
            {"to_emails": {"$regex": filters.search_term, "$options": "i"}},
        ]
    
    # Filtro por etiquetas
    if filters.labels:
        query["labels"] = {"$all": filters.labels}
    
    # Executar query com paginação
    skip = (page - 1) * limit
    total = await db.emails.count_documents(query)
    
    emails = await db.emails.find(
        query,
        {"_id": 0}
    ).sort("sent_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Enriquecer emails
    enriched_emails = []
    for email in emails:
        enriched = await enrich_email(email)
        enriched_emails.append(enriched)
    
    return {
        "emails": enriched_emails,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


async def run_get_email_timeline(process_id: str, current_user: dict):
    """
    Obter timeline de emails de um processo.
    Inclui eventos agrupados por dia.
    """
    emails = await db.emails.find(
        {"process_id": process_id, "is_archived": {"$ne": True}},
        {"_id": 0}
    ).sort("sent_at", 1).to_list(500)
    
    # Agrupar por data
    timeline = {}
    for email in emails:
        if email.get("sent_at"):
            date_key = email["sent_at"][:10]  # YYYY-MM-DD
            if date_key not in timeline:
                timeline[date_key] = {
                    "date": date_key,
                    "emails": [],
                    "stats": {"sent": 0, "received": 0}
                }
            
            timeline[date_key]["emails"].append(email)
            if email.get("direction") == "sent":
                timeline[date_key]["stats"]["sent"] += 1
            else:
                timeline[date_key]["stats"]["received"] += 1
    
    # Converter para lista ordenada
    timeline_list = sorted(timeline.values(), key=lambda x: x["date"], reverse=True)
    
    return {"timeline": timeline_list, "total_emails": len(emails)}


async def run_get_process_emails(process_id: str, current_user: dict, direction: Optional[EmailDirection] = None, filter_by_user: bool = False, include_archived: bool = False, force_refresh: bool = False):
    """
    Listar emails de um processo.
    
    Retorna todos os emails associados ao processo (via process_id),
    ordenados por data descendente.
    
    Associação de emails a processos é feita automaticamente por:
    1. Smart Threading (herança de process_id via In-Reply-To / References)
    2. Tag Mágica [Proc-{id}] no assunto
    3. Associação manual pelo utilizador (botão Ligar a Processo no Webmail)
    
    Se force_refresh=True, limpa emails sincronizados em cache e
    dispara sincronização global (smart threading + tags aplicam-se automaticamente).
    """
    if force_refresh:
        # Limpar cache: apagar emails sincronizados (marcados com "Sincronizado de" nas notes)
        delete_result = await db.emails.delete_many({
            "process_id": process_id,
            "notes": {"$regex": "^Sincronizado de", "$options": "i"}
        })
        logger.info(f"Cache limpa para processo {process_id}: {delete_result.deleted_count} emails removidos")
        
        # Re-sincronizar do IMAP
        user_email = current_user.get("email")
        try:
            sync_result = await sync_emails_for_process(process_id, days=30, user_email=user_email)
            logger.info(f"Re-sync após limpeza de cache: {sync_result}")
        except Exception as e:
            logger.error(f"Erro na re-sync após limpeza de cache: {e}")
    
    # ── Query principal: emails com process_id directo ──
    base_conditions = [{"process_id": process_id}]

    # ── Fallback: emails sem process_id mas que envolvem o cliente do processo ──
    # Isto apanha emails enviados/recebidos (Sent/Drafts) que o Smart Threading
    # não associou automaticamente porque não tinham In-Reply-To ou tag [Proc-xxx].
    process_doc = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "client_email": 1, "monitored_emails": 1}
    )
    client_email = (process_doc or {}).get("client_email", "").lower().strip()
    monitored = (process_doc or {}).get("monitored_emails", [])

    if client_email or monitored:
        # Construir lista de endereços do cliente para matching
        client_emails = set()
        if client_email:
            client_emails.add(client_email)
        for me in monitored:
            if me and isinstance(me, str):
                client_emails.add(me.lower().strip())
        client_emails.discard("")

        if client_emails:
            email_match_or = []
            for ce in client_emails:
                escaped = re.escape(ce)
                email_match_or.extend([
                    {"from_email": {"$regex": f"^{escaped}$", "$options": "i"}},
                    {"to_emails": {"$regex": f"^{escaped}$", "$options": "i"}},
                ])

            # Só incluir se NÃO tiver process_id já (evitar duplicados)
            fallback_condition = {
                "$and": [
                    {"$or": [{"process_id": None}, {"process_id": {"$exists": False}}]},
                    {"$or": email_match_or},
                ]
            }
            base_conditions.append(fallback_condition)

    query = {"$or": base_conditions} if len(base_conditions) > 1 else base_conditions[0]

    if direction:
        query = {"$and": [query, {"direction": direction.value}]}

    if not include_archived:
        if "$and" in query:
            query["$and"].append({"is_archived": {"$ne": True}})
        else:
            query = {"$and": [query, {"is_archived": {"$ne": True}}]}

    if filter_by_user:
        user_email = current_user.get("email", "").lower()
        if user_email:
            user_filter = {
                "$or": [
                    {"from_email": {"$regex": user_email, "$options": "i"}},
                    {"to_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}},
                    {"cc_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}}
                ]
            }
            if "$and" in query:
                query["$and"].append(user_filter)
            else:
                query = {"$and": [query, user_filter]}

    emails = await db.emails.find(query, {"_id": 0}).sort("sent_at", -1).to_list(500)
    
    enriched_emails = []
    for email in emails:
        enriched = await enrich_email(email)
        enriched_emails.append(EmailResponse(**enriched))
    
    return enriched_emails


async def run_get_email_stats(process_id: str, current_user: dict):
    """Obter estatísticas de emails de um processo."""
    # Construir query com fallback por email do cliente (mesma lógica de get_process_emails)
    base_conditions = [{"process_id": process_id}]
    process_doc = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "client_email": 1, "monitored_emails": 1}
    )
    client_email_val = (process_doc or {}).get("client_email", "").lower().strip()
    monitored = (process_doc or {}).get("monitored_emails", [])
    if client_email_val or monitored:
        client_emails = set()
        if client_email_val:
            client_emails.add(client_email_val)
        for me in monitored:
            if me and isinstance(me, str):
                client_emails.add(me.lower().strip())
        client_emails.discard("")
        if client_emails:
            email_match_or = []
            for ce in client_emails:
                escaped = re.escape(ce)
                email_match_or.extend([
                    {"from_email": {"$regex": f"^{escaped}$", "$options": "i"}},
                    {"to_emails": {"$regex": f"^{escaped}$", "$options": "i"}},
                ])
            fallback_condition = {
                "$and": [
                    {"$or": [{"process_id": None}, {"process_id": {"$exists": False}}]},
                    {"$or": email_match_or},
                ]
            }
            base_conditions.append(fallback_condition)

    stats_query = {"$or": base_conditions} if len(base_conditions) > 1 else base_conditions[0]
    stats_query["is_archived"] = {"$ne": True}

    pipeline = [
        {"$match": stats_query},
        {"$group": {
            "_id": "$direction",
            "count": {"$sum": 1}
        }}
    ]

    results = await db.emails.aggregate(pipeline).to_list(10)

    stats = {
        "total": 0,
        "sent": 0,
        "received": 0,
        "unread": 0,
        "important": 0,
        "starred": 0
    }

    for r in results:
        if r["_id"] == "sent":
            stats["sent"] = r["count"]
        elif r["_id"] == "received":
            stats["received"] = r["count"]
        stats["total"] += r["count"]

    # Contar não lidos, importantes e estrelados
    stats["unread"] = await db.emails.count_documents({
        **stats_query, "is_read": False
    })
    stats["important"] = await db.emails.count_documents({
        **stats_query, "is_important": True
    })
    stats["starred"] = await db.emails.count_documents({
        **stats_query, "is_starred": True
    })

    return stats


async def run_sync_process_emails(process_id: str, background_tasks: BackgroundTasks, current_user: dict, days: int = 30, blocking: bool = False):
    """Sincronizar emails de um processo."""
    user_email = current_user.get("email")
    
    if blocking:
        result = await sync_emails_for_process(process_id, days, user_email=user_email)
        return result
    else:
        async def run_sync():
            """Executa a sincronização de emails em background para o processo.

            Atualiza ``_sync_status`` com o estado (running/completed/failed)
            para que o frontend possa fazer polling do progresso.

            Args:
                Nenhum parâmetro direto — usa variáveis do closure
                (process_id, days, user_email).

            Returns:
                None. Resultado é guardado em ``_sync_status[process_id]``.
            """
            try:
                _sync_status[process_id] = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
                result = await sync_emails_for_process(process_id, days, user_email=user_email)
                _sync_status[process_id] = {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": result
                }
            except Exception as e:
                logger.error(f"Erro na sincronização de emails para {process_id}: {e}")
                _sync_status[process_id] = {
                    "status": "error",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
        
        asyncio.create_task(run_sync())
        
        return {
            "success": True,
            "message": "Sincronização iniciada em background",
            "process_id": process_id,
            "status": "started"
        }


async def run_get_sync_status(process_id: str, current_user: dict):
    """Verificar o status da sincronização de emails."""
    if process_id in _sync_status:
        return _sync_status[process_id]
    return {"status": "not_found", "message": "Nenhuma sincronização encontrada"}


async def run_associate_email_to_client(data: dict, current_user: dict):
    """Associar um email existente a um processo/cliente específico.

    SEGURANÇA: Não-admin só pode associar emails que lhe pertencem.
    """
    from models.auth import UserRole

    email_id = data.get("email_id")
    process_id = data.get("process_id")
    
    if not email_id or not process_id:
        raise HTTPException(status_code=400, detail="email_id e process_id são obrigatórios")
    
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "id": 1, "client_name": 1})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = await db.emails.find_one(
        {"$or": [{"id": email_id}, {"message_id": email_id}]},
        {"_id": 0}
    )
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    # === ISOLAMENTO: verificar que o utilizador tem acesso ao email ===
    user_role = current_user.get("role", "")
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)

    if not can_see_all:
        user_id = current_user["id"]
        is_owner = (
            email.get("created_by") == user_id
            or email.get("synced_for_user") == user_id
        )
        is_shared_role = (
            email.get("shared_role")
            and email.get("shared_role") == user_role
        )
        if not (is_owner or is_shared_role):
            raise HTTPException(status_code=403, detail="Sem permissão para associar este email")
    
    if email.get("process_id") == process_id:
        return {"success": True, "message": "Email já está associado a este processo"}
    
    now = datetime.now(timezone.utc).isoformat()
    await db.emails.update_one(
        {"id": email["id"]},
        {"$set": {
            "process_id": process_id,
            "associated_by": current_user["id"],
            "associated_at": now
        }}
    )
    
    logger.info(f"Email {email['id']} associado ao processo {process_id} por {current_user['email']}")
    
    return {
        "success": True,
        "message": f"Email associado ao cliente {process.get('client_name', process_id)}",
        "email_id": email["id"],
        "process_id": process_id
    }


async def run_search_emails(q: str, current_user: dict, limit: int = 20):
    """Pesquisar emails para associação manual.

    SEGURANÇA: Não-admin só pode pesquisar nos seus próprios emails.
    """
    from models.auth import UserRole

    if len(q) < 3:
        raise HTTPException(status_code=400, detail="Termo deve ter pelo menos 3 caracteres")

    # === ISOLAMENTO DE DADOS ===
    user_role = current_user.get("role", "")
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)

    text_filter = {
        "$or": [
            {"subject": {"$regex": q, "$options": "i"}},
            {"from_email": {"$regex": q, "$options": "i"}},
            {"to_emails": {"$regex": q, "$options": "i"}},
            {"body": {"$regex": q, "$options": "i"}},
        ]
    }

    if can_see_all:
        query = text_filter
    else:
        user_id = current_user["id"]
        ownership_filter = {
            "$or": [
                {"created_by": user_id},
                {"synced_for_user": user_id},
            ]
        }
        # Incluir emails do role partilhado
        shared_config = await db.shared_role_email_configs.find_one(
            {"role": user_role, "is_configured": True}, {"_id": 0, "role": 1}
        )
        if shared_config:
            ownership_filter["$or"].append({"shared_role": user_role})

        query = {"$and": [ownership_filter, text_filter]}
    
    emails = await db.emails.find(
        query,
        {"_id": 0, "id": 1, "subject": 1, "from_email": 1, "to_emails": 1, "sent_at": 1, "process_id": 1}
    ).sort("sent_at", -1).limit(limit).to_list(limit)
    
    for email in emails:
        if email.get("process_id"):
            process = await db.processes.find_one(
                {"id": email["process_id"]},
                {"_id": 0, "client_name": 1}
            )
            if process:
                email["client_name"] = process.get("client_name")
    
    return {"emails": emails, "total": len(emails)}


async def run_send_email(payload: EmailSendRequest, request: Request, current_user: dict, account: str = "power"):
    """
    Enviar email através de uma das contas configuradas.
    
    ISOLAMENTO DE REMETENTE:
    - admin/ceo/diretor: podem usar contas globais (power, precision) OU pessoal
    - outros roles (consultor, intermediario, etc.): obrigatoriamente usam
      a conta pessoal configurada no seu perfil (email_config).
      Se não tiver email configurado, o envio é bloqueado.
    
    BOX SUPPORT (from_box):
    - indexacao: ao enviar, usa automaticamente a conta partilhada do role
    - general (from_box): CEO/admin/diretor podem enviar da caixa geral (shared_role=geral)
    """
    from models.auth import UserRole
    from services.email_config_resolver import resolve_email_config_for_sync

    # === PACOTE AL: Extração Imediata da Empresa e do Remetente Base ===
    # 1. active_company_id: tentar header direto primeiro (mais rápido),
    #    depois fallback para get_active_company_id_async.
    active_company_id = request.headers.get("x-company-id")
    if not active_company_id:
        try:
            from services.auth import get_active_company_id_async
            active_company_id = await get_active_company_id_async(request, current_user)
        except Exception:
            active_company_id = None

    user_role = current_user.get("role", "")
    can_use_global_accounts = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)
    from_box = payload.from_box
    from_email = current_user.get("email")  # Remetente Base

    # === indexacao role: auto-use shared email account ===
    if user_role == UserRole.INDEXACAO:
        shared_config = await db.shared_role_email_configs.find_one(
            {"role": UserRole.INDEXACAO, "is_configured": True},
            {"_id": 0, "email_address": 1, "email": 1},
        )
        if shared_config:
            shared_email_addr = shared_config.get("email_address") or shared_config.get("email", "")
            account = "personal"
            logger.info(f"[Send Email] indexacao user {current_user.get('email')}: using shared account {shared_email_addr}")
        else:
            resolved = await resolve_email_config_for_sync(
                current_user["id"],
                active_role=user_role,
                active_company_id=active_company_id
            )
            if not resolved:
                raise HTTPException(
                    status_code=403,
                    detail="Configuração de email partilhada para indexacao não encontrada. Contacte o administrador."
                )
            account = "personal"

    # === PACOTE AL: Forçar conta pessoal e Resolver a Config ===
    # from_box == "personal" OU utilizador não-admin → usar conta pessoal.
    elif from_box == "personal" or not can_use_global_accounts:
        account = "personal"

    # === from_box == "general": use shared geral account ===
    elif from_box == "general":
        if user_role not in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR):
            raise HTTPException(
                status_code=403,
                detail="Apenas admin, CEO e diretor podem enviar emails a partir da caixa geral."
            )
        account = "power"
        logger.info(f"[Send Email] user {current_user.get('email')} ({user_role}): sending from geral box (account={account})")

    # === PACOTE AL: Resolver config pessoal (exceto indexacao já tratado) ===
    # Resolve o from_email correto a partir da config do utilizador para a
    # empresa ativa. Isto garante que o email sai pela conta certa e que
    # o reply_to aponta para o email configurado.
    if account == "personal" and user_role != UserRole.INDEXACAO:
        try:
            resolved = await resolve_email_config_for_sync(
                current_user["id"],
                active_role=user_role,
                active_company_id=active_company_id
            )
        except Exception as e:
            logger.exception(f"[Send Email] Erro no resolver para user {current_user.get('email')}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao resolver configuração de email: {type(e).__name__}: {e}"
            )
        if not resolved:
            raise HTTPException(
                status_code=403,
                detail="Configuração de email não encontrada para esta empresa. Vá ao seu Perfil > Configuração de Webmail para configurar o seu email antes de enviar."
            )
        from_email = resolved.get("email_address") or from_email
        logger.info(f"[Send Email] Utilizador {current_user.get('email')} ({user_role}): conta pessoal (from_email={from_email}, empresa={active_company_id})")

    # Sanitize inputs before sending and DB insert
    to_emails = [e for e in (sanitize_email(e) for e in payload.to_emails) if e]
    cc_emails = None
    if payload.cc_emails:
        cc_emails = [e for e in (sanitize_email(e) for e in payload.cc_emails) if e]
    subject = sanitize_string(payload.subject, max_length=300)
    body = sanitize_string(payload.body, max_length=10000)
    # PACOTE AK: Sanitização e proteção do HTML — inline styles para imagens
    # evitam desformatação em clientes de email clássicos (Gmail/Outlook)
    body_html = payload.body_html
    if body_html:
        body_html = sanitize_html(body_html, allow_email_html=True)
        # Injetar max-width nas imagens para evitar desformatação em clientes de email
        body_html = body_html.replace('<img ', '<img style="max-width: 100%; height: auto;" ')

    if not to_emails:
        raise HTTPException(status_code=400, detail="Pelo menos um email destinatário válido é necessário")

    # ==== PROCESS TEMP ATTACHMENTS ====
    email_attachments = []
    temp_attachment_records = []  # Track for S3 move + cleanup
    temp_keys_to_cleanup = []

    if payload.attachment_ids:
        # Look up temp attachments from MongoDB
        temp_docs = await db.temp_attachments.find(
            {"id": {"$in": payload.attachment_ids}, "user_id": current_user["id"]},
            {"_id": 0}
        ).to_list(20)

        if len(temp_docs) != len(payload.attachment_ids):
            found_ids = {d["id"] for d in temp_docs}
            missing = [aid for aid in payload.attachment_ids if aid not in found_ids]
            logger.warning(f"Temp attachments not found: {missing}")
            # Continue with available attachments

        from services.s3_storage import s3_service

        for temp_doc in temp_docs:
            temp_key = temp_doc["temp_key"]
            file_name = temp_doc["file_name"]
            mime_type = temp_doc.get("mime_type", "application/octet-stream")

            try:
                # Download content from temp S3 path
                loop = asyncio.get_running_loop()
                content_bytes = await loop.run_in_executor(
                    None, lambda tk=temp_key: s3_service.get_file_content(tk)
                )
                if content_bytes:
                    email_attachments.append({
                        "filename": file_name,
                        "content_bytes": content_bytes,
                        "content_type": mime_type,
                    })
                    temp_attachment_records.append({
                        "id": temp_doc["id"],
                        "file_name": file_name,
                        "file_size": temp_doc.get("file_size", len(content_bytes)),
                        "mime_type": mime_type,
                        "temp_key": temp_key,
                    })
                    temp_keys_to_cleanup.append(temp_key)
                    logger.info(f"Temp attachment prepared for send: {file_name}")
                else:
                    logger.warning(f"Could not download temp attachment from S3: {temp_key}")
            except Exception as e:
                logger.error(f"Error downloading temp attachment {file_name}: {e}")

    # === EMPRESA ATIVA + from_email — já resolvidos no início (Pacote AL) ===
    # active_company_id: para a assinatura correta da empresa ativa.
    # from_email: remetente pessoal resolvido da config (não a conta geral).
    # reply_to: respostas vão para o email do utilizador, não para a conta geral.

    try:
        result = await send_email(
            account_name=account,
            to_emails=to_emails,
            subject=subject,
            body=body,
            body_html=body_html,
            cc_emails=cc_emails,
            process_id=payload.process_id,
            created_by=current_user["id"],
            attachments=email_attachments if email_attachments else None,
            active_company_id=active_company_id,
            from_email=from_email,
            reply_to=from_email,
        )
    except Exception as e:
        logger.exception(f"[Send Email] Erro ao chamar send_email: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao enviar email: {type(e).__name__}: {e}"
        )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao enviar email"))

    # ==== MOVE ATTACHMENTS FROM TEMP TO PERMANENT + UPDATE EMAIL DOC ====
    if temp_attachment_records and payload.process_id:
        from services.s3_storage import s3_service

        # Find the most recently created sent email for this user+process
        sent_email = await db.emails.find_one(
            {
                "process_id": payload.process_id,
                "created_by": current_user["id"],
                "direction": "sent",
            },
            sort=[("sent_at", -1)],
        )

        if sent_email:
            permanent_attachments = []
            for att_rec in temp_attachment_records:
                permanent_s3_key = f"Emails/{sent_email['id']}/{att_rec['file_name']}"
                try:
                    loop = asyncio.get_running_loop()
                    moved = await loop.run_in_executor(
                        None,
                        lambda sk=att_rec["temp_key"], pk=permanent_s3_key: s3_service.rename_file(sk, pk)
                    )
                    if moved:
                        logger.info(f"Attachment moved: {att_rec['temp_key']} -> {permanent_s3_key}")
                    else:
                        logger.warning(f"Failed to move attachment: {att_rec['temp_key']}")
                        permanent_s3_key = att_rec["temp_key"]  # Keep temp key as fallback
                except Exception as e:
                    logger.error(f"Error moving attachment {att_rec['temp_key']}: {e}")
                    permanent_s3_key = att_rec["temp_key"]

                permanent_attachments.append({
                    "id": att_rec["id"],
                    "filename": att_rec["file_name"],
                    "file_name": att_rec["file_name"],
                    "size": att_rec["file_size"],
                    "content_type": att_rec["mime_type"],
                    "s3_key": permanent_s3_key,
                })

            # Update email document with permanent attachment metadata
            existing_attachments = sent_email.get("attachments", [])
            await db.emails.update_one(
                {"id": sent_email["id"]},
                {"$set": {"attachments": existing_attachments + permanent_attachments}}
            )

        # Clean up temp attachment metadata from MongoDB
        await db.temp_attachments.delete_many({"id": {"$in": [r["id"] for r in temp_attachment_records]}})

        # Clean up temp files from S3 (for any that weren't moved)
        from services.s3_storage import s3_service
        for temp_key in temp_keys_to_cleanup:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda tk=temp_key: s3_service.delete_file(tk))
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {temp_key}: {e}")

    result["attachments_sent"] = len(email_attachments)
    return result


async def run_create_email_record(email_data: EmailCreate, current_user: dict):
    """Registar um email no histórico."""
    email_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Sanitize inputs before DB insert
    from_email = sanitize_email(email_data.from_email)
    to_emails = [e for e in (sanitize_email(e) for e in email_data.to_emails) if e]
    cc_emails = [e for e in (sanitize_email(e) for e in (email_data.cc_emails or [])) if e]
    bcc_emails = [e for e in (sanitize_email(e) for e in (email_data.bcc_emails or [])) if e]
    subject = sanitize_string(email_data.subject, max_length=300)
    body = sanitize_string(email_data.body, max_length=10000)
    notes = sanitize_string(email_data.notes, max_length=1000) if email_data.notes else None

    email = {
        "id": email_id,
        "process_id": email_data.process_id,
        "direction": email_data.direction.value,
        "from_email": from_email,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "subject": subject,
        "body": body,
        "body_html": email_data.body_html,
        "attachments": [a.dict() for a in (email_data.attachments or [])],
        "status": email_data.status.value,
        "sent_at": email_data.sent_at or now,
        "created_at": now,
        "created_by": current_user["id"],
        "notes": notes,
        "is_important": False,
        "is_read": True,
        "is_starred": False,
        "is_archived": False,
        "labels": []
    }
    
    await db.emails.insert_one(email)
    logger.info(f"Email registado: {email_id} para processo {email_data.process_id}")
    
    enriched = await enrich_email(email)
    return EmailResponse(**enriched)


async def run_get_email(email_id: str, request: Request, current_user: dict):
    """Obter detalhes de um email.

    SEGURANÇA: Não-admin só pode ver emails que lhe pertencem.
    Verifica created_by, synced_for_user ou shared_role.
    Usa o effective_role (X-Active-Role) para determinar can_see_all.
    """
    from models.auth import UserRole
    from services.auth import get_effective_role

    email = await db.emails.find_one({"id": email_id}, {"_id": 0})

    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    # === ISOLAMENTO DE DADOS ===
    # PACOTE AU: usar effective_role (X-Active-Role) em vez do role primário
    user_role = get_effective_role(request, current_user)
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)

    if not can_see_all:
        user_id = current_user["id"]
        user_email = (current_user.get("email") or "").lower().strip()

        # Verificar se o utilizador tem acesso a este email
        is_owner = (
            email.get("created_by") == user_id
            or email.get("synced_for_user") == user_id
        )
        is_shared_role = (
            email.get("shared_role")
            and email.get("shared_role") == user_role
        )
        is_in_conversation = False
        if user_email:
            from_emails = email.get("from_email") or ""
            to_emails = email.get("to_emails") or []
            is_in_conversation = (
                user_email in from_emails.lower()
                or any(user_email in addr.lower() for addr in to_emails)
            )

        if not (is_owner or is_shared_role or is_in_conversation):
            raise HTTPException(status_code=403, detail="Sem permissão para ver este email")

    enriched = await enrich_email(email)

    try:
        return EmailResponse(**enriched)
    except Exception as e:
        logger.error(f"Erro ao validar email {email_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar email {email_id}: {str(e)}"
        )


async def run_update_email(email_id: str, email_data: EmailUpdate, current_user: dict):
    """Actualizar registo de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if email_data.subject is not None:
        update_data["subject"] = sanitize_string(email_data.subject, max_length=300)
    if email_data.body is not None:
        update_data["body"] = sanitize_string(email_data.body, max_length=10000)
    if email_data.notes is not None:
        update_data["notes"] = sanitize_string(email_data.notes, max_length=1000)
    if email_data.status is not None:
        update_data["status"] = email_data.status.value
    if email_data.is_important is not None:
        update_data["is_important"] = email_data.is_important
    if email_data.is_read is not None:
        update_data["is_read"] = email_data.is_read
    if email_data.is_starred is not None:
        update_data["is_starred"] = email_data.is_starred
    if email_data.is_archived is not None:
        update_data["is_archived"] = email_data.is_archived
    if email_data.labels is not None:
        update_data["labels"] = email_data.labels
    
    if update_data:
        await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    updated_email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    enriched = await enrich_email(updated_email)

    try:
        return EmailResponse(**enriched)
    except Exception as e:
        logger.error(f"Erro ao validar email {email_id} após update: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar email {email_id}: {str(e)}"
        )


async def run_delete_email(email_id: str, current_user: dict):
    """Eliminar registo de email (MongoDB + mover para Trash no IMAP server)."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    # === IMAP BIDIRECTIONAL SYNC: Move to Trash on IMAP server (instead of permanent delete) ===
    message_id = email.get("message_id")
    if message_id:
        try:
            account_value = email.get("account", "")
            synced_for_user = email.get("synced_for_user")
            email_account = await _get_email_account_for_email(account_value, synced_for_user)
            if email_account:
                folder = "INBOX" if email.get("direction") == "received" else "Sent"
                imap_result = await imap_move_to_trash(email_account, message_id, folder)
                if imap_result.get("success"):
                    trash_folder = imap_result.get("trash_folder")
                    fallback = imap_result.get("fallback")
                    if trash_folder:
                        logger.info(f"[IMAP Sync] Email {email_id} movido para '{trash_folder}' no IMAP")
                    elif fallback:
                        logger.warning(f"[IMAP Sync] Email {email_id} fallback expunge (Trash não encontrado)")
                else:
                    logger.warning(f"[IMAP Sync] Falha ao mover email para Trash: {imap_result.get('error')}")
        except Exception as imap_err:
            logger.warning(f"[IMAP Sync] Erro ao mover email para Trash: {imap_err}")
    
    # Soft-delete — mark as archived (appears in Trash folder)
    await db.emails.update_one(
        {"id": email_id},
        {"$set": {"is_archived": True, "archived_at": datetime.now(timezone.utc).isoformat()}}
    )
    logger.info(f"Email {email_id} movido para o Lixo por {current_user['name']}")
    
    return {"success": True, "message": "Email movido para o Lixo"}


async def run_permanently_delete_email(email_id: str, current_user: dict):
    """Elimina permanentemente um email (apenas da pasta Lixo)."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    if not email.get("is_archived"):
        raise HTTPException(status_code=400, detail="Apenas emails no Lixo podem ser eliminados permanentemente")
    
    await db.emails.delete_one({"id": email_id})
    logger.info(f"Email {email_id} permanentemente eliminado por {current_user['name']}")
    
    return {"success": True, "message": "Email permanentemente eliminado"}


async def run_get_monitored_emails(process_id: str, current_user: dict):
    """Obter lista de emails monitorizados de um processo."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "client_email": 1, "monitored_emails": 1})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    return {
        "client_email": process.get("client_email"),
        "monitored_emails": process.get("monitored_emails", [])
    }


async def run_add_monitored_email(process_id: str, email: str, current_user: dict):
    """Adicionar email à lista de monitorizados."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = sanitize_email(email)
    if not email:
        raise HTTPException(status_code=400, detail="Email inválido")
    
    monitored = process.get("monitored_emails", [])
    
    if email in monitored or email == process.get("client_email", "").lower():
        raise HTTPException(status_code=400, detail="Email já está na lista")
    
    monitored.append(email)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"monitored_emails": monitored}}
    )
    
    logger.info(f"Email {email} adicionado à monitorização do processo {process_id}")
    
    return {
        "success": True,
        "monitored_emails": monitored
    }


async def run_remove_monitored_email(process_id: str, email: str, current_user: dict):
    """Remover email da lista de monitorizados."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = email.lower().strip()
    monitored = process.get("monitored_emails", [])
    
    if email not in monitored:
        raise HTTPException(status_code=404, detail="Email não encontrado na lista")
    
    monitored.remove(email)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"monitored_emails": monitored}}
    )
    
    logger.info(f"Email {email} removido da monitorização do processo {process_id}")
    
    return {
        "success": True,
        "monitored_emails": monitored
    }


