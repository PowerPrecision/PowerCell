"""
====================================================================
SERVIÇO: Portal Documents Notify — Pacote G
====================================================================
Gatilho inteligente para o Portal do Cliente.

Quando o cliente termina de submeter TODA a documentação exigida, o
sistema envia automaticamente um email de confirmação ao cliente em nome
do intermediário atribuído, com fallback para o SMTP geral da empresa.

Função principal: check_and_notify_documents_complete(process_id, company_id)

Gatilho: invocada após cada `confirm_portal_upload` em routes/portal.py.

Idempotente: só dispara uma vez por processo (flag
`documents_complete_notified_at` no documento do processo).

Lógica:
  1. Se o processo já foi notificado → não faz nada.
  2. Conta documentos com status REQUESTED/PENDING.
  3. Se > 0 → ainda há pendentes → não faz nada.
  4. Se = 0 → todos submetidos → dispara:
     a. Resolve SMTP do intermediário (resolve_email_config_for_sync
        já faz herança user→company→system).
     b. Se tiver config pessoal funcional → envia pelo SMTP do intermediário.
     c. Caso contrário → fallback para send_email(force_system=True).
  5. Marca flag de idempotência + regista log no histórico.
====================================================================
"""
import asyncio
import logging
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from database import db

logger = logging.getLogger(__name__)


async def check_and_notify_documents_complete(
    process_id: str,
    company_id: Optional[str] = None,
) -> dict:
    """
    Verifica se TODOS os documentos pedidos (REQUESTED/PENDING) do processo foram
    submetidos pelo cliente via Portal. Quando sim, envia automaticamente um email
    de confirmação ao cliente usando o SMTP EXATO do intermediário atribuído
    (com fallback para o SMTP geral da empresa) e regista no histórico.

    Gatilho: invocada após cada `confirm_portal_upload`.
    Idempotente: só dispara uma vez por processo (flag documents_complete_notified_at).
    """
    from services.encryption import encryption_service
    from services.email_config_resolver import resolve_email_config_for_sync
    from services.email_service import send_email
    from services.history import log_history

    # ─── 1) Processo (dados frescos) + guarda de idempotência ───────────────
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return {"success": False, "reason": "process_not_found"}

    if process.get("documents_complete_notified_at"):
        return {"success": False, "reason": "already_notified"}

    # ─── 2) VERIFICAÇÃO: ainda há documentos pedidos pendentes? ─────────────
    #       Se SIM → não faz nada. Se NÃO (todos uploaded/validated) → dispara.
    pending_count = await db.documents.count_documents({
        "process_id": process_id,
        "status": {"$in": ["REQUESTED", "PENDING", "requested", "pending"]},
    })
    if pending_count > 0:
        return {"success": False, "reason": "pending_documents", "pending": pending_count}

    client_email = process.get("client_email")
    client_name = process.get("client_name", "Cliente")
    if not client_email:
        return {"success": False, "reason": "no_client_email"}

    company = company_id or process.get("company") or process.get("company_id")

    # ─── 3) Resolver SMTP do intermediário atribuído ───────────────────────
    #    resolve_email_config_for_sync já implementa a herança:
    #       user → company → system   (SMTP exato do intermediário,
    #       caindo para o SMTP geral da empresa se aquele não tiver config)
    intermediary_ids = _gather_intermediary_ids(process)
    resolved = None
    chosen_intermediary = None
    for uid in intermediary_ids:
        try:
            cfg = await resolve_email_config_for_sync(uid, active_company_id=company)
        except Exception as e:
            logger.warning(f"[DocsComplete] Erro ao resolver SMTP do intermediário {uid}: {e}")
            cfg = None
        # Só serve se tiver servidor + password própria (envio SMTP direto)
        if cfg and cfg.get("has_password") and cfg.get("smtp_server") and cfg.get("encrypted_password"):
            resolved = cfg
            chosen_intermediary = uid
            break

    subject = "Documentação Recebida com Sucesso - Em Análise"
    text_body = (
        f"Olá {client_name},\n\n"
        "Recebemos com sucesso toda a documentação submetida via Portal do Cliente.\n"
        "O seu processo entrou agora em fase de Análise de Crédito e entraremos em "
        "contacto brevemente para os próximos passos.\n\n"
        "Obrigado pela confiança,\nEquipa PowerCell"
    )
    html_body = _build_documents_complete_html(client_name)

    sent = False
    source = None

    # ─── 4a) CAMINHO A — Envio pelo SMTP EXATO do intermediário ────────────
    if resolved:
        try:
            password = encryption_service.decrypt(resolved["encrypted_password"])
            from_email = resolved.get("email_address") or ""
            ok = await _send_via_smtp(
                smtp_server=resolved["smtp_server"],
                smtp_port=int(resolved.get("smtp_port", 465)),
                from_email=from_email,
                password=password,
                to_email=client_email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                reply_to=from_email,
            )
            if ok:
                sent = True
                source = f"intermediary:{chosen_intermediary}({resolved.get('config_source')})"
                logger.info(f"[DocsComplete] Email enviado via SMTP do intermediário {chosen_intermediary}")
        except Exception as e:
            logger.warning(f"[DocsComplete] SMTP do intermediário falhou ({chosen_intermediary}): {e}")

    # ─── 4b) CAMINHO B — Fallback para o SMTP geral da empresa ─────────────
    if not sent:
        try:
            fb = await send_email(
                account_name="precision",
                to_emails=[client_email],
                subject=subject,
                body=text_body,
                body_html=html_body,
                process_id=process_id,
                created_by=chosen_intermediary,
                force_system=True,            # nunca usa credenciais pessoais
                system_purpose="DOCUMENTS",   # tenta transporter específico antes do fallback
                active_company_id=company,
            )
            if fb.get("success"):
                sent = True
                source = "company_fallback"
                logger.info("[DocsComplete] Email enviado via SMTP geral da empresa (fallback)")
        except Exception as e:
            logger.error(f"[DocsComplete] Fallback da empresa falhou: {e}")

    if not sent:
        return {"success": False, "reason": "email_send_failed"}

    # ─── 5) Marcar idempotência + Log no histórico (activities) ────────────
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"documents_complete_notified_at": now_iso}}
    )

    try:
        await log_history(
            process_id,
            user={"id": None, "name": "Sistema (Portal)", "role": "system"},
            action="DOCUMENTS_COMPLETE_EMAIL_SENT",
            field="documento",
            old_value=None,
            new_value="Email automático de confirmação de documentação enviado via Portal",
        )
    except Exception as e:
        logger.warning(f"[DocsComplete] Erro ao registar histórico: {e}")

    return {"success": True, "source": source, "notified_at": now_iso}


# ─────────────────────────────────────────────────────────────────────
# Helpers auxiliares
# ─────────────────────────────────────────────────────────────────────
def _gather_intermediary_ids(process: dict) -> list:
    """Reúne os IDs dos intermediários atribuídos ao processo (sem duplicados, por ordem)."""
    raw = []
    raw.append(process.get("intermediario_id"))
    raw += (process.get("assigned_mediador_ids") or [])
    raw.append(process.get("assigned_mediador_id"))
    raw += (process.get("assigned_consultor_ids") or [])
    raw.append(process.get("assigned_consultor_id"))
    seen, ordered = set(), []
    for uid in raw:
        if uid and uid not in seen:
            seen.add(uid)
            ordered.append(uid)
    return ordered


async def _send_via_smtp(smtp_server, smtp_port, from_email, password,
                         to_email, subject, text_body, html_body, reply_to=None) -> bool:
    """Envio SMTP_SSL direto (numa thread p/ não bloquear o event loop)."""
    def _sync():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=ctx, timeout=30) as srv:
            srv.login(from_email, password)
            srv.sendmail(from_email, [to_email], msg.as_bytes())
        return True
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)
    except Exception as e:
        logger.error(f"[DocsComplete] Erro SMTP direto: {e}")
        return False


def _build_documents_complete_html(client_name: str) -> str:
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;
                color:#1f2937;line-height:1.6;">
      <div style="background:#0f766e;padding:24px;border-radius:8px 8px 0 0;">
        <h1 style="color:#ffffff;margin:0;font-size:20px;">Documentação Recebida com Sucesso</h1>
      </div>
      <div style="padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">
        <p style="margin:0 0 16px;">Olá <strong>{client_name}</strong>,</p>
        <p style="margin:0 0 16px;">
          Recebemos com sucesso <strong>toda a documentação</strong> que submeteu através
          do Portal do Cliente. Obrigado pela rapidez.
        </p>
        <div style="background:#ecfdf5;border-left:4px solid #0f766e;padding:14px 16px;
                    margin:0 0 16px;border-radius:4px;">
          <strong>O seu processo entrou agora em fase de «Análise de Crédito».</strong>
          Entraremos em contacto brevemente para os próximos passos.
        </div>
        <p style="margin:0 0 8px;">Obrigado pela confiança,</p>
        <p style="margin:0;"><strong>Equipa PowerCell</strong></p>
      </div>
      <p style="font-size:12px;color:#9ca3af;text-align:center;margin-top:16px;">
        Este é um email automático — por favor não responda.
      </p>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────
# Geração automática de pedidos de documento (Pacote G — ponto 1)
# ─────────────────────────────────────────────────────────────────────
async def generate_mandatory_document_requests(
    process_id: Optional[str] = None,
    company_id: Optional[str] = None,
    requested_by: Optional[str] = None,
    requested_by_name: str = "Sistema",
    client_id: Optional[str] = None,
) -> dict:
    """
    Gera pedidos de documento (status=REQUESTED) com base na checklist
    SystemConfig (`mandatory_documents`).

    Pode ser ligado a um processo (fluxo legado/staff) OU a um cliente
    ainda sem processo (registo público — process_id=None, client_id set).

    Idempotente por process_id ou client_id + source=mandatory_checklist.
    """
    from services.system_config import get_system_config

    if not process_id and not client_id:
        return {"created": 0, "skipped": 0, "total": 0, "reason": "missing_scope"}

    try:
        config = await get_system_config(company_id or "default")
    except Exception as e:
        logger.warning(f"[MandatoryDocs] Erro ao carregar config: {e}")
        return {"created": 0, "skipped": 0, "total": 0, "reason": "config_error"}

    md = config.mandatory_documents
    if not md or not md.enabled or not md.documents:
        return {"created": 0, "skipped": 0, "total": 0, "reason": "disabled_or_empty"}

    # Idempotência
    idem_query: dict = {"source": "mandatory_checklist"}
    if process_id:
        idem_query["process_id"] = process_id
    else:
        idem_query["client_id"] = client_id
        idem_query["$or"] = [
            {"process_id": None},
            {"process_id": ""},
            {"process_id": {"$exists": False}},
        ]

    existing = await db.documents.count_documents(idem_query)
    if existing > 0:
        return {
            "created": 0,
            "skipped": existing,
            "total": len(md.documents),
            "reason": "already_generated",
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    docs_to_insert = []
    for item in md.documents:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        category = (item.get("category") or "outros").strip().lower() or "outros"
        if not name:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "category": category,
            "filename": None,
            "original_filename": None,
            "status": "REQUESTED",
            "notes": f"Documento obrigatório: {name}",
            "custom_label": name,
            "requested_by": requested_by or "system",
            "requested_by_name": requested_by_name,
            "source": "mandatory_checklist",
            "file_size": None,
            "content_type": None,
            "uploaded_at": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        if client_id:
            doc["client_id"] = client_id
        docs_to_insert.append(doc)

    if docs_to_insert:
        try:
            await db.documents.insert_many(docs_to_insert, ordered=False)
            scope = process_id or f"client:{client_id}"
            logger.info(
                f"[MandatoryDocs] {len(docs_to_insert)} pedidos gerados para {scope}"
            )
        except Exception as e:
            logger.error(f"[MandatoryDocs] Erro ao inserir pedidos: {e}")
            return {"created": 0, "skipped": 0, "total": len(md.documents), "reason": "insert_error"}

    return {
        "created": len(docs_to_insert),
        "skipped": 0,
        "total": len(md.documents),
        "reason": "ok",
    }
