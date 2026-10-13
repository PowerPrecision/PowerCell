"""Public client registration (Pacote D).

Extraído de `routes/public.py`.
Preserva sanitização, encriptação RGPD, criação de processo + magic link.
"""
from __future__ import annotations

import dataclasses
import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

from database import db
from services.s3_document_root import pasta_para_gravar
from services.s3_storage import s3_service
from models.process import PublicClientRegistration
from fastapi import HTTPException
from services.form_config_scope import rede_do_link_publico
from services.alert_audience import gestao_da_rede_do_processo
from services.client_uniqueness import encontrar_cliente_duplicado, erro_publico_de_duplicado
from services.tenant_network import CAMPO_REDE
from services.email import send_new_client_notification
from services.alerts import notify_new_client_registration
from services.background_tasks import spawn_background_task
from utils.frontend_url import get_frontend_url
from services.encryption import encrypt_client_data
from services.portal_profile_sections import dados_financeiros_do_registo
from models.client import generate_portal_access_code
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, log_sanitization_rejection
)

logger = logging.getLogger(__name__)

#: Quem recebe o aviso de um registo novo — a gestão DA REDE do link.
PAPEIS_QUE_RECEBEM_O_AVISO_DE_REGISTO = ("admin", "ceo", "diretor")


async def run_public_client_registration(request: Request, data: PublicClientRegistration):
    """
    Endpoint público para registo de clientes - sem autenticação.
    
    FLUXO DE TRIAGEM MANUAL:
    1. Bloqueio de duplicados (D-38): se o NIF, Email ou Telemóvel já existe **na rede
       do link**, recusa com 409 — não cria nem actualiza em silêncio. Nunca olha
       para outra rede (D-32).
    2. Marcação: Cliente fica com lead_status="new" para triagem na página de Registos
    3. SEM CRIAÇÃO DE PROCESSO — o processo só é criado quando o staff aprova
    
    SEGURANÇA: Rate limiting, sanitização de inputs, encriptação RGPD.
    """
    
    # Sanitizar inputs
    clean_email = sanitize_email(data.email)
    if not clean_email:
        log_sanitization_rejection("email", data.email, "email inválido no registo público")
        return JSONResponse(status_code=400, content={"success": False, "detail": "Email inválido"})
    
    clean_name = sanitize_name(data.name) if data.name else ""
    clean_phone = sanitize_phone(data.phone) if data.phone else None
    
    # O formulário é POR EMPRESA: o link diz de que empresa é, e o cliente nasce dela.
    # Identificador desconhecido/inactivo recusa-se (404) em vez de registar no vazio.
    carimbo_da_empresa: dict = {}
    try:
        _rede, _empresa = await rede_do_link_publico(data.empresa_id)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"success": False, "detail": exc.detail})
    if _empresa:
        carimbo_da_empresa = {
            "company_id": _empresa.get("id"),
            "company_name": _empresa.get("name"),
            CAMPO_REDE: _rede,
        }

    # Processar dados do formulário
    has_property = data.has_property or False
    process_type = data.process_type or "credito_habitacao"
    now = datetime.now(timezone.utc).isoformat()

    # =========================================
    # PASSO 1: BLOQUEIO RIGOROSO DE DUPLICADOS (D-38)
    # NIF, Email e Telemóvel não se repetem DENTRO DA REDE do link. Se algum já
    # existe, o pedido é recusado (409): nem se cria um registo novo nem se
    # actualiza o antigo em silêncio — quem submete tem de saber que aquele
    # contacto já está registado. A resposta é genérica (sem id, nome nem
    # campo): a porta é anónima.
    # =========================================
    nif_do_formulario = None
    if isinstance(data.personal_data, dict) and data.personal_data.get("nif"):
        nif_do_formulario = sanitize_nif(str(data.personal_data.get("nif")))
    duplicado = await encontrar_cliente_duplicado(
        nif_do_formulario, clean_email, clean_phone, rede=_rede,
    )
    if duplicado:
        logger.info(
            "[PUBLIC FORM] Registo recusado: contacto já existente na rede %s (cliente %s)",
            _rede, duplicado.get("id"),
        )
        return JSONResponse(status_code=409, content=erro_publico_de_duplicado())

    # ── NOVO CLIENTE: Criar documento isolado na coleção clients ──
    client_id = str(uuid.uuid4())
    
    personal_data = {
        "nome": clean_name,
        "email": clean_email,
        "telefone": clean_phone,
    }
    
    client_doc = {
        "id": client_id,
        "nome": clean_name,
        "contacto": {
            "email": clean_email.lower(),
            "telefone": clean_phone
        },
        "dados_pessoais": personal_data,
        # Passos 4–5 do registo. Copiam-se para o processo quando ele é criado
        # (`onboarding_mandatory_config`/`client_assign`); o NIF da entidade patronal
        # fica cifrado como no processo.
        "dados_financeiros": dados_financeiros_do_registo(data.financial_data),
        "dados_imobiliarios": {},  # Dados do imóvel recolhidos depois
        "process_ids": [],  # Será preenchido quando o staff criar o processo
        "portal_access_code": generate_portal_access_code(),  # Código de acesso ao Portal
        "fonte": "public_form",
        "has_property": has_property,
        "idade_menos_35": False,
        "created_at": now,
        "updated_at": now,
        "registration_completed": True,
        "assigned_to": None,
        "assigned_at": None,
        "lead_status": "new",  # Pendente — processo só após docs obrigatórios
        "custom_fields": data.custom_fields if data.custom_fields else {},
        "pending_process_type": process_type,
        "titular2_data": data.titular2_data if data.titular2_data else {},
        "pending_real_estate_data": data.real_estate_data if data.real_estate_data else {},
        **carimbo_da_empresa,
    }

    # Merge personal_data do formulário em dados_pessoais
    if data.personal_data and isinstance(data.personal_data, dict):
        for pk, pv in data.personal_data.items():
            if pv is not None and str(pv).strip() != "":
                personal_data[pk] = pv
        client_doc["dados_pessoais"] = personal_data
    
    # RGPD: Encriptar dados sensíveis ANTES de inserir na BD
    try:
        client_doc = encrypt_client_data(client_doc)
        logger.info(f"Dados do cliente {client_id} encriptados com sucesso (blind indexes incluídos)")
    except Exception as e:
        logger.warning(f"Falha ao encriptar dados do cliente {client_id}: {e}")
        try:
            from services.system_error_logger import system_error_logger
            await system_error_logger.log_error(
                error_type="encryption_failure",
                message=f"Falha ao encriptar dados do cliente {client_id}: {e}",
                component="public_form",
                details={"client_id": client_id, "error": str(e)},
                severity="warning",
                request_path="/api/public/client-registration"
            )
        except Exception:
            pass
    
    await db.clients.insert_one(client_doc)
    
    # M3 - Criar pasta S3 para o cliente
    try:
        import asyncio
        result = await asyncio.to_thread(
            s3_service.initialize_client_folders,
            client_id,
            clean_name,
            None  # Sem segundo titular no formulário público
        )
        if result and len(result) == 2:
            success, s3_folder_name = result
            caminho = pasta_para_gravar(
                s3_folder_name, contexto=f"registo público do cliente {client_id}"
            )
            if success and caminho:
                await db.clients.update_one(
                    {"id": client_id},
                    {"$set": {"s3_folder": caminho}}
                )
                logger.info(f"Pasta S3 criada para cliente {client_id}: {s3_folder_name}")
    except Exception as e:
        logger.warning(f"Não foi possível criar pasta S3 para cliente {client_id}: {e}")

    # =========================================
    # REGISTO SEM PROCESSO — cliente + portal + checklist SystemConfig
    # =========================================
    # O processo só é criado quando os documentos obrigatórios
    # (SystemConfig.mandatory_documents) estiverem submetidos.
    # titular2_data fica no cliente e é copiado na criação do processo.
    # =========================================
    process_id = None
    magic_link_sent = False
    # Contexto de REDE dos emails ao cliente (nome da empresa, remetente, link
    # do Portal). Resolvido a partir do carimbo do LINK — a empresa a que o
    # cliente se registou — e nunca de uma constante.
    contexto_portal = None
    id_da_empresa_do_link = (_empresa or {}).get("id")
    try:
        from services.portal_security import create_access_code_session_token
        from services.portal_documents_notify import generate_mandatory_document_requests

        # Pedidos de docs obrigatórios ligados ao CLIENTE (sem process_id)
        asyncio.create_task(
            generate_mandatory_document_requests(
                process_id=None,
                client_id=client_id,
                company_id=None,
                requested_by="public_form",
                requested_by_name="Formulário Público",
            )
        )

        # Token de portal client-scoped (sem processo ainda)
        import secrets as _secrets
        from datetime import datetime as _dt, timezone as _tz
        token = create_access_code_session_token("no_process", client_id)
        short_id = _secrets.token_urlsafe(6)[:8]
        await db.portal_tokens.update_one(
            {"client_id": client_id, "source": "public_form_auto"},
            {
                "$set": {
                    "short_id": short_id,
                    "jwt_token": token,
                    "process_id": None,
                    "client_id": client_id,
                    "created_by": "public_form",
                    "source": "public_form_auto",
                    "updated_at": _dt.now(_tz.utc),
                },
                "$setOnInsert": {
                    "created_at": _dt.now(_tz.utc),
                },
            },
            upsert=True,
        )

        # Referer/Origin do browser de quem se registou, depois FRONTEND_URL.
        frontend_url = get_frontend_url(request)
        magic_link = f"{frontend_url}/portal/{short_id}" if frontend_url else f"/portal/{short_id}"

        from services.portal_email_context import (
            enviar_email_do_portal,
            resolver_contexto,
        )

        contexto_portal = await resolver_contexto(
            company_id=id_da_empresa_do_link, network_id=_rede,
            client_id=client_id, frontend_url=frontend_url,
        )
        # No email, o botão leva directo ao Portal (link mágico) e a página de
        # entrada fica como alternativa para quem usa o código de acesso.
        endereco_de_entrada = contexto_portal.portal_url
        contexto_portal = dataclasses.replace(contexto_portal, portal_url=magic_link)

        _portal_access_code_dc = None
        try:
            _client_doc_dc = await db.clients.find_one(
                {"id": client_id}, {"portal_access_code": 1, "_id": 0}
            )
            if _client_doc_dc:
                _portal_access_code_dc = _client_doc_dc.get("portal_access_code")
        except Exception as _e_dc:
            logger.warning(f"[PUBLIC FORM] Erro ao obter portal_access_code para email: {_e_dc}")

        _access_code_html_dc = ""
        _access_code_text_dc = ""
        if _portal_access_code_dc:
            _access_code_html_dc = f"""
                <div style="background: #f0fdfa; border: 1px solid #0d9488; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <p style="font-size: 14px; color: #1e293b; margin: 0 0 10px 0;">Se o link não funcionar, aceda a <strong>{endereco_de_entrada or "ao Portal do Cliente"}</strong> e insira o seguinte Código de Acesso:</p>
                    <h3 style="text-align: center; margin: 10px 0;"><strong style="font-family: 'Courier New', monospace; font-size: 22px; color: #0f766e; letter-spacing: 3px;">{_portal_access_code_dc}</strong></h3>
                </div>
            """
            _access_code_text_dc = (
                f"\nSe o link não funcionar, aceda a {endereco_de_entrada or 'ao Portal do Cliente'} e "
                f"insira o seguinte Código de Acesso: {_portal_access_code_dc}\n"
            )

        # Logótipo DESTA empresa (sem recurso global: o da Power num convite
        # da Domus seria a mesma fuga que o nome).
        from services.email_branding import build_email_header_logo_html

        _invite_logo_html = build_email_header_logo_html(
            contexto_portal.logo_url, alt=contexto_portal.nome
        )

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #0F766E; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
                {_invite_logo_html}<h1 style="margin: 0; font-size: 20px;">Bem-vindo ao seu Portal do Cliente</h1>
            </div>
            <div style="padding: 30px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px;">
                <p style="font-size: 16px; color: #1e293b;">Olá {clean_name},</p>
                <p style="font-size: 14px; color: #475569;">
                    Recebemos o seu registo. Para avançarmos, aceda ao Portal do Cliente,
                    complete o seu perfil e envie a documentação solicitada.
                </p>
                <p style="font-size: 14px; color: #475569;">
                    O processo de crédito só será criado após a submissão dos documentos obrigatórios.
                </p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{magic_link}" style="display: inline-block; background: #0F766E; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">
                        Aceder ao meu Portal
                    </a>
                </div>
                <p style="font-size: 12px; color: #94a3b8; text-align: center;">
                    Ou copie este link no seu navegador:<br>
                    <span style="color: #64748b;">{magic_link}</span>
                </p>
                {_access_code_html_dc}
                <p style="font-size: 12px; color: #94a3b8; margin-top: 20px;">
                    Este link é válido por 90 dias. Se precisar de ajuda, contacte-nos.
                </p>
            </div>
        </div>
        """
        text_body = (
            f"Olá {clean_name},\n\n"
            f"Recebemos o seu registo. Aceda ao Portal do Cliente para completar "
            f"o perfil e enviar a documentação solicitada.\n"
            f"O processo só será criado após os documentos obrigatórios.\n\n"
            f"{magic_link}\n"
            f"{_access_code_text_dc}\n"
            f"Este link é válido por 90 dias.\n\n"
            f"{contexto_portal.nome}"
        )
        # BUGFIX (Set 2026): o envio era AWAITED aqui dentro. Um servidor de
        # email lento punha um formulário PÚBLICO a responder ao fim de 30s
        # (o timeout do SMTP) — e, como o envio nunca condicionou a resposta
        # (o `except` abaixo só regista um aviso), o utilizador esperava por
        # algo que nem sequer podia falhar-lhe o registo. Passa a background,
        # com referência forte, como já se fazia em `process_create`.
        async def _enviar_convite_do_portal():
            try:
                await enviar_email_do_portal(
                    contexto_portal,
                    to_emails=[clean_email],
                    subject=f"Bem-vindo ao seu Portal do Cliente — {clean_name}",
                    body=text_body,
                    body_html=html_body,
                )
                logger.info(
                    f"[PUBLIC FORM] Email de convite do Portal enviado para {clean_email} "
                    f"(cliente {client_id}, short_id {short_id}, sem processo ainda)"
                )
            except Exception as envio_err:
                logger.warning(
                    f"[PUBLIC FORM] Falha no envio do convite do Portal para "
                    f"{clean_email} (cliente {client_id}): {envio_err}"
                )

        spawn_background_task(
            _enviar_convite_do_portal(),
            name=f"portal-invite-email:{client_id}",
        )
        # Semântica: o convite foi AGENDADO (o resultado do envio vai para os
        # logs). Nenhum consumidor depende deste campo; mantido por retrocompat.
        magic_link_sent = True
    except Exception as e:
        logger.warning(
            f"[PUBLIC FORM] Falha ao preparar portal/email de convite "
            f"para cliente {client_id}: {e}"
        )

    # =========================================
    # PÓS-REGISTO: Email de Confirmação, Notificações, Alertas
    # =========================================
    
    # Obter o código de acesso ao portal do cliente (para incluir no email)
    portal_access_code = None
    try:
        client_doc = await db.clients.find_one({"id": client_id}, {"portal_access_code": 1, "_id": 0})
        if client_doc:
            portal_access_code = client_doc.get("portal_access_code")
            # Se o cliente existente não tem código (caso raro), gerar um
            if not portal_access_code:
                from models.client import generate_portal_access_code as _gen_code
                portal_access_code = _gen_code()
                await db.clients.update_one(
                    {"id": client_id},
                    {"$set": {"portal_access_code": portal_access_code}}
                )
    except Exception as e:
        logger.warning(f"Erro ao obter/gerar portal_access_code para {client_id}: {e}")
    
    # Enviar email de confirmação ao cliente
    # BUGFIX (E2E, Set 2026 — PACOTE BH): antes tentava PRIMEIRO enfileirar
    # no ARQ/Redis (`send_registration_email_task` — função sem consumidor:
    # o worker de produção é `python worker.py`, loop próprio da fila Mongo;
    # o worker ARQ nunca arranca nem tem a task registada). Com Redis UP, o
    # job_id devolvido fazia o envio directo nunca executar. Ordem canónica:
    # envio DIRECTO primeiro; fila ARQ apenas como retry de falha real.
    # BUGFIX (Set 2026): terceiro envio que era awaited dentro do pedido — e o
    # único sem `try/except`, pelo que um servidor de email em baixo podia
    # devolver 500 num registo JÁ gravado. Vai também para background; a
    # idempotência (`portal_email_delivery.status`) continua do lado do
    # `deliver_registration_email`.
    from services.client_portal_email import deliver_registration_email

    async def _enviar_email_de_registo():
        try:
            enviado = await deliver_registration_email(
                client_email=clean_email,
                client_name=clean_name,
                portal_access_code=portal_access_code,
                client_id=client_id,
                company_id=id_da_empresa_do_link,
                contexto=contexto_portal,
                frontend_url=get_frontend_url(request),
            )
            logger.info(
                f"[PUBLIC FORM] Email de registo para {clean_email} "
                f"(cliente {client_id}): enviado={bool(enviado)}"
            )
        except Exception as registo_err:
            logger.warning(
                f"[PUBLIC FORM] Falha no email de registo para {clean_email} "
                f"(cliente {client_id}): {registo_err}"
            )

    spawn_background_task(
        _enviar_email_de_registo(),
        name=f"portal-welcome-email:{client_id}",
    )
    # Semântica: AGENDADO (o resultado real vai para os logs). Nenhum
    # consumidor lê este campo; mantido por retrocompatibilidade.
    email_sent = True
    
    # Criar alertas no sistema de notificações (passar dados do cliente — SEM processo)
    client_notification_data = {
        "id": client_id,
        "client_id": client_id,
        "client_name": clean_name,
        "client_email": clean_email,
        "client_phone": clean_phone,
        "nome": clean_name,
        "contacto": {"email": clean_email, "telefone": clean_phone},
        "process_type": process_type,
        # A gestão a avisar é a da rede do LINK. Sem o carimbo, o aviso caía
        # sempre na rede de omissão: a Domus nunca sabia dos seus registos e a
        # gestão da Power recebia os nomes dos clientes da Domus (D-32).
        **({CAMPO_REDE: _rede} if _rede else {}),
        **({"company_id": _empresa.get("id")} if _empresa else {}),
    }
    await notify_new_client_registration(client_notification_data, has_property)
    ids_da_gestao = await gestao_da_rede_do_processo(
        client_notification_data, PAPEIS_QUE_RECEBEM_O_AVISO_DE_REGISTO,
    )
    gestao = []
    if ids_da_gestao:
        gestao = await db.users.find(
            {"id": {"$in": ids_da_gestao}, "is_active": {"$ne": False}},
            {"_id": 0},
        ).to_list(100)

    # Enviar push notifications para a gestão DA REDE do registo (nunca a de todas).
    try:
        from services.push_notifications import send_push_notification

        for membro in gestao:
            await send_push_notification(
                user_id=membro["id"],
                title="Novo Cliente Registado",
                body=f"{clean_name} registou-se via formulário",
                tag="new_client",
                url="/registos-clientes",  # Link para página de registos de clientes
                data={
                    "type": "new_client",
                    "client_id": client_id,
                    "client_name": clean_name
                }
            )

        logger.info(f"Push notifications enviadas para {len(gestao)} membros da gestão da rede")
    except Exception as e:
        logger.warning(f"Erro ao enviar push notifications: {e}")

    # Email para o primeiro da gestão DA REDE (antes: o primeiro admin/CEO/diretor
    # da base de dados inteira, de qualquer rede, com o nome, o email e o
    # telefone do cliente no corpo).
    staff = gestao

    if staff:
        first_admin = staff[0]
        # PACOTE BH — envio DIRECTO primeiro; fila ARQ (`send_email_task`)
        # apenas como retry quando o envio directo falha (o job ARQ sem
        # consumidor fazia o email do staff perder-se em silêncio).
        # BUGFIX (Set 2026): também este envio era awaited no pedido. Dois
        # envios bloqueantes em série dão até 60s de espera a quem submete o
        # formulário público. O retry pela fila ARQ mantém-se — apenas deixa
        # de acontecer dentro do ciclo pedido/resposta.
        async def _notificar_staff():
            staff_sent = False
            try:
                staff_sent = await send_new_client_notification(
                    client_name=clean_name,
                    client_email=clean_email,
                    client_phone=clean_phone or "N/A",
                    process_type=process_type,
                    staff_email=first_admin["email"],
                    staff_name=first_admin["name"]
                )
            except Exception as staff_err:
                logger.warning(f"[PUBLIC FORM] Falha no email directo ao staff: {staff_err}")
            if not staff_sent:
                try:
                    from services.task_queue import task_queue
                    await task_queue.send_email(
                        to=first_admin["email"],
                        subject=f"Novo Cliente Registado: {clean_name}",
                        body=f"Foi registado um novo cliente via formulário público:\n\nNome: {clean_name}\nEmail: {clean_email}\nTelefone: {clean_phone or 'N/A'}\nTipo pretendido: {process_type}\n\nO registo aguarda triagem na página de Registos de Clientes."
                    )
                except Exception as tq_err:
                    logger.warning(f"[PUBLIC FORM] Task Queue indisponível para email ao staff: {tq_err}")

        spawn_background_task(
            _notificar_staff(),
            name=f"staff-new-client-email:{client_id}",
        )
    
    # Sem `is_new_client` na resposta: num endpoint público e anónimo era uma
    # sonda de «este email já está registado nesta empresa?». Nenhum consumidor
    # o lia (D-32).
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Registo criado com sucesso. A equipa entrará em contacto.",
            "client_id": client_id,
            "process_id": process_id,  # None até docs obrigatórios (SystemConfig)
            "magic_link_sent": magic_link_sent,
            "lead_status": "new",
            "has_property": has_property,
            # Retrocompat: True quando o email de boas-vindas partiu
            # (envio directo — PACOTE BH; já não depende da fila ARQ).
            "email_queued": bool(email_sent)
        }
    )

