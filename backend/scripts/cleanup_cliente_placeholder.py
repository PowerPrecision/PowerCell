#!/usr/bin/env python3
"""
====================================================================
SCRIPT PARA APAGAR CLIENTES COM NOME "Cliente" - POWERCELL
====================================================================
Este script remove clientes que têm o nome placeholder "Cliente".

Uso:
    python scripts/cleanup_cliente_placeholder.py [--dry-run]

Opções:
    --dry-run    Simula as eliminações sem executar
    --verbose    Mostrar mais detalhes
====================================================================
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime, timezone
from typing import List, Dict, Any

# Adicionar diretório pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db

# Logs
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def find_cliente_placeholder(dry_run: bool = True, verbose: bool = False) -> List[Dict[str, Any]]:
    """
    Encontra todos os clientes com nome "Cliente".
    
    Args:
        dry_run: Se True, apenas lista sem apagar
        verbose: Mostrar mais detalhes
        
    Returns:
        Lista de clientes encontrados
    """
    # Procurar clientes com nome exatamente "Cliente"
    # Suporta múltiplos campos: nome, name, client_name
    query = {
        "$or": [
            {"nome": "Cliente"},
            {"nome": {"$regex": "^Cliente$", "$options": "i"}},
            {"name": "Cliente"},
            {"name": {"$regex": "^Cliente$", "$options": "i"}},
            {"client_name": "Cliente"},
            {"client_name": {"$regex": "^Cliente$", "$options": "i"}},
        ]
    }
    
    clients = await db.clients.find(query).to_list(1000)
    
    logger.info(f"Encontrados {len(clients)} clientes com nome 'Cliente'")
    
    for client in clients:
        if verbose:
            logger.info(f"  - ID: {client.get('id')}")
            logger.info(f"    Nome: {client.get('nome') or client.get('name') or client.get('client_name')}")
            logger.info(f"    Email: {client.get('email') or client.get('contacto', {}).get('email') or client.get('client_email', 'N/A')}")
            logger.info(f"    Criado: {client.get('created_at', 'N/A')}")
        else:
            email = client.get('email') or client.get('contacto', {}).get('email') or client.get('client_email', 'sem email')
            logger.info(f"  - {client.get('id')}: {email}")
    
    return clients


async def find_processes_for_clients(client_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Encontra processos associados aos clientes.
    
    Args:
        client_ids: Lista de IDs de clientes
        
    Returns:
        Lista de processos encontrados
    """
    if not client_ids:
        return []
    
    processes = await db.processes.find({
        "client_id": {"$in": client_ids}
    }).to_list(1000)
    
    return processes


async def cleanup_cliente_placeholder(dry_run: bool = True, verbose: bool = False) -> Dict[str, int]:
    """
    Apaga clientes com nome "Cliente" e os respetivos processos.
    
    Args:
        dry_run: Se True, apenas simula
        verbose: Mostrar mais detalhes
        
    Returns:
        Estatísticas da limpeza
    """
    logger.info("=" * 60)
    logger.info("LIMPEZA DE CLIENTES PLACEHOLDER")
    logger.info(f"Modo: {'SIMULAÇÃO (dry-run)' if dry_run else 'EXECUÇÃO REAL'}")
    logger.info("=" * 60)
    
    stats = {
        "clients_found": 0,
        "clients_deleted": 0,
        "processes_found": 0,
        "processes_deleted": 0,
        "errors": 0
    }
    
    # 1. Encontrar clientes com nome "Cliente"
    clients = await find_cliente_placeholder(dry_run, verbose)
    stats["clients_found"] = len(clients)
    
    if not clients:
        logger.info("Nenhum cliente com nome 'Cliente' encontrado.")
        return stats
    
    client_ids = [c.get("id") for c in clients if c.get("id")]
    
    # 2. Encontrar processos associados
    processes = await find_processes_for_clients(client_ids)
    stats["processes_found"] = len(processes)
    
    if processes:
        logger.info(f"\nProcessos associados: {len(processes)}")
        for proc in processes:
            logger.info(f"  - Processo {proc.get('id')}: {proc.get('status', 'N/A')}")
    
    if dry_run:
        logger.info("\n" + "=" * 60)
        logger.info("SIMULAÇÃO - Seriam eliminados:")
        logger.info(f"  - {len(clients)} clientes")
        logger.info(f"  - {len(processes)} processos")
        logger.info("=" * 60)
        logger.info("⚠️  MODO SIMULAÇÃO - Nenhuma alteração foi feita!")
        logger.info("   Execute sem --dry-run para aplicar as alterações.")
        return stats
    
    # 3. Apagar processos
    if processes:
        process_ids = [p.get("id") for p in processes if p.get("id")]
        result = await db.processes.delete_many({"id": {"$in": process_ids}})
        stats["processes_deleted"] = result.deleted_count
        logger.info(f"\n✅ {result.deleted_count} processos eliminados")
    
    # 4. Apagar clientes
    if client_ids:
        result = await db.clients.delete_many({"id": {"$in": client_ids}})
        stats["clients_deleted"] = result.deleted_count
        logger.info(f"✅ {result.deleted_count} clientes eliminados")
    
    # 5. Resumo
    logger.info("\n" + "=" * 60)
    logger.info("RESUMO DA LIMPEZA:")
    logger.info(f"  Clientes encontrados: {stats['clients_found']}")
    logger.info(f"  Clientes eliminados: {stats['clients_deleted']}")
    logger.info(f"  Processos encontrados: {stats['processes_found']}")
    logger.info(f"  Processos eliminados: {stats['processes_deleted']}")
    logger.info("=" * 60)
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Apaga clientes com nome 'Cliente' (placeholder)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula as eliminações sem executar"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar mais detalhes"
    )
    
    args = parser.parse_args()
    
    asyncio.run(cleanup_cliente_placeholder(
        dry_run=args.dry_run,
        verbose=args.verbose
    ))


if __name__ == "__main__":
    main()
