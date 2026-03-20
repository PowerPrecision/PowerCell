#!/usr/bin/env python3
"""
Script de diagnóstico para verificar clientes e processos na base de dados.
"""

import asyncio
import sys
import os
from datetime import datetime

# Adicionar diretório pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db


async def diagnose():
    """Diagnóstico da base de dados."""
    print("=" * 60)
    print("DIAGNÓSTICO DA BASE DE DADOS")
    print("=" * 60)
    
    # 1. Contar total de clientes
    total_clients = await db.clients.count_documents({})
    print(f"\n📊 Total de clientes: {total_clients}")
    
    # 2. Contar clientes por campo de nome
    clientes_com_nome = await db.clients.count_documents({"nome": {"$exists": True, "$ne": None, "$ne": ""}})
    clientes_com_name = await db.clients.count_documents({"name": {"$exists": True, "$ne": None, "$ne": ""}})
    clientes_com_client_name = await db.clients.count_documents({"client_name": {"$exists": True, "$ne": None, "$ne": ""}})
    
    print(f"\n📋 Campos de nome:")
    print(f"  - Com campo 'nome': {clientes_com_nome}")
    print(f"  - Com campo 'name': {clientes_com_name}")
    print(f"  - Com campo 'client_name': {clientes_com_client_name}")
    
    # 3. Contar clientes com nome "Cliente"
    clientes_cliente = await db.clients.count_documents({
        "$or": [
            {"nome": "Cliente"},
            {"name": "Cliente"},
            {"client_name": "Cliente"}
        ]
    })
    print(f"\n⚠️  Clientes com nome 'Cliente': {clientes_cliente}")
    
    # 4. Contar processos
    total_processes = await db.processes.count_documents({})
    print(f"\n📊 Total de processos: {total_processes}")
    
    # 5. Contar processos com client_name "Cliente"
    processos_cliente = await db.processes.count_documents({"client_name": "Cliente"})
    print(f"⚠️  Processos com client_name 'Cliente': {processos_cliente}")
    
    # 6. Mostrar exemplos de clientes
    print("\n📝 Exemplos de clientes (primeiros 10):")
    print("-" * 60)
    
    cursor = db.clients.find({}).limit(10)
    async for c in cursor:
        nome = c.get("nome") or c.get("name") or c.get("client_name") or "SEM NOME"
        email = c.get("email") or c.get("contacto", {}).get("email") or "sem email"
        created = c.get("created_at", "N/A")
        print(f"  ID: {c.get('id')}")
        print(f"    Nome: {nome}")
        print(f"    Email: {email}")
        print(f"    Criado: {created}")
        print()
    
    # 7. Mostrar clientes com nome "Cliente"
    if clientes_cliente > 0:
        print("\n⚠️  Clientes com nome 'Cliente':")
        print("-" * 60)
        cursor = db.clients.find({
            "$or": [
                {"nome": "Cliente"},
                {"name": "Cliente"},
                {"client_name": "Cliente"}
            ]
        }).limit(20)
        async for c in cursor:
            print(f"  ID: {c.get('id')}")
            print(f"    Criado: {c.get('created_at', 'N/A')}")
            print(f"    Fonte: {c.get('fonte') or c.get('source', 'N/A')}")
            print()
    
    # 8. Mostrar processos com client_name "Cliente"
    if processos_cliente > 0:
        print("\n⚠️  Processos com client_name 'Cliente':")
        print("-" * 60)
        cursor = db.processes.find({"client_name": "Cliente"}).limit(20)
        async for p in cursor:
            print(f"  Processo #{p.get('process_number', 'N/A')} - ID: {p.get('id')}")
            print(f"    Status: {p.get('status', 'N/A')}")
            print(f"    Fonte: {p.get('source', 'N/A')}")
            print(f"    Criado: {p.get('created_at', 'N/A')}")
            print()
    
    print("=" * 60)
    print("FIM DO DIAGNÓSTICO")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(diagnose())
