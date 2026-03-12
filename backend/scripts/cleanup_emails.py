#!/usr/bin/env python3
"""
Script para limpar emails com formatação markdown na base de dados.
Executa uma única vez para corrigir dados existentes.

Uso:
    cd /app/backend
    python scripts/cleanup_emails.py
"""
import re
import asyncio
import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')


def sanitize_email(email: str) -> str:
    """
    Limpa emails com formatação markdown ou outros artefactos.
    """
    if not email:
        return ""
    
    original = email
    email = email.strip()
    
    # Padrão: [texto](mailto:email) ou [email](mailto:email)
    markdown_link = re.search(r'\[.*?\]\(mailto:([^)]+)\)', email)
    if markdown_link:
        email = markdown_link.group(1)
    
    # Padrão: mailto:email
    if email.startswith('mailto:'):
        email = email.replace('mailto:', '')
    
    # Padrão: <email>
    angle_brackets = re.search(r'<([^>]+@[^>]+)>', email)
    if angle_brackets:
        email = angle_brackets.group(1)
    
    # Remover quaisquer caracteres markdown restantes
    email = re.sub(r'[\[\]\(\)]', '', email)
    
    email = email.strip().lower()
    
    if original != email:
        print(f"  Corrigido: '{original}' -> '{email}'")
    
    return email


async def cleanup_emails():
    """Limpa emails formatados incorrectamente na base de dados."""
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print("=" * 60)
    print("Limpeza de Emails - PowerCell")
    print("=" * 60)
    print(f"Database: {db_name}")
    print()
    
    # Encontrar processos com emails que parecem ter markdown
    patterns = [
        {"client_email": {"$regex": r"\[.*\]\(mailto:"}},  # Markdown link
        {"client_email": {"$regex": r"^mailto:"}},         # mailto: prefix
        {"client_email": {"$regex": r"<.*@.*>"}},          # <email>
    ]
    
    total_cleaned = 0
    
    for pattern in patterns:
        cursor = db.processes.find(pattern, {"id": 1, "client_email": 1, "client_name": 1})
        processes = await cursor.to_list(None)
        
        if processes:
            print(f"Encontrados {len(processes)} processos com padrão problemático")
            
            for process in processes:
                old_email = process.get("client_email", "")
                new_email = sanitize_email(old_email)
                
                if old_email != new_email:
                    await db.processes.update_one(
                        {"id": process["id"]},
                        {"$set": {"client_email": new_email}}
                    )
                    print(f"  Processo {process.get('client_name', 'N/A')}: '{old_email}' -> '{new_email}'")
                    total_cleaned += 1
    
    # Verificar também na personal_data
    print("\nVerificando personal_data.email...")
    cursor = db.processes.find(
        {"personal_data.email": {"$regex": r"(\[|\]|\(mailto:)"}},
        {"id": 1, "personal_data.email": 1, "client_name": 1}
    )
    processes = await cursor.to_list(None)
    
    for process in processes:
        personal_data = process.get("personal_data", {})
        old_email = personal_data.get("email", "")
        new_email = sanitize_email(old_email)
        
        if old_email != new_email:
            await db.processes.update_one(
                {"id": process["id"]},
                {"$set": {"personal_data.email": new_email}}
            )
            print(f"  Processo {process.get('client_name', 'N/A')}: personal_data.email corrigido")
            total_cleaned += 1
    
    print()
    print("=" * 60)
    print(f"Total de emails corrigidos: {total_cleaned}")
    print("=" * 60)
    
    client.close()


if __name__ == "__main__":
    asyncio.run(cleanup_emails())
