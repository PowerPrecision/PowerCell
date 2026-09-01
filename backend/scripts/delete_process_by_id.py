#!/usr/bin/env python3
"""
====================================================================
ELIMINAR PROCESSO POR ID (CASCATA)
====================================================================

Apaga em CASCATA um processo especifico (identificado pelo seu `id`)
e todos os documentos anexados a esse processo (collection `documents`,
campo `process_id`).

Cascata (ordem de eliminacao - filhos antes do pai):

    1. Documentos com `process_id` igual ao processo indicado
    2. O proprio processo (collection `processes`)

NOTA: Este script NAO apaga o Cliente associado ao processo - apenas
o processo e os documentos anexados a ele.

Utilizacao:
    cd backend && python -m scripts.delete_process_by_id <process_id>

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


async def delete_process_by_id(process_id: str, dry_run: bool = True):
    from database import db

    print("=" * 70)
    print("ELIMINAR PROCESSO POR ID (CASCATA)")
    print(f"Processo: {process_id}")
    print(f"Modo: {'SIMULACAO (dry-run)' if dry_run else 'EXECUCAO REAL'}")
    print("=" * 70)

    process = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, "client_email": 1}
    )
    if not process:
        print(f"\nNenhum processo encontrado com id={process_id}. Nada a fazer.")
        return

    print(
        f"\nProcesso encontrado: #{process.get('process_number', '?')} | "
        f"{process.get('client_name', '?')} | {process.get('client_email', '?')}"
    )

    documents_query = {"process_id": process_id}
    documents_count = await db.documents.count_documents(documents_query)
    print(f"Documentos anexados: {documents_count}")

    if dry_run:
        print("\n" + "=" * 70)
        print(f"SIMULACAO - seriam eliminados {documents_count} documentos e 1 processo")
        print("=" * 70)
        print("\nPara executar a eliminacao real:")
        print(f"   python -m scripts.delete_process_by_id {process_id} --execute")
        return

    print("\nA eliminar em cascata...")

    doc_result = await db.documents.delete_many(documents_query)
    print(f"OK: {doc_result.deleted_count} documentos eliminados")

    process_result = await db.processes.delete_one({"id": process_id})
    print(f"OK: {process_result.deleted_count} processo eliminado")

    print("\n" + "=" * 70)
    print("ELIMINACAO CONCLUIDA")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apaga em cascata um Processo (por id) e os Documentos anexados a ele"
    )
    parser.add_argument("process_id", help="ID do processo a eliminar")
    parser.add_argument("--execute", action="store_true", help="Executar a eliminacao real (sem isto e simulacao)")
    args = parser.parse_args()

    asyncio.run(delete_process_by_id(args.process_id, dry_run=not args.execute))
