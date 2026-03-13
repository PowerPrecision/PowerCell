#!/usr/bin/env python3
"""
Script para remover processos duplicados causados por merge.
Executa a mesma lógica do endpoint /api/admin/processes/fix-duplicates

Uso:
    cd backend
    export MONGO_URL="mongodb+srv://user:pass@cluster.mongodb.net"
    export DB_NAME="powercell"
    
    # Ver duplicados sem remover
    python fix_process_duplicates.py --dry-run
    
    # Remover duplicados
    python fix_process_duplicates.py
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    print("ERRO: motor não está instalado.")
    print("Instale com: pip install motor")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass


async def find_and_fix_duplicates(dry_run: bool = False):
    """Encontrar e remover processos duplicados."""
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'powercell_dev')
    
    print("=" * 70)
    print("PowerCell - Correção de Processos Duplicados")
    print("=" * 70)
    print(f"MongoDB: {mongo_url[:40]}..." if len(mongo_url) > 40 else f"MongoDB: {mongo_url}")
    print(f"Database: {db_name}")
    print(f"Modo: {'DRY-RUN (sem alterações)' if dry_run else 'EXECUÇÃO (remover duplicados)'}")
    print()
    
    try:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=10000)
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
    
    # Buscar todos os processos
    print("A carregar processos...")
    all_processes = await db.processes.find({}).to_list(length=None)
    print(f"Total de processos: {len(all_processes)}")
    print()
    
    # Agrupar por email
    by_email = defaultdict(list)
    # Agrupar por NIF
    by_nif = defaultdict(list)
    
    for proc in all_processes:
        email = proc.get("client_email", "").lower().strip() if proc.get("client_email") else None
        personal_data = proc.get("personal_data") or {}
        nif = personal_data.get("nif") if isinstance(personal_data, dict) else None
        
        if email:
            by_email[email].append(proc)
        if nif:
            by_nif[nif].append(proc)
    
    # Identificar duplicados
    ids_to_remove = set()
    report = {
        "analyzed": len(all_processes),
        "duplicates_by_email": [],
        "duplicates_by_nif": [],
        "removed": 0
    }
    
    print("A analisar duplicados por EMAIL...")
    print("-" * 70)
    
    # Processar duplicados por email
    for email, procs in sorted(by_email.items()):
        if len(procs) > 1:
            # Ordenar por created_at descendente (mais recente primeiro)
            procs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            print(f"\n🔴 DUPLICADO POR EMAIL: '{email}' ({len(procs)} processos)")
            
            duplicate_info = {
                "key": email,
                "count": len(procs),
                "keeping": procs[0].get("id"),
                "keeping_name": procs[0].get("client_name"),
                "removing": []
            }
            
            # Manter o mais recente
            for i, proc in enumerate(procs):
                proc_id = proc.get("id")
                name = proc.get("client_name", "N/A")
                created = proc.get("created_at", "N/A")
                status = proc.get("status", "N/A")
                
                if i == 0:
                    print(f"   ✅ MANTER: {name} | Status: {status} | Criado: {created}")
                else:
                    print(f"   ❌ REMOVER: {name} | Status: {status} | Criado: {created}")
                    if proc_id not in ids_to_remove:
                        ids_to_remove.add(proc_id)
                        duplicate_info["removing"].append({
                            "id": proc_id,
                            "name": name,
                            "created_at": created
                        })
            
            report["duplicates_by_email"].append(duplicate_info)
    
    print()
    print("A analisar duplicados por NIF...")
    print("-" * 70)
    
    # Processar duplicados por NIF
    for nif, procs in sorted(by_nif.items()):
        if len(procs) > 1:
            # Ordenar por created_at descendente
            procs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            print(f"\n🔴 DUPLICADO POR NIF: '{nif}' ({len(procs)} processos)")
            
            duplicate_info = {
                "key": nif,
                "count": len(procs),
                "keeping": procs[0].get("id"),
                "keeping_name": procs[0].get("client_name"),
                "removing": []
            }
            
            # Manter o mais recente
            for i, proc in enumerate(procs):
                proc_id = proc.get("id")
                name = proc.get("client_name", "N/A")
                created = proc.get("created_at", "N/A")
                status = proc.get("status", "N/A")
                
                if i == 0:
                    print(f"   ✅ MANTER: {name} | Status: {status} | Criado: {created}")
                else:
                    print(f"   ❌ REMOVER: {name} | Status: {status} | Criado: {created}")
                    if proc_id not in ids_to_remove:
                        ids_to_remove.add(proc_id)
                        duplicate_info["removing"].append({
                            "id": proc_id,
                            "name": name,
                            "created_at": created
                        })
            
            report["duplicates_by_nif"].append(duplicate_info)
    
    print()
    print("=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"Processos analisados: {report['analyzed']}")
    print(f"Duplicados por email: {len(report['duplicates_by_email'])} grupos")
    print(f"Duplicados por NIF: {len(report['duplicates_by_nif'])} grupos")
    print(f"Total a remover: {len(ids_to_remove)}")
    
    if len(ids_to_remove) == 0:
        print()
        print("✅ Não foram encontrados processos duplicados!")
        client.close()
        return
    
    if dry_run:
        print()
        print("🔍 MODO DRY-RUN - Nenhuma alteração foi feita.")
        print("   Execute sem --dry-run para remover os duplicados.")
    else:
        print()
        print("A REMOVER DUPLICADOS...")
        print("-" * 70)
        
        # Remover duplicados
        for proc_id in ids_to_remove:
            # Contar documentos associados
            docs = await db.documents.count_documents({"process_id": proc_id})
            tasks = await db.tasks.count_documents({"process_id": proc_id})
            history = await db.history.count_documents({"process_id": proc_id})
            
            # Remover
            await db.documents.delete_many({"process_id": proc_id})
            await db.tasks.delete_many({"process_id": proc_id})
            await db.history.delete_many({"process_id": proc_id})
            await db.processes.delete_one({"id": proc_id})
            
            report["removed"] += 1
            print(f"   ❌ Removido processo {proc_id[:20]}... (+ {docs} docs, {tasks} tarefas, {history} histórico)")
        
        # Registrar no histórico
        await db.history.insert_one({
            "id": str(os.urandom(16).hex()),
            "process_id": None,
            "user_id": "system",
            "user_name": "Script de Correção",
            "action": f"Correção automática de processos duplicados - {report['removed']} processos removidos",
            "field": "process_duplicates_fixed",
            "old_value": None,
            "new_value": str(report["removed"]),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        print()
        print("-" * 70)
        
        # Verificar resultado final
        remaining = await db.processes.count_documents({})
        print(f"Processos restantes: {remaining}")
        print()
        print(f"✅ REMOVIDOS {report['removed']} processos duplicados!")
    
    client.close()
    print()
    print("=" * 70)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    
    asyncio.run(find_and_fix_duplicates(dry_run))
