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
import html
import logging
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from database import db
from services.document_portal_counts import (
    COMPLETED_PORTAL_STATUSES,
    parse_expected_count,
)

logger = logging.getLogger(__name__)

# De onde sai o nome legível de um pedido, por ordem de preferência. O
# `custom_label` é o que foi PEDIDO ("Recibo de Vencimento"); o
# `original_filename` é o que o cliente chamou ao ficheiro. Listar o
# primeiro é o que faz o email confirmar o pedido, e não o upload.
CAMPOS_DO_NOME_DO_PEDIDO: tuple[str, ...] = (
    "custom_label",
    "original_filename",
    "filename",
    "category",
)


def nome_legivel_do_pedido(doc: Optional[dict]) -> str:
    """O nome de um documento recebido, como o cliente o reconhece."""
    if not isinstance(doc, dict):
        return ""
    for campo in CAMPOS_DO_NOME_DO_PEDIDO:
        valor = doc.get(campo)
        if valor is not None and str(valor).strip():
            return str(valor).strip()
    return ""


async def nomes_dos_documentos_recebidos(process_id: str) -> list[str]:
    """Os documentos que o cliente submeteu, para a lista do email.

    Lote 2, ponto 2: o email confirmava "toda a documentação" sem dizer
    QUAL — e uma confirmação que não enumera o que recebeu não serve de
    recibo. Quem a lê não consegue detectar que faltou uma peça.

    Os estados de "concluído" vêm de `document_portal_counts`, nunca de
    uma lista escrita aqui: duas listas de estados divergem na primeira
    vez que aparecer um estado novo.

    NUNCA levanta — um email sem a lista é melhor do que email nenhum.
    """
    try:
        recebidos = await db.documents.find(
            {"process_id": process_id, "status": {"$in": list(COMPLETED_PORTAL_STATUSES)}},
            {"_id": 0, "custom_label": 1, "original_filename": 1, "filename": 1,
             "category": 1, "attached_files": 1},
        ).to_list(200)
    except Exception as e:  # pragma: no cover - degradação
        logger.warning("[DocsComplete] Não foi possível listar os documentos: %s", e)
        return []

    nomes: list[str] = []
    vistos: set[str] = set()
    for doc in recebidos:
        nome = nome_legivel_do_pedido(doc)
        if not nome or nome.lower() in vistos:
            continue
        vistos.add(nome.lower())
        # Quando o pedido trouxe mais do que um ficheiro, dizê-lo: é a
        # diferença entre "recebemos os recibos" e "recebemos 3 recibos",
        # e é por aí que o cliente confirma a quantidade.
        quantos = len(doc.get("attached_files") or [])
        nomes.append(f"{nome} ({quantos} ficheiros)" if quantos > 1 else nome)
    return nomes


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
    #       Documentos OPCIONAIS (is_optional=True) nunca bloqueiam esta
    #       notificação — só os obrigatórios/pedidos normais contam.
    pending_count = await db.documents.count_documents({
        "process_id": process_id,
        "status": {"$in": ["REQUESTED", "PENDING", "requested", "pending"]},
        "is_optional": {"$ne": True},
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

    # Lote 2, ponto 2: a confirmação ENUMERA o que foi recebido. Os nomes
    # vão no CORPO e os ficheiros NUNCA em anexo — reenviar ao cliente os
    # documentos que ele acabou de submeter põe dados pessoais a circular
    # por email sem necessidade nenhuma, e o Portal é onde eles vivem.
    nomes_recebidos = await nomes_dos_documentos_recebidos(process_id)

    subject = "Documentação Recebida com Sucesso - Em Análise"
    lista_em_texto = (
        "\nDocumentos recebidos:\n"
        + "".join(f"  - {nome}\n" for nome in nomes_recebidos)
        if nomes_recebidos
        else ""
    )
    text_body = (
        f"Olá {client_name},\n\n"
        "Recebemos com sucesso toda a documentação submetida via Portal do Cliente.\n"
        f"{lista_em_texto}"
        "\nO seu processo entrou agora em fase de Análise de Crédito e entraremos em "
        "contacto brevemente para os próximos passos.\n\n"
        # PACOTE DI — marca client-facing actualizada para Precision Crédito.
        "Obrigado pela confiança,\nEquipa Precision Crédito"
    )
    html_body = _build_documents_complete_html(client_name, nomes_recebidos)

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


def _escapar(texto: str) -> str:
    """O nome do documento vem de um ficheiro que o CLIENTE nomeou.

    Entra num corpo HTML, logo é conteúdo externo: sem escape, um nome
    com `<` parte o email, e com `<script>` leva-o lá dentro.
    """
    return html.escape(str(texto or ""), quote=True)


def _lista_de_nomes_em_html(nomes: list[str]) -> str:
    """A lista de documentos recebidos. Vazia não desenha caixa nenhuma —
    uma caixa com o título e nada dentro lê-se como um erro."""
    if not nomes:
        return ""
    itens = "".join(f"<li style=\"margin:0 0 4px;\">{_escapar(n)}</li>" for n in nomes)
    return (
        '<div style="background:#f9fafb;border:1px solid #e5e7eb;padding:14px 16px;'
        'margin:0 0 16px;border-radius:4px;">'
        '<p style="margin:0 0 8px;font-weight:bold;">Documentos recebidos:</p>'
        f'<ul style="margin:0;padding-left:20px;">{itens}</ul>'
        "</div>"
    )


def _build_documents_complete_html(client_name: str, nomes_recebidos: Optional[list] = None) -> str:
    lista = _lista_de_nomes_em_html(nomes_recebidos or [])
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
        {lista}
        <div style="background:#ecfdf5;border-left:4px solid #0f766e;padding:14px 16px;
                    margin:0 0 16px;border-radius:4px;">
          <strong>O seu processo entrou agora em fase de «Análise de Crédito».</strong>
          Entraremos em contacto brevemente para os próximos passos.
        </div>
        <p style="margin:0 0 8px;">Obrigado pela confiança,</p>
        <p style="margin:0;"><strong>Equipa Precision Crédito</strong></p>
      </div>
      <p style="font-size:12px;color:#9ca3af;text-align:center;margin-top:16px;">
        Este é um email automático — por favor não responda.
      </p>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────
# Geração automática de pedidos de documento (Pacote G — ponto 1)
# ─────────────────────────────────────────────────────────────────────
async def _generate_document_requests_for_list(
    items: list,
    *,
    source: str,
    is_optional: bool,
    process_id: Optional[str],
    client_id: Optional[str],
    requested_by: Optional[str],
    requested_by_name: str,
) -> dict:
    """Gera pedidos REQUESTED para uma lista de documentos (obrigatórios OU
    opcionais), com idempotência própria por `source`. Documentos opcionais
    NUNCA bloqueiam `is_mandatory_checklist_complete` (que só conta
    source="mandatory_checklist") — apenas ficam disponíveis no Portal."""
    if not items:
        return {"created": 0, "skipped": 0, "total": 0, "reason": "empty_list"}

    idem_query: dict = {"source": source}
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
            "total": len(items),
            "reason": "already_generated",
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    docs_to_insert = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        category = (item.get("category") or "outros").strip().lower() or "outros"
        if not name:
            continue
        # BUGFIX (E2E — lógica de quantidade, Set 2026): grava a quantidade
        # pedida (checklist SystemConfig, campo opcional `quantity`, int>=1)
        # como `expected_count` — o pedido só fica RECEIVED quando o número
        # de ficheiros carregados atingir esta quantidade.
        expected_count = parse_expected_count(item)
        doc = {
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "category": category,
            "filename": None,
            "original_filename": None,
            "status": "REQUESTED",
            "notes": f"Documento {'opcional' if is_optional else 'obrigatório'}: {name}",
            "custom_label": name,
            "is_optional": is_optional,
            "expected_count": expected_count,
            "requested_by": requested_by or "system",
            "requested_by_name": requested_by_name,
            "source": source,
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
                f"[MandatoryDocs] {len(docs_to_insert)} pedidos "
                f"({'opcionais' if is_optional else 'obrigatórios'}) gerados para {scope}"
            )
        except Exception as e:
            logger.error(f"[MandatoryDocs] Erro ao inserir pedidos ({source}): {e}")
            return {"created": 0, "skipped": 0, "total": len(items), "reason": "insert_error"}

    return {"created": len(docs_to_insert), "skipped": 0, "total": len(items), "reason": "ok"}


async def generate_mandatory_document_requests(
    process_id: Optional[str] = None,
    company_id: Optional[str] = None,
    requested_by: Optional[str] = None,
    requested_by_name: str = "Sistema",
    client_id: Optional[str] = None,
) -> dict:
    """
    Gera pedidos de documento (status=REQUESTED) com base na checklist
    SystemConfig (`mandatory_documents`) — Obrigatórios (`documents`) e
    Opcionais (`optional_documents`).

    Pode ser ligado a um processo (fluxo legado/staff) OU a um cliente
    ainda sem processo (registo público — process_id=None, client_id set).

    Idempotente por process_id ou client_id + source (mandatory_checklist /
    mandatory_checklist_optional).

    Os pedidos Obrigatórios (source="mandatory_checklist") são os únicos
    considerados por `is_mandatory_checklist_complete` — os Opcionais
    (source="mandatory_checklist_optional", is_optional=True) nunca
    bloqueiam a criação do processo.
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
    if not md or not md.enabled or (not md.documents and not md.optional_documents):
        return {"created": 0, "skipped": 0, "total": 0, "reason": "disabled_or_empty"}

    mandatory_result = await _generate_document_requests_for_list(
        md.documents,
        source="mandatory_checklist",
        is_optional=False,
        process_id=process_id,
        client_id=client_id,
        requested_by=requested_by,
        requested_by_name=requested_by_name,
    )
    optional_result = await _generate_document_requests_for_list(
        md.optional_documents,
        source="mandatory_checklist_optional",
        is_optional=True,
        process_id=process_id,
        client_id=client_id,
        requested_by=requested_by,
        requested_by_name=requested_by_name,
    )

    return {
        "created": mandatory_result["created"] + optional_result["created"],
        "skipped": mandatory_result["skipped"] + optional_result["skipped"],
        "total": mandatory_result["total"] + optional_result["total"],
        "mandatory": mandatory_result,
        "optional": optional_result,
        "reason": "ok",
    }
