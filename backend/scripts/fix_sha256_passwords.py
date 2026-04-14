"""
Script de Migração: Corrigir passwords SHA-256 → bcrypt
=========================================================
Se seed_database.py foi corrido contra uma BD, as passwords ficaram hasheadas
com SHA-256 (64 hex chars) em vez de bcrypt ($2b$12$...). O login-v2 usa
passlib bcrypt para verificar, pelo que passwords SHA-256 nunca passam.

Este script detecta passwords no formato SHA-256 e alerta o utilizador.
Como não é possível reverter SHA-256 para texto claro, o utilizador precisa
definir novas passwords via reset ou actualizar manualmente.

Uso:
    python -m scripts.fix_sha256_passwords

Ambiente:
    MONGO_URL e DB_NAME devem estar definidos como variáveis de ambiente,
    ou este script usa os valores hardcoded abaixo.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

# Adicionar o diretório backend ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuração — ajustar conforme necessário
MONGO_URL = os.environ.get(
    "MONGO_URL",
    "mongodb+srv://admin:y8aEj7BByvgeO2zO@cluster0.373e1eh.mongodb.net/?appName=Cluster0&retryWrites=true&w=majority"
)
DB_NAME = os.environ.get("DB_NAME", "powercell_dev")


def is_sha256_hash(value: str) -> bool:
    """Verifica se uma string é um hash SHA-256 (64 hex chars)."""
    if not value or len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def is_bcrypt_hash(value: str) -> bool:
    """Verifica se uma string é um hash bcrypt (começa com $2b$ ou $2a$)."""
    return bool(value and (value.startswith("$2b$") or value.startswith("$2a$")))


async def check_passwords(mongo_url: str, db_name: str, fix: bool = False):
    """Verifica e opcionalmente corrige passwords no formato errado."""

    print(f"🔌 A conectar ao MongoDB ({db_name})...")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    try:
        await client.admin.command("ping")
        print("✅ Conexão estabelecida!")

        # Buscar todos os utilizadores
        users = await db.users.find(
            {},
            {"id": 1, "email": 1, "name": 1, "role": 1, "password": 1, "hashed_password": 1}
        ).to_list(length=None)

        if not users:
            print("⚠️  Nenhum utilizador encontrado na colecção 'users'.")
            return

        print(f"\n📋 Total de utilizadores: {len(users)}\n")

        sha256_users = []
        bcrypt_users = []
        no_password_users = []

        for user in users:
            pw = user.get("password") or user.get("hashed_password", "")
            uid = user.get("id", "?")
            email = user.get("email", "?")
            name = user.get("name", "?")

            if not pw:
                no_password_users.append(user)
                print(f"  ❌ {email} ({name}) — SEM PASSWORD")
            elif is_sha256_hash(pw):
                sha256_users.append(user)
                print(f"  ⚠️  {email} ({name}) — SHA-256 detectado (login NÃO funciona)")
            elif is_bcrypt_hash(pw):
                bcrypt_users.append(user)
                print(f"  ✅ {email} ({name}) — bcrypt correcto")
            else:
                sha256_users.append(user)
                print(f"  ❓ {email} ({name}) — formato desconhecido: {pw[:20]}...")

        # Resumo
        print(f"\n{'='*60}")
        print(f"  ✅ bcrypt correcto:    {len(bcrypt_users)}")
        print(f"  ⚠️  SHA-256 (quebrado): {len(sha256_users)}")
        print(f"  ❌ Sem password:        {len(no_password_users)}")
        print(f"{'='*60}")

        if not sha256_users:
            print("\n🎉 Todas as passwords estão em formato bcrypt. Nada a corrigir.")
            return

        if not fix:
            print(f"\n⚠️  {len(sha256_users)} utilizador(es) com passwords SHA-256.")
            print("   O login-v2 usa bcrypt, pelo que estas contas NÃO conseguem fazer login.")
            print()
            print("   OPÇÕES:")
            print("   1. Correr com --fix para resetar as passwords para um valor default")
            print("   2. Usar o endpoint /auth/forgot-password para cada utilizador")
            print("   3. Actualizar manualmente no MongoDB Compass")
            print()
            print("   Para correr com --fix: python -m scripts.fix_sha256_passwords --fix")
            return

        # Modo fix: resetar passwords para default
        print(f"\n🔧 A corrigir {len(sha256_users)} passwords...")
        print("   As passwords serão resetadas para: PowerCell2025")
        print("   ⚠️  Os utilizadores devem alterar a password após o primeiro login.\n")

        default_password = "PowerCell2025"
        fixed = 0

        for user in sha256_users:
            email = user.get("email", "?")
            new_hash = pwd_context.hash(default_password)

            # Determinar o campo de password correcto
            field = "password" if user.get("password") else "hashed_password"

            result = await db.users.update_one(
                {"id": user.get("id")},
                {"$set": {field: new_hash, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )

            if result.modified_count > 0:
                fixed += 1
                print(f"  ✅ {email} — password actualizada para bcrypt")
            else:
                print(f"  ❌ {email} — FALHOU a actualizar")

        print(f"\n{'='*60}")
        print(f"  ✅ {fixed}/{len(sha256_users)} passwords corrigidas com sucesso!")
        print(f"  🔑 Password temporária: PowerCell2025")
        print(f"  ⚠️  Os utilizadores DEVEM alterar a password após login.")
        print(f"{'='*60}")

    except Exception as e:
        print(f"\n❌ Erro: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Corrigir passwords SHA-256 → bcrypt")
    parser.add_argument("--fix", action="store_true", help="Corrigir passwords (resetar para default)")
    parser.add_argument("--db", type=str, default=DB_NAME, help=f"Nome da BD (default: {DB_NAME})")
    args = parser.parse_args()

    asyncio.run(check_passwords(MONGO_URL, args.db, fix=args.fix))
