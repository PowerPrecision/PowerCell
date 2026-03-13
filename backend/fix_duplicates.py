#!/usr/bin/env python3
"""
Script para identificar e remover fases duplicadas do workflow.
O merge do código causou duplicação dos estados do workflow.

Uso:
    cd backend
    
    # Definir a conexão MongoDB (produção)
    export MONGO_URL="mongodb+srv://user:pass@cluster.mongodb.net"
    export DB_NAME="powercell"
    
    # Ver duplicados sem remover
    python fix_duplicates.py --dry-run
    
    # Remover duplicados
    python fix_duplicates.py
"""

import asyncio
import os
import sys
from pathlib import Path
from collections import defaultdict

# Tentar importar motor
try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    print("ERRO: motor não está instalado.")
    print("Instale com: pip install motor")
    sys.exit(1)

# Tentar importar dotenv
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass  # dotenv é opcional


async def find_and_fix_duplicates(dry_run: bool = False):
    """Encontrar e remover duplicados da coleção workflow_statuses."""
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'powercell_dev')
    
    print("=" * 60)
    print("PowerCell - Correção de Fases Duplicadas")
    print("=" * 60)
    print(f"MongoDB: {mongo_url[:30]}..." if len(mongo_url) > 30 else f"MongoDB: {mongo_url}")
    print(f"Database: {db_name}")
    print()
    
    try:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        
        # Testar conexão
        await db.list_collection_names()
    except Exception as e:
        print(f"ERRO: Não foi possível conectar à base de dados.")
        print(f"Detalhes: {e}")
        print()
        print("Certifique-se de definir as variáveis de ambiente:")
        print("  export MONGO_URL='mongodb+srv://user:pass@cluster.mongodb.net'")
        print("  export DB_NAME='powercell'")
        return
    
    # Buscar todos os workflow_statuses
    all_statuses = await db.workflow_statuses.find({}).to_list(length=None)
    
    print(f"Total de documentos em workflow_statuses: {len(all_statuses)}")
    print()
    
    if not all_statuses:
        print("Nenhum documento encontrado.")
        client.close()
        return
    
    # Agrupar por nome (name é o identificador único)
    by_name = defaultdict(list)
    for status in all_statuses:
        by_name[status.get('name')].append(status)
    
    # Identificar duplicados
    duplicates_found = False
    ids_to_remove = []
    
    print("Análise de duplicados:")
    print("-" * 60)
    
    for name, statuses in sorted(by_name.items(), key=lambda x: x[1][0].get('order', 0)):
        if len(statuses) > 1:
            duplicates_found = True
            print(f"\n🔴 DUPLICADO: '{name}' ({len(statuses)} ocorrências)")
            
            # Ordenar por order para manter o mais relevante
            statuses.sort(key=lambda x: x.get('order', 999))
            
            # Vamos manter o primeiro e remover os restantes
            for i, status in enumerate(statuses):
                status_id = status.get('id') or str(status.get('_id'))
                label = status.get('label', 'N/A')
                order = status.get('order', 'N/A')
                color = status.get('color', 'N/A')
                
                marker = "✅ MANTER" if i == 0 else "❌ REMOVER"
                print(f"   {marker} - ID: {status_id[:20]}..., Label: '{label}', Order: {order}")
                
                if i > 0:
                    ids_to_remove.append(status.get('id'))
        else:
            status = statuses[0]
            label = status.get('label', 'N/A')
            order = status.get('order', 'N/A')
            print(f"✅ '{name}' - '{label}' (Order: {order})")
    
    print()
    print("-" * 60)
    
    if not duplicates_found:
        print("✅ Não foram encontrados duplicados!")
        client.close()
        return
    
    print(f"Total de documentos a remover: {len(ids_to_remove)}")
    
    if dry_run:
        print("\n🔍 MODO DRY-RUN - Nenhuma alteração foi feita.")
        print("   Execute sem --dry-run para remover os duplicados.")
    else:
        print("\nA remover duplicados...")
        
        # Remover duplicados
        for status_id in ids_to_remove:
            result = await db.workflow_statuses.delete_one({"id": status_id})
            if result.deleted_count > 0:
                print(f"   ❌ Removido: {status_id[:30]}...")
        
        print()
        
        # Verificar resultado
        remaining = await db.workflow_statuses.count_documents({})
        print(f"Documentos restantes: {remaining}")
        
        # Mostrar lista final
        print("\nLista final de fases:")
        final_statuses = await db.workflow_statuses.find({}).sort("order", 1).to_list(length=None)
        for status in final_statuses:
            print(f"   {status.get('order'):2d}. {status.get('name')} - '{status.get('label')}'")
    
    client.close()
    print()
    print("=" * 60)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    
    asyncio.run(find_and_fix_duplicates(dry_run))
