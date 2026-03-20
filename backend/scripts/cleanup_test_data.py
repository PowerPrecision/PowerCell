#!/usr/bin/env python3
"""
Script para apagar dados de teste da base de dados.
- Processos com client_name "Cliente"
- Processos/Clientes com _test_data: true
- Processos/Clientes com IDs contendo "test"
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def cleanup_test_data(dry_run: bool = True):
    """Remove dados de teste da base de dados."""
    
    print("=" * 60)
    print("LIMPEZA DE DADOS DE TESTE")
    print(f"Modo: {'SIMULAÇÃO (dry-run)' if dry_run else 'EXECUÇÃO REAL'}")
    print("=" * 60)
    
    # 1. Contar processos com client_name "Cliente"
    processos_cliente = await db.processes.count_documents({"client_name": "Cliente"})
    print(f"\n📊 Processos com client_name 'Cliente': {processos_cliente}")
    
    # 2. Contar processos com _test_data: true
    processos_test = await db.processes.count_documents({"_test_data": True})
    print(f"📊 Processos com _test_data: true: {processos_test}")
    
    # 3. Contar clientes com _test_data: true
    clientes_test = await db.clients.count_documents({"_test_data": True})
    print(f"📊 Clientes com _test_data: true: {clientes_test}")
    
    # 4. Contar clientes com nome "Cliente"
    clientes_cliente = await db.clients.count_documents({
        "$or": [
            {"nome": "Cliente"},
            {"name": "Cliente"},
            {"client_name": "Cliente"}
        ]
    })
    print(f"📊 Clientes com nome 'Cliente': {clientes_cliente}")
    
    if dry_run:
        print("\n" + "=" * 60)
        print("SIMULAÇÃO - Seriam eliminados:")
        print(f"  - {processos_cliente} processos com client_name 'Cliente'")
        print(f"  - {processos_test} processos com _test_data: true")
        print(f"  - {clientes_test} clientes com _test_data: true")
        print(f"  - {clientes_cliente} clientes com nome 'Cliente'")
        print("=" * 60)
        print("\n⚠️  Para executar a limpeza real, execute:")
        print("   python scripts/cleanup_test_data.py --execute")
        return
    
    # Executar limpeza
    print("\n🗑️  A eliminar dados de teste...")
    
    # Apagar processos com client_name "Cliente"
    if processos_cliente > 0:
        result = await db.processes.delete_many({"client_name": "Cliente"})
        print(f"✅ {result.deleted_count} processos com client_name 'Cliente' eliminados")
    
    # Apagar processos com _test_data: true
    if processos_test > 0:
        result = await db.processes.delete_many({"_test_data": True})
        print(f"✅ {result.deleted_count} processos com _test_data: true eliminados")
    
    # Apagar clientes com _test_data: true
    if clientes_test > 0:
        result = await db.clients.delete_many({"_test_data": True})
        print(f"✅ {result.deleted_count} clientes com _test_data: true eliminados")
    
    # Apagar clientes com nome "Cliente"
    if clientes_cliente > 0:
        result = await db.clients.delete_many({
            "$or": [
                {"nome": "Cliente"},
                {"name": "Cliente"},
                {"client_name": "Cliente"}
            ]
        })
        print(f"✅ {result.deleted_count} clientes com nome 'Cliente' eliminados")
    
    print("\n" + "=" * 60)
    print("✅ LIMPEZA CONCLUÍDA")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Limpar dados de teste")
    parser.add_argument("--execute", action="store_true", help="Executar a limpeza (sem isto é simulação)")
    args = parser.parse_args()
    
    asyncio.run(cleanup_test_data(dry_run=not args.execute))
