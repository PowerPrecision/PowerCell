"""Scrapers Finanças / Segurança Social no Portal + MFA/jobs.

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import gc as _gc
import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from database import db
from services.portal_assigned_users import get_all_assigned_user_ids as _get_all_assigned_user_ids
from services.notification_service import send_notification_with_preference_check
from services.websocket_manager import WSEventType
from services.realtime_delivery import entregar_na_sala, sala_do_processo
from services.gov_fetch_archive import arquivar_documentos, rotulos_em_falta
from services.gov_fetch_jobs import (
    criar_job,
    encerrar_jobs_mortos,
    job_activo_do_processo,
    ler_job_do_processo,
)
from services.gov_fetch_policy import MFA_ESPERA_SEGUNDOS

logger = logging.getLogger(__name__)


# ====================================================================
# NOTIFICAÇÃO DO FIM DE UMA RECOLHA — dois eventos, duas audiências
# ====================================================================
# Motivos de falha que o CLIENTE pode ver, porque são sobre acções DELE: as
# credenciais que introduziu e o código de confirmação que lhe foi pedido.
# Tudo o que não estiver neste mapa colapsa em `indisponivel` — o cliente não
# precisa do nosso classificador interno, e um "unexpected_error" no ecrã dele
# é ruído que não o ajuda a agir.
#
# É um mapa FECHADO com omissão segura, e não um `.replace()` ou um passa-tudo:
# um motivo novo do lado do scraper aparece ao cliente como "indisponível" até
# alguém decidir que ele o deve ver.
MOTIVOS_VISIVEIS_AO_CLIENTE: dict[str, str] = {
    "credenciais_invalidas": "credenciais_invalidas",
    "mfa_requerido": "confirmacao_necessaria",
    "mfa_timeout": "confirmacao_expirada",
    "mfa_codigo_incorreto": "confirmacao_incorreta",
}
MOTIVO_GENERICO = "indisponivel"


def motivo_para_o_cliente(error_type: str | None) -> str:
    """Traduz o classificador interno no motivo que o cliente pode ver."""
    return MOTIVOS_VISIVEIS_AO_CLIENTE.get(error_type or "", MOTIVO_GENERICO)


async def _notificar_recolha(
    process_id: str,
    source: str,
    *,
    docs_count: int = 0,
    error_type: str | None = None,
) -> None:
    """Notifica a sala do processo sobre o fim de uma recolha no Estado.

    Emite DOIS eventos, e são dois de propósito:

    * `DOCUMENT_UPLOADED` — para a EQUIPA, com o payload de sempre (incluindo o
      `error` interno). É o que o comentário original deste ficheiro dizia:
      "Notificar equipa via WebSocket".
    * `PORTAL_GOV_PROGRESS` — para o CLIENTE, e é o único dos dois que está na
      lista de permissão do socket do Portal (`ws_client_identity`).

    Porque não reaproveitar o primeiro para o cliente: `document_uploaded` tem
    nome genérico e nada impede que amanhã um upload da equipa o emita com o
    NOME do ficheiro no payload — e nesse dia o cliente passaria a ver nomes de
    documentos internos, em silêncio. Um evento próprio tem um contrato próprio.

    Nunca levanta: uma notificação perdida degrada a UI para polling e não pode
    fazer falhar a recolha que já correu.
    """
    para_a_equipa: dict = {"process_id": process_id, "source": source}
    para_o_cliente: dict = {"process_id": process_id, "source": source}

    if error_type:
        para_a_equipa["error"] = error_type
        para_o_cliente["estado"] = "falhou"
        para_o_cliente["motivo"] = motivo_para_o_cliente(error_type)
    else:
        para_a_equipa["documents_count"] = docs_count
        para_o_cliente["estado"] = "concluido"
        para_o_cliente["documents_count"] = docs_count

    try:
        await entregar_na_sala(
            sala_do_processo(process_id),
            WSEventType.DOCUMENT_UPLOADED,
            para_a_equipa,
        )
    except Exception as ws_err:
        logger.warning(f"[PORTAL-BG] Erro ao notificar a equipa via WebSocket: {ws_err}")

    try:
        await entregar_na_sala(
            sala_do_processo(process_id),
            WSEventType.PORTAL_GOV_PROGRESS,
            para_o_cliente,
        )
    except Exception as ws_err:
        logger.warning(f"[PORTAL-BG] Erro ao notificar o cliente via WebSocket: {ws_err}")


# ====================================================================
# FONTES — o que distingue Finanças de Segurança Social
# ====================================================================
# Os dois pipelines eram duas cópias de ~450 linhas que só diferiam nisto.
# As cópias divergiam sem dar erro (uma tinha `mfa_no_input` mapeado e a outra
# não), e uma correcção feita numa ficava por fazer na outra.
@dataclass(frozen=True)
class FonteGovernamental:
    chave: str  # `source` do job e do email
    nome: str  # como o cliente a conhece
    origem: str  # `source` dos documentos arquivados
    enviado_por: str  # `uploaded_by` dos documentos arquivados
    nome_do_identificador: str  # NIF / NISS
    funcao_do_scraper: str  # nome em `services.gov_scraper`
    nome_da_equipa: str  # como aparece na notificação à equipa
    ids_do_processo: str  # etiqueta do WS (`auto_financas`...)


FINANCAS = FonteGovernamental(
    chave="financas",
    nome="Portal das Finanças",
    origem="auto_financas",
    enviado_por="system_financas_scraper",
    nome_do_identificador="NIF",
    funcao_do_scraper="fetch_financas_documents",
    nome_da_equipa="Portal das Finanças",
    ids_do_processo="auto_financas",
)
SEGURANCA_SOCIAL = FonteGovernamental(
    chave="seguranca_social",
    nome="Segurança Social",
    origem="auto_seguranca_social",
    enviado_por="system_seguranca_social_scraper",
    nome_do_identificador="NISS",
    funcao_do_scraper="fetch_seg_social_documents",
    nome_da_equipa="Segurança Social",
    ids_do_processo="auto_seguranca_social",
)

# Erro do scraper -> o que se grava no job (`error_type`). O que não está aqui
# é `scraper_unavailable`.
_TIPO_DE_ERRO = {
    "credenciais_invalidas": "credenciais_invalidas",
    "mfa_requerido": "mfa_requerido",
    "mfa_timeout": "mfa_timeout",
    "mfa_codigo_incorreto": "mfa_codigo_incorreto",
    "mfa_no_input": "mfa_error",
    "mfa_error": "mfa_error",
    "timeout": "timeout_scraper",
    "timeout_login": "timeout_scraper",
    "sem_documentos": "sem_documentos",
    "scraper_ocupado": "scraper_ocupado",
    "arquivo_falhou": "arquivo_falhou",
    "memory_error": "scraper_unavailable",
    "MemoryError": "scraper_unavailable",
}


def classificar_falha(error_detail: str | None, fonte: FonteGovernamental) -> tuple[str, str]:
    """(`error_type`, mensagem para o cliente) de uma recolha falhada."""
    tipo = _TIPO_DE_ERRO.get(error_detail or "", "scraper_unavailable")
    manual = (
        f"Pode descarregar os documentos directamente do {fonte.nome} e enviá-los "
        f"através do botão de upload."
    )
    mensagens = {
        "credenciais_invalidas": (
            f"As credenciais que introduziu estão incorretas. Verifique o seu "
            f"{fonte.nome_do_identificador} e a password do {fonte.nome}."
        ),
        "mfa_requerido": (
            "O portal requere verificação em 2 passos (Chave Móvel Digital). "
            "Introduza o código enviado para o seu telemóvel."
        ),
        "mfa_timeout": (
            f"O código de verificação não foi submetido a tempo (limite de "
            f"{MFA_ESPERA_SEGUNDOS // 60} minutos). Tente novamente."
        ),
        "mfa_codigo_incorreto": (
            "O código de verificação SMS introduzido parece estar incorreto. "
            "O login não foi concluído."
        ),
        "mfa_error": "Erro ao processar o código de verificação. Tente novamente.",
        "timeout_scraper": f"O {fonte.nome} demorou demasiado a responder. Tente novamente mais tarde. {manual}",
        "sem_documentos": f"Não foi possível localizar os documentos no {fonte.nome}. {manual}",
        "scraper_ocupado": (
            "O serviço está ocupado com outros pedidos neste momento. "
            "Tente novamente dentro de alguns minutos."
        ),
        "arquivo_falhou": (
            f"Os documentos foram obtidos mas não foi possível guardá-los no seu "
            f"processo. Tente novamente ou contacte o seu consultor. {manual}"
        ),
        "scraper_unavailable": (
            f"O serviço de obtenção automática de documentos não está disponível "
            f"de momento. {manual}"
        ),
    }
    return tipo, mensagens[tipo]


def mensagem_de_sucesso(fonte: FonteGovernamental, obtidos: int, em_falta: list[str]) -> str:
    plural = "s" if obtidos != 1 else ""
    mensagem = f"{obtidos} documento{plural} obtido{plural} do {fonte.nome}."
    if em_falta:
        mensagem += (
            f" Não foi possível obter: {', '.join(em_falta)}. "
            f"Pode descarregá-lo do {fonte.nome} e enviá-lo através do botão de upload."
        )
    return mensagem


async def _gravar_estado_do_job(scraper_job_id: str, campos: dict, *, remover: tuple[str, ...] = ()) -> None:
    """Grava o estado final do job. Nunca levanta.

    O estado final é a única coisa que o cliente lê. Uma excepção aqui, dentro
    do `except` do pipeline, escondia a causa original e deixava o job a
    «processar» para sempre.
    """
    operacao: dict = {"$set": {**campos, "updated_at": datetime.now(timezone.utc).isoformat()}}
    operacao["$unset"] = {campo: "" for campo in ("mfa_code", *remover)}
    try:
        await db.portal_scraper_jobs.update_one({"id": scraper_job_id}, operacao)
    except Exception as exc:
        logger.error(
            "[PORTAL-BG] Não foi possível gravar o estado do job %s: %s",
            scraper_job_id, type(exc).__name__, exc_info=True,
        )


async def _recolher(fonte: FonteGovernamental, identificador: str, password: str, process_id: str) -> dict:
    """Corre o scraper e arquiva o que ele trouxe. Devolve um dict de resultado.

    SEGURANÇA: as credenciais só existem em memória, durante esta chamada. Nunca
    são persistidas nem escritas no log.
    """
    from services import gov_scraper

    obter = getattr(gov_scraper, fonte.funcao_do_scraper)
    resultado = await obter(identificador, password, process_id=process_id)

    if not resultado.success:
        falha = {
            "success": False,
            "error": resultado.error or "erro_desconhecido",
            "step_failed": resultado.step_failed,
        }
        if resultado.screenshot_b64:
            falha["screenshot_available"] = True
            logger.info("[PORTAL] Screenshot disponível para debug (%d chars)", len(resultado.screenshot_b64))
        return falha

    arquivo = await arquivar_documentos(
        process_id, list(resultado.documents), origem=fonte.origem, enviado_por=fonte.enviado_por
    )
    resultado.documents = []  # libertar os bytes: já estão no S3 (e em `arquivo.registados`)
    if arquivo.total == 0:
        # O scraper obteve, o arquivo falhou: «0 documentos obtidos» com sucesso
        # seria mentir ao cliente e à equipa.
        return {
            "success": False,
            "error": "arquivo_falhou" if arquivo.falhados else "sem_documentos",
            "step_failed": "archive",
        }

    return {
        "success": True,
        "documents_count": arquivo.total,
        "documents": arquivo.registados,
        "documents_missing": rotulos_em_falta(fonte.chave, arquivo.registados),
    }


async def _run_financas_scraper(nif: str, password: str, process_id: str):
    return await _recolher(FINANCAS, nif, password, process_id)


async def _run_seguranca_social_scraper(niss: str, password: str, process_id: str):
    return await _recolher(SEGURANCA_SOCIAL, niss, password, process_id)


async def _executar_recolha(
    fonte: FonteGovernamental,
    scraper,
    identificador: str,
    password: str,
    process_id: str,
    client_name: str,
    client_email: str,
    process: dict,
    scraper_job_id: str,
) -> None:
    """Pipeline completo de uma recolha, com o estado final garantido.

    Regra: depois de os documentos estarem arquivados, NADA do que vem a seguir
    (email, notificação à equipa, WebSocket) pode transformar o job em erro. A
    cópia anterior chamava `_notify_assigned_team_fetch` sem guarda dentro do
    mesmo `try` que apanhava os erros do scraper: uma excepção ao notificar
    sobrescrevia um job `success` com `unexpected_error` — o cliente via
    «falhou» num processo onde os documentos já estavam arquivados.
    """
    try:
        await _send_portal_fetch_email(client_email, client_name, fonte.chave, "started")
    except Exception as exc:
        logger.warning("[PORTAL-BG] Erro ao enviar email de início (%s): %s", fonte.nome, exc)

    try:
        resultado = await scraper(identificador, password, process_id)
    except Exception as exc:
        logger.error(
            "[PORTAL-BG] Erro inesperado na recolha %s: %s", fonte.nome, type(exc).__name__, exc_info=True
        )
        resultado = {"success": False, "error": "unexpected_error"}
    finally:
        del password  # a referência local; o `gov_scraper` já limpou as dele

    if resultado.get("success"):
        await _concluir_com_sucesso(fonte, resultado, process_id, client_name, client_email, process, scraper_job_id)
    else:
        await _concluir_com_erro(fonte, resultado, process_id, client_name, client_email, scraper_job_id)
    _gc.collect()


async def _concluir_com_sucesso(
    fonte, resultado, process_id, client_name, client_email, process, scraper_job_id
) -> None:
    obtidos = resultado.get("documents_count", 0)
    em_falta = resultado.get("documents_missing", [])
    logger.info("[PORTAL-BG] %s: %d documento(s) obtido(s) para o processo %s", fonte.nome, obtidos, process_id)

    await _gravar_estado_do_job(
        scraper_job_id,
        {
            "status": "success",
            "documents_count": obtidos,
            "documents_missing": em_falta,
            "message": mensagem_de_sucesso(fonte, obtidos, em_falta),
        },
    )
    anexos = resultado.get("documents") or None
    for passo, coro in (
        ("email de sucesso", lambda: _send_portal_fetch_email(
            client_email, client_name, fonte.chave, "success", docs_count=obtidos, attachments=anexos)),
        ("notificação da equipa", lambda: _notify_assigned_team_fetch(process, fonte.nome_da_equipa, obtidos)),
        ("notificação em tempo real", lambda: _notificar_recolha(process_id, fonte.ids_do_processo, docs_count=obtidos)),
    ):
        try:
            await coro()
        except Exception as exc:
            logger.warning("[PORTAL-BG] %s (%s) falhou: %s", passo, fonte.nome, type(exc).__name__)
    resultado.pop("documents", None)


async def _concluir_com_erro(fonte, resultado, process_id, client_name, client_email, scraper_job_id) -> None:
    detalhe = resultado.get("error", "erro_desconhecido")
    tipo, mensagem = classificar_falha(detalhe, fonte)
    logger.error("[PORTAL-BG] Recolha %s falhou: %s (passo: %s)", fonte.nome, detalhe, resultado.get("step_failed"))

    await _gravar_estado_do_job(
        scraper_job_id, {"status": "error", "error_type": tipo, "message": mensagem}
    )
    for passo, coro in (
        ("email de erro", lambda: _send_portal_fetch_email(client_email, client_name, fonte.chave, "error")),
        ("notificação em tempo real", lambda: _notificar_recolha(
            process_id, f"{fonte.ids_do_processo}_error", error_type=tipo)),
    ):
        try:
            await coro()
        except Exception as exc:
            logger.warning("[PORTAL-BG] %s (%s) falhou: %s", passo, fonte.nome, type(exc).__name__)


async def _run_financas_background(nif: str, password: str, process_id: str, client_name: str, client_email: str, process: dict, scraper_job_id: str):
    """Background task do scraper das Finanças (ver `_executar_recolha`)."""
    await _executar_recolha(
        FINANCAS, _run_financas_scraper, nif, password, process_id,
        client_name, client_email, process, scraper_job_id,
    )


async def _run_seguranca_social_background(niss: str, password: str, process_id: str, client_name: str, client_email: str, process: dict, scraper_job_id: str):
    """Background task do scraper da Segurança Social (ver `_executar_recolha`)."""
    await _executar_recolha(
        SEGURANCA_SOCIAL, _run_seguranca_social_scraper, niss, password, process_id,
        client_name, client_email, process, scraper_job_id,
    )


async def _send_portal_fetch_email(to_email: str, client_name: str, source: str, status: str, docs_count: int = 0, attachments: list = None):
    """
    Envia email de estado ao cliente sobre a obtenção automática de documentos.

    Utiliza o serviço de email principal (send_email) em vez de SMTP directo,
    para suportar tanto Resend API como SMTP, e garantir que os emails são
    registados no histórico do processo.

    Args:
        to_email: Email do destinatário (cliente).
        client_name: Nome do cliente.
        source: Origem dos documentos ("financas" ou "seguranca_social").
        status: Estado do processo ("started", "error" ou "success").
        docs_count: Número de documentos obtidos (apenas para status="success").
        attachments: Lista de anexos a incluir no email (apenas para status="success").
            Cada anexo é um dict com:
            - filename (str): Nome do ficheiro.
            - content_bytes (bytes): Conteúdo binário do documento.
            - content_type (str): Tipo MIME (ex: "application/pdf").

    Status:
    - started:  "O nosso sistema automático começou a reunir os seus documentos..."
    - error:    "As credenciais que introduziu estão incorretas..."
    - success:  "Os documentos foram descarregados e anexados ao seu processo com sucesso..."
    """
    if not to_email:
        return

    source_label = {
        "financas": "Portal das Finanças",
        "seguranca_social": "Segurança Social",
    }.get(source, source)

    if status == "started":
        subject = f"Obtenção de Documentos — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"O nosso sistema automático começou a reunir os seus documentos "
            f"junto do {source_label}.\n\n"
            f"Iremos notificá-lo(a) assim que o processo esteja concluído.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    elif status == "error":
        subject = f"Credenciais Incorretas — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"As credenciais que introduziu estão incorretas para o {source_label}.\n\n"
            f"Por favor, verifique os seus dados e tente novamente no portal, "
            f"ou contacte o seu consultor para assistência.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    elif status == "success":
        subject = f"Documentos Obtidos com Sucesso — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"Os documentos foram descarregados e anexados ao seu processo com sucesso "
            f"junto do {source_label} ({docs_count} documento{'s' if docs_count != 1 else ''} obtido{'s' if docs_count != 1 else ''}).\n\n"
            f"Não é necessário qualquer ação adicional da sua parte.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    else:
        return

    html_content = f"""
    <html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #0f766e; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h2 style="margin: 0;">Power Precision</h2>
        </div>
        <div style="background: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px;">
            <p>{body_text.replace(chr(10), '<br>')}</p>
        </div>
        <p style="text-align: center; font-size: 11px; color: #999; margin-top: 15px;">
            Este email foi enviado automaticamente. Não responda diretamente.
        </p>
    </div>
    </body></html>
    """

    # ── Enviar via serviço de email principal (Resend API ou SMTP) ──
    # Incluir anexos apenas no email de sucesso (quando há documentos para enviar)
    try:
        from services.email_service import send_email
        await send_email(
            account_name="power",
            to_emails=[to_email],
            subject=subject,
            body=body_text,
            body_html=html_content,
            force_system=True,
            system_purpose="NOTIFICATIONS",
            attachments=attachments if status == "success" and attachments else None,
        )
        att_info = f" com {len(attachments)} anexo(s)" if attachments and status == "success" else ""
        logger.info(f"[PORTAL] Email de estado '{status}' enviado para {to_email} ({source_label}{att_info})")
    except Exception as e:
        # Fallback para SMTP directo se o serviço principal falhar
        logger.warning(f"[PORTAL] Serviço de email principal falhou, a tentar SMTP directo: {type(e).__name__}")
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.mime.application import MIMEApplication

            smtp_server = os.environ.get('SMTP_SERVER')
            smtp_port = int(os.environ.get('SMTP_PORT', 465))
            smtp_email = os.environ.get('SMTP_EMAIL')
            smtp_password_env = os.environ.get('SMTP_PASSWORD')

            if not all([smtp_server, smtp_email, smtp_password_env]):
                logger.warning("[PORTAL] SMTP também não configurado — email de estado não enviado")
                return

            # Construir mensagem com suporte a anexos
            if attachments and status == "success":
                msg = MIMEMultipart("mixed")
                body_part = MIMEMultipart("alternative")
                body_part.attach(MIMEText(body_text, "plain", "utf-8"))
                body_part.attach(MIMEText(html_content, "html", "utf-8"))
                msg.attach(body_part)

                # Anexar documentos PDF
                for att in attachments:
                    att_bytes = att.get("content_bytes")
                    att_filename = att.get("filename", "documento.pdf")
                    if att_bytes:
                        pdf_part = MIMEApplication(att_bytes, _subtype="pdf")
                        pdf_part.add_header(
                            "Content-Disposition", "attachment",
                            filename=att_filename,
                        )
                        msg.attach(pdf_part)
                        logger.info(
                            f"[PORTAL] Anexo adicionado ao SMTP fallback: "
                            f"{att_filename} ({len(att_bytes)} bytes)"
                        )
            else:
                msg = MIMEMultipart('alternative')
                msg.attach(MIMEText(html_content, 'html'))

            msg['Subject'] = subject
            msg['From'] = smtp_email
            msg['To'] = to_email

            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context, timeout=30) as server:
                server.login(smtp_email, smtp_password_env)
                server.sendmail(smtp_email, to_email, msg.as_string())

            att_info = f" com {len(attachments)} anexo(s)" if attachments and status == "success" else ""
            logger.info(f"[PORTAL] Email de estado '{status}' enviado via SMTP fallback para {to_email}{att_info}")
        except Exception as fallback_err:
            logger.warning(f"[PORTAL] SMTP fallback também falhou: {type(fallback_err).__name__}")


async def _notify_assigned_team_fetch(process: dict, source_name: str, docs_count: int):
    """Notifica a equipa atribuída sobre documentos obtidos automaticamente."""
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
                    f"Documentos Obtidos — {source_name}",
                    f"O sistema obteve {docs_count} documento{'s' if docs_count != 1 else ''} do {source_name} para o cliente {client_name} no processo {process_ref}.",
                    notification_type="document_auto_fetch"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar {uid} sobre fetch {source_name}: {e}")


async def run_check_scraper_status():
    """
    Verifica se o serviço de obtenção automática de documentos está disponível.

    Retorna o estado do Playwright e do browser Chromium, para diagnóstico.
    Endpoint público (não requer autenticação) para permitir verificação prévia.

    Em DEV (ENVIRONMENT != production): retorna mock sem importar Playwright.
    """
    # DEV MODE: Mock — não importar Playwright em DEV para poupar RAM
    if os.environ.get('ENVIRONMENT') != 'production':
        return {
            "available": False,
            "playwright_installed": False,
            "chromium_available": False,
            "dev_mode": True,
            "error": "MOCK DEV: Scraper de portais governamentais desativado em DEV para poupar RAM. Funciona apenas em ENVIRONMENT=production.",
        }

    try:
        from services.gov_scraper import check_playwright_available
        result = await check_playwright_available()
        return {
            "available": result.get("playwright_installed") and result.get("chromium_available"),
            "playwright_installed": result.get("playwright_installed", False),
            "chromium_available": result.get("chromium_available", False),
            "browsers_path": result.get("browsers_path"),
            "browsers_dir_exists": result.get("browsers_dir_exists"),
            "error": result.get("error"),
        }
    except Exception as e:
        return {
            "available": False,
            "playwright_installed": False,
            "chromium_available": False,
            "error": str(e),
        }


def _processo_minimo(process: dict) -> dict:
    """Só os campos que a notificação da equipa precisa (evita reter o documento)."""
    return {
        "id": process.get("id"),
        "client_name": process.get("client_name", ""),
        "process_number": process.get("process_number", ""),
        "assigned_consultor_ids": process.get("assigned_consultor_ids"),
        "assigned_consultor_id": process.get("assigned_consultor_id"),
        "assigned_mediador_ids": process.get("assigned_mediador_ids"),
        "assigned_mediador_id": process.get("assigned_mediador_id"),
        "assigned_indexacao_id": process.get("assigned_indexacao_id"),
        "assigned_parceiro_id": process.get("assigned_parceiro_id"),
    }


async def _iniciar_recolha(
    fonte: FonteGovernamental,
    corpo_background,
    data: dict,
    chave_do_identificador: str,
    tamanho_do_identificador: int,
    background_tasks: BackgroundTasks,
    client_data: dict,
):
    """Valida o pedido, regista o job e agenda a recolha. Responde logo.

    SEGURANÇA: as credenciais NUNCA são guardadas na BD. Passam em memória para
    a tarefa de fundo e são descartadas.

    Há UM job activo por processo: o código MFA vive numa chave por processo e
    um segundo login em paralelo faria o cliente receber outro SMS e o código
    que escreveu servir a execução errada. Um pedido repetido para a MESMA fonte
    devolve o job em curso (o ecrã liga-se a ele); para outra fonte é um 409.
    """
    # Só PRODUÇÃO lança o browser. Em dev o scraper é simulado.
    if os.environ.get('ENVIRONMENT') != 'production':
        logger.info("[PORTAL] MOCK DEV: fetch-%s desativado em DEV para poupar RAM.", fonte.chave)
        return {
            "success": True,
            "message": (
                f"MOCK DEV: Acesso ao {fonte.nome} desativado em DEV para poupar RAM. "
                "Funciona apenas em ENVIRONMENT=production."
            ),
            "documents_count": 0,
            "dev_mode": True,
        }

    process = client_data["process"]
    process_id = process["id"]
    identificador = (data.get(chave_do_identificador) or "").strip()
    password = data.get("password") or ""

    if (
        not identificador
        or len(identificador) != tamanho_do_identificador
        or not identificador.isdigit()
    ):
        raise HTTPException(
            status_code=400,
            detail=f"{fonte.nome_do_identificador} inválido. Deve conter {tamanho_do_identificador} dígitos.",
        )
    if not password:
        raise HTTPException(status_code=400, detail="A password é obrigatória.")

    activo = await job_activo_do_processo(process_id)
    if activo:
        if activo.get("source") == fonte.chave:
            logger.info("[PORTAL] Recolha %s já em curso para o processo %s — a reutilizar o job.", fonte.nome, process_id)
            return JSONResponse(content={
                "status": "processing",
                "message": "Já existe uma obtenção em curso. A acompanhar o seu progresso.",
                "scraper_job_id": activo["id"],
                "process_id": process_id,
                "already_running": True,
            })
        raise HTTPException(
            status_code=409,
            detail="Já existe uma obtenção de documentos em curso. Aguarde que termine antes de iniciar outra.",
        )

    scraper_job_id = await criar_job(process_id, fonte.chave)
    background_tasks.add_task(
        corpo_background,
        **{
            chave_do_identificador: identificador,
            "password": password,
            "process_id": process_id,
            "client_name": process.get("client_name", "Cliente"),
            "client_email": process.get("client_email", ""),
            "process": _processo_minimo(process),
            "scraper_job_id": scraper_job_id,
        },
    )
    logger.info("[PORTAL] Fetch %s agendado em background para o processo %s", fonte.nome, process_id)
    return JSONResponse(content={
        "status": "processing",
        "message": "A obter documentos em background. Será notificado quando estiverem prontos.",
        "scraper_job_id": scraper_job_id,
        "process_id": process_id,
    })


async def run_fetch_financas_documents(data: dict, background_tasks: BackgroundTasks, client_data: dict):
    """Obtém documentos do Portal das Finanças (IRS, Nota de Liquidação).

    Body: `nif` (9 dígitos) e `password`. Responde logo (`processing`); o cliente
    acompanha por polling/WebSocket. Ver `_iniciar_recolha`.
    """
    return await _iniciar_recolha(
        FINANCAS, _run_financas_background, data, "nif", 9, background_tasks, client_data
    )


async def run_fetch_seguranca_social_documents(data: dict, background_tasks: BackgroundTasks, client_data: dict):
    """Obtém documentos da Segurança Social.

    Body: `niss` (11 dígitos) e `password`. Responde logo (`processing`); o
    cliente acompanha por polling/WebSocket. Ver `_iniciar_recolha`.
    """
    return await _iniciar_recolha(
        SEGURANCA_SOCIAL, _run_seguranca_social_background, data, "niss", 11, background_tasks, client_data
    )


async def run_submit_mfa_code(data: dict, client_data: dict):
    """
    Submete o código MFA recebido por SMS para retomar o scraper.

    Quando o portal pede verificação em 2 passos, o scraper pausa e coloca o
    job em `awaiting_mfa`. O ecrã mostra o campo e, ao submeter, este endpoint
    guarda o código (Redis, TTL 300 s; MongoDB como recurso) para o scraper o
    consumir.

    Body: `process_id` (opcional, tem de ser o do token) e `mfa_code` (4-8 dígitos).
    """
    process = client_data["process"]
    process_id = process["id"]

    body_process_id = (data.get("process_id") or "").strip()
    if body_process_id and body_process_id != process_id:
        raise HTTPException(status_code=403, detail="process_id não corresponde ao token.")

    mfa_code = (data.get("mfa_code") or "").strip()
    if not mfa_code:
        raise HTTPException(status_code=400, detail="Código MFA é obrigatório.")
    if not mfa_code.isdigit() or len(mfa_code) < 4 or len(mfa_code) > 8:
        raise HTTPException(status_code=400, detail="Código MFA inválido. Deve conter entre 4 e 8 dígitos.")

    await encerrar_jobs_mortos(process_id)
    job = await db.portal_scraper_jobs.find_one(
        {"process_id": process_id, "status": "awaiting_mfa"}, {"_id": 0, "id": 1}
    )
    if not job:
        # O MAIS RECENTE, não «um qualquer»: o `find_one` sem ordenação devolvia
        # o job mais antigo do processo, e a resposta descrevia uma recolha de
        # semanas atrás.
        ultimo = await db.portal_scraper_jobs.find_one(
            {"process_id": process_id}, {"_id": 0, "status": 1}, sort=[("created_at", -1)]
        )
        if not ultimo:
            raise HTTPException(status_code=404, detail="Nenhum job de scraper encontrado para este processo.")
        if ultimo.get("status") == "processing":
            raise HTTPException(
                status_code=409,
                detail="O scraper ainda está a processar o login. Aguarde que o pedido de MFA apareça.",
            )
        raise HTTPException(
            status_code=409,
            detail="Já não há nenhum código à espera (a obtenção terminou ou expirou). Inicie de novo.",
        )

    from services.mfa_cache import set_mfa_code

    if not await set_mfa_code(process_id, mfa_code, ttl=300):
        raise HTTPException(status_code=500, detail="Erro ao guardar o código MFA. Tente novamente.")

    logger.info("[PORTAL] Código MFA submetido para o processo %s (%d dígitos)", process_id, len(mfa_code))
    return JSONResponse(content={
        "success": True,
        "message": "Código submetido com sucesso. O scraper vai utilizá-lo automaticamente.",
        "process_id": process_id,
    })


async def run_get_scraper_job_status(job_id: str, client_data: dict):
    """Estado de um job de recolha, para o polling do ecrã do cliente.

    Só o dono do job o lê (404 igual para «não existe» e «não é teu») e só
    devolve os campos de `CAMPOS_PUBLICOS_DO_JOB`: este endpoint não tinha
    autenticação e devolvia o documento inteiro, `mfa_code` incluído.

    Estados: `processing` | `awaiting_mfa` | `success` | `error`.
    """
    job = await ler_job_do_processo(job_id, client_data["process"]["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return job
