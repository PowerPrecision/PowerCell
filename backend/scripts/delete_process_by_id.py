#!/usr/bin/env python3
"""
====================================================================
ELIMINAR PROCESSO POR ID (CASCATA TOTAL)
====================================================================

Apaga em CASCATA TOTAL um processo especifico (identificado pelo seu
`id`) e tudo o que lhe esta associado:

    1. Logs de Tarefas (task_logs) ligados as tarefas/processo
    2. Tarefas (tasks) do processo
    3. Atividades (activities) do processo
    4. Historico (history) do processo
    5. Documentos (documents) anexados ao processo
    6. O proprio Processo (processes)

NOTA: Este script NAO apaga o Cliente associado ao processo - apenas
o processo e tudo o que lhe pertence directamente.

Utilizacao:
    cd backend && python -m scripts.delete_process_by_id <process_id>

Flags:
    --execute   Executa a eliminacao real. Sem esta flag, o script
                corre em modo SIMULACAO (dry-run) e so reporta o que
                seria apagado, sem tocar em nada. Ao usar --execute,
                e pedida uma password de seguranca no terminal
                (variavel de ambiente CLEANUP_SCRIPT_PASSWORD, com
                fallback para "POWERCELL_CLEANUP_2026" se nao estiver
                definida).

Nota de seguranca: este script NAO cria nenhum ficheiro de log nem
guarda rasto do que foi eliminado - toda a informacao e apenas
impressa na consola durante a execucao.
====================================================================
"""

import asyncio
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CLEANUP_SCRIPT_PASSWORD_DEFAULT = "POWERCELL_CLEANUP_2026"


def _confirm_password() -> bool:
    """Pede a password de seguranca no terminal (carateres ocultos)."""
    expected = os.environ.get("CLEANUP_SCRIPT_PASSWORD") or CLEANUP_SCRIPT_PASSWORD_DEFAULT
    entered = getpass.getpass("Password de seguranca para EXECUCAO REAL: ")
    return entered == expected


async def delete_process_by_id(process_id: str, dry_run: bool = True):
    from database import db

    print("=" * 70)
    print("ELIMINAR PROCESSO POR ID (CASCATA TOTAL)")
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

    process_id_filter = {"process_id": process_id}
    empty_in = {"id_placeholder_never_matches": True}

    documents_count = await db.documents.count_documents(process_id_filter)
    print(f"Documentos anexados: {documents_count}")

    task_ids = [t["id"] for t in await db.tasks.find(process_id_filter, {"_id": 0, "id": 1}).to_list(None)]
    tasks_count = len(task_ids)
    print(f"Tarefas: {tasks_count}")

    task_log_query = {"$or": [process_id_filter, {"task_id": {"$in": task_ids}} if task_ids else empty_in]}
    task_logs_count = await db.task_logs.count_documents(task_log_query)
    print(f"Logs de tarefas: {task_logs_count}")

    activities_count = await db.activities.count_documents(process_id_filter)
    print(f"Atividades: {activities_count}")

    history_count = await db.history.count_documents(process_id_filter)
    print(f"Entradas de historico: {history_count}")

    if dry_run:
        print("\n" + "=" * 70)
        print(
            f"SIMULACAO - seriam eliminados: {task_logs_count} logs de tarefas, "
            f"{tasks_count} tarefas, {activities_count} atividades, "
            f"{history_count} entradas de historico, {documents_count} documentos "
            f"e 1 processo"
        )
        print("=" * 70)
        print("\nPara executar a eliminacao real:")
        print(f"   python -m scripts.delete_process_by_id {process_id} --execute")
        return

    if not _confirm_password():
        print("\nERRO DE AUTENTICACAO: password incorreta. Nada foi eliminado.")
        sys.exit(1)
    print("Password validada.\n")

    print("A eliminar em cascata...")

    task_logs_result = await db.task_logs.delete_many(task_log_query)
    print(f"OK: {task_logs_result.deleted_count} logs de tarefas eliminados")

    tasks_result = await db.tasks.delete_many(process_id_filter)
    print(f"OK: {tasks_result.deleted_count} tarefas eliminadas")

    activities_result = await db.activities.delete_many(process_id_filter)
    print(f"OK: {activities_result.deleted_count} atividades eliminadas")

    history_result = await db.history.delete_many(process_id_filter)
    print(f"OK: {history_result.deleted_count} entradas de historico eliminadas")

    doc_result = await db.documents.delete_many(process_id_filter)
    print(f"OK: {doc_result.deleted_count} documentos eliminados")

    process_result = await db.processes.delete_one({"id": process_id})
    print(f"OK: {process_result.deleted_count} processo eliminado")

    print("\n" + "=" * 70)
    print("ELIMINACAO CONCLUIDA")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apaga em cascata total um Processo (por id) e tudo o que lhe esta associado (documentos, tarefas, logs, atividades, historico)"
    )
    parser.add_argument("process_id", help="ID do processo a eliminar")
    parser.add_argument("--execute", action="store_true", help="Executar a eliminacao real (sem isto e simulacao)")
    args = parser.parse_args()

    asyncio.run(delete_process_by_id(args.process_id, dry_run=not args.execute))
