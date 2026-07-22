"""Public client registration (Pacote D).

Extraído de `routes/public.py`.
Preserva sanitização, encriptação RGPD, criação de processo + magic link.
"""
from __future__ import annotations

import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

from database import db
from services.s3_storage import s3_service
from models.auth import UserRole
from models.process import PublicClientRegistration
from services.email import send_registration_confirmation, send_new_client_notification
from services.alerts import notify_new_client_registration
from services.encryption import (
    encrypt_client_data,
    decrypt_client_data,
    generate_nif_hash,
    generate_email_hash,
)
from models.client import generate_portal_access_code
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, log_sanitization_rejection
)

logger = logging.getLogger(__name__)

async def run_public_client_registration(request: Request, data: PublicClientRegistration):
    """
    Endpoint público para registo de clientes - sem autenticação.
    
    FLUXO DE TRIAGEM MANUAL:
    1. Anti-Duplicação: Procura cliente por email/NIF → upsert se existe, cria se não
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
    
    # Processar dados do formulário
    has_property = data.has_property or False
    process_type = data.process_type or "credito_habitacao"
    now = datetime.now(timezone.utc).isoformat()

    # =========================================
    # PASSO 1: ANTI-DUPLICAÇÃO (Upsert de Cliente)
    # Procurar por email (blind index) ou NIF.
    # Se existe → atualizar dados novos e reutilizar client_id
    # Se NÃO existe → criar novo documento de cliente
    # =========================================
    
    email_hash = generate_email_hash(clean_email)
    existing_client = None
    
    # Procurar por email (blind index para dados encriptados, fallback plain text)
    if email_hash:
        existing_client = await db.clients.find_one({"contacto.email_hash": email_hash})
    if not existing_client:
        existing_client = await db.clients.find_one({"contacto.email": clean_email.lower()})
    
    # Procurar por NIF (se disponível no payload — atualmente não vem no formulário público)
    clean_nif = None
    if not existing_client and clean_nif:
        nif_hash = generate_nif_hash(clean_nif)
        if nif_hash:
            existing_client = await db.clients.find_one({"dados_pessoais.nif_hash": nif_hash})
        if not existing_client:
            existing_client = await db.clients.find_one({"dados_pessoais.nif": clean_nif})
    
    if existing_client:
        # ── CLIENTE JÁ EXISTE: Atualizar dados novos (upsert parcial) ──
        client_id = existing_client["id"]
        
        # Desencriptar para comparar dados
        try:
            decrypted_existing = decrypt_client_data(existing_client)
        except Exception:
            decrypted_existing = existing_client
        
        # Atualizar campos que possam ter mudado ou sido adicionados
        client_updates = {
            "updated_at": now,
            # Re-marcar como lead pendente se já tinha sido convertido
            # (novo registo = nova submissão que precisa de triagem)
            "lead_status": "new",
        }
        
        # Atualizar telefone se novo ou vazio
        existing_phone = (decrypted_existing.get("contacto") or {}).get("telefone", "")
        if clean_phone and not existing_phone:
            client_updates["contacto.telefone"] = clean_phone
        
        # Atualizar nome se existente está vazio
        existing_name = decrypted_existing.get("nome", "")
        if not existing_name and clean_name:
            client_updates["nome"] = clean_name
        
        # Atualizar has_property se o cliente indicou ter imóvel agora
        if has_property and not existing_client.get("has_property"):
            client_updates["has_property"] = True
        
        # Mesclar custom_fields
        existing_custom = existing_client.get("custom_fields") or {}
        new_custom = data.custom_fields or {}
        if new_custom:
            merged_custom = {**existing_custom, **new_custom}
            client_updates["custom_fields"] = merged_custom

        # Persistir intenção de processo + 2.º titular (processo só após docs)
        if data.process_type:
            client_updates["pending_process_type"] = data.process_type
        if data.titular2_data:
            client_updates["titular2_data"] = data.titular2_data
        if data.personal_data and isinstance(data.personal_data, dict):
            # Merge shallow into dados_pessoais (campos não vazios)
            for pk, pv in data.personal_data.items():
                if pv is not None and str(pv).strip() != "":
                    client_updates[f"dados_pessoais.{pk}"] = pv
        if data.real_estate_data:
            client_updates["pending_real_estate_data"] = data.real_estate_data
        
        # Re-encriptar dados atualizados
        try:
            # Construir doc temporário para encriptação seletiva
            temp_update = {}
            for k, v in client_updates.items():
                if k.startswith("contacto."):
                    if "contacto" not in temp_update:
                        temp_update["contacto"] = {}
                    temp_update["contacto"][k.replace("contacto.", "")] = v
                elif k.startswith("dados_pessoais."):
                    if "dados_pessoais" not in temp_update:
                        temp_update["dados_pessoais"] = {}
                    temp_update["dados_pessoais"][k.replace("dados_pessoais.", "")] = v
                else:
                    temp_update[k] = v
            
            encrypted_updates = encrypt_client_data(temp_update)
            
            # Reconverter para dot-notation
            final_updates = {}
            for k, v in client_updates.items():
                if k.startswith("contacto.") and "contacto" in encrypted_updates:
                    field = k.replace("contacto.", "")
                    final_updates[k] = encrypted_updates["contacto"].get(field, v)
                elif k.startswith("dados_pessoais.") and "dados_pessoais" in encrypted_updates:
                    field = k.replace("dados_pessoais.", "")
                    final_updates[k] = encrypted_updates["dados_pessoais"].get(field, v)
                elif k in encrypted_updates:
                    final_updates[k] = encrypted_updates[k]
                else:
                    final_updates[k] = v
            
            # Preservar blind indexes que não precisam de encriptação
            if "contacto.email_hash" in client_updates:
                final_updates["contacto.email_hash"] = client_updates["contacto.email_hash"]
            
            client_updates = final_updates
        except Exception as e:
            logger.warning(f"Falha ao encriptar updates do cliente existente {client_id}: {e}")
        
        await db.clients.update_one({"id": client_id}, {"$set": client_updates})
        logger.info(f"Cliente existente atualizado via formulário público: {client_id}")
    else:
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
            "dados_financeiros": {},  # Dados financeiros pertencem ao Processo
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
                if success and s3_folder_name:
                    await db.clients.update_one(
                        {"id": client_id},
                        {"$set": {"s3_folder": s3_folder_name}}
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
    try:
        from services.portal_security import create_access_code_session_token
        from services.email_service import send_email
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

        from urllib.parse import urlparse
        frontend_url = ""
        referer = request.headers.get("referer") or request.headers.get("origin")
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                frontend_url = f"{parsed.scheme}://{parsed.netloc}"
        if not frontend_url:
            frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
        magic_link = f"{frontend_url}/portal/{short_id}"

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
                    <p style="font-size: 14px; color: #1e293b; margin: 0 0 10px 0;">Se o link não funcionar, aceda a <strong>www.powercell.pt/portal</strong> e insira o seguinte Código de Acesso:</p>
                    <h3 style="text-align: center; margin: 10px 0;"><strong style="font-family: 'Courier New', monospace; font-size: 22px; color: #0f766e; letter-spacing: 3px;">{_portal_access_code_dc}</strong></h3>
                </div>
            """
            _access_code_text_dc = (
                f"\nSe o link não funcionar, aceda a www.powercell.pt/portal e "
                f"insira o seguinte Código de Acesso: {_portal_access_code_dc}\n"
            )

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #0F766E; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
                <h1 style="margin: 0; font-size: 20px;">Bem-vindo ao seu Portal do Cliente</h1>
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
            f"Power Precision · Crédito Habitação"
        )
        await send_email(
            account_name="power",
            to_emails=[clean_email],
            subject=f"Bem-vindo ao seu Portal do Cliente — {clean_name}",
            body=text_body,
            body_html=html_body,
            process_id=None,
            force_system=True,
            system_purpose="NOTIFICATIONS",
        )
        magic_link_sent = True
        logger.info(
            f"[PUBLIC FORM] Email de convite do Portal enviado para {clean_email} "
            f"(cliente {client_id}, short_id {short_id}, sem processo ainda)"
        )
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
    from services.task_queue import task_queue
    job_id = await task_queue.send_registration_email(
        client_email=clean_email,
        client_name=clean_name,
        portal_access_code=portal_access_code
    )
    if not job_id:
        logger.info("Task Queue não disponível, enviando email directamente")
        await send_registration_confirmation(
            client_email=clean_email,
            client_name=clean_name,
            portal_access_code=portal_access_code
        )
    
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
    }
    await notify_new_client_registration(client_notification_data, has_property)
    
    # Enviar push notifications para staff
    try:
        from services.push_notifications import send_push_notification
        from services.role_query import deep_role_in_filter
        staff_for_push = await db.users.find(
            {"$and": [deep_role_in_filter([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]), {"is_active": True}]},
            {"_id": 0, "id": 1}
        ).to_list(20)
        
        for staff_member in staff_for_push:
            await send_push_notification(
                user_id=staff_member["id"],
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
        
        logger.info(f"Push notifications enviadas para {len(staff_for_push)} membros do staff")
    except Exception as e:
        logger.warning(f"Erro ao enviar push notifications: {e}")
    
    # Email para o primeiro admin/CEO/diretor
    from services.role_query import deep_role_in_filter
    staff = await db.users.find(
        deep_role_in_filter([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]),
        {"_id": 0}
    ).to_list(100)
    
    if staff:
        first_admin = staff[0]
        staff_job = await task_queue.send_email(
            to=first_admin["email"],
            subject=f"Novo Cliente Registado: {clean_name}",
            body=f"Foi registado um novo cliente via formulário público:\n\nNome: {clean_name}\nEmail: {clean_email}\nTelefone: {clean_phone or 'N/A'}\nTipo pretendido: {process_type}\n\nO registo aguarda triagem na página de Registos de Clientes."
        )
        
        if not staff_job:
            await send_new_client_notification(
                client_name=clean_name,
                client_email=clean_email,
                client_phone=clean_phone or "N/A",
                process_type=process_type,
                staff_email=first_admin["email"],
                staff_name=first_admin["name"]
            )
    
    is_new_client = existing_client is None
    
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Registo criado com sucesso. A equipa entrará em contacto.",
            "client_id": client_id,
            "process_id": process_id,  # Pacote D — processo criado com status vazio (Lead)
            "magic_link_sent": magic_link_sent,  # Pacote D — email de convite enviado
            "lead_status": "new",  # Pendente de triagem
            "is_new_client": is_new_client,
            "has_property": has_property,
            "email_queued": bool(job_id)
        }
    )

