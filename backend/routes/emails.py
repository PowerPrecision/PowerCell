"""
====================================================================
ROTAS DE EMAILS - POWERCELL
====================================================================
Endpoints para gestão de histórico de emails.

FEATURES:
- Visualização de anexos (preview, download)
- Filtros avançados (por data, por conta, por tipo)
- Marcação de emails (importante, lido, etc.)
- Templates de resposta rápida
- Timeline de emails no processo
- Notificações de novos emails
====================================================================
"""

import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import base64

from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks
from fastapi.responses import Response

from database import db
from models.email import (
    EmailCreate, EmailUpdate, EmailResponse, EmailDirection, EmailStatus,
    EmailMarkType, EmailTemplateCreate, EmailTemplateResponse, EmailFilter
)
from services.auth import get_current_user
from services.email_service import sync_emails_for_process, send_email, test_email_connection, get_email_accounts
from services.email_draft_service import (
    get_pending_drafts,
    get_draft_stats,
    update_draft,
    send_draft,
    discard_draft,
    create_missing_doc_draft,
    batch_create_missing_doc_drafts,
)
from utils.input_sanitization import sanitize_string, sanitize_name, sanitize_email, sanitize_html, sanitize_url, log_sanitization_rejection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Emails"])

# NOTA: doc_router foi removido. Os endpoints send-documentation e document-recipients
# estão agora registados no router principal ANTES das rotas com /{email_id}.
# Isto resolve o bug 404 que ocorria quando a ordem de montagem dos routers
# no server.py causava conflitos com o catch-all /{email_id}.
doc_router = None  # Mantido como None para compatibilidade com server.py

# Armazenar status de sincronizações em progresso
_sync_status = {}


async def enrich_email(email: dict) -> dict:
    """Adicionar nomes ao email."""
    # Nome do processo/cliente
    if email.get("process_id"):
        process = await db.processes.find_one(
            {"id": email["process_id"]},
            {"_id": 0, "client_name": 1}
        )
        if process:
            email["client_name"] = process.get("client_name", "")
    
    # Nome de quem criou
    if email.get("created_by"):
        user = await db.users.find_one(
            {"id": email["created_by"]},
            {"_id": 0, "name": 1}
        )
        if user:
            email["created_by_name"] = user.get("name", "")
    
    return email


# ==== DOCUMENT RECIPIENTS & SEND DOCUMENTATION (antes de /{email_id} para evitar conflito) ====

@router.get("/document-recipients")
async def get_document_recipients(
    current_user: dict = Depends(get_current_user)
):
    """
    Obter lista de destinatários disponíveis para envio de documentação.
    Apenas Admin e CEO podem editar as configurações.
    """
    from services.system_config import get_system_config
    
    config = await get_system_config()
    doc_config = config.document_recipients
    
    if not doc_config.enabled:
        return {
            "enabled": False,
            "recipients": [],
            "email_template": None,
            "default_to": None,
            "default_to_name": None,
            "default_to_emails": []
        }
    
    import json
    
    # Parse recipients JSON
    recipients = []
    if doc_config.recipients:
        try:
            recipients = json.loads(doc_config.recipients)
        except (json.JSONDecodeError, TypeError):
            recipients = []
    
    # Parse default_to_emails (múltiplos emails TO)
    default_to_emails = []
    if doc_config.default_to_emails:
        try:
            parsed = json.loads(doc_config.default_to_emails)
            if isinstance(parsed, list):
                default_to_emails = [e for e in parsed if e and "@" in str(e)]
        except (json.JSONDecodeError, TypeError):
            default_to_emails = []
    
    # Fallback: se default_to_emails está vazio mas default_to tem valor, usá-lo
    if not default_to_emails and doc_config.default_to and "@" in str(doc_config.default_to):
        default_to_emails = [doc_config.default_to]
    
    return {
        "enabled": True,
        "recipients": recipients,
        "email_template": doc_config.email_template,
        "default_to": doc_config.default_to,
        "default_to_name": doc_config.default_to_name,
        "default_to_emails": default_to_emails,
        "can_edit": current_user["role"] in ["admin", "ceo"]
    }


# ==== SEND DOCUMENTATION (antes de /{email_id} para evitar conflito de rota) ====
# Estes endpoints devem estar ANTES das rotas com /{email_id} para que
# o FastAPI faça match correcto e não trate "send-documentation" como um email_id.

@router.post("/send-documentation/{process_id}")
async def send_documentation_email(
    process_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Enviar documentação do processo para balcões/bancos.
    """
    from services.system_config import get_system_config
    
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Obter configuração
    config = await get_system_config()
    doc_config = config.document_recipients
    
    if not doc_config.enabled:
        raise HTTPException(status_code=400, detail="Envio de documentação não está activado")
    
    # Dados do request
    document_ids = data.get("document_ids", [])
    # Sanitize email addresses from user input
    bcc_recipients = [e for e in (sanitize_email(e) for e in data.get("bcc_recipients", [])) if e]
    cc_emails = [e for e in (sanitize_email(e) for e in data.get("cc_emails", [])) if e]
    custom_message = data.get("custom_message")
    
    # TO emails: usar os selecionados pelo utilizador, ou fallback para config
    request_to_emails = [e for e in (sanitize_email(e) for e in data.get("to_emails", [])) if e]
    
    if not document_ids:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um documento")
    
    if not bcc_recipients:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um destinatário")
    
    # Validar destinatários contra contas ativas e simulações
    financial_data = process.get("financial_data", {}) or {}
    bancos_creditos = financial_data.get("bancos_creditos", []) or []
    bancos_simulacoes = financial_data.get("bancos_simulacoes", []) or []
    
    def normalize_bank_name(name):
        return name.lower().strip() if name else ""
    
    blocked_banks = [normalize_bank_name(b) for b in bancos_creditos + bancos_simulacoes]
    
    # Parse recipients para validar
    recipients_list = []
    if doc_config.recipients:
        try:
            import json
            recipients_list = json.loads(doc_config.recipients)
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Validar cada BCC recipient
    validated_bcc = []
    warnings = []
    
    for bcc_email in bcc_recipients:
        recipient_info = next(
            (r for r in recipients_list if r.get("email", "").lower() == bcc_email.lower()),
            {"name": bcc_email, "email": bcc_email}
        )
        
        recipient_name = normalize_bank_name(recipient_info.get("name", ""))
        is_blocked = any(blocked in recipient_name or recipient_name in blocked for blocked in blocked_banks)
        
        if is_blocked:
            warnings.append(f"⚠️ {recipient_info.get('name', bcc_email)}: Cliente tem conta ativa ou simulação neste banco")
        else:
            validated_bcc.append(bcc_email)
    
    if warnings:
        logger.warning(f"Destinatários bloqueados para processo {process_id}: {warnings}")
    
    if not validated_bcc:
        raise HTTPException(
            status_code=400, 
            detail="Nenhum destinatário válido. O cliente tem contas ativas ou simulações em todos os bancos selecionados."
        )
    
    # Obter documentos da coleção document_metadata (onde são guardados)
    documents = await db.document_metadata.find(
        {"id": {"$in": document_ids}},
        {"_id": 0}
    ).to_list(100)
    
    if not documents:
        raise HTTPException(status_code=404, detail="Nenhum documento encontrado")
    
    # Preparar lista de documentos para o email
    documents_list = "\n".join([
        f"- {doc.get('original_name', doc.get('filename', 'Documento'))}" 
        for doc in documents
    ])
    
    # Preparar template do email
    email_template = doc_config.email_template or """Prezados,

Segue em anexo a documentação do cliente:

**Cliente:** {client_name}
**NIF:** {client_nif}
**Processo:** #{process_number}

**Documentos enviados:**
{documents_list}

Esta documentação foi enviada através do sistema PowerCell.

Com os melhores cumprimentos,
{sender_name}
{sender_email}"""
    
    # Substituir variáveis
    client_name = process.get("client_name", "N/A")
    personal_data = process.get("personal_data", {}) or {}
    client_nif = personal_data.get("nif", process.get("client_nif", "N/A"))
    process_number = process.get("process_number", "N/A")
    
    email_body = email_template.format(
        client_name=client_name,
        client_nif=client_nif,
        process_number=process_number,
        documents_list=documents_list,
        sender_name=current_user.get("name", ""),
        sender_email=current_user.get("email", "")
    )
    
    # Se admin/CEO enviou mensagem personalizada, usar essa
    if custom_message and current_user["role"] in ["admin", "ceo"]:
        custom_message = sanitize_string(custom_message, max_length=10000)
        email_body = custom_message.format(
            client_name=client_name,
            client_nif=client_nif,
            process_number=process_number,
            documents_list=documents_list,
            sender_name=current_user.get("name", ""),
            sender_email=current_user.get("email", "")
        )
    
    # Preparar destinatários TO (suporta múltiplos emails)
    # Prioridade: emails selecionados pelo utilizador > config > fallback
    to_emails = []
    if request_to_emails:
        to_emails = request_to_emails
    elif doc_config.default_to_emails:
        try:
            import json
            parsed_to = json.loads(doc_config.default_to_emails)
            if isinstance(parsed_to, list):
                to_emails = [e for e in parsed_to if e and "@" in str(e)]
        except (json.JSONDecodeError, TypeError):
            pass
    # Fallback para default_to singular (compatibilidade)
    if not to_emails and doc_config.default_to and "@" in str(doc_config.default_to):
        to_emails = [doc_config.default_to]
    # Último fallback: email do utilizador actual
    if not to_emails:
        to_emails = [current_user["email"]]
    subject = f"Documentação - {client_name} (Processo #{process_number})"
    
    # ==== PREPARAR ANEXOS (download do S3) ====
    email_attachments = []
    failed_attachments = []
    for doc in documents:
        filename = doc.get("original_name", doc.get("filename", "documento"))
        s3_path = doc.get("s3_path") or doc.get("path")
        
        if s3_path:
            try:
                from services.s3_storage import s3_service
                loop = asyncio.get_event_loop()
                content_bytes = await loop.run_in_executor(
                    None, lambda p=s3_path: s3_service.get_file_content(p)
                )
                if content_bytes:
                    email_attachments.append({
                        "filename": filename,
                        "content_bytes": content_bytes,
                        "content_type": doc.get("content_type") or doc.get("mime_type")
                    })
                    logger.info(f"Anexo preparado: {filename} ({len(content_bytes)} bytes)")
                else:
                    failed_attachments.append(filename)
                    logger.warning(f"Falha ao descarregar anexo do S3: {s3_path}")
            except Exception as e:
                failed_attachments.append(filename)
                logger.error(f"Erro ao descarregar anexo {filename} do S3: {e}")
        else:
            failed_attachments.append(filename)
            logger.warning(f"Documento sem s3_path: {filename}")
    
    if failed_attachments:
        warnings.append(f"⚠️ {len(failed_attachments)} documento(s) não puderam ser anexados: {', '.join(failed_attachments)}")
    
    # ==== ENVIAR EMAIL COM ANEXOS ====
    result = await send_email(
        account_name="power",
        to_emails=to_emails,
        subject=subject,
        body=email_body,
        cc_emails=cc_emails if cc_emails else None,
        bcc_emails=validated_bcc,
        process_id=process_id,
        created_by=current_user["id"],
        attachments=email_attachments if email_attachments else None
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao enviar email"))
    
    # NOTA: O registo no histórico já é feito pelo send_email() internamente.
    # Adicionar label "documentação" ao registo criado pelo send_email
    try:
        await db.emails.update_one(
            {"process_id": process_id, "created_by": current_user["id"], "direction": "sent"},
            {"$set": {
                "is_important": False,
                "is_read": True,
                "is_starred": False,
                "is_archived": False,
            },
            "$addToSet": {"labels": "documentação"}},
            sort=[("sent_at", -1)]
        )
    except Exception as e:
        logger.warning(f"Não foi possível adicionar label 'documentação' ao registo: {e}")
    
    logger.info(f"Documentação enviada para processo {process_id} por {current_user['email']}: {len(validated_bcc)} destinatários, {len(email_attachments)} anexos")
    
    return {
        "success": True,
        "message": f"Documentação enviada com sucesso para {len(validated_bcc)} destinatário(s) ({len(email_attachments)} anexo(s))",
        "warnings": warnings,
        "sent_to": validated_bcc,
        "attachments_sent": len(email_attachments),
        "attachments_failed": len(failed_attachments) if failed_attachments else 0
    }


# ==== MARCAÇÃO DE EMAILS ====

@router.post("/{email_id}/mark")
async def mark_email(
    email_id: str,
    mark_type: EmailMarkType = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """
    Marcar um email como importante, lido, etc.
    
    Tipos de marcação:
    - important: Marcar como importante
    - read: Marcar como lido
    - unread: Marcar como não lido
    - starred: Marcar com estrela
    - archived: Arquivar
    - spam: Marcar como spam
    """
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if mark_type == EmailMarkType.IMPORTANT:
        update_data["is_important"] = True
    elif mark_type == EmailMarkType.READ:
        update_data["is_read"] = True
    elif mark_type == EmailMarkType.UNREAD:
        update_data["is_read"] = False
    elif mark_type == EmailMarkType.STARRED:
        update_data["is_starred"] = True
    elif mark_type == EmailMarkType.ARCHIVED:
        update_data["is_archived"] = True
    elif mark_type == EmailMarkType.SPAM:
        update_data["is_spam"] = True
    
    await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    logger.info(f"Email {email_id} marcado como {mark_type.value} por {current_user['email']}")
    
    return {
        "success": True,
        "email_id": email_id,
        "mark_type": mark_type.value
    }


@router.delete("/{email_id}/mark/{mark_type}")
async def unmark_email(
    email_id: str,
    mark_type: EmailMarkType,
    current_user: dict = Depends(get_current_user)
):
    """Remover marcação de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if mark_type == EmailMarkType.IMPORTANT:
        update_data["is_important"] = False
    elif mark_type == EmailMarkType.STARRED:
        update_data["is_starred"] = False
    elif mark_type == EmailMarkType.ARCHIVED:
        update_data["is_archived"] = False
    
    await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    return {"success": True, "email_id": email_id, "removed": mark_type.value}


# ==== LABELS/ETIQUETAS ====

@router.post("/{email_id}/labels")
async def add_email_label(
    email_id: str,
    label: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Adicionar etiqueta ao email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    labels = email.get("labels", [])
    label = sanitize_string(label, max_length=200)
    if label not in labels:
        labels.append(label)
        await db.emails.update_one(
            {"id": email_id},
            {"$set": {"labels": labels, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    return {"success": True, "labels": labels}


@router.delete("/{email_id}/labels/{label}")
async def remove_email_label(
    email_id: str,
    label: str,
    current_user: dict = Depends(get_current_user)
):
    """Remover etiqueta do email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    labels = email.get("labels", [])
    if label in labels:
        labels.remove(label)
        await db.emails.update_one(
            {"id": email_id},
            {"$set": {"labels": labels, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    return {"success": True, "labels": labels}


# ==== ANEXOS ====

@router.get("/{email_id}/attachments")
async def get_email_attachments(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Listar anexos de um email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0, "attachments": 1})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    return {"attachments": email.get("attachments", [])}


@router.get("/{email_id}/attachments/{attachment_id}")
async def download_attachment(
    email_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download de anexo."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    attachments = email.get("attachments", [])
    attachment = next((a for a in attachments if a.get("id") == attachment_id), None)
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    
    # Se tiver URL externa, redirecionar
    if attachment.get("url"):
        return {"redirect_url": attachment["url"]}
    
    # Se tiver conteúdo em base64
    if attachment.get("content"):
        content = base64.b64decode(attachment["content"])
        return Response(
            content=content,
            media_type=attachment.get("content_type", "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{attachment["filename"]}"'
            }
        )
    
    raise HTTPException(status_code=404, detail="Conteúdo do anexo não disponível")


@router.get("/{email_id}/attachments/{attachment_id}/preview")
async def preview_attachment(
    email_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Preview de anexo (para imagens e PDFs)."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    attachments = email.get("attachments", [])
    attachment = next((a for a in attachments if a.get("id") == attachment_id), None)
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    
    content_type = attachment.get("content_type", "")
    
    # Verificar se é previewable
    previewable_types = ["image/", "application/pdf", "text/"]
    if not any(pt in content_type for pt in previewable_types):
        raise HTTPException(status_code=400, detail="Este tipo de ficheiro não suporta preview")
    
    # Se tiver preview_url
    if attachment.get("preview_url"):
        return {"preview_url": attachment["preview_url"]}
    
    # Se tiver conteúdo em base64
    if attachment.get("content"):
        content = base64.b64decode(attachment["content"])
        return Response(
            content=content,
            media_type=content_type
        )
    
    raise HTTPException(status_code=404, detail="Preview não disponível")


# ==== FILTROS AVANÇADOS ====

@router.post("/search/advanced")
async def advanced_email_search(
    filters: EmailFilter,
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
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
    
    # Filtro por direção
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


# ==== TIMELINE DE EMAILS ====

@router.get("/timeline/{process_id}")
async def get_email_timeline(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
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


# ==== TEMPLATES DE RESPOSTA ====

@router.get("/templates", response_model=List[EmailTemplateResponse])
async def get_email_templates(
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Listar templates de resposta rápida."""
    query = {}
    if category:
        query["category"] = category
    
    templates = await db.email_templates.find(
        query,
        {"_id": 0}
    ).sort("usage_count", -1).to_list(50)
    
    return templates


@router.post("/templates", response_model=EmailTemplateResponse)
async def create_email_template(
    template: EmailTemplateCreate,
    current_user: dict = Depends(get_current_user)
):
    """Criar novo template de resposta."""
    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    template_doc = {
        "id": template_id,
        "name": sanitize_string(template.name, max_length=200),
        "subject": sanitize_string(template.subject, max_length=300),
        "body": sanitize_string(template.body, max_length=10000),
        "category": template.category,
        "is_default": template.is_default,
        "created_by": current_user["id"],
        "created_at": now,
        "usage_count": 0
    }
    
    # Se for default, remover default de outros
    if template.is_default:
        await db.email_templates.update_many(
            {"category": template.category},
            {"$set": {"is_default": False}}
        )
    
    await db.email_templates.insert_one(template_doc)
    
    return EmailTemplateResponse(**template_doc)


@router.put("/templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: str,
    template: EmailTemplateCreate,
    current_user: dict = Depends(get_current_user)
):
    """Atualizar template de resposta."""
    existing = await db.email_templates.find_one({"id": template_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    update_data = {
        "name": sanitize_string(template.name, max_length=200),
        "subject": sanitize_string(template.subject, max_length=300),
        "body": sanitize_string(template.body, max_length=10000),
        "category": template.category,
        "is_default": template.is_default,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.email_templates.update_one(
        {"id": template_id},
        {"$set": update_data}
    )
    
    updated = await db.email_templates.find_one({"id": template_id}, {"_id": 0})
    return EmailTemplateResponse(**updated)


@router.delete("/templates/{template_id}")
async def delete_email_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar template de resposta."""
    result = await db.email_templates.delete_one({"id": template_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {"success": True}


@router.post("/templates/{template_id}/use")
async def use_template(
    template_id: str,
    process_id: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Incrementar contador de uso de template."""
    await db.email_templates.update_one(
        {"id": template_id},
        {"$inc": {"usage_count": 1}}
    )
    
    # Obter template
    template = await db.email_templates.find_one({"id": template_id}, {"_id": 0})
    
    # Obter dados do processo para personalizar
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    # Substituir variáveis
    body = template.get("body", "")
    subject = template.get("subject", "")
    
    if process:
        body = body.replace("{cliente}", process.get("client_name", ""))
        body = body.replace("{email_cliente}", process.get("client_email", ""))
        subject = subject.replace("{cliente}", process.get("client_name", ""))
    
    return {
        "subject": subject,
        "body": body
    }


# ==== NOTIFICAÇÕES ====

@router.get("/notifications/unread")
async def get_unread_notifications(
    current_user: dict = Depends(get_current_user)
):
    """
    Obter contagem de emails não lidos por processo.
    Para mostrar badges de notificação.
    """
    # Obter processos do utilizador
    user_email = current_user.get("email", "").lower()
    
    # Admin/CEO veem todos, outros só os seus
    if current_user["role"] in ["admin", "ceo"]:
        processes = await db.processes.find({}, {"_id": 0, "id": 1, "client_name": 1}).to_list(1000)
    else:
        processes = await db.processes.find(
            {"assigned_to": current_user["id"]},
            {"_id": 0, "id": 1, "client_name": 1}
        ).to_list(1000)
    
    process_ids = [p["id"] for p in processes]
    
    # Contar emails não lidos por processo
    pipeline = [
        {"$match": {
            "process_id": {"$in": process_ids},
            "is_read": False,
            "is_archived": {"$ne": True}
        }},
        {"$group": {
            "_id": "$process_id",
            "count": {"$sum": 1},
            "latest": {"$max": "$sent_at"}
        }}
    ]
    
    unread_counts = await db.emails.aggregate(pipeline).to_list(1000)
    
    # Mapear para resposta
    result = {}
    for item in unread_counts:
        process_id = item["_id"]
        process = next((p for p in processes if p["id"] == process_id), None)
        if process:
            result[process_id] = {
                "count": item["count"],
                "latest": item["latest"],
                "client_name": process.get("client_name", "")
            }
    
    total_unread = sum(r["count"] for r in result.values())
    
    return {
        "total_unread": total_unread,
        "by_process": result
    }


@router.get("/test-connection")
async def test_email_connections(
    account: Optional[str] = Query(None, description="Conta específica (precision, power) ou todas"),
    current_user: dict = Depends(get_current_user)
):
    """Testar conexão com as contas de email."""
    if current_user["role"] not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    results = await test_email_connection(account)
    return results


@router.get("/accounts")
async def get_configured_accounts(
    current_user: dict = Depends(get_current_user)
):
    """Listar contas de email configuradas."""
    accounts = get_email_accounts()
    return [
        {
            "name": a.name,
            "email": a.email,
            "imap_server": a.imap_server,
            "smtp_server": a.smtp_server
        }
        for a in accounts
    ]


@router.get("/process/{process_id}", response_model=List[EmailResponse])
async def get_process_emails(
    process_id: str,
    direction: Optional[EmailDirection] = Query(None, description="Filtrar por direção"),
    filter_by_user: bool = Query(False, description="Filtrar apenas emails onde o utilizador participou"),
    include_archived: bool = Query(False, description="Incluir emails arquivados"),
    force_refresh: bool = Query(False, description="Limpar emails em cache e re-sincronizar do IMAP"),
    current_user: dict = Depends(get_current_user)
):
    """
    Listar emails de um processo.
    
    Se force_refresh=True, elimina todos os emails sincronizados do processo
    e faz uma nova sincronização IMAP antes de devolver os resultados.
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
    
    query = {"process_id": process_id}
    
    if direction:
        query["direction"] = direction.value
    
    if not include_archived:
        query["is_archived"] = {"$ne": True}
    
    if filter_by_user:
        user_email = current_user.get("email", "").lower()
        if user_email:
            query["$or"] = [
                {"from_email": {"$regex": user_email, "$options": "i"}},
                {"to_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}},
                {"cc_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}}
            ]
    
    emails = await db.emails.find(query, {"_id": 0}).sort("sent_at", -1).to_list(500)
    
    enriched_emails = []
    for email in emails:
        enriched = await enrich_email(email)
        enriched_emails.append(EmailResponse(**enriched))
    
    return enriched_emails


@router.get("/stats/{process_id}")
async def get_email_stats(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter estatísticas de emails de um processo."""
    pipeline = [
        {"$match": {"process_id": process_id, "is_archived": {"$ne": True}}},
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
        "process_id": process_id,
        "is_read": False,
        "is_archived": {"$ne": True}
    })
    stats["important"] = await db.emails.count_documents({
        "process_id": process_id,
        "is_important": True
    })
    stats["starred"] = await db.emails.count_documents({
        "process_id": process_id,
        "is_starred": True
    })
    
    return stats


@router.post("/sync/{process_id}")
async def sync_process_emails(
    process_id: str,
    background_tasks: BackgroundTasks,
    days: int = Query(30, description="Sincronizar emails dos últimos X dias"),
    blocking: bool = Query(False, description="Esperar pela sincronização (pode demorar)"),
    current_user: dict = Depends(get_current_user)
):
    """Sincronizar emails de um processo."""
    user_email = current_user.get("email")
    
    if blocking:
        result = await sync_emails_for_process(process_id, days, user_email=user_email)
        return result
    else:
        async def run_sync():
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


@router.get("/sync-status/{process_id}")
async def get_sync_status(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Verificar o status da sincronização de emails."""
    if process_id in _sync_status:
        return _sync_status[process_id]
    return {"status": "not_found", "message": "Nenhuma sincronização encontrada"}


@router.post("/associate")
async def associate_email_to_client(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Associar um email existente a um processo/cliente específico."""
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


@router.get("/search")
async def search_emails(
    q: str = Query(..., description="Termo de pesquisa"),
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Pesquisar emails para associação manual."""
    if len(q) < 3:
        raise HTTPException(status_code=400, detail="Termo deve ter pelo menos 3 caracteres")
    
    query = {
        "$or": [
            {"subject": {"$regex": q, "$options": "i"}},
            {"from_email": {"$regex": q, "$options": "i"}}
        ]
    }
    
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


@router.post("/send")
async def send_email_endpoint(
    to_emails: List[str],
    subject: str,
    body: str,
    body_html: Optional[str] = None,
    cc_emails: Optional[List[str]] = None,
    account: str = Query("precision", description="Conta de email"),
    process_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Enviar email através de uma das contas configuradas."""
    # Sanitize inputs before sending and DB insert
    to_emails = [e for e in (sanitize_email(e) for e in to_emails) if e]
    if cc_emails:
        cc_emails = [e for e in (sanitize_email(e) for e in cc_emails) if e]
    subject = sanitize_string(subject, max_length=300)
    body = sanitize_string(body, max_length=10000)

    if not to_emails:
        raise HTTPException(status_code=400, detail="Pelo menos um email destinatário válido é necessário")

    result = await send_email(
        account_name=account,
        to_emails=to_emails,
        subject=subject,
        body=body,
        body_html=body_html,
        cc_emails=cc_emails,
        process_id=process_id,
        created_by=current_user["id"]
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao enviar email"))
    
    return result


# ==== RASCUNHOS AUTOMÁTICOS (Auto-Draft) ====

@router.get("/drafts")
async def list_auto_drafts(
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Listar rascunhos automáticos pendentes.
    Admin/CEO veem todos, outros só os dos seus processos.
    """
    drafts = await get_pending_drafts(
        user_id=current_user["id"],
        user_role=current_user["role"],
        limit=limit,
    )
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=current_user["role"],
    )
    return {"drafts": drafts, "stats": stats}


@router.get("/drafts/stats")
async def auto_drafts_stats(
    current_user: dict = Depends(get_current_user)
):
    """Obter estatísticas de rascunhos automáticos pendentes."""
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=current_user["role"],
    )
    return stats


@router.put("/drafts/{draft_id}")
async def edit_auto_draft(
    draft_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Editar um rascunho automático (subject, body, to_emails)."""
    # Sanitize user inputs before passing to service
    if "subject" in data and data["subject"]:
        data["subject"] = sanitize_string(data["subject"], max_length=300)
    if "body" in data and data["body"]:
        data["body"] = sanitize_string(data["body"], max_length=10000)
    if "to_emails" in data and data["to_emails"]:
        data["to_emails"] = [e for e in (sanitize_email(e) for e in data["to_emails"]) if e]

    result = await update_draft(draft_id, data)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Erro ao atualizar"))
    return result


@router.post("/drafts/{draft_id}/send")
async def send_auto_draft(
    draft_id: str,
    account: str = Query("power", description="Conta de email (power/precision)"),
    current_user: dict = Depends(get_current_user)
):
    """Enviar um rascunho automático."""
    result = await send_draft(
        draft_id=draft_id,
        user_id=current_user["id"],
        account=account,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao enviar"))
    return result


@router.delete("/drafts/{draft_id}")
async def delete_auto_draft(
    draft_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Descartar (eliminar) um rascunho automático."""
    result = await discard_draft(draft_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Rascunho não encontrado"))
    return result


@router.post("/drafts/create")
async def manually_create_draft(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Criar manualmente um rascunho automático para um documento em falta.
    Útil quando o admin quer gerar um rascunho para um processo específico.
    """
    process_id = data.get("process_id")
    doc_type = data.get("doc_type")

    if not process_id or not doc_type:
        raise HTTPException(status_code=400, detail="process_id e doc_type são obrigatórios")

    # Obter dados do processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    result = await create_missing_doc_draft(
        process_id=process_id,
        client_name=process.get("client_name", ""),
        missing_doc_type=doc_type,
        process_number=process.get("process_number", ""),
    )

    return result


# ==== ROTAS CRUD GENÉRICAS ====

@router.post("", response_model=EmailResponse)
async def create_email_record(
    email_data: EmailCreate,
    current_user: dict = Depends(get_current_user)
):
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


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter detalhes de um email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    enriched = await enrich_email(email)
    return EmailResponse(**enriched)


@router.put("/{email_id}", response_model=EmailResponse)
async def update_email(
    email_id: str,
    email_data: EmailUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Atualizar registo de email."""
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
    return EmailResponse(**enriched)


@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar registo de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    await db.emails.delete_one({"id": email_id})
    logger.info(f"Email {email_id} eliminado por {current_user['name']}")
    
    return {"success": True, "message": "Email eliminado"}


# ==== GESTÃO DE EMAILS MONITORIZADOS ====

@router.get("/monitored/{process_id}")
async def get_monitored_emails(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter lista de emails monitorizados de um processo."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "client_email": 1, "monitored_emails": 1})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    return {
        "client_email": process.get("client_email"),
        "monitored_emails": process.get("monitored_emails", [])
    }


@router.post("/monitored/{process_id}")
async def add_monitored_email(
    process_id: str,
    email: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
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


@router.delete("/monitored/{process_id}/{email}")
async def remove_monitored_email(
    process_id: str,
    email: str,
    current_user: dict = Depends(get_current_user)
):
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
