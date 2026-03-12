"""
====================================================================
SERVIÇO DE ATRIBUIÇÃO DE PROCESSOS - CREDITOIMO
====================================================================
Lógica de negócio para atribuição de consultores e intermediários
a processos.
====================================================================
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from database import db

logger = logging.getLogger(__name__)


# ==== VALIDAÇÃO DE ATRIBUIÇÃO ====

async def validate_assignment_user(user_id: str) -> Tuple[bool, Optional[dict], str]:
    """
    Valida se o utilizador existe e pode ser atribuído.
    
    Args:
        user_id: ID do utilizador a validar
        
    Returns:
        Tuple com (válido, dados do utilizador, mensagem de erro)
    """
    if not user_id:
        return False, None, "ID do utilizador não fornecido"
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    
    if not user:
        return False, None, f"Utilizador {user_id} não encontrado"
    
    if not user.get("is_active", True):
        return False, None, f"Utilizador {user.get('name', user_id)} está inactivo"
    
    return True, user, ""


# ==== ATRIBUIÇÃO PRINCIPAL ====

async def assign_consultant_to_process(
    process_id: str,
    consultant_id: str,
    assigning_user: dict
) -> Tuple[bool, dict, str]:
    """
    Atribui um consultor a um processo.
    
    Args:
        process_id: ID do processo
        consultant_id: ID do consultor a atribuir
        assigning_user: Utilizador que está a fazer a atribuição
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    # Validar consultor
    valid, consultant, error = await validate_assignment_user(consultant_id)
    if not valid:
        return False, {}, error
    
    # Atualizar processo
    update_data = {
        "consultant_id": consultant_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, {
        "consultant_id": consultant_id,
        "consultant_name": consultant.get("name", "")
    }, f"Consultor {consultant.get('name')} atribuído com sucesso"


async def assign_mediador_to_process(
    process_id: str,
    mediador_id: str,
    assigning_user: dict
) -> Tuple[bool, dict, str]:
    """
    Atribui um mediador/intermediário a um processo.
    
    Args:
        process_id: ID do processo
        mediador_id: ID do mediador a atribuir
        assigning_user: Utilizador que está a fazer a atribuição
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    # Validar mediador
    valid, mediador, error = await validate_assignment_user(mediador_id)
    if not valid:
        return False, {}, error
    
    # Atualizar processo
    update_data = {
        "mediador_id": mediador_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, {
        "mediador_id": mediador_id,
        "mediador_name": mediador.get("name", "")
    }, f"Mediador {mediador.get('name')} atribuído com sucesso"


async def assign_both_to_process(
    process_id: str,
    consultant_id: Optional[str],
    mediador_id: Optional[str],
    assigning_user: dict
) -> Tuple[bool, dict, str]:
    """
    Atribui consultor e/ou mediador a um processo.
    
    Args:
        process_id: ID do processo
        consultant_id: ID do consultor (opcional)
        mediador_id: ID do mediador (opcional)
        assigning_user: Utilizador que está a fazer a atribuição
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    messages = []
    result_data = {}
    
    # Validar e preparar consultor
    if consultant_id:
        valid, consultant, error = await validate_assignment_user(consultant_id)
        if not valid:
            return False, {}, f"Consultor: {error}"
        update_data["consultant_id"] = consultant_id
        result_data["consultant_id"] = consultant_id
        result_data["consultant_name"] = consultant.get("name", "")
        messages.append(f"Consultor: {consultant.get('name')}")
    
    # Validar e preparar mediador
    if mediador_id:
        valid, mediador, error = await validate_assignment_user(mediador_id)
        if not valid:
            return False, {}, f"Mediador: {error}"
        update_data["mediador_id"] = mediador_id
        result_data["mediador_id"] = mediador_id
        result_data["mediador_name"] = mediador.get("name", "")
        messages.append(f"Mediador: {mediador.get('name')}")
    
    if len(update_data) == 1:  # Apenas updated_at
        return False, {}, "Nenhuma atribuição especificada"
    
    # Atualizar processo
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, result_data, f"Atribuído: {', '.join(messages)}"


# ==== AUTO-ATRIBUIÇÃO ====

async def assign_self_to_process(
    process_id: str,
    user: dict,
    role_type: str = "consultant"
) -> Tuple[bool, dict, str]:
    """
    Atribui o utilizador actual a um processo.
    
    Args:
        process_id: ID do processo
        user: Utilizador actual
        role_type: Tipo de papel ("consultant" ou "mediador")
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    user_id = user.get("id")
    user_name = user.get("name", "")
    
    if role_type == "consultant":
        field = "consultant_id"
    else:
        field = "mediador_id"
    
    update_data = {
        field: user_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, {field: user_id, f"{role_type}_name": user_name}, f"Auto-atribuição como {role_type}: {user_name}"


async def unassign_self_from_process(
    process_id: str,
    user: dict
) -> Tuple[bool, dict, str]:
    """
    Remove a auto-atribuição do utilizador de um processo.
    
    Args:
        process_id: ID do processo
        user: Utilizador actual
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    user_id = user.get("id")
    
    # Verificar se o utilizador está atribuído
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return False, {}, "Processo não encontrado"
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    removed_from = []
    
    if process.get("consultant_id") == user_id:
        update_data["consultant_id"] = None
        removed_from.append("consultor")
    
    if process.get("mediador_id") == user_id:
        update_data["mediador_id"] = None
        removed_from.append("mediador")
    
    if len(update_data) == 1:  # Apenas updated_at
        return False, {}, "Não está atribuído a este processo"
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Erro ao remover atribuição"
    
    return True, update_data, f"Removido de: {', '.join(removed_from)}"


# ==== LISTA DE UTILIZADORES PARA ATRIBUIÇÃO ====

async def get_users_for_assignment(role_filter: Optional[str] = None) -> list:
    """
    Obtém lista de utilizadores disponíveis para atribuição.
    
    Args:
        role_filter: Filtrar por papel específico (opcional)
        
    Returns:
        Lista de utilizadores
    """
    query = {"is_active": True}
    
    if role_filter:
        query["role"] = role_filter
    
    cursor = db.users.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).sort("name", 1)
    
    return await cursor.to_list(length=100)
