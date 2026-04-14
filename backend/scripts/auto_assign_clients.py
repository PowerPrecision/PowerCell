#!/usr/bin/env python3
"""
====================================================================
SCRIPT DE ATRIBUIÇÃO AUTOMÁTICA DE PROCESSOS - POWERCELL
====================================================================
Este script atribui automaticamente processos a utilizadores baseado
em regras configuráveis.

Uso:
    python scripts/auto_assign_clients.py [--dry-run] [--role ROLE]

Opções:
    --dry-run    Simula as atribuições sem guardar na base de dados
    --role       Filtrar por role de utilizador (consultor, intermediario, indexacao)
    --limit      Limite de processos a processar (default: 10000)
    --verbose    Mostrar mais detalhes

Regras de atribuição:
    1. Processos sem consultor/mediador atribuído
    2. Distribuição round-robin entre utilizadores disponíveis
    3. Respeita capacidade máxima por utilizador (configurável)
====================================================================
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Adicionar diretório pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from models.auth import UserRole


# ====================================================================
# CONFIGURAÇÕES
# ====================================================================

# Capacidade máxima de processos por utilizador (por role)
# Valores altos para garantir que todos os processos são atribuídos
MAX_PROCESS_PER_USER = {
    UserRole.CONSULTOR: 10000,
    UserRole.INTERMEDIARIO: 10000,
    UserRole.MEDIADOR: 10000,
    UserRole.INDEXACAO: 10000,
}

# Roles que podem receber atribuições automáticas
# CEO e DIRETOR excluídos
ELIGIBLE_ROLES = [
    UserRole.CONSULTOR,
    UserRole.INTERMEDIARIO,
    UserRole.MEDIADOR,
    UserRole.INDEXACAO,
]

# Logs
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ====================================================================
# FUNÇÕES AUXILIARES
# ====================================================================

async def get_unassigned_processes(limit: int = 10000) -> List[Dict[str, Any]]:
    """
    Obtém processos sem consultor/mediador atribuído.
    
    Args:
        limit: Número máximo de processos a retornar
        
    Returns:
        Lista de processos não atribuídos
    """
    # Processos que não têm consultor nem mediador atribuído
    # E que não são dados de teste (client_name != "Cliente")
    query = {
        "$and": [
            {
                "$or": [
                    {"assigned_consultor_id": None},
                    {"assigned_consultor_id": {"$exists": False}},
                ]
            },
            {
                "$or": [
                    {"assigned_mediador_id": None},
                    {"assigned_mediador_id": {"$exists": False}},
                ]
            },
            {"client_name": {"$ne": "Cliente"}},  # Excluir dados de teste
        ]
    }
    
    processes = await db.processes.find(query).limit(limit).to_list(limit)
    
    logger.info(f"Encontrados {len(processes)} processos não atribuídos")
    
    return processes


async def get_available_users(role: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Obtém utilizadores disponíveis para atribuição.
    
    Args:
        role: Filtrar por role específico (opcional)
        
    Returns:
        Lista de utilizadores disponíveis
    """
    # Query base - incluir utilizadores ativos ou sem campo is_active definido
    query = {
        "$or": [
            {"is_active": True},
            {"is_active": {"$exists": False}},
        ]
    }
    
    if role:
        query["role"] = role
    else:
        query["role"] = {"$in": ELIGIBLE_ROLES}
    
    users = await db.users.find(query).to_list(50)
    
    # Contar processos atuais de cada utilizador
    for user in users:
        # Contar processos atribuídos como consultor ou mediador
        count_consultor = await db.processes.count_documents({"assigned_consultor_id": user["id"]})
        count_mediador = await db.processes.count_documents({"assigned_mediador_id": user["id"]})
        user["current_process_count"] = count_consultor + count_mediador
        user["max_processes"] = MAX_PROCESS_PER_USER.get(user["role"], 50)
        user["available_slots"] = user["max_processes"] - user["current_process_count"]
    
    # Ordenar por disponibilidade (mais slots disponíveis primeiro)
    users.sort(key=lambda u: u["available_slots"], reverse=True)
    
    logger.info(f"Encontrados {len(users)} utilizadores disponíveis")
    for user in users:
        logger.info(f"  - {user.get('name', user.get('email'))} ({user['role']}): "
                   f"{user['current_process_count']}/{user['max_processes']} processos "
                   f"({user['available_slots']} slots disponíveis)")
    
    return users


async def assign_process_to_user(
    process: Dict[str, Any],
    user: Dict[str, Any],
    dry_run: bool = False
) -> bool:
    """
    Atribui um processo a um utilizador.
    
    Args:
        process: Dados do processo
        user: Dados do utilizador
        dry_run: Se True, não guarda na base de dados
        
    Returns:
        True se atribuído com sucesso
    """
    process_id = process.get("id")
    user_id = user["id"]
    user_name = user.get("name", user.get("email", "Utilizador"))
    user_role = user.get("role")
    
    if dry_run:
        logger.info(f"[DRY-RUN] Atribuir processo {process_id} a {user_name}")
        return True
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Determinar campo de atribuição baseado no role
    if user_role in [UserRole.INTERMEDIARIO, UserRole.MEDIADOR]:
        update_fields = {
            "assigned_mediador_id": user_id,
            "mediador_name": user_name,
            "updated_at": now
        }
    else:
        update_fields = {
            "assigned_consultor_id": user_id,
            "consultor_name": user_name,
            "updated_at": now
        }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_fields}
    )
    
    if result.modified_count > 0:
        # Actualizar também o cliente se existir
        client_id = process.get("client_id")
        if client_id:
            await db.clients.update_one(
                {"id": client_id},
                {"$set": {
                    "assigned_to": user_id,
                    "assigned_to_name": user_name,
                    "assigned_at": now
                }}
            )
        return True
    
    return False


async def run_auto_assignment(
    dry_run: bool = False,
    role_filter: Optional[str] = None,
    limit: int = 10000,
    verbose: bool = False
) -> Dict[str, int]:
    """
    Executa a atribuição automática de processos.
    
    Args:
        dry_run: Se True, não guarda alterações
        role_filter: Filtrar por role de utilizador
        limit: Limite de processos a processar
        verbose: Mostrar mais detalhes
        
    Returns:
        Estatísticas da execução
    """
    logger.info("=" * 60)
    logger.info("INICIANDO ATRIBUIÇÃO AUTOMÁTICA DE PROCESSOS")
    logger.info(f"Modo: {'SIMULAÇÃO (dry-run)' if dry_run else 'EXECUÇÃO REAL'}")
    logger.info("=" * 60)
    
    stats = {
        "processes_found": 0,
        "processes_assigned": 0,
        "users_available": 0,
        "errors": 0
    }
    
    # 1. Obter processos não atribuídos
    processes = await get_unassigned_processes(limit)
    stats["processes_found"] = len(processes)
    
    if not processes:
        logger.info("Nenhum processo para atribuir.")
        return stats
    
    # 2. Obter utilizadores disponíveis
    users = await get_available_users(role_filter)
    stats["users_available"] = len(users)
    
    if not users:
        logger.warning("Nenhum utilizador disponível para atribuição!")
        return stats
    
    # 3. Distribuir processos round-robin
    user_index = 0
    users_with_capacity = [u for u in users if u["available_slots"] > 0]
    
    if not users_with_capacity:
        logger.warning("Todos os utilizadores estão com capacidade máxima!")
        return stats
    
    for process in processes:
        # Encontrar próximo utilizador com capacidade
        assigned = False
        attempts = 0
        
        while attempts < len(users_with_capacity) and not assigned:
            user = users_with_capacity[user_index % len(users_with_capacity)]
            
            if user["available_slots"] <= 0:
                user_index += 1
                attempts += 1
                continue
            
            process_id = process.get("id")
            client_name = process.get("client_name", "N/A")
            user_name = user.get("name", user.get("email", "Utilizador"))
            
            if verbose:
                logger.info(f"Atribuindo processo de '{client_name}' a '{user_name}'...")
            
            # Atribuir processo
            success = await assign_process_to_user(process, user, dry_run)
            
            if success:
                stats["processes_assigned"] += 1
                
                # Actualizar contagem local
                user["current_process_count"] += 1
                user["available_slots"] -= 1
                
                assigned = True
            
            user_index += 1
            attempts += 1
        
        if not assigned:
            logger.warning(f"Não foi possível atribuir processo {process.get('id')}")
            stats["errors"] += 1
    
    # 4. Resumo
    logger.info("=" * 60)
    logger.info("RESUMO DA EXECUÇÃO:")
    logger.info(f"  Processos encontrados: {stats['processes_found']}")
    logger.info(f"  Processos atribuídos: {stats['processes_assigned']}")
    logger.info(f"  Utilizadores disponíveis: {stats['users_available']}")
    logger.info(f"  Erros: {stats['errors']}")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("⚠️  MODO SIMULAÇÃO - Nenhuma alteração foi guardada!")
        logger.info("   Execute sem --dry-run para aplicar as alterações.")
    
    return stats


# ====================================================================
# MAIN
# ====================================================================

def main():
    """Ponto de entrada CLI para atribuição automática de processos.

    Distribui processos sem consultor/mediador atribuído por um algoritmo
    round-robin entre utilizadores ativos com capacidade disponível.
    Suporta os seguintes argumentos:

    - ``--dry-run``: Simula as atribuições sem persistir na base de dados.
    - ``--role ROLE``: Filtra utilizadores elegíveis por role específico.
    - ``--limit N``: Limita o número de processos a processar (default: 10000).
    - ``--verbose``: Mostra detalhe de cada atribuição.

    Processos com ``client_name == "Cliente"`` são excluídos (dados de teste).
    """
    parser = argparse.ArgumentParser(
        description="Atribuição automática de processos a utilizadores"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula as atribuições sem guardar na base de dados"
    )
    parser.add_argument(
        "--role",
        type=str,
        choices=["consultor", "intermediario", "mediador", "indexacao"],
        help="Filtrar por role de utilizador"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Limite de processos a processar (default: 10000)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar mais detalhes"
    )
    
    args = parser.parse_args()
    
    asyncio.run(run_auto_assignment(
        dry_run=args.dry_run,
        role_filter=args.role,
        limit=args.limit,
        verbose=args.verbose
    ))


if __name__ == "__main__":
    main()
