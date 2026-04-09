"""
Search Routes - Pesquisa Global
Endpoint para pesquisa unificada em processos, clientes e tarefas
"""
import logging
import unicodedata
import re
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query

from database import db
from services.auth import get_current_user
from services.encryption import generate_nif_hash, generate_email_hash, generate_telefone_hash
from utils.input_sanitization import (sanitize_string, sanitize_email, sanitize_phone, sanitize_url, log_sanitization_rejection)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


def normalize_text(text: str) -> str:
    """
    Remove acentos e normaliza texto para pesquisa.
    Exemplo: 'José' -> 'Jose', 'São Paulo' -> 'Sao Paulo'
    """
    if not text:
        return ""
    # Normalizar para forma NFD e remover caracteres combinantes (acentos)
    normalized = unicodedata.normalize('NFD', text)
    # Remover caracteres diacríticos (acentos, cedilhas, etc.)
    result = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
    return result.lower()


def create_accent_insensitive_regex(search_term: str) -> dict:
    """
    Cria um regex MongoDB que ignora acentos.
    
    Exemplo: pesquisar 'jose' encontra 'José', 'JOSE', 'josé', 'JÓSÉ'
    
    Funciona convertendo cada caractere numa classe que inclui todas as variantes acentuadas.
    """
    if not search_term:
        return {"$regex": "", "$options": "i"}
    
    # Mapeamento de caracteres base para todas as suas variantes acentuadas
    accent_map = {
        'a': '[aàáâãäåAÀÁÂÃÄÅ]',
        'e': '[eèéêëEÈÉÊË]',
        'i': '[iìíîïIÌÍÎÏ]',
        'o': '[oòóôõöOÒÓÔÕÖ]',
        'u': '[uùúûüUÙÚÛÜ]',
        'c': '[cçCÇ]',
        'n': '[nñNÑ]',
        'y': '[yýÿYÝŸ]',
        's': '[sS]',  # Não há variante acentuada comum
        'r': '[rR]',
        'l': '[lL]',
        't': '[tT]',
        'd': '[dD]',
        'm': '[mM]',
        'p': '[pP]',
        'b': '[bB]',
        'f': '[fF]',
        'g': '[gG]',
        'h': '[hH]',
        'j': '[jJ]',
        'k': '[kK]',
        'q': '[qQ]',
        'v': '[vV]',
        'w': '[wW]',
        'x': '[xX]',
        'z': '[zZ]',
    }
    
    # Construir padrão regex caractere a caractere
    pattern_parts = []
    for char in search_term.lower():
        if char in accent_map:
            pattern_parts.append(accent_map[char])
        elif char.isalnum():
            # Outros caracteres alfanuméricos sem variantes acentuadas
            pattern_parts.append(f'[{char}{char.upper()}]' if char.isalpha() else char)
        else:
            # Caracteres especiais - escapar
            pattern_parts.append(re.escape(char))
    
    pattern = ''.join(pattern_parts)
    return {"$regex": pattern, "$options": ""}  # Não precisa de 'i' porque já incluímos maiúsculas


@router.get("/global")
async def global_search(
    q: str = Query(..., min_length=1, description="Termo de pesquisa"),
    limit: int = Query(5, ge=1, le=20, description="Limite de resultados por tipo"),
    user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Pesquisa global em processos, clientes e tarefas.
    
    Usado pelo modal de pesquisa rápida (Ctrl+K).
    
    Returns:
        {
            "processes": [...],
            "clients": [...],
            "tasks": [...]
        }
    """
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
    is_telefone_search = len(telefone_clean) >= 9 and len(telefone_clean) <= 15 and search_term.replace('+', '').replace(' ', '').isdigit()
    
    results = {
        "processes": [],
        "clients": [],
        "tasks": []
    }
    
    try:
        # Pesquisar processos - usar blind indexes quando apropriado
        process_search_conditions = [
            {"client_name": regex_pattern},
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
        else:
            process_search_conditions.append({"personal_data.email": simple_regex})
        
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
        client_search_conditions = [
            {"nome": regex_pattern},
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
        
        client_query = {"$or": client_search_conditions}
        
        clients = await db.clients.find(
            client_query,
            {
                "_id": 0,
                "id": 1,
                "nome": 1,
                "dados_pessoais": 1,
                "contacto": 1,
                "process_ids": 1,
                "assigned_to": 1
            }
        ).limit(limit).to_list(limit)
        
        # Formatar resultados dos clientes
        formatted_clients = []
        for client in clients:
            # Se tem processos, usar o primeiro processo válido para navegação
            process_ids = client.get("process_ids", [])
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
                "id": client.get("id"),
                "client_name": client.get("nome"),
                "personal_data": client.get("dados_pessoais", {}),
                "contacto": client.get("contacto", {}),
                "has_process": bool(first_process_id),
                "process_count": len(process_ids),
                "first_process_id": first_process_id
            })
        
        results["clients"] = formatted_clients
        
        # Pesquisar tarefas
        task_query = {
            "$or": [
                {"title": regex_pattern},
                {"description": regex_pattern},
                {"client_name": regex_pattern},
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
        
        logger.info(f"Pesquisa global '{search_term}': {len(processes)} processos, {len(formatted_clients)} clientes, {len(tasks)} tarefas")
        
    except Exception as e:
        logger.error(f"Erro na pesquisa global: {e}")
    
    return results


@router.get("/processes")
async def search_processes(
    q: str = Query(..., min_length=2),
    status: Optional[str] = None,
    process_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Pesquisa avançada em processos.
    
    Args:
        q: Termo de pesquisa
        status: Filtrar por status
        process_type: Filtrar por tipo de processo
        limit: Limite de resultados
    """
    # Sanitize search term to prevent ReDoS / regex injection
    search_term = sanitize_string(q, max_length=200)
    if not search_term:
        return []
    
    regex_pattern = create_accent_insensitive_regex(search_term)
    simple_regex = {"$regex": re.escape(search_term), "$options": "i"}
    
    query = {
        "$or": [
            {"client_name": regex_pattern},
            {"personal_data.nif": simple_regex},
            {"personal_data.email": simple_regex},
            {"personal_data.telefone": simple_regex},
        ]
    }
    
    if status:
        query["status"] = status
    
    if process_type:
        query["process_type"] = process_type
    
    processes = await db.processes.find(
        query,
        {"_id": 0}
    ).sort("updated_at", -1).limit(limit).to_list(limit)
    
    return processes


@router.get("/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=1),
    user: dict = Depends(get_current_user)
) -> List[str]:
    """
    Obter sugestões de pesquisa baseadas no histórico e dados existentes.
    """
    # Sanitize search term to prevent ReDoS / regex injection
    search_term = sanitize_string(q, max_length=200)
    if not search_term:
        return []
    search_term = search_term.lower()
    suggestions = set()
    
    # Regex que ignora acentos para sugestões
    regex_pattern = create_accent_insensitive_regex(search_term)
    
    # Buscar nomes de clientes que começam com o termo
    clients = await db.processes.find(
        {"client_name": regex_pattern},
        {"_id": 0, "client_name": 1}
    ).limit(5).to_list(5)
    
    for client in clients:
        suggestions.add(client.get("client_name", ""))
    
    # Buscar títulos de tarefas
    tasks = await db.tasks.find(
        {"title": regex_pattern},
        {"_id": 0, "title": 1}
    ).limit(3).to_list(3)
    
    for task in tasks:
        suggestions.add(task.get("title", ""))
    
    return list(suggestions)[:10]
