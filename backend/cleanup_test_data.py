#!/usr/bin/env python3
"""
==============================================
CLEANUP TEST DATA - PowerCell
==============================================
Script para eliminar dados de teste da base de dados.

CUIDADO: Este script elimina dados permanentemente!

Uso:
    cd /app/backend
    python cleanup_test_data.py

O script irá:
1. Identificar utilizadores de teste (email @test.com ou criados pelo seed)
2. Eliminar processos criados por esses utilizadores
3. Eliminar os próprios utilizadores de teste
4. Eliminar clientes de teste
5. Eliminar leads de teste
6. Eliminar propriedades de teste
==============================================
"""

import asyncio
import os
from pathlib import Path
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


# Padrões para identificar dados de teste
TEST_EMAIL_PATTERNS = [
    "@test.com",
    "@teste.com",
    "@example.com",
    "test@",
    "teste@",
]

TEST_NAME_PATTERNS = [
    "test",
    "teste",
    "sample",
    "demo",
    "dummy",
    "fake",
]

# Emails específicos que são SEMPRE de teste
KNOWN_TEST_EMAILS = [
    "admin@test.com",
    "consultor@test.com",
    "mediador@test.com",
    "test@test.com",
    "user@test.com",
]


def is_test_email(email: str) -> bool:
    """Verifica se um email é de teste."""
    if not email:
        return False
    email_lower = email.lower()
    
    # Verificar emails conhecidos
    if email_lower in KNOWN_TEST_EMAILS:
        return True
    
    # Verificar padrões
    for pattern in TEST_EMAIL_PATTERNS:
        if pattern in email_lower:
            return True
    
    return False


def is_test_name(name: str) -> bool:
    """Verifica se um nome parece ser de teste."""
    if not name:
        return False
    name_lower = name.lower()
    
    for pattern in TEST_NAME_PATTERNS:
        if pattern in name_lower:
            return True
    
    return False


async def cleanup_test_data(dry_run: bool = True):
    """
    Elimina dados de teste da base de dados.
    
    Args:
        dry_run: Se True, apenas mostra o que seria eliminado sem apagar
    """
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    
    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]
    
    print("=" * 60)
    print("CLEANUP DE DADOS DE TESTE - PowerCell")
    print("=" * 60)
    print(f"MongoDB: {mongo_url[:50]}...")
    print(f"Database: {db_name}")
    print(f"Modo: {'DRY RUN (simulação)' if dry_run else 'EXECUÇÃO REAL'}")
    print()
    
    # Estatísticas
    stats = {
        "users_found": 0,
        "users_deleted": 0,
        "processes_found": 0,
        "processes_deleted": 0,
        "clients_found": 0,
        "clients_deleted": 0,
        "leads_found": 0,
        "leads_deleted": 0,
        "properties_found": 0,
        "properties_deleted": 0,
    }
    
    # ============================================================
    # 1. ENCONTRAR UTILIZADORES DE TESTE
    # ============================================================
    print("-" * 60)
    print("1. UTILIZADORES DE TESTE")
    print("-" * 60)
    
    test_user_ids = []
    test_user_emails = []
    
    async for user in db.users.find({}):
        email = user.get("email", "")
        name = user.get("name", "")
        
        if is_test_email(email) or is_test_name(name):
            test_user_ids.append(user.get("id"))
            test_user_emails.append(email)
            stats["users_found"] += 1
            print(f"  [TESTE] {name} <{email}> (role: {user.get('role', 'N/A')})")
    
    if not test_user_ids:
        print("  Nenhum utilizador de teste encontrado.")
    else:
        print(f"\n  Total: {stats['users_found']} utilizadores de teste")
    
    # ============================================================
    # 2. ENCONTRAR PROCESSOS CRIADOS POR UTILIZADORES DE TESTE
    # ============================================================
    print()
    print("-" * 60)
    print("2. PROCESSOS DE TESTE")
    print("-" * 60)
    
    # Processos criados por utilizadores de teste
    if test_user_ids:
        query = {"$or": [
            {"created_by": {"$in": test_user_ids}},
            {"assigned_consultor_id": {"$in": test_user_ids}},
        ]}
        async for process in db.processes.find(query):
            stats["processes_found"] += 1
            print(f"  [TESTE] #{process.get('process_number', '?')} - {process.get('client_name', 'N/A')}")
    
    # Processos com nomes de cliente de teste
    async for process in db.processes.find({}):
        client_name = process.get("client_name", "")
        client_email = process.get("client_email", "")
        
        if is_test_name(client_name) or is_test_email(client_email):
            # Evitar contar duas vezes
            if process.get("created_by") not in test_user_ids:
                stats["processes_found"] += 1
                print(f"  [TESTE] #{process.get('process_number', '?')} - {client_name} <{client_email}>")
    
    if stats["processes_found"] == 0:
        print("  Nenhum processo de teste encontrado.")
    else:
        print(f"\n  Total: {stats['processes_found']} processos de teste")
    
    # ============================================================
    # 3. ENCONTRAR CLIENTES DE TESTE
    # ============================================================
    print()
    print("-" * 60)
    print("3. CLIENTES DE TESTE")
    print("-" * 60)
    
    async for client in db.clients.find({}):
        name = client.get("name", "")
        email = client.get("email", "")
        
        if is_test_name(name) or is_test_email(email):
            stats["clients_found"] += 1
            print(f"  [TESTE] {name} <{email}>")
    
    if stats["clients_found"] == 0:
        print("  Nenhum cliente de teste encontrado.")
    else:
        print(f"\n  Total: {stats['clients_found']} clientes de teste")
    
    # ============================================================
    # 4. ENCONTRAR LEADS DE TESTE
    # ============================================================
    print()
    print("-" * 60)
    print("4. LEADS DE TESTE")
    print("-" * 60)
    
    async for lead in db.leads.find({}):
        title = lead.get("titulo", lead.get("title", ""))
        
        if is_test_name(title):
            stats["leads_found"] += 1
            print(f"  [TESTE] {title}")
    
    if stats["leads_found"] == 0:
        print("  Nenhum lead de teste encontrado.")
    else:
        print(f"\n  Total: {stats['leads_found']} leads de teste")
    
    # ============================================================
    # 5. ENCONTRAR PROPRIEDADES DE TESTE
    # ============================================================
    print()
    print("-" * 60)
    print("5. PROPRIEDADES DE TESTE")
    print("-" * 60)
    
    async for prop in db.properties.find({}):
        title = prop.get("titulo", prop.get("title", ""))
        owner = prop.get("proprietario_nome", prop.get("owner_name", ""))
        
        if is_test_name(title) or is_test_name(owner):
            stats["properties_found"] += 1
            print(f"  [TESTE] {title} (owner: {owner})")
    
    if stats["properties_found"] == 0:
        print("  Nenhuma propriedade de teste encontrada.")
    else:
        print(f"\n  Total: {stats['properties_found']} propriedades de teste")
    
    # ============================================================
    # RESUMO E ELIMINAÇÃO
    # ============================================================
    print()
    print("=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"  Utilizadores de teste: {stats['users_found']}")
    print(f"  Processos de teste: {stats['processes_found']}")
    print(f"  Clientes de teste: {stats['clients_found']}")
    print(f"  Leads de teste: {stats['leads_found']}")
    print(f"  Propriedades de teste: {stats['properties_found']}")
    
    total = sum([
        stats["users_found"],
        stats["processes_found"],
        stats["clients_found"],
        stats["leads_found"],
        stats["properties_found"]
    ])
    
    print(f"\n  TOTAL DE REGISTOS A ELIMINAR: {total}")
    
    if total == 0:
        print("\n  Nada a eliminar. Base de dados limpa!")
        client.close()
        return stats
    
    if dry_run:
        print("\n" + "=" * 60)
        print("MODO DRY RUN - Nenhum dado foi eliminado.")
        print("Para eliminar, execute: python cleanup_test_data.py --execute")
        print("=" * 60)
        client.close()
        return stats
    else:
        print("\n" + "=" * 60)
        print("A ELIMINAR DADOS...")
        print("=" * 60)
        
        # Eliminar processos
        if test_user_ids:
            result = await db.processes.delete_many({"$or": [
                {"created_by": {"$in": test_user_ids}},
                {"assigned_consultor_id": {"$in": test_user_ids}},
            ]})
            stats["processes_deleted"] += result.deleted_count
        
        # Eliminar processos por nome de cliente de teste
        for pattern in TEST_NAME_PATTERNS:
            result = await db.processes.delete_many({
                "client_name": {"$regex": pattern, "$options": "i"}
            })
            stats["processes_deleted"] += result.deleted_count
        
        for pattern in TEST_EMAIL_PATTERNS:
            result = await db.processes.delete_many({
                "client_email": {"$regex": pattern, "$options": "i"}
            })
            stats["processes_deleted"] += result.deleted_count
        
        print(f"  Processos eliminados: {stats['processes_deleted']}")
        
        # Eliminar clientes de teste
        for pattern in TEST_NAME_PATTERNS:
            result = await db.clients.delete_many({
                "name": {"$regex": pattern, "$options": "i"}
            })
            stats["clients_deleted"] += result.deleted_count
        
        for pattern in TEST_EMAIL_PATTERNS:
            result = await db.clients.delete_many({
                "email": {"$regex": pattern, "$options": "i"}
            })
            stats["clients_deleted"] += result.deleted_count
        
        print(f"  Clientes eliminados: {stats['clients_deleted']}")
        
        # Eliminar leads de teste
        for pattern in TEST_NAME_PATTERNS:
            result = await db.leads.delete_many({
                "$or": [
                    {"titulo": {"$regex": pattern, "$options": "i"}},
                    {"title": {"$regex": pattern, "$options": "i"}}
                ]
            })
            stats["leads_deleted"] += result.deleted_count
        
        print(f"  Leads eliminados: {stats['leads_deleted']}")
        
        # Eliminar propriedades de teste
        for pattern in TEST_NAME_PATTERNS:
            result = await db.properties.delete_many({
                "$or": [
                    {"titulo": {"$regex": pattern, "$options": "i"}},
                    {"title": {"$regex": pattern, "$options": "i"}},
                    {"proprietario_nome": {"$regex": pattern, "$options": "i"}}
                ]
            })
            stats["properties_deleted"] += result.deleted_count
        
        print(f"  Propriedades eliminadas: {stats['properties_deleted']}")
        
        # Eliminar utilizadores de teste (por último)
        if test_user_emails:
            result = await db.users.delete_many({
                "email": {"$in": test_user_emails}
            })
            stats["users_deleted"] = result.deleted_count
        
        print(f"  Utilizadores eliminados: {stats['users_deleted']}")
        
        print()
        print("=" * 60)
        print("LIMPEZA CONCLUÍDA!")
        print("=" * 60)
    
    mongo_client.close()
    return stats


async def main():
    """Função principal."""
    import sys
    
    # Verificar argumento --execute
    execute = "--execute" in sys.argv or "-e" in sys.argv
    
    if not execute:
        print("\n" + "!" * 60)
        print("AVISO: Isto é uma SIMULAÇÃO (dry run).")
        print("Para eliminar dados, use: python cleanup_test_data.py --execute")
        print("!" * 60 + "\n")
    
    await cleanup_test_data(dry_run=not execute)


if __name__ == "__main__":
    asyncio.run(main())
