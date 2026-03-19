#!/usr/bin/env python3
"""
====================================================================
SCRIPT PARA ATRIBUIR CLIENTES ESPECÍFICOS - POWERCELL
====================================================================
Atribui clientes específicos a utilizadores específicos.

Uso:
    # Atribuir um cliente a um utilizador
    python scripts/assign_specific_clients.py --client CLIENT_ID --user USER_ID

    # Atribuir múltiplos clientes a um utilizador
    python scripts/assign_specific_clients.py --clients ID1,ID2,ID3 --user USER_ID

    # Listar utilizadores disponíveis
    python scripts/assign_specific_clients.py --list-users

    # Listar clientes não atribuídos
    python scripts/assign_specific_clients.py --list-unassigned
====================================================================
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from models.auth import UserRole

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def list_users():
    """Lista todos os utilizadores ativos."""
    users = await db.users.find({
        "is_active": True,
        "role": {"$in": ["admin", "ceo", "diretor", "consultor", "mediador", "indexacao"]}
    }).to_list(100)
    
    print("\n" + "=" * 80)
    print("UTILIZADORES DISPONÍVEIS")
    print("=" * 80)
    print(f"{'ID':<40} {'Nome':<30} {'Email':<35} {'Role':<15}")
    print("-" * 80)
    
    for user in users:
        print(f"{user['id']:<40} {user.get('name', 'N/A'):<30} {user.get('email', 'N/A'):<35} {user['role']:<15}")
    
    print("=" * 80 + "\n")


async def list_unassigned(limit: int = 50):
    """Lista clientes não atribuídos."""
    clients = await db.clients.find({
        "$or": [
            {"assigned_to": None},
            {"assigned_to": ""},
            {"assigned_to": {"$exists": False}}
        ]
    }).limit(limit).to_list(limit)
    
    print("\n" + "=" * 80)
    print(f"CLIENTES NÃO ATRIBUÍDOS (mostrando {len(clients)})")
    print("=" * 80)
    print(f"{'ID':<40} {'Nome':<30} {'Email':<35} {'Telefone':<15}")
    print("-" * 80)
    
    for client in clients:
        name = client.get("name") or client.get("client_name", "N/A")
        email = client.get("email") or client.get("client_email", "N/A")
        phone = client.get("phone") or client.get("client_phone", "N/A")
        print(f"{client['id']:<40} {name:<30} {email:<35} {phone:<15}")
    
    print("=" * 80 + "\n")


async def assign_client(client_id: str, user_id: str, create_process: bool = True):
    """Atribui um cliente a um utilizador."""
    import uuid
    
    # Verificar se cliente existe
    client = await db.clients.find_one({"id": client_id})
    if not client:
        logger.error(f"Cliente não encontrado: {client_id}")
        return False
    
    # Verificar se utilizador existe
    user = await db.users.find_one({"id": user_id})
    if not user:
        logger.error(f"Utilizador não encontrado: {user_id}")
        return False
    
    client_name = client.get("name") or client.get("client_name", "Cliente")
    user_name = user.get("name", user.get("email", "Utilizador"))
    
    # Atualizar cliente
    await db.clients.update_one(
        {"id": client_id},
        {"$set": {
            "assigned_to": user_id,
            "assigned_to_name": user_name,
            "assigned_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    logger.info(f"✅ Cliente '{client_name}' atribuído a '{user_name}'")
    
    # Criar processo se não existir
    if create_process:
        existing_process = await db.processes.find_one({"client_id": client_id})
        if not existing_process:
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
                "source": "manual_assignment"
            }
            
            await db.processes.insert_one(process_doc)
            logger.info(f"   📋 Processo criado: {process_id}")
        else:
            logger.info(f"   📋 Processo já existe: {existing_process.get('id')}")
    
    return True


async def assign_multiple_clients(client_ids: list, user_id: str, create_process: bool = True):
    """Atribui múltiplos clientes a um utilizador."""
    success_count = 0
    
    for client_id in client_ids:
        success = await assign_client(client_id.strip(), user_id, create_process)
        if success:
            success_count += 1
    
    logger.info(f"\nTotal: {success_count}/{len(client_ids)} clientes atribuídos com sucesso")


def main():
    parser = argparse.ArgumentParser(
        description="Atribuir clientes específicos a utilizadores"
    )
    
    parser.add_argument("--list-users", action="store_true", help="Listar utilizadores disponíveis")
    parser.add_argument("--list-unassigned", action="store_true", help="Listar clientes não atribuídos")
    parser.add_argument("--client", type=str, help="ID do cliente a atribuir")
    parser.add_argument("--clients", type=str, help="IDs de clientes separados por vírgula")
    parser.add_argument("--user", type=str, help="ID do utilizador para atribuição")
    parser.add_argument("--no-process", action="store_true", help="Não criar processo automaticamente")
    parser.add_argument("--limit", type=int, default=50, help="Limite para listagem")
    
    args = parser.parse_args()
    
    async def run():
        if args.list_users:
            await list_users()
        elif args.list_unassigned:
            await list_unassigned(args.limit)
        elif args.client and args.user:
            await assign_client(args.client, args.user, not args.no_process)
        elif args.clients and args.user:
            client_ids = args.clients.split(",")
            await assign_multiple_clients(client_ids, args.user, not args.no_process)
        else:
            parser.print_help()
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
