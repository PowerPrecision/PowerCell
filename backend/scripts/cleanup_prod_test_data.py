#!/usr/bin/env python3
"""
====================================================================
CLEANUP DE DADOS DE TESTE EM PRODUCAO
====================================================================

Procura e apaga em CASCATA todos os registos cujo email contenha
"test" ou "teste" (case-insensitive - "teste" ja e apanhado pela
substring "test"), nas seguintes coleccoes:

    Leads / Clientes  -> collection `clients`
                        ("Leads" e "Clientes" sao o MESMO documento
                        Mongo - um Lead e apenas um cliente ainda sem
                        processo criado, `lead_status` preenchido).
    Processos         -> collection `processes`
    Documentos        -> collection `documents`

Cascata (ordem de eliminacao - filhos antes dos pais, para evitar
registos orfaos a meio da execucao caso o script seja interrompido):

    1. Documentos ligados aos clientes/processos encontrados
    2. Processos ligados aos clientes encontrados (ou com
       `client_email` a corresponder directamente)
    3. Clientes/Leads cujo email corresponde ao filtro

Campos de email considerados (cobre variacoes legadas do schema):
    clients.contacto.email
    clients.email
    processes.client_email

Utilizacao:
    cd backend && python -m scripts.cleanup_prod_test_data

Flags:
    --execute   Executa a eliminacao real. Sem esta flag, o script
                corre em modo SIMULACAO (dry-run) e so reporta o que
                seria apagado, sem tocar em nada.
====================================================================
"""

import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Substring "test" cobre tambem "teste" (pt-pt) - case-insensitive.
EMAIL_PATTERN = {"$regex": "test", "$options": "i"}


async def cleanup_prod_test_data(dry_run: bool = True):
    from database import db

    print("=" * 70)
    print("LIMPEZA DE DADOS DE TESTE (Leads, Clientes, Processos, Documentos)")
    print("Filtro: email contem 'test' ou 'teste' (case-insensitive)")
    print(f"Modo: {'SIMULACAO (dry-run)' if dry_run else 'EXECUCAO REAL'}")
    print("=" * 70)

    empty_in = {"id_placeholder_never_matches": True}

    # -- 1) Identificar Leads/Clientes por email --------------------------
    client_query = {
        "$or": [
            {"contacto.email": EMAIL_PATTERN},
            {"email": EMAIL_PATTERN},
        ]
    }
    clients = await db.clients.find(
        client_query, {"_id": 0, "id": 1, "nome": 1, "contacto": 1, "email": 1}
    ).to_list(None)
    client_ids = [c["id"] for c in clients if c.get("id")]

    print(f"\nLeads/Clientes encontrados: {len(clients)}")
    for c in clients[:10]:
        email = (c.get("contacto") or {}).get("email") or c.get("email") or "?"
        print(f"   - {c.get('nome', '?')} | {email} | id={c.get('id')}")
    if len(clients) > 10:
        print(f"   ... e mais {len(clients) - 10}")

    # -- 2) Identificar Processos (por client_id OU client_email directo) --
    process_id_filter = {"client_id": {"$in": client_ids}} if client_ids else empty_in
    process_query = {
        "$or": [
            process_id_filter,
            {"client_email": EMAIL_PATTERN},
        ]
    }
    processes = await db.processes.find(
        process_query, {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, "client_email": 1}
    ).to_list(None)
    process_ids = [p["id"] for p in processes if p.get("id")]

    print(f"\nProcessos encontrados: {len(processes)}")
    for p in processes[:10]:
        print(f"   - #{p.get('process_number', '?')} | {p.get('client_name', '?')} | {p.get('client_email', '?')} | id={p.get('id')}")
    if len(processes) > 10:
        print(f"   ... e mais {len(processes) - 10}")

    # -- 3) Identificar Documentos ligados aos clientes/processos acima --
    doc_client_filter = {"client_id": {"$in": client_ids}} if client_ids else empty_in
    doc_process_filter = {"process_id": {"$in": process_ids}} if process_ids else empty_in
    document_query = {"$or": [doc_client_filter, doc_process_filter]}
    documents_count = await db.documents.count_documents(document_query)
    print(f"\nDocumentos encontrados: {documents_count}")

    if not clients and not processes and documents_count == 0:
        print("\nNada para limpar - nao ha dados de teste correspondentes.")
        return

    if dry_run:
        print("\n" + "=" * 70)
        print(
            f"SIMULACAO - seriam eliminados {documents_count} documentos, "
            f"{len(processes)} processos e {len(clients)} leads/clientes"
        )
        print("=" * 70)
        print("\nPara executar a limpeza real:")
        print("   python -m scripts.cleanup_prod_test_data --execute")
        return

    # -- Execucao real - cascata: Documentos -> Processos -> Clientes ----
    print("\nA eliminar em cascata...")

    doc_result = await db.documents.delete_many(document_query)
    print(f"OK: {doc_result.deleted_count} documentos eliminados")

    process_result = await db.processes.delete_many(process_query)
    print(f"OK: {process_result.deleted_count} processos eliminados")

    client_result = await db.clients.delete_many(client_query)
    print(f"OK: {client_result.deleted_count} leads/clientes eliminados")

    print("\n" + "=" * 70)
    print("LIMPEZA CONCLUIDA")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apaga em cascata Leads/Clientes/Processos/Documentos cujo email contenha 'test' ou 'teste'"
    )
    parser.add_argument("--execute", action="store_true", help="Executar a limpeza real (sem isto e simulacao)")
    args = parser.parse_args()

    asyncio.run(cleanup_prod_test_data(dry_run=not args.execute))
