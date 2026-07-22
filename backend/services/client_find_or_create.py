"""POST /clients/find-or-create.

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

from services.client_crud import run_create_client

async def run_find_or_create_client(
    nome: str,
    user: dict,
    email: Optional[str] = None,
    nif: Optional[str] = None,
    telefone: Optional[str] = None
):
    """
    Encontrar cliente existente ou criar novo.
    
    Procura por NIF, email ou nome similar.
    Se não encontrar, cria um novo cliente.
    """
    # Sanitizar inputs
    sanitized_nome = sanitize_name(nome)
    if not sanitized_nome:
        log_sanitization_rejection("nome", nome or "", "Nome vazio ou inválido após sanitização")
        raise HTTPException(status_code=400, detail="Nome inválido. Use apenas letras e espaços.")
    
    sanitized_email = sanitize_email(email) if email else None
    if email and not sanitized_email:
        log_sanitization_rejection("email", email, "Email inválido após sanitização")
        raise HTTPException(status_code=400, detail="Formato de email inválido.")
    
    sanitized_nif = sanitize_nif(nif) if nif else None
    if nif and not sanitized_nif:
        log_sanitization_rejection("nif", nif, "NIF inválido após sanitização")
        raise HTTPException(status_code=400, detail="NIF inválido. Deve ter 9 dígitos.")
    
    sanitized_telefone = sanitize_phone(telefone) if telefone else None

    # Tentar encontrar por NIF (usar blind index para dados encriptados)
    if sanitized_nif:
        nif_hash = generate_nif_hash(sanitized_nif)
        existing = None
        if nif_hash:
            existing = await db.clients.find_one({"dados_pessoais.nif_hash": nif_hash})
        # Fallback para dados antigos não migrados
        if not existing:
            existing = await db.clients.find_one({"dados_pessoais.nif": sanitized_nif})
        if existing:
            return {
                "found": True,
                "client": existing,
                "match_type": "nif"
            }

    # Tentar encontrar por email (usar blind index para dados encriptados)
    if sanitized_email:
        email_hash = generate_email_hash(sanitized_email)
        existing = None
        if email_hash:
            existing = await db.clients.find_one({"contacto.email_hash": email_hash})
        # Fallback para dados antigos não migrados
        if not existing:
            existing = await db.clients.find_one({"contacto.email": sanitized_email.lower()})
        if existing:
            return {
                "found": True,
                "client": existing,
                "match_type": "email"
            }
    
    # Tentar encontrar por nome similar
    if sanitized_nome:
        # Pesquisa fuzzy pelo nome
        from routes.ai_bulk import normalize_text_for_matching
        nome_norm = normalize_text_for_matching(sanitized_nome)
        
        # Buscar candidatos
        candidates = await db.clients.find(
            {},
            {"_id": 0, "id": 1, "nome": 1}
        ).to_list(length=1000)
        
        for candidate in candidates:
            candidate_norm = normalize_text_for_matching(candidate.get("nome", ""))
            # Match exacto após normalização
            if nome_norm == candidate_norm:
                full_client = await db.clients.find_one({"id": candidate["id"]}, {"_id": 0})
                return {
                    "found": True,
                    "client": full_client,
                    "match_type": "nome"
                }
    
    # Não encontrou - criar novo cliente
    client_data = ClientCreate(
        nome=sanitized_nome,
        email=sanitized_email,
        telefone=sanitized_telefone,
        nif=sanitized_nif,
        fonte="auto_created"
    )
    
    new_client = await run_create_client(client_data, user)
    
    return {
        "found": False,
        "client": new_client.model_dump(),
        "match_type": "created"
    }
