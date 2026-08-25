"""GET/POST/PUT clientes — get, create, update.

Extraído de `routes/clients.py`.
"""
from __future__ import annotations

import uuid
import logging
import asyncio
import copy
import re
import os
import unicodedata
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from database import db
from models.client import (
    Client, ClientCreate, ClientUpdate,
    ClientContact, ClientPersonalData,
    find_or_create_client_key,
    generate_portal_access_code,
)
from services.auth import get_effective_role
from models.auth import UserRole
from services.encryption import (
    encryption_service,
    encrypt_client_data,
    decrypt_client_data,
    decrypt_clients_list,
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
)
from services.process_service import get_next_process_number
from services.s3_storage import s3_service
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, sanitize_url, log_sanitization_rejection,
)
from utils.search_filters import create_accent_insensitive_regex, build_multiword_search_filter

logger = logging.getLogger(__name__)

from services.client_portal_email import _send_portal_welcome_email_safe

async def run_get_client(
    client_id: str,
    user: dict
):
    """Obter detalhes de um cliente."""
    client = await db.clients.find_one({"id": client_id}, {"_id": 0})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Carregar detalhes dos processos (como titular principal E como 2º titular)
    process_ids_as_main = client.get("process_ids") or []
    
    # Procurar processos onde este cliente é 2º titular (second_client_id)
    processes_as_second = await db.processes.find(
        {"second_client_id": client_id},
        {"_id": 0, "id": 1}
    ).to_list(length=50)
    process_ids_as_second = [p["id"] for p in processes_as_second]
    
    # Combinar IDs (sem duplicados)
    all_process_ids = list(dict.fromkeys(process_ids_as_main + process_ids_as_second))
    
    processes = []
    if all_process_ids:
        processes = await db.processes.find(
            {"id": {"$in": all_process_ids}},
            {"_id": 0, "id": 1, "process_number": 1, "status": 1, "process_type": 1, 
             "prioridade": 1, "created_at": 1, "updated_at": 1, "is_active": 1,
             "client_id": 1, "second_client_id": 1, "client_name": 1}
        ).to_list(length=50)
    
    # Enriquecer processos com labels, cores do workflow e role do cliente
    if processes:
        statuses = await db.workflow_statuses.find({}, {"_id": 0}).to_list(100)
        status_map = {s["name"]: s for s in statuses}
        for p in processes:
            status_info = status_map.get(p.get("status"), {})
            p["status_label"] = status_info.get("label", p.get("status", ""))
            p["status_color"] = status_info.get("color", "#6B7280")
            
            # Determinar o role do cliente neste processo
            if p.get("second_client_id") == client_id and p.get("client_id") != client_id:
                p["client_role"] = "2º titular"
            elif p.get("client_id") == client_id:
                p["client_role"] = "titular"
            elif client_id in (p.get("process_ids") or []):
                p["client_role"] = "titular"
            else:
                p["client_role"] = "2º titular"
    
    client["processes"] = processes

    # ============================================================
    # PACOTE DA — latest_activity: atividade mais recente do cliente
    # ============================================================
    # Busca a última entrada da coleção activities ligada a qualquer
    # processo deste cliente (all_process_ids). O Frontend
    # (ClientDetailsModal) mostra isto na secção "Observações e IA"
    # para que o consultor veja a última interação registada.
    # ============================================================
    try:
        if all_process_ids:
            latest_act = await db.activities.find_one(
                {"process_id": {"$in": all_process_ids}, "comment": {"$exists": True, "$ne": ""}},
                {"_id": 0},
                sort=[("created_at", -1)]
            )
            client["latest_activity"] = latest_act
        else:
            client["latest_activity"] = None
    except Exception as e:
        logger.warning(f"Erro ao buscar latest_activity para cliente {client_id}: {e}")
        client["latest_activity"] = None

    # ============================================================
    # PACOTE DC — portal_access: Código de Acesso + magic link ativo
    # ============================================================
    try:
        portal_access_code = client.get("portal_access_code")
        active_short_id = None
        active_magic_link = None
        if all_process_ids:
            token_doc = await db.portal_tokens.find_one(
                {"process_id": {"$in": all_process_ids}},
                {"_id": 0, "short_id": 1, "process_id": 1, "created_at": 1}
            )
            if token_doc and token_doc.get("short_id"):
                active_short_id = token_doc["short_id"]
                _fe_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
                if _fe_url:
                    active_magic_link = f"{_fe_url}/portal/{active_short_id}"
        client["portal_access"] = {
            "portal_access_code": portal_access_code,
            "short_id": active_short_id,
            "magic_link": active_magic_link,
            "has_active_token": active_short_id is not None,
        }
    except Exception as e:
        logger.warning(f"Erro ao buscar portal_access para cliente {client_id}: {e}")
        client["portal_access"] = None

    # Desencriptar dados sensíveis
    client = decrypt_client_data(client)
    
    # Safeguard: garantir que created_at, updated_at e assigned_at são sempre válidos
    now_iso = datetime.now(timezone.utc).isoformat()
    if not client.get("created_at"):
        client["created_at"] = now_iso
    if not client.get("updated_at"):
        client["updated_at"] = now_iso
    if client.get("assigned_at") == "" or client.get("assigned_at") is False:
        client["assigned_at"] = None
    
    return client

async def run_create_client(
    client_data: ClientCreate,
    user: dict
):
    """Criar um novo cliente."""
    
    # Sanitizar inputs do utilizador
    sanitized_nome = sanitize_name(client_data.nome)
    if not sanitized_nome:
        log_sanitization_rejection("nome", client_data.nome or "", "Nome vazio ou inválido após sanitização")
        raise HTTPException(status_code=400, detail="Nome inválido. Use apenas letras e espaços.")
    
    # VALIDAÇÃO: E-mail obrigatório para acesso ao Portal do Cliente
    if not client_data.email or not client_data.email.strip():
        raise HTTPException(
            status_code=400,
            detail="O e-mail é obrigatório para a criação do Portal do Cliente."
        )
    
    sanitized_email = sanitize_email(client_data.email) if client_data.email else None
    if client_data.email and not sanitized_email:
        log_sanitization_rejection("email", client_data.email, "Email inválido após sanitização")
        raise HTTPException(status_code=400, detail="Formato de email inválido.")
    
    sanitized_telefone = sanitize_phone(client_data.telefone) if client_data.telefone else None
    
    sanitized_nif = sanitize_nif(client_data.nif) if client_data.nif else None
    if client_data.nif and not sanitized_nif:
        log_sanitization_rejection("nif", client_data.nif, "NIF inválido após sanitização")
        raise HTTPException(status_code=400, detail="NIF inválido. Deve ter 9 dígitos.")
    
    sanitized_fonte = sanitize_string(client_data.fonte, max_length=100) if client_data.fonte else None
    sanitized_notas = sanitize_string(client_data.notas, max_length=500) if client_data.notas else None

    # Verificar se já existe cliente com mesmo NIF ou email
    # Usar blind index (nif_hash, email_hash) para pesquisa de dados encriptados
    existing_query = []
    if sanitized_nif:
        nif_hash = generate_nif_hash(sanitized_nif)
        if nif_hash:
            existing_query.append({"dados_pessoais.nif_hash": nif_hash})
        # Fallback para dados antigos não migrados
        existing_query.append({"dados_pessoais.nif": sanitized_nif})
    if sanitized_email:
        email_hash = generate_email_hash(sanitized_email)
        if email_hash:
            existing_query.append({"contacto.email_hash": email_hash})
        # Fallback para dados antigos não migrados
        existing_query.append({"contacto.email": sanitized_email.lower()})

    if existing_query:
        existing = await db.clients.find_one({"$or": existing_query})
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Já existe um cliente com este NIF ou email: {existing.get('nome')}"
            )
    
    now = datetime.now(timezone.utc).isoformat()
    
    client = Client(
        id=str(uuid.uuid4()),
        nome=sanitized_nome,
        contacto=ClientContact(
            email=sanitized_email,
            telefone=sanitized_telefone
        ),
        dados_pessoais=ClientPersonalData(
            nif=sanitized_nif
        ),
        portal_access_code=generate_portal_access_code(),
        fonte=sanitized_fonte,
        notas=sanitized_notas,
        created_at=now,
        updated_at=now,
        created_by=user.get("email")
    )
    
    # Encriptar campos sensíveis antes de guardar
    client_dict = client.model_dump()
    client_dict = encrypt_client_data(client_dict)
    
    await db.clients.insert_one(client_dict)

    logger.info(f"Cliente criado: {client.id} - {client.nome} por {user.get('email')}")

    # ============================================================
    # PACOTE FQ-3 — Garantir mapeamento de pasta S3 logo na criação
    # ============================================================
    # Antes, a pasta S3 do cliente só era criada de forma "lazy" no
    # primeiro upload via Portal (ver `services/portal_upload_ops.py`).
    # Isto deixava o cliente sem `s3_folder` até esse momento, o que
    # atrasava/quebrava fluxos que dependem do mapeamento logo após a
    # criação (Explorer S3 admin, checklist de documentos, etc.).
    # Chamamos `ensure_client_folder_mapping` já aqui, imediatamente a
    # seguir à inserção do cliente na BD, e persistimos o resultado via
    # `$set` estrito apenas na chave `s3_folder`.
    try:
        s3_mapping = await asyncio.to_thread(
            s3_service.ensure_client_folder_mapping,
            client.id,
            sanitized_nome,
            None,
            None,
        )
        if s3_mapping.get("success") and s3_mapping.get("s3_folder"):
            await db.clients.update_one(
                {"id": client.id},
                {"$set": {"s3_folder": s3_mapping["s3_folder"]}}
            )
            client_dict["s3_folder"] = s3_mapping["s3_folder"]
            logger.info(
                f"[CLIENT-CREATE][S3-MAPPING] Mapeamento S3 "
                f"{'criado' if s3_mapping.get('created') else 'recuperado'} "
                f"para cliente {client.id}: {s3_mapping['s3_folder']}"
            )
        else:
            logger.warning(
                f"[CLIENT-CREATE][S3-MAPPING] Não foi possível criar/recuperar "
                f"mapeamento S3 para cliente {client.id} ({client.nome})"
            )
    except Exception as e:
        logger.warning(
            f"[CLIENT-CREATE][S3-MAPPING] Erro ao criar mapeamento S3 "
            f"para cliente {client.id}: {e}"
        )

    # ============================================================
    # PACOTE CY — Enviar email de boas-vindas do Portal em background
    # ============================================================
    # Antes o email NÃO era enviado na criação do cliente (só gerava o
    # portal_access_code). Agora dispara em background via asyncio.create_task
    # para não atrasar a resposta da API. Falhas são logadas mas não
    # rebentam o fluxo de criação.
    # ============================================================
    if sanitized_email:
        asyncio.create_task(_send_portal_welcome_email_safe(
            client_email=sanitized_email,
            client_name=sanitized_nome,
            portal_access_code=client.portal_access_code,
            client_id=client.id,
        ))

    # Desencriptar para a resposta
    client_dict = decrypt_client_data(client_dict)
    return Client(**client_dict)

async def run_update_client(
    client_id: str,
    client_data: ClientUpdate,
    request: Request,
    user: dict
):
    """Actualizar dados de um cliente."""
    client = await db.clients.find_one({"id": client_id})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Verificar permissão de edição
    user_role = user.get("role", "")
    user_permissions = user.get("permissions", {})
    user_actions = user_permissions.get("actions", [])
    
    # Se o utilizador tem permissões personalizadas, verificar se tem "edit_client"
    # Caso contrário, verificar pelo role (roles que historicamente podem editar)
    can_edit = "edit_client" in user_actions
    if not can_edit and not user_actions:
        # Sem permissões personalizadas - verificar pelo role
        from models.auth import UserRole
        can_edit = user_role in [UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
                                UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
    
    if not can_edit:
        raise HTTPException(
            status_code=403, 
            detail="Não tem permissão para editar dados do cliente. Apenas visualização."
        )
    
    # Sanitizar inputs
    sanitized_nome = None
    if client_data.nome:
        sanitized_nome = sanitize_name(client_data.nome)
        if not sanitized_nome:
            log_sanitization_rejection("nome", client_data.nome, "Nome vazio ou inválido após sanitização")
            raise HTTPException(status_code=400, detail="Nome inválido. Use apenas letras e espaços.")
    
    sanitized_contacto = None
    if client_data.contacto:
        contact_dump = client_data.contacto.model_dump(exclude_unset=True)
        if "email" in contact_dump and contact_dump["email"]:
            s_email = sanitize_email(contact_dump["email"])
            if not s_email:
                log_sanitization_rejection("contacto.email", contact_dump["email"], "Email inválido após sanitização")
                raise HTTPException(status_code=400, detail="Formato de email inválido.")
            contact_dump["email"] = s_email
        if "telefone" in contact_dump and contact_dump["telefone"]:
            contact_dump["telefone"] = sanitize_phone(contact_dump["telefone"]) or contact_dump["telefone"]
        if "telefone_secundario" in contact_dump and contact_dump["telefone_secundario"]:
            contact_dump["telefone_secundario"] = sanitize_phone(contact_dump["telefone_secundario"]) or contact_dump["telefone_secundario"]
        # Merge with existing contacto to preserve fields not in this update
        existing_contacto = client.get("contacto") or {}
        sanitized_contacto = {**existing_contacto, **contact_dump}
    
    sanitized_dados_pessoais = None
    if client_data.dados_pessoais:
        pessoais_dump = client_data.dados_pessoais.model_dump(exclude_unset=True)
        if "nif" in pessoais_dump and pessoais_dump["nif"]:
            s_nif = sanitize_nif(pessoais_dump["nif"])
            if not s_nif:
                log_sanitization_rejection("dados_pessoais.nif", pessoais_dump["nif"], "NIF inválido após sanitização")
                raise HTTPException(status_code=400, detail="NIF inválido. Deve ter 9 dígitos.")
            pessoais_dump["nif"] = s_nif
        for str_field in ["nome", "documento_id", "morada_fiscal", "phone", "telefone", "nacionalidade", "profissao"]:
            if str_field in pessoais_dump and pessoais_dump[str_field]:
                pessoais_dump[str_field] = sanitize_string(str(pessoais_dump[str_field]), max_length=200)
        # Merge with existing dados_pessoais to preserve fields not in this update
        existing_pessoais = client.get("dados_pessoais") or {}
        sanitized_dados_pessoais = {**existing_pessoais, **pessoais_dump}
    
    sanitized_notas = sanitize_string(client_data.notas, max_length=500) if client_data.notas is not None else None
    
    update_dict = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if sanitized_nome:
        update_dict["nome"] = sanitized_nome
    if sanitized_contacto:
        update_dict["contacto"] = sanitized_contacto
    if sanitized_dados_pessoais:
        update_dict["dados_pessoais"] = sanitized_dados_pessoais
    if client_data.tags is not None:
        update_dict["tags"] = client_data.tags
    if sanitized_notas is not None:
        update_dict["notas"] = sanitized_notas

    # PACOTE CS — Data Provenance: aceitar field_metadata do frontend
    # e fazer merge seguro (não apaga metadata de campos não atualizados).
    # Formato: {"dados_pessoais.nif": {"source": "manual", "updated_at": "...", "confidence": 0.95}}
    raw_body = await request.json() if hasattr(request, 'json') else {}
    field_metadata = raw_body.get("field_metadata")
    if field_metadata and isinstance(field_metadata, dict):
        existing_metadata = client.get("field_metadata") or {}
        merged_metadata = {**existing_metadata, **field_metadata}
        update_dict["field_metadata"] = merged_metadata

    # RGPD: Encriptar dados sensíveis antes de actualizar
    # Isto garante que NIFs, telefones e outros dados sensíveis
    # são guardados encriptados, mesmo em actualizações
    update_dict = encrypt_client_data(update_dict)

    await db.clients.update_one(
        {"id": client_id},
        {"$set": update_dict}
    )
    
    # === SYNC TO LINKED PROCESSES: Propagate name, email, phone, dados_pessoais ===
    process_ids = client.get("process_ids", [])
    if process_ids:
        process_sync = {}

        # 1. Sincronizar NOME do cliente → client_name em todos os processos
        if sanitized_nome:
            process_sync["client_name"] = sanitized_nome
            process_sync["personal_data.nome"] = sanitized_nome
            process_sync["personal_data.name"] = sanitized_nome

        # 2. Sincronizar EMAIL do cliente
        if sanitized_contacto:
            new_email = sanitized_contacto.get("email")
            new_phone = sanitized_contacto.get("telefone")

            if new_email:
                process_sync["client_email"] = new_email
                process_sync["personal_data.email"] = new_email
                from services.encryption import generate_email_hash
                process_sync["personal_data.email_hash"] = generate_email_hash(new_email)
            if new_phone:
                process_sync["client_phone"] = new_phone
                process_sync["personal_data.telefone"] = new_phone
                process_sync["personal_data.phone"] = new_phone

        # 3. Sincronizar DADOS PESSOAIS (NIF, morada, etc.) para personal_data dos processos
        if sanitized_dados_pessoais:
            dados_sync_map = {
                "nif": "personal_data.nif",
                "documento_id": "personal_data.documento_id",
                "data_nascimento": "personal_data.data_nascimento",
                "birth_date": "personal_data.data_nascimento",
                "morada_fiscal": "personal_data.morada_fiscal",
                "estado_civil": "personal_data.estado_civil",
                "profissao": "personal_data.profissao",
                "nacionalidade": "personal_data.nacionalidade",
                "naturalidade": "personal_data.naturalidade",
                "sexo": "personal_data.sexo",
                "nome_pai": "personal_data.nome_pai",
                "nome_mae": "personal_data.nome_mae",
                "data_validade_cc": "personal_data.data_validade_cc",
            }
            # Adicionar NIF hash se NIF foi alterado
            if "nif" in sanitized_dados_pessoais and sanitized_dados_pessoais["nif"]:
                from services.encryption import generate_nif_hash
                nif_hash = generate_nif_hash(sanitized_dados_pessoais["nif"])
                if nif_hash:
                    process_sync["personal_data.nif_hash"] = nif_hash

            for src_key, dst_key in dados_sync_map.items():
                if src_key in sanitized_dados_pessoais and sanitized_dados_pessoais[src_key] is not None:
                    process_sync[dst_key] = sanitized_dados_pessoais[src_key]

        if process_sync:
            await db.processes.update_many(
                {"id": {"$in": process_ids}},
                {"$set": process_sync}
            )
            logger.info(f"Sincronizados dados para {len(process_ids)} processos do cliente {client_id}: {list(process_sync.keys())}")
    
    logger.info(f"Cliente {client_id} actualizado por {user.get('email')}")
    
    return {"success": True, "message": "Cliente actualizado"}
