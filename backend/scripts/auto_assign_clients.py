#!/usr/bin/env python3
"""
====================================================================
SCRIPT DE ATRIBUIÇÃO AUTOMÁTICA DE CLIENTES - POWERCELL
====================================================================
Este script atribui automaticamente clientes a utilizadores baseado
em regras configuráveis.

Uso:
    python scripts/auto_assign_clients.py [--dry-run] [--role ROLE]

Opções:
    --dry-run    Simula as atribuições sem guardar na base de dados
    --role       Filtrar por role de utilizador (consultor, mediador, indexacao)
    --limit      Limite de clientes a processar (default: 100)
    --verbose    Mostrar mais detalhes

Regras de atribuição:
    1. Clientes sem utilizador atribuído
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
from models.auth import UserRole, UserRoleEnum


# ====================================================================
# CONFIGURAÇÕES
# ====================================================================

# Capacidade máxima de clientes por utilizador (por role)
MAX_CLIENTS_PER_USER = {
    UserRole.CONSULTOR: 50,
    UserRole.INTERMEDIARIO: 50,  # Intermediário de Crédito
    UserRole.MEDIADOR: 30,       # Legacy alias
    UserRole.INDEXACAO: 100,
    UserRole.CEO: 100,           # CEO também pode ter clientes
    UserRole.DIRETOR: 80,        # Diretor também pode ter clientes
}

# Prioridade de roles para atribuição (strings diretamente)
# Inclui todos os roles que podem receber clientes
PRIORITY_ROLES = [
    UserRole.CONSULTOR,
    UserRole.INTERMEDIARIO,  # Intermediário de Crédito
    UserRole.MEDIADOR,       # Legacy alias
    UserRole.INDEXACAO,
    UserRole.CEO,
    UserRole.DIRETOR,
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

async def get_unassigned_clients(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Obtém clientes sem utilizador atribuído.
    
    Args:
        limit: Número máximo de clientes a retornar
        
    Returns:
        Lista de clientes não atribuídos
    """
    # Clientes da coleção 'clients' que não têm assigned_to
    unassigned_clients = await db.clients.find({
        "$or": [
            {"assigned_to": None},
            {"assigned_to": ""},
            {"assigned_to": {"$exists": False}}
        ]
    }).limit(limit).to_list(limit)
    
    logger.info(f"Encontrados {len(unassigned_clients)} clientes não atribuídos na coleção 'clients'")
    
    return unassigned_clients


async def get_unassigned_processes(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Obtém processos sem consultor/mediador atribuído.
    
    Args:
        limit: Número máximo de processos a retornar
        
    Returns:
        Lista de processos não atribuídos
    """
    # Processos que não têm consultor nem mediador atribuído
    unassigned_processes = await db.processes.find({
        "$and": [
            {"assigned_consultor_id": None},
            {"assigned_mediador_id": None}
        ]
    }).limit(limit).to_list(limit)
    
    logger.info(f"Encontrados {len(unassigned_processes)} processos não atribuídos")
    
    return unassigned_processes


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
            {"is_active": {"$exists": False}},  # Incluir se campo não existe
        ]
    }
    
    if role:
        # Se role for especificado, usar apenas esse
        query["role"] = role
    else:
        # Caso contrário, usar os roles prioritários (já são strings)
        query["role"] = {"$in": PRIORITY_ROLES}
    
    users = await db.users.find(query).to_list(50)
    
    # Contar clientes actuais de cada utilizador
    for user in users:
        count = await db.clients.count_documents({"assigned_to": user["id"]})
        user["current_client_count"] = count
        # user["role"] já é uma string, usar diretamente
        user["max_clients"] = MAX_CLIENTS_PER_USER.get(user["role"], 50)
        user["available_slots"] = user["max_clients"] - user["current_client_count"]
    
    # Ordenar por disponibilidade (mais slots disponíveis primeiro)
    users.sort(key=lambda u: u["available_slots"], reverse=True)
    
    logger.info(f"Encontrados {len(users)} utilizadores disponíveis")
    for user in users:
        logger.info(f"  - {user.get('name', user.get('email'))} ({user['role']}): "
                   f"{user['current_client_count']}/{user['max_clients']} clientes "
                   f"({user['available_slots']} slots disponíveis)")
    
    return users


async def assign_client_to_user(
    client_id: str,
    user_id: str,
    user_name: str,
    dry_run: bool = False
) -> bool:
    """
    Atribui um cliente a um utilizador.
    
    Args:
        client_id: ID do cliente
        user_id: ID do utilizador
        user_name: Nome do utilizador
        dry_run: Se True, não guarda na base de dados
        
    Returns:
        True se atribuído com sucesso
    """
    if dry_run:
        logger.info(f"[DRY-RUN] Atribuir cliente {client_id} a {user_name}")
        return True
    
    result = await db.clients.update_one(
        {"id": client_id},
        {"$set": {
            "assigned_to": user_id,
            "assigned_to_name": user_name,
            "assigned_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return result.modified_count > 0


async def create_process_for_client(
    client: Dict[str, Any],
    user_id: str,
    user_name: str,
    dry_run: bool = False
) -> Optional[str]:
    """
    Cria um processo para um cliente atribuído.
    
    Args:
        client: Dados do cliente
        user_id: ID do utilizador
        user_name: Nome do utilizador
        dry_run: Se True, não guarda na base de dados
        
    Returns:
        ID do processo criado ou None
    """
    import uuid
    
    client_id = client.get("id")
    client_name = client.get("name") or client.get("client_name", "Cliente")
    
    if dry_run:
        logger.info(f"[DRY-RUN] Criar processo para cliente {client_name}")
        return str(uuid.uuid4())
    
    # Verificar se já existe processo para este cliente
    existing = await db.processes.find_one({"client_id": client_id})
    if existing:
        logger.info(f"Cliente {client_name} já tem processo: {existing.get('id')}")
        return existing.get("id")
    
    # Criar processo
    process_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    process_doc = {
        "id": process_id,
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client.get("email") or client.get("client_email"),
        "client_phone": client.get("phone") or client.get("client_phone"),
        "status": "novo",
        "assigned_consultor_id": user_id,
        "assigned_consultor_name": user_name,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "source": "auto_assignment"
    }
    
    await db.processes.insert_one(process_doc)
    logger.info(f"Processo criado: {process_id} para cliente {client_name}")
    
    return process_id


async def run_auto_assignment(
    dry_run: bool = False,
    role_filter: Optional[str] = None,
    limit: int = 100,
    create_processes: bool = True,
    verbose: bool = False
) -> Dict[str, int]:
    """
    Executa a atribuição automática de clientes.
    
    Args:
        dry_run: Se True, não guarda alterações
        role_filter: Filtrar por role de utilizador
        limit: Limite de clientes a processar
        create_processes: Se True, cria processos para clientes atribuídos
        verbose: Mostrar mais detalhes
        
    Returns:
        Estatísticas da execução
    """
    logger.info("=" * 60)
    logger.info("INICIANDO ATRIBUIÇÃO AUTOMÁTICA DE CLIENTES")
    logger.info(f"Modo: {'SIMULAÇÃO (dry-run)' if dry_run else 'EXECUÇÃO REAL'}")
    logger.info("=" * 60)
    
    stats = {
        "clients_found": 0,
        "clients_assigned": 0,
        "processes_created": 0,
        "users_available": 0,
        "errors": 0
    }
    
    # 1. Obter clientes não atribuídos
    clients = await get_unassigned_clients(limit)
    stats["clients_found"] = len(clients)
    
    if not clients:
        logger.info("Nenhum cliente para atribuir.")
        return stats
    
    # 2. Obter utilizadores disponíveis
    users = await get_available_users(role_filter)
    stats["users_available"] = len(users)
    
    if not users:
        logger.warning("Nenhum utilizador disponível para atribuição!")
        return stats
    
    # 3. Distribuir clientes round-robin
    user_index = 0
    users_with_capacity = [u for u in users if u["available_slots"] > 0]
    
    if not users_with_capacity:
        logger.warning("Todos os utilizadores estão com capacidade máxima!")
        return stats
    
    for client in clients:
        # Encontrar próximo utilizador com capacidade
        assigned = False
        attempts = 0
        
        while attempts < len(users_with_capacity) and not assigned:
            user = users_with_capacity[user_index % len(users_with_capacity)]
            
            if user["available_slots"] <= 0:
                user_index += 1
                attempts += 1
                continue
            
            client_id = client.get("id")
            client_name = client.get("name") or client.get("client_name", "Cliente")
            user_id = user["id"]
            user_name = user.get("name", user.get("email", "Utilizador"))
            
            if verbose:
                logger.info(f"Atribuindo '{client_name}' a '{user_name}'...")
            
            # Atribuir cliente
            success = await assign_client_to_user(
                client_id, user_id, user_name, dry_run
            )
            
            if success:
                stats["clients_assigned"] += 1
                
                # Atualizar contagem local
                user["current_client_count"] += 1
                user["available_slots"] -= 1
                
                # Criar processo se solicitado
                if create_processes:
                    process_id = await create_process_for_client(
                        client, user_id, user_name, dry_run
                    )
                    if process_id:
                        stats["processes_created"] += 1
                
                assigned = True
            
            user_index += 1
            attempts += 1
        
        if not assigned:
            logger.warning(f"Não foi possível atribuir cliente {client.get('id')}")
            stats["errors"] += 1
    
    # 4. Resumo
    logger.info("=" * 60)
    logger.info("RESUMO DA EXECUÇÃO:")
    logger.info(f"  Clientes encontrados: {stats['clients_found']}")
    logger.info(f"  Clientes atribuídos: {stats['clients_assigned']}")
    logger.info(f"  Processos criados: {stats['processes_created']}")
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
    parser = argparse.ArgumentParser(
        description="Atribuição automática de clientes a utilizadores"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula as atribuições sem guardar na base de dados"
    )
    parser.add_argument(
        "--role",
        type=str,
        choices=["consultor", "mediador", "indexacao"],
        help="Filtrar por role de utilizador"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limite de clientes a processar (default: 100)"
    )
    parser.add_argument(
        "--no-processes",
        action="store_true",
        help="Não criar processos automaticamente"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar mais detalhes"
    )
    
    args = parser.parse_args()
    
    # Executar
    asyncio.run(run_auto_assignment(
        dry_run=args.dry_run,
        role_filter=args.role,
        limit=args.limit,
        create_processes=not args.no_processes,
        verbose=args.verbose
    ))


if __name__ == "__main__":
    main()
