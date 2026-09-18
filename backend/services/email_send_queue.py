"""
====================================================================
FILA DE ENVIO DE EMAIL COM UNDO (PACOTE 9 — "Desfazer Envio", 10s)
====================================================================

Implementa o fluxo "Enviar → janela de 10 segundos → Desfazer" do
Webmail:

    POST /api/emails/send
        └→ validações síncronas (permissões/config SMTP — 403 imediatos)
        └→ grava registo PENDING na colecção ``pending_email_sends``
        └→ agenda a execução real para daqui a UNDO_SEND_WINDOW_SECONDS
        └→ responde {queued: true, send_id, undo_window_seconds}

    POST /api/emails/{send_id}/cancel-send   (dentro da janela)
        └→ apaga o registo pending — nada sai para a rede SMTP
        └→ devolve o payload do rascunho para o frontend reabrir a edição

EXECUÇÃO (após a janela):
- Duas vias concorrentes, ambas idempotentes:
  1. Job ARQ ``send_pending_webmail_email_task`` enfileirado com
     ``defer_by`` (sobrevive a restarts do processo API);
  2. Timer in-process (``spawn_background_task`` + ``asyncio.sleep``) —
     rede de segurança para dev sem Redis e para o worker ARQ em baixo.
- As duas disputam um CLAIM ATÓMICO em Mongo
  (``update_one({"id", "status": "pending"}) → "claimed"``) — só a
  primeira executa o envio; nunca há envio duplicado.

CICLO DE VIDA DO REGISTO:
    pending  ──(claim)──►  claimed  ──(envio SMTP)──►  [apagado]
       │
       └──(cancel)──►  [apagado]  (nunca enviado)
    claimed ──(falha SMTP)──► failed  (mantido para auditoria)

Nota de desenho: os registos vivem numa colecção DEDICADA
(``pending_email_sends``) e não em ``emails`` — o documento de email
"sent" continua a ser criado exclusivamente por ``send_email`` (com o
seu próprio id), evitando duplicados e mantendo o serviço de envio
inalterado. Emails cancelados não deixam rasto em ``emails``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from services.email_service import send_email

logger = logging.getLogger(__name__)


# ====================================================================
# PACOTE 10 — TASK LOGS DO MONITOR GLOBAL (widget "Processos em
# Segundo Plano")
# ====================================================================
# Cada envio enfileirado ganha um task_log (EMAIL_SEND) que segue o
# ciclo pending → processing → completed/failed/cancelled. Isto torna
# os envios de email VISIBLES no widget global da topbar
# (GET /tasks/active) com estado Loading/Success/Failed — pedido
# explícito do Pacote 10. Best-effort: falhas a criar/actualizar o
# task_log nunca afectam o envio em si.


async def attach_task_log_to_pending_record(record: dict) -> Optional[str]:
    """
    Cria o task_log EMAIL_SEND para um registo pending e devolve o
    task_id (o chamador deve gravá-lo em ``record["task_log_id"]``
    ANTES do insert na colecção).

    Usado tanto pelo caminho diferido (``queue_email_send``) como pelo
    legacy síncrono (``run_send_email`` com EMAIL_UNDO_SEND_WINDOW=0).
    """
    user_id = record.get("created_by")
    if not user_id:
        return None
    try:
        from models.task_log import TaskType
        from services.task_log_service import task_log_service

        subject = (record.get("subject") or "(sem assunto)")[:120]
        task = await task_log_service.create_task(
            task_type=TaskType.EMAIL_SEND,
            user_id=user_id,
            title="Envio de Email",
            description=f"Assunto: {subject}",
            process_id=record.get("process_id"),
            metadata={"send_id": record.get("id"), "kind": "webmail_send"},
        )
        return task.task_id if task else None
    except Exception as exc:  # pragma: no cover — best-effort
        logger.warning(
            "[UNDO-SEND] Falha ao criar task log do monitor para %s: %s",
            record.get("id"), exc,
        )
        return None


async def _update_task_log(task_log_id: Optional[str], **updates) -> None:
    """Actualiza o task_log do monitor (best-effort, nunca lança)."""
    if not task_log_id:
        return
    try:
        from services.task_log_service import task_log_service

        await task_log_service.update_task(task_log_id, **updates)
    except Exception as exc:  # pragma: no cover — best-effort
        logger.warning(
            "[UNDO-SEND] Falha ao actualizar task log %s: %s", task_log_id, exc,
        )


# Janela de Undo (segundos). 0 = envio imediato (comportamento legacy,
# p.ex. para ambientes de teste automatizado).
def _resolve_undo_window_seconds() -> int:
    try:
        return max(0, int(os.environ.get("EMAIL_UNDO_SEND_WINDOW", "10")))
    except (TypeError, ValueError):
        return 10


UNDO_SEND_WINDOW_SECONDS = _resolve_undo_window_seconds()

STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_FAILED = "failed"


def _pending_collection():
    """Colecção canónica dos envios pendentes (indirecta p/ testes)."""
    return db.pending_email_sends


def build_pending_send_record(
    *,
    account: str,
    to_emails: list,
    subject: str,
    body: str,
    body_html: Optional[str],
    cc_emails: Optional[list],
    process_id: Optional[str],
    from_box: Optional[str],
    from_email: Optional[str],
    company_id: Optional[str],
    created_by: str,
    created_by_email: Optional[str],
    attachment_ids: Optional[list],
) -> dict:
    """Constrói o documento PENDING (função pura — testável isoladamente)."""
    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "status": STATUS_PENDING,
        "created_at": now.isoformat(),
        "send_after": (now + timedelta(seconds=UNDO_SEND_WINDOW_SECONDS)).isoformat(),
        "undo_window_seconds": UNDO_SEND_WINDOW_SECONDS,
        # Remetente/config resolvidos de forma síncrona pelo run_send_email
        "account": account,
        "from_box": from_box,
        "from_email": from_email,
        "company_id": company_id,
        # Payload do email (já sanitizado)
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "subject": subject,
        "body": body,
        "body_html": body_html,
        "process_id": process_id,
        "attachment_ids": list(attachment_ids or []),
        # Auditoria
        "created_by": created_by,
        "created_by_email": created_by_email,
    }


async def queue_email_send(record: dict) -> dict:
    """
    Grava o registo pending e agenda a execução após a janela de undo.

    PACOTE 10 — cria também o task_log do monitor global (widget
    "Processos em Segundo Plano") para o envio ser visível com estado
    Loading → Success/Failed na topbar.

    Returns:
        Payload de resposta do POST /emails/send:
        {"success": True, "queued": True, "send_id", "undo_window_seconds",
         "message"}
    """
    # PACOTE 10 — task_log ANTES do insert (o task_id fica persistido
    # no próprio registo pending para as transições futuras).
    task_log_id = await attach_task_log_to_pending_record(record)
    if task_log_id:
        record["task_log_id"] = task_log_id
    await _pending_collection().insert_one(dict(record))
    await schedule_pending_email_send(record["id"])

    logger.info(
        "[UNDO-SEND] Email em fila (janela %ss): send_id=%s para=%s "
        "processo=%s user=%s",
        UNDO_SEND_WINDOW_SECONDS, record["id"], record.get("to_emails"),
        record.get("process_id"), record.get("created_by_email"),
    )

    return {
        "success": True,
        "queued": True,
        "send_id": record["id"],
        "undo_window_seconds": UNDO_SEND_WINDOW_SECONDS,
        "message": "Email a ser enviado — pode desfazer durante a janela de envio.",
    }


async def schedule_pending_email_send(
    send_id: str, delay_seconds: Optional[float] = None
) -> dict:
    """
    Agenda a execução do envio pendente por DUAS vias concorrentes:

    1. ARQ ``defer_by`` (se Redis disponível — o job sobrevive a restarts
       do processo API; consumidor: ``send_pending_webmail_email_task``).
    2. Timer in-process (rede de segurança — dev sem Redis / worker ARQ
       em baixo). Usa ``spawn_background_task`` (referência forte, ver
       services/background_tasks.py) para não ser recolhido pelo GC.

    Ambas chamam ``execute_pending_email_send`` — o claim atómico em Mongo
    garante execução única (sem duplicados).

    Returns:
        {"arq": bool, "timer": bool}
    """
    delay = float(
        delay_seconds if delay_seconds is not None else UNDO_SEND_WINDOW_SECONDS
    )

    scheduled_arq = False
    try:
        from services.task_queue import task_queue

        job_id = await task_queue.enqueue(
            "send_pending_webmail_email_task",
            send_id=send_id,
            defer_by=timedelta(seconds=delay),
        )
        scheduled_arq = bool(job_id)
        if not scheduled_arq:
            logger.info(
                "[UNDO-SEND] ARQ indisponível para %s — a relying no timer "
                "in-process.", send_id,
            )
    except Exception as e:
        logger.warning(
            "[UNDO-SEND] Erro ao enfileirar job ARQ para %s: %s — a relying "
            "no timer in-process.", send_id, e,
        )

    async def _timer():
        await asyncio.sleep(delay)
        try:
            await execute_pending_email_send(send_id)
        except Exception as e:
            logger.error(
                "[UNDO-SEND] Timer in-process falhou para %s: %s", send_id, e,
                exc_info=True,
            )

    try:
        from services.background_tasks import spawn_background_task

        spawn_background_task(_timer(), name=f"undo-send-timer:{send_id}")
    except Exception:
        asyncio.create_task(_timer())

    return {"arq": scheduled_arq, "timer": True}


async def execute_pending_email_send(send_id: str) -> dict:
    """
    Executa o envio real de um email pendente (idempotente).

    1. Claim atómico: só prossegue se conseguir transitar
       ``pending → claimed`` (update_one com filtro de status).
    2. Descarrega anexos temporários do S3 (se existirem).
    3. Envia via ``send_email`` (SMTP/Resend).
    4. Move os anexos de temp → permanente e limpa os registos temp.
    5. Sucesso → apaga o registo pending (o email "sent" vive em
       ``db.emails``, criado pelo próprio send_email quando tem
       process_id). Falha → marca ``failed`` para auditoria.

    Returns:
        {"executed": bool, "success": bool|None, "reason": str}
    """
    collection = _pending_collection()
    record = await collection.find_one({"id": send_id})
    if not record:
        return {"executed": False, "success": None, "reason": "not_found"}

    if record.get("status") != STATUS_PENDING:
        return {
            "executed": False,
            "success": None,
            "reason": f"status_{record.get('status')}",
        }

    # ── 1) Claim atómico (primeiro executor ganha) ────────────────
    claim = await collection.update_one(
        {"id": send_id, "status": STATUS_PENDING},
        {"$set": {"status": STATUS_CLAIMED, "claimed_at": datetime.now(timezone.utc).isoformat()}},
    )
    if not claim or not getattr(claim, "matched_count", 1):
        return {"executed": False, "success": None, "reason": "already_claimed"}

    # PACOTE 10 — monitor global: pending → processing
    await _update_task_log(
        record.get("task_log_id"),
        status="processing",
        progress_message="A enviar email...",
    )

    logger.info(
        "[UNDO-SEND] A executar envio real: send_id=%s para=%s",
        send_id, record.get("to_emails"),
    )

    # ── 2) Anexos temporários (download do S3 no momento do envio) ─
    email_attachments, temp_attachment_records, temp_keys_to_cleanup = (
        await _prepare_temp_attachments(record)
    )

    # ── 3) Envio real ─────────────────────────────────────────────
    try:
        result = await send_email(
            account_name=record.get("account") or "power",
            to_emails=record.get("to_emails") or [],
            subject=record.get("subject") or "",
            body=record.get("body") or "",
            body_html=record.get("body_html"),
            cc_emails=record.get("cc_emails"),
            process_id=record.get("process_id"),
            created_by=record.get("created_by"),
            attachments=email_attachments if email_attachments else None,
            active_company_id=record.get("company_id"),
            from_email=record.get("from_email"),
            reply_to=record.get("from_email"),
        )
    except Exception as e:
        logger.error(
            "[UNDO-SEND] Excepção no envio de %s: %s", send_id, e, exc_info=True,
        )
        await _mark_failed(send_id, str(e), task_log_id=record.get("task_log_id"))
        return {"executed": True, "success": False, "reason": f"exception:{e}"}

    if not result or not result.get("success"):
        error = (result or {}).get("error", "Erro desconhecido no envio")
        logger.error("[UNDO-SEND] Envio falhou para %s: %s", send_id, error)
        await _mark_failed(send_id, error, task_log_id=record.get("task_log_id"))
        return {"executed": True, "success": False, "reason": error}

    # ── 4) Mover anexos temp → permanente + limpeza ───────────────
    await _finalize_attachments(record, temp_attachment_records, temp_keys_to_cleanup)

    # ── 5) Sucesso → apagar registo pending ──────────────────────
    try:
        await collection.delete_one({"id": send_id})
    except Exception as e:
        logger.warning("[UNDO-SEND] Erro ao apagar registo %s: %s", send_id, e)

    logger.info(
        "[UNDO-SEND] Email enviado com sucesso: send_id=%s anexos=%s",
        send_id, len(temp_attachment_records),
    )

    # PACOTE 10 — monitor global: processing → completed (fica visível
    # no widget com estado Success até o utilizador confirmar/OK).
    await _update_task_log(
        record.get("task_log_id"),
        status="completed",
        progress=100,
        progress_message="Email enviado com sucesso.",
    )
    return {"executed": True, "success": True, "reason": "sent"}


async def cancel_pending_email_send(send_id: str, user: dict) -> dict:
    """
    Cancela um envio pendente (endpoint POST /emails/{id}/cancel-send).

    Regras:
    - Só o autor do envio (ou admin) pode cancelar.
    - Só cancelável enquanto ``status == pending`` (dentro da janela).
    - O cancelamento APAGA o registo — nada sai para a rede SMTP e o
      utilizador regressa ao modo de edição do rascunho (o payload é
      devolvido na resposta para o frontend repovoar o composer).

    Raises:
        HTTPException: 404 (não encontrado), 403 (sem permissão),
        409 (janela expirada / já enviado ou em processamento).
    """
    collection = _pending_collection()
    record = await collection.find_one({"id": send_id})
    if not record:
        raise HTTPException(
            status_code=404,
            detail="Envio pendente não encontrado (já enviado ou cancelado).",
        )

    requester_id = user.get("id")
    requester_role = (user.get("effective_role") or user.get("role") or "").lower()
    if record.get("created_by") != requester_id and requester_role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Só o autor do envio pode cancelá-lo.",
        )

    if record.get("status") != STATUS_PENDING:
        status = record.get("status")
        if status == STATUS_CLAIMED:
            raise HTTPException(
                status_code=409,
                detail="O email já está a ser enviado — já não é possível cancelar.",
            )
        raise HTTPException(
            status_code=409,
            detail=f"O envio já foi processado (estado: {status}).",
        )

    await collection.delete_one({"id": send_id, "status": STATUS_PENDING})

    # PACOTE 10 — monitor global: o envio desfeito sai do widget
    # (task_log cancelada em vez de ficar pendente para sempre).
    await _update_task_log(
        record.get("task_log_id"),
        status="cancelled",
        progress_message="Envio cancelado pelo utilizador (Desfazer).",
    )

    logger.info(
        "[UNDO-SEND] Envio cancelado pelo utilizador: send_id=%s user=%s",
        send_id, requester_id,
    )

    # Payload do rascunho para o frontend regressar ao modo de edição
    return {
        "success": True,
        "cancelled": True,
        "send_id": send_id,
        "message": "Envio cancelado — pode continuar a editar o rascunho.",
        "draft": {
            "to_emails": record.get("to_emails") or [],
            "cc_emails": record.get("cc_emails") or [],
            "subject": record.get("subject") or "",
            "body": record.get("body") or "",
            "body_html": record.get("body_html"),
            "process_id": record.get("process_id"),
            "attachment_ids": record.get("attachment_ids") or [],
            "from_box": record.get("from_box"),
            "account": record.get("account"),
        },
    }


# ====================================================================
# HELPERS DE ANEXOS (extraídos de run_send_email para reuso no envio
# diferido — o download do S3 passa a acontecer no MOMENTO do envio)
# ====================================================================

async def _prepare_temp_attachments(record: dict) -> tuple:
    """Descarrega os anexos temporários (S3) referenciados no registo.

    Returns:
        (email_attachments, temp_attachment_records, temp_keys_to_cleanup)
    """
    email_attachments: list = []
    temp_attachment_records: list = []
    temp_keys_to_cleanup: list = []

    attachment_ids = record.get("attachment_ids") or []
    if not attachment_ids:
        return email_attachments, temp_attachment_records, temp_keys_to_cleanup

    from services.s3_storage import s3_service

    temp_docs = await db.temp_attachments.find(
        {"id": {"$in": attachment_ids}, "user_id": record.get("created_by")},
        {"_id": 0},
    ).to_list(20)

    if len(temp_docs) != len(attachment_ids):
        found_ids = {d["id"] for d in temp_docs}
        missing = [aid for aid in attachment_ids if aid not in found_ids]
        logger.warning(f"Temp attachments not found: {missing}")
        # Continua com os anexos disponíveis (degradação graciosa)

    for temp_doc in temp_docs:
        temp_key = temp_doc["temp_key"]
        file_name = temp_doc["file_name"]
        mime_type = temp_doc.get("mime_type", "application/octet-stream")

        try:
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

    return email_attachments, temp_attachment_records, temp_keys_to_cleanup


async def _finalize_attachments(
    record: dict,
    temp_attachment_records: list,
    temp_keys_to_cleanup: list,
) -> None:
    """Pós-envio: move anexos temp→permanente e limpa registos temporários."""
    if not temp_attachment_records or not record.get("process_id"):
        return

    from services.s3_storage import s3_service

    # Email enviado mais recente deste user+processo (criado por send_email)
    sent_email = await db.emails.find_one(
        {
            "process_id": record.get("process_id"),
            "created_by": record.get("created_by"),
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
                    lambda sk=att_rec["temp_key"], pk=permanent_s3_key: s3_service.rename_file(sk, pk),
                )
                if moved:
                    logger.info(f"Attachment moved: {att_rec['temp_key']} -> {permanent_s3_key}")
                else:
                    logger.warning(f"Failed to move attachment: {att_rec['temp_key']}")
                    permanent_s3_key = att_rec["temp_key"]  # Fallback: manter temp key
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

        existing_attachments = sent_email.get("attachments", [])
        await db.emails.update_one(
            {"id": sent_email["id"]},
            {"$set": {"attachments": existing_attachments + permanent_attachments}},
        )

    # Limpar metadados temporários do Mongo
    try:
        await db.temp_attachments.delete_many(
            {"id": {"$in": [r["id"] for r in temp_attachment_records]}}
        )
    except Exception as e:
        logger.warning(f"Erro ao limpar temp_attachments: {e}")

    # Limpar ficheiros temporários do S3 (os que não foram movidos)
    for temp_key in temp_keys_to_cleanup:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda tk=temp_key: s3_service.delete_file(tk))
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {temp_key}: {e}")


async def _mark_failed(
    send_id: str, error: str, task_log_id: Optional[str] = None
) -> None:
    """Marca um registo pending como failed (mantido para auditoria).

    PACOTE 10 — propaga também ao task_log do monitor global (widget
    "Processos em Segundo Plano") para a falha ser visível na topbar.
    """
    try:
        await _pending_collection().update_one(
            {"id": send_id},
            {"$set": {
                "status": STATUS_FAILED,
                "error": str(error)[:500],
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    except Exception as e:
        logger.warning(f"Erro ao marcar send {send_id} como failed: {e}")

    # PACOTE 10 — monitor global: → failed (badge vermelho no widget)
    await _update_task_log(
        task_log_id,
        status="failed",
        error_message=str(error)[:500],
        progress_message="O envio do email falhou.",
    )


async def recover_stale_pending_sends(older_than_seconds: int = 300) -> int:
    """
    Rede de segurança: reexecuta envios pendentes cuja janela já passou
    há muito tempo (p.ex. processo API reiniciado a meio da janela com
    Redis indisponível — ARQ e timer perderam-se).

    Chamado manualmente ou por cron do worker. Retorna o número de
    envios re-executados.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)).isoformat()
    collection = _pending_collection()
    stale = await collection.find(
        {"status": STATUS_PENDING, "send_after": {"$lt": cutoff}}
    ).to_list(100)

    recovered = 0
    for record in stale:
        result = await execute_pending_email_send(record["id"])
        if result.get("executed"):
            recovered += 1
    if stale:
        logger.info(
            "[UNDO-SEND] Recuperação de envios obsoletos: %d processados (%d executados)",
            len(stale), recovered,
        )
    return recovered


# Convenção do repo: entrypoints das rotas prefixados com run_*
async def run_cancel_pending_email_send(send_id: str, current_user: dict) -> dict:
    """POST /emails/{send_id}/cancel-send — cancela o envio pendente."""
    return await cancel_pending_email_send(send_id, current_user)
