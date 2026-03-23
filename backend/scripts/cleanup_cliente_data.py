#!/usr/bin/env python3
"""
Script para apagar processos e clientes com nome "Cliente".
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


async def cleanup_cliente_data(dry_run: bool = True):
    """Remove dados com nome 'Cliente'."""
    
    print("=" * 60)
    print("LIMPEZA DE DADOS COM NOME 'Cliente'")
    print(f"Modo: {'SIMULAÇÃO (dry-run)' if dry_run else 'EXECUÇÃO REAL'}")
    print("=" * 60)
    
    # 1. Contar processos com client_name "Cliente"
    processos = await db.processes.count_documents({"client_name": "Cliente"})
    print(f"\n📊 Processos com client_name 'Cliente': {processos}")
    
    # 2. Mostrar alguns exemplos
    if processos > 0:
        print("\n📝 Exemplos:")
        cursor = db.processes.find({"client_name": "Cliente"}).limit(5)
        async for p in cursor:
            print(f"  - Processo #{p.get('process_number')} | ID: {p.get('id')} | Status: {p.get('status')}")
    
    if dry_run:
        print("\n" + "=" * 60)
        print(f"⚠️  SIMULAÇÃO - Seriam eliminados {processos} processos")
        print("=" * 60)
        print("\nPara executar a limpeza real:")
        print("   python scripts/cleanup_cliente_data.py --execute")
        return
    
    # Executar limpeza
    print("\n🗑️  A eliminar processos...")
    
    if processos > 0:
        result = await db.processes.delete_many({"client_name": "Cliente"})
        print(f"✅ {result.deleted_count} processos eliminados")
    
    print("\n" + "=" * 60)
    print("✅ LIMPEZA CONCLUÍDA")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Limpar dados com nome 'Cliente'")
    parser.add_argument("--execute", action="store_true", help="Executar a limpeza (sem isto é simulação)")
    args = parser.parse_args()
    
    asyncio.run(cleanup_cliente_data(dry_run=not args.execute))
