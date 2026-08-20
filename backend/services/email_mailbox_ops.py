"""
Operações de mailbox: anexos, marcações e labels por email.

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

import base64
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from database import db
from models.email import EmailMarkType
from services.email_service import (
    imap_mark_as_seen,
    imap_mark_as_unseen,
    _get_email_account_for_email,
)
from utils.input_sanitization import sanitize_string

logger = logging.getLogger(__name__)


# ==== ATTACHMENT UPLOAD ====

async def run_upload_attachments(files: list, current_user: dict):
    """
    Carregar um ou mais ficheiros para o S3 (pasta temporária).
    Máximo 25MB por ficheiro, máximo 10 ficheiros.
    Retorna lista de metadados com temp_key para referência futura.
    """
    from services.s3_storage import s3_service

    if not files:
        raise HTTPException(status_code=400, detail="Nenhum ficheiro enviado")

    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Máximo de 10 ficheiros por upload")

    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
    user_id = current_user["id"]
    uploaded = []
    errors = []

    for file in files:
        # Read content
        content = await file.read()

        if len(content) > MAX_FILE_SIZE:
            errors.append(f"{file.filename}: ficheiro excede 25MB")
            continue

        if not content:
            errors.append(f"{file.filename}: ficheiro vazio")
            continue

        file_id = str(uuid.uuid4())
        safe_filename = file.filename or "unnamed"
        temp_key = f"temp/attachments/{user_id}/{file_id}_{safe_filename}"

        try:
            import io
            file_obj = io.BytesIO(content)
            s3_service.s3_client.upload_fileobj(
                file_obj,
                s3_service.bucket_name,
                temp_key,
                ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'}
            )

            attachment_meta = {
                "id": file_id,
                "file_name": safe_filename,
                "file_size": len(content),
                "mime_type": file.content_type or "application/octet-stream",
                "temp_key": temp_key,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Store temp attachment metadata for lookup during send
            await db.temp_attachments.insert_one(attachment_meta)

            uploaded.append({
                "id": file_id,
                "file_name": safe_filename,
                "file_size": len(content),
                "mime_type": file.content_type or "application/octet-stream",
                "temp_key": temp_key,
            })
            logger.info(f"Attachment upload: {safe_filename} -> {temp_key}")
        except Exception as e:
            errors.append(f"{file.filename}: erro no upload - {str(e)}")
            logger.error(f"Erro no upload de attachment {safe_filename}: {e}")

    if not uploaded:
        raise HTTPException(status_code=500, detail=f"Nenhum ficheiro carregado: {'; '.join(errors)}")

    return {
        "attachments": uploaded,
        "errors": errors if errors else None,
    }


# ==== ATTACHMENT DOWNLOAD (presigned URL) ====

async def run_download_email_attachment(email_id: str, file_id: str, current_user: dict):
    """
    Obter URL pré-assinada para download de anexo de email.
    Procura o attachment pelo id no array de attachments do email.
    Se tiver s3_key, gera presigned URL (1h). Caso contrário, retorna URL existente.
    """
    from services.s3_storage import s3_service

    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    attachments = email.get("attachments", [])
    attachment = next((a for a in attachments if a.get("id") == file_id), None)

    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")

    filename = attachment.get("filename", attachment.get("file_name", "anexo"))
    content_type = attachment.get("content_type", attachment.get("mime_type", "application/octet-stream"))

    # If has s3_key, generate presigned URL
    s3_key = attachment.get("s3_key")
    if s3_key:
        url = s3_service.get_presigned_url(s3_key, expiration=3600)
        if url:
            return {"url": url, "filename": filename, "content_type": content_type}
        raise HTTPException(status_code=500, detail="Erro ao gerar URL de download")

    # Fallback: return existing URL or embedded content info
    if attachment.get("url"):
        return {"url": attachment["url"], "filename": filename, "content_type": content_type}

    raise HTTPException(status_code=404, detail="Conteúdo do anexo não disponível para download")


# ==== MARCAÇÃO DE EMAILS ====

async def run_mark_email(email_id: str, data: dict, current_user: dict):
    """
    Marcar um email como importante, lido, etc.
    
    Tipos de marcação:
    - important: Marcar como importante
    - read: Marcar como lido
    - unread: Marcar como não lido
    - starred: Marcar com estrela
    - archived: Arquivar
    - spam: Marcar como spam
    
    Aceita tanto {"type": "read"} como {"mark_type": "read"}
    """
    mark_type_str = data.get("type") or data.get("mark_type")
    if not mark_type_str:
        raise HTTPException(status_code=422, detail="Campo 'type' obrigatório")
    
    try:
        mark_type = EmailMarkType(mark_type_str)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Tipo de marcação inválido: {mark_type_str}")
    
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
    
    # === IMAP BIDIRECTIONAL SYNC: Reflect read/unread on IMAP server ===
    message_id = email.get("message_id")
    if message_id and mark_type in (EmailMarkType.READ, EmailMarkType.UNREAD):
        try:
            account_value = email.get("account", "")
            synced_for_user = email.get("synced_for_user")
            email_account = await _get_email_account_for_email(account_value, synced_for_user)
            if email_account:
                folder = "INBOX" if email.get("direction") == "received" else "Sent"
                if mark_type == EmailMarkType.READ:
                    imap_result = await imap_mark_as_seen(email_account, message_id, folder)
                else:
                    imap_result = await imap_mark_as_unseen(email_account, message_id, folder)
                if not imap_result.get("success"):
                    logger.warning(f"[IMAP Sync] Falha ao sincronizar flags para {email_id}: {imap_result.get('error')}")
        except Exception as imap_err:
            logger.warning(f"[IMAP Sync] Erro ao sincronizar flags IMAP para {email_id}: {imap_err}")
    
    logger.info(f"Email {email_id} marcado como {mark_type.value} por {current_user['email']}")
    
    return {
        "success": True,
        "email_id": email_id,
        "mark_type": mark_type.value
    }


async def run_unmark_email(email_id: str, mark_type: EmailMarkType, current_user: dict):
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

async def run_add_email_label(email_id: str, label: str, current_user: dict):
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


async def run_remove_email_label(email_id: str, label: str, current_user: dict):
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

async def run_get_email_attachments(email_id: str, current_user: dict):
    """Listar anexos de um email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0, "attachments": 1})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    return {"attachments": email.get("attachments", [])}


async def run_download_attachment(email_id: str, attachment_id: str, current_user: dict):
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


async def run_preview_attachment(email_id: str, attachment_id: str, current_user: dict):
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


def _content_disposition_attachment(filename: str) -> str:
    safe_name = (filename or "anexo").replace('"', "").replace("\r", "").replace("\n", "")
    ascii_name = safe_name.encode("ascii", "replace").decode("ascii") or "anexo"
    encoded = quote(safe_name, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _match_attachment(attachments: list, attachment_id: str):
    """Resolve anexo por id, índice (`emailId:idx`) ou filename."""
    if not attachments:
        return None, None
    for idx, att in enumerate(attachments):
        if not isinstance(att, dict):
            continue
        if att.get("id") == attachment_id:
            return att, idx
    if ":" in attachment_id:
        _, _, suffix = attachment_id.rpartition(":")
        if suffix.isdigit():
            idx = int(suffix)
            if 0 <= idx < len(attachments) and isinstance(attachments[idx], dict):
                return attachments[idx], idx
    target = attachment_id.lower().strip()
    for idx, att in enumerate(attachments):
        if not isinstance(att, dict):
            continue
        name = (att.get("filename") or att.get("file_name") or "").lower()
        if name == target:
            return att, idx
    return None, None


async def _assert_email_readable(email: dict, request: Request, current_user: dict) -> None:
    from models.auth import UserRole
    from services.auth import get_effective_role

    user_role = get_effective_role(request, current_user)
    if user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR):
        return

    user_id = current_user.get("id")
    user_email = (current_user.get("email") or "").lower().strip()
    is_owner = (
        email.get("created_by") == user_id
        or email.get("synced_for_user") == user_id
        or email.get("synced_for_user") == user_email
    )
    is_shared = bool(email.get("shared_role") and email.get("shared_role") == user_role)
    is_in_conversation = False
    if user_email:
        from_email = (email.get("from_email") or "").lower()
        to_emails = email.get("to_emails") or []
        is_in_conversation = user_email in from_email or any(
            user_email in str(addr).lower() for addr in to_emails
        )
    if not (is_owner or is_shared or is_in_conversation):
        raise HTTPException(status_code=403, detail="Sem permissão para descarregar este anexo")


async def _load_attachment_bytes(email: dict, attachment: dict, current_user: dict) -> Optional[bytes]:
    """S3 → conteúdo em BD → IMAP (fallback)."""
    s3_key = attachment.get("s3_key") or attachment.get("temp_key")
    if s3_key:
        try:
            from services.s3_storage import s3_service
            if s3_service.is_configured():
                content = s3_service.get_file_content(s3_key)
                if content:
                    return content
        except Exception as exc:
            logger.warning("[Webmail Attachment] S3 falhou para %s: %s", s3_key, exc)

    raw = attachment.get("content") or attachment.get("content_base64")
    if raw:
        try:
            if isinstance(raw, bytes):
                return raw
            return base64.b64decode(raw)
        except Exception:
            logger.warning("[Webmail Attachment] Conteúdo base64 inválido")

    message_id = email.get("message_id")
    filename = attachment.get("filename") or attachment.get("file_name")
    if not message_id or not filename:
        return None

    try:
        from services.email_config_resolver import resolve_email_config_for_sync
        from services.email_service import (
            EmailAccount,
            fetch_attachment_bytes_from_imap_sync,
        )
        from services.encryption import encryption_service

        company_id = email.get("company_id")
        owner_id = email.get("synced_for_user") or email.get("created_by")
        lookup_id = current_user.get("id")
        if isinstance(owner_id, str) and owner_id and "@" not in owner_id:
            lookup_id = owner_id
        resolved = await resolve_email_config_for_sync(
            lookup_id,
            active_company_id=company_id,
        )
        account = None
        if resolved and resolved.get("encrypted_password") and resolved.get("imap_server"):
            password = encryption_service.decrypt(resolved["encrypted_password"])
            account = EmailAccount(
                name="webmail_att",
                imap_server=resolved.get("imap_server") or "",
                imap_port=int(resolved.get("imap_port") or 993),
                smtp_server=resolved.get("smtp_server") or "",
                smtp_port=int(resolved.get("smtp_port") or 465),
                email=resolved.get("email_address") or "",
                password=password,
            )
        if account is None:
            account = await _get_email_account_for_email(
                email.get("account", ""),
                email.get("synced_for_user"),
            )
        if not account:
            return None

        import asyncio
        loop = asyncio.get_event_loop()
        from services.email_service import _email_executor
        return await loop.run_in_executor(
            _email_executor,
            lambda: fetch_attachment_bytes_from_imap_sync(account, message_id, filename),
        )
    except Exception as exc:
        logger.warning("[Webmail Attachment] Fallback IMAP falhou: %s", exc)
        return None


async def run_download_webmail_attachment(
    attachment_id: str,
    current_user: dict,
    request: Request,
    email_id: Optional[str] = None,
):
    """GET /api/webmail/attachments/{id} — stream binário autenticado (Pacote DN.1)."""
    attachment_id = (attachment_id or "").strip()
    if not attachment_id:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")

    email = None
    if email_id:
        email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if email is None:
        email = await db.emails.find_one({"attachments.id": attachment_id}, {"_id": 0})
    if email is None and ":" in attachment_id:
        maybe_email_id, _, _ = attachment_id.rpartition(":")
        if maybe_email_id:
            email = await db.emails.find_one({"id": maybe_email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")

    await _assert_email_readable(email, request, current_user)

    attachments = email.get("attachments") or []
    attachment, _idx = _match_attachment(attachments, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")

    content = await _load_attachment_bytes(email, attachment, current_user)
    if not content:
        raise HTTPException(
            status_code=404,
            detail="Conteúdo do anexo não encontrado na base de dados, S3 ou IMAP",
        )

    filename = attachment.get("filename") or attachment.get("file_name") or "anexo"
    content_type = (
        attachment.get("content_type")
        or attachment.get("mime_type")
        or "application/octet-stream"
    )
    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={
            "Content-Disposition": _content_disposition_attachment(filename),
            "Content-Length": str(len(content)),
            "Cache-Control": "private, max-age=60",
        },
    )



