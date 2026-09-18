"""POST /clients/{id}/assign — atribuir cliente e criar processo.

Extraído de `routes/clients.py`.

PACOTE 9:
- Guard de sobreposição: o cliente já atribuído a outro utilizador só
  pode ser re-atribuído por perfis de gestão (admin/ceo/diretor).
- Cargo efectivo (X-Active-Role/UCR) em vez da role primária do JWT —
  utilizadores multi-perfil passam a ser validados pelo perfil activo.
- A pasta S3 do processo é criada de VERDADE no S3 (marcadores .keep +
  reutilização de pastas existentes) e o mapeamento é persistido no
  processo E no cliente — antes gravava-se apenas uma string de path
  calculada, sem estrutura no bucket.
- Campos multi-assignee (assigned_consultor_ids/consultor_names, etc.)
  preenchidos em simultâneo com os singulars de compatibilidade.
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

async def run_assign_client_to_user(
    client_id: str,
    user: dict,
    assign_to_user_id: Optional[str] = None,
    create_process: bool = True,
    process_type: str = 'credito_habitacao'
):
    """
    Atribuir um cliente a um utilizador.
    
    FLUXO:
    1. Atribui o cliente ao utilizador
    2. Se create_process=True, cria automaticamente um processo
    
    Permissões:
    - Admin/CEO/Diretor: Podem atribuir a qualquer utilizador
    - Consultor/Intermediario: Atribuem a si próprios
    """
    # PACOTE 9 — cargo EFECTIVO (X-Active-Role resolvido contra UCR em
    # get_current_user) em vez da role primária do JWT: um utilizador
    # multi-perfil (ex.: admin com perfil activo de consultor) passa a ser
    # validado pelo perfil com que está a trabalhar neste momento.
    user_role = user.get("effective_role") or user.get("role", "")
    user_id = user.get("id", "")
    
    
    # Determinar utilizador de destino
    if user_role in ["admin", "ceo", "diretor"]:
        target_user_id = assign_to_user_id or user_id
    else:
        target_user_id = user_id  # Apenas a si próprio
    
    # Buscar cliente
    client = await db.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # ============================================================
    # PACOTE 9 — GUARD DE SOBREPOSIÇÃO
    # ============================================================
    # O sistema nunca pode (re)atribuir automaticamente um cliente que
    # já tem alguém atribuído. A reatribuição deliberada continua a ser
    # possível apenas para perfis de gestão (admin/ceo/diretor).
    existing_assignee = (client.get("assigned_to") or "").strip()
    if (
        existing_assignee
        and existing_assignee != target_user_id
        and user_role not in ("admin", "ceo", "diretor")
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Este cliente já está atribuído a outro utilizador. "
                "Apenas Admin, CEO ou Diretor podem re-atribuir clientes."
            ),
        )

    # Desencriptar dados sensíveis do cliente antes de copiar para o processo
    # Isto evita dupla encriptação quando o processo for encriptado
    client = decrypt_client_data(client)
    
    # Buscar utilizador de destino
    target_user = await db.users.find_one({"id": target_user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    process_id = None
    process_number = None
    
    # Criar processo se solicitado
    if create_process:
        # Obter próximo número de processo
        process_number = await get_next_process_number()
        process_id = str(uuid.uuid4())
        
        # Obter estado inicial
        first_status = await db.workflow_statuses.find_one({}, {"_id": 0}, sort=[("order", 1)])
        initial_status = first_status["name"] if first_status else "clientes_espera"
        
        # Preparar dados do processo
        client_email = client.get("contacto", {}).get("email", "")
        client_phone = client.get("contacto", {}).get("telefone", "")
        client_name = client.get("nome", "")
        
        # VALIDAÇÃO: E-mail obrigatório para acesso ao Portal do Cliente
        if not client_email or not client_email.strip():
            raise HTTPException(
                status_code=400,
                detail="O e-mail é obrigatório para a criação do Portal do Cliente. "
                       "Adicione um e-mail de contacto ao cliente antes de atribuir."
            )
        
        personal_data = client.get("dados_pessoais", {}) or {}
        if client_email and not personal_data.get("email"):
            personal_data["email"] = client_email
        if client_phone and not personal_data.get("telefone"):
            personal_data["telefone"] = client_phone
        if client_name and not personal_data.get("nome"):
            personal_data["nome"] = client_name
        # Remover blind indexes (nif_hash, email_hash) que não pertencem ao processo
        personal_data.pop("nif_hash", None)
        personal_data.pop("email_hash", None)
        personal_data.pop("telefone_hash", None)
        
        # Criar documento do processo
        # PACOTE 9 — o s3_folder gravado no doc é apenas um valor INICIAL de
        # fallback (quando o S3 não está configurado). A estrutura REAL no
        # bucket (marcadores .keep + reutilização de pastas existentes) é
        # garantida logo após a inserção via ensure_s3_mapping_on_process_create,
        # que também faz o backfill do mapeamento no documento do cliente.
        titular2_data = client.get("titular2_data")
        # Remover blind indexes do titular2_data
        if titular2_data and isinstance(titular2_data, dict):
            titular2_data.pop("nif_hash", None)
        second_client_name = titular2_data.get("name") if titular2_data else None
        
        # Fallback determinístico (mesma convenção de naming do serviço S3)
        safe_name = "_".join(w.capitalize() for w in client_name.strip().split()) if client_name else process_id[:8]
        s3_folder = f"Documentação Clientes/{safe_name}"
        if second_client_name:
            safe_second_name = "_".join(w.capitalize() for w in second_client_name.strip().split())
            s3_folder = f"Documentação Clientes/{safe_name}_e_{safe_second_name}"
        
        process_doc = {
            "id": process_id,
            "process_number": process_number,
            "client_ids": [client_id],
            "client_id": client_id,
            "client_name": client_name,
            "client_email": client_email,
            "client_phone": client_phone,
            "client_nif": client.get("dados_pessoais", {}).get("nif"),
            "process_type": process_type,
            "status": initial_status,
            "is_active": True,
            "personal_data": personal_data,
            "financial_data": client.get("dados_financeiros", {}),
            "real_estate_data": client.get("dados_imobiliarios", {}),
            "titular2_data": client.get("titular2_data"),
            "credit_data": None,
            "has_property": client.get("has_property", False),
            "idade_menos_35": client.get("idade_menos_35", False),
            "s3_folder": s3_folder,
            "source": "client_assignment",
            "created_at": now,
            "updated_at": now,
            "created_by": user.get("email")
        }
        
        # Atribuir automaticamente baseado no papel do utilizador de destino
        # PACOTE 9 — preencher também os campos multi-assignee (listas) em
        # sincronia com os singulars de compatibilidade, tal como faz o
        # build_staff_assign_update do fluxo manual.
        target_role = target_user.get("role", "")
        if target_role == "intermediario":
            process_doc["assigned_mediador_id"] = target_user_id
            process_doc["mediador_name"] = target_user.get("name")
            process_doc["assigned_mediador_ids"] = [target_user_id]
            process_doc["mediador_names"] = [target_user.get("name")]
        elif target_role == "consultor":
            process_doc["assigned_consultor_id"] = target_user_id
            process_doc["consultor_name"] = target_user.get("name")
            process_doc["consultor_id"] = target_user_id  # Consultor associado ao processo
            process_doc["assigned_consultor_ids"] = [target_user_id]
            process_doc["consultor_names"] = [target_user.get("name")]
        elif target_role == "indexacao":
            process_doc["assigned_indexacao_id"] = target_user_id

        # Encriptar dados sensíveis do processo antes de inserir
        # (o cliente já foi desencriptado acima, por isso os dados estão em plain text)
        from services.process_service import encrypt_sensitive_data as encrypt_process_data
        process_doc = encrypt_process_data(process_doc)

        # Inserir processo
        await db.processes.insert_one(process_doc)

        # ============================================================
        # PACOTE 9 — CRIAR ESTRUTURA S3 REAL NO MOMENTO DA CRIAÇÃO
        # ============================================================
        # Antes: gravava-se apenas a string de path calculada acima — sem
        # marcadores .keep no bucket, sem reutilização de pastas existentes
        # (risco de duplicados) e sem mapeamento no documento do cliente.
        # Agora: ensure_client_folder_mapping cria/verifica a estrutura e o
        # mapeamento correcto é persistido no processo E no cliente.
        # Degradação graciosa — falhas S3 nunca rebentam a atribuição.
        try:
            from services.s3_mapping_on_create import (
                ensure_s3_mapping_on_process_create,
            )

            await ensure_s3_mapping_on_process_create(
                process_id=process_id,
                client_id=client_id,
                client_name=client_name,
                second_client_name=second_client_name,
                process_existing_s3_folder=process_doc.get("s3_folder"),
            )
        except Exception as e:
            logger.warning(
                f"[ASSIGN-CLIENT][S3-MAPPING] Erro ao garantir mapeamento S3 "
                f"para processo {process_id}: {e}"
            )
        
        # ============================================================
        # AUTO-ATRIBUIÇÃO DE INDEXADOR
        # Se o destino NÃO é indexação, invocar assign_to_indexer() para:
        # 1. Encontrar o indexador com menor carga (< 15 processos ativos)
        # 2. Atribuir o processo ao indexador (assigned_indexacao_id)
        # 3. Se nenhum indexador disponível → status = fila_espera
        # ============================================================
        if target_role != "indexacao" and process_id:
            try:
                from services.process_assignment import assign_to_indexer
                assign_success, assign_data, assign_msg = await assign_to_indexer(process_id)
                if assign_success and assign_data.get("assigned"):
                    logger.info(
                        f"[ASSIGN-CLIENT] Indexador auto-atribuído: {assign_data.get('indexacao_name')} "
                        f"para processo {process_id}"
                    )
                else:
                    logger.warning(
                        f"[ASSIGN-CLIENT] Sem indexador disponível para processo {process_id}: {assign_msg}"
                    )
            except Exception as e:
                logger.warning(f"[ASSIGN-CLIENT] Erro na auto-atribuição de indexador para processo {process_id}: {e}")
    
    # Actualizar cliente + marcar lead como convertido
    if process_id:
        await db.clients.update_one(
            {"id": client_id},
            {
                "$set": {
                    "assigned_to": target_user_id,
                    "assigned_at": now,
                    "updated_at": now,
                    "lead_status": "converted"  # Lead já não aparece na página de Registos
                },
                "$addToSet": {"process_ids": process_id}
            }
        )
    else:
        await db.clients.update_one(
            {"id": client_id},
            {"$set": {"assigned_to": target_user_id, "assigned_at": now, "updated_at": now}}
        )
    
    logger.info(f"Cliente {client_id} atribuído a {target_user_id} por {user.get('email')}")
    
    return {
        "success": True,
        "message": f"Cliente atribuído a {target_user.get('name')}",
        "client_id": client_id,
        "assigned_to": target_user_id,
        "assigned_to_name": target_user.get("name"),
        "process_created": create_process,
        "process_id": process_id,
        "process_number": process_number
    }
