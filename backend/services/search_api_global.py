"""Global search handler.

Extraído de `routes/search.py`.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict

from database import db
from services.encryption import (
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
    decrypt_client_data,  # PACOTE DD — desencriptar clientes na pesquisa global
)
from utils.input_sanitization import sanitize_string
from utils.search_filters import (
    create_accent_insensitive_regex,
    build_multiword_search_filter,
)

logger = logging.getLogger(__name__)


async def run_global_search(q: str, limit: int, user: dict) -> Dict[str, Any]:
    """Pesquisa global em processos, clientes e tarefas."""
    # Sanitize search term to prevent ReDoS / regex injection
    search_term = sanitize_string(q, max_length=200)
    if not search_term:
        return {
            "processes": [],
            "clients": [],
            "tasks": []
        }

    # Se o termo for muito curto, retornar resultados vazios (não erro)
    if len(search_term) < 2:
        return {
            "processes": [],
            "clients": [],
            "tasks": []
        }

    # Criar regex para pesquisa que ignora acentos e case
    regex_pattern = create_accent_insensitive_regex(search_term)

    # Para campos que não precisam de ignorar acentos (NIF, email, telefone)
    # usamos regex simples case-insensitive
    simple_regex = {"$regex": re.escape(search_term), "$options": "i"}

    # Verificar se a pesquisa parece um NIF (9 dígitos)
    nif_clean = re.sub(r'[^\d]', '', search_term)
    is_nif_search = len(nif_clean) == 9

    # Verificar se parece um email
    is_email_search = '@' in search_term

    # Verificar se parece um telefone (9+ dígitos)
    telefone_clean = re.sub(r'[^\d]', '', search_term)
    is_telefone_search = (
        len(telefone_clean) >= 9
        and len(telefone_clean) <= 15
        and search_term.replace('+', '').replace(' ', '').isdigit()
    )

    results = {
        "processes": [],
        "clients": [],
        "tasks": []
    }

    try:
        # Pesquisar processos - usar blind indexes quando apropriado
        name_filter_processes = build_multiword_search_filter(search_term, "client_name")
        process_search_conditions = [
            name_filter_processes,
            {"process_type": regex_pattern},
        ]

        # Se parece NIF, usar blind index
        if is_nif_search:
            nif_hash = generate_nif_hash(nif_clean)
            if nif_hash:
                process_search_conditions.append({"personal_data.nif_hash": nif_hash})
            # Fallback para dados antigos não migrados
            process_search_conditions.append({"personal_data.nif": simple_regex})
        else:
            process_search_conditions.append({"personal_data.nif": simple_regex})

        # Se parece email, usar blind index
        if is_email_search:
            email_hash = generate_email_hash(search_term.lower().strip())
            if email_hash:
                process_search_conditions.append({"personal_data.email_hash": email_hash})
            process_search_conditions.append({"personal_data.email": simple_regex})
            # Também pesquisar no campo client_email (nível raiz)
            process_search_conditions.append({"client_email": simple_regex})
        else:
            process_search_conditions.append({"personal_data.email": simple_regex})
            process_search_conditions.append({"client_email": simple_regex})

        process_query = {"$or": process_search_conditions}

        processes = await db.processes.find(
            process_query,
            {
                "_id": 0,
                "id": 1,
                "client_name": 1,
                "process_type": 1,
                "status": 1,
                "personal_data.nif": 1
            }
        ).limit(limit).to_list(limit)

        results["processes"] = processes

        # Pesquisar CLIENTES (registos de clientes) - usar blind indexes
        name_filter_clients = build_multiword_search_filter(search_term, "nome")
        client_search_conditions = [
            name_filter_clients,
        ]

        # Se parece NIF, usar blind index
        if is_nif_search:
            nif_hash = generate_nif_hash(nif_clean)
            if nif_hash:
                client_search_conditions.append({"dados_pessoais.nif_hash": nif_hash})
                client_search_conditions.append({"titular2_data.nif_hash": nif_hash})
            # Fallback para dados antigos não migrados
            client_search_conditions.append({"dados_pessoais.nif": simple_regex})
        else:
            client_search_conditions.append({"dados_pessoais.nif": simple_regex})

        # Se parece email, usar blind index
        if is_email_search:
            email_hash = generate_email_hash(search_term.lower().strip())
            if email_hash:
                client_search_conditions.append({"contacto.email_hash": email_hash})
            client_search_conditions.append({"contacto.email": simple_regex})
        else:
            client_search_conditions.append({"contacto.email": simple_regex})

        # Se parece telefone, usar blind index
        if is_telefone_search:
            telefone_hash = generate_telefone_hash(telefone_clean)
            if telefone_hash:
                client_search_conditions.append({"contacto.telefone_hash": telefone_hash})
            client_search_conditions.append({"contacto.telefone": simple_regex})
        else:
            client_search_conditions.append({"contacto.telefone": simple_regex})

        # PACOTE DG — excluir clientes eliminados (soft-delete) da pesquisa global.
        client_query = {"$or": client_search_conditions, "is_deleted": {"$ne": True}}

        clients = await db.clients.find(
            client_query,
            {
                "_id": 0,
                "id": 1,
                "nome": 1,
                "dados_pessoais": 1,
                "contacto": 1,
                "process_ids": 1,
                "assigned_to": 1,
                "status": 1,
                "fase_principal": 1,
            }
        ).limit(limit).to_list(limit)

        # Formatar resultados dos clientes
        # PACOTE DD — desencriptar campos sensíveis (NIF, telefone, documento_id)
        # antes de devolver ao frontend para evitar hashes "ENC:" na UI.
        formatted_clients = []
        for client in clients:
            decrypted_client = decrypt_client_data(client)

            # Se tem processos, usar o primeiro processo válido para navegação
            process_ids = decrypted_client.get("process_ids", [])
            first_process_id = None

            # Verificar se o primeiro processo existe realmente
            if process_ids:
                # Verificar se o processo existe na coleção processes
                existing_process = await db.processes.find_one(
                    {"id": process_ids[0]},
                    {"_id": 0, "id": 1}
                )
                if existing_process:
                    first_process_id = process_ids[0]

            formatted_clients.append({
                "id": decrypted_client.get("id"),
                "client_name": decrypted_client.get("nome"),
                "personal_data": decrypted_client.get("dados_pessoais", {}),
                "contacto": decrypted_client.get("contacto", {}),
                "has_process": bool(first_process_id),
                "process_count": len(process_ids),
                "first_process_id": first_process_id,
                "status": decrypted_client.get("fase_principal", {}).get("status") or decrypted_client.get("status"),
            })

        results["clients"] = formatted_clients

        # Pesquisar tarefas
        name_filter_tasks = build_multiword_search_filter(search_term, "client_name")
        task_query = {
            "$or": [
                {"title": regex_pattern},
                {"description": regex_pattern},
                name_filter_tasks,
            ]
        }

        tasks = await db.tasks.find(
            task_query,
            {
                "_id": 0,
                "id": 1,
                "title": 1,
                "status": 1,
                "priority": 1,
                "client_name": 1
            }
        ).limit(limit).to_list(limit)

        results["tasks"] = tasks

        logger.info(
            f"Pesquisa global '{search_term}': {len(processes)} processos, "
            f"{len(formatted_clients)} clientes, {len(tasks)} tarefas"
        )

    except Exception as e:
        logger.error(f"Erro na pesquisa global: {e}")

    return results
