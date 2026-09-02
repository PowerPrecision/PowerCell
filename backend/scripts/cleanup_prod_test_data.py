#!/usr/bin/env python3
"""
====================================================================
CLEANUP DE DADOS DE TESTE EM PRODUCAO
====================================================================

Procura e apaga em CASCATA TOTAL todos os registos cujo email, nome
de cliente OU nome/titulo de processo contenha "test" ou "teste"
(case-insensitive - "teste" ja e apanhado pela substring "test"),
nas seguintes coleccoes:

    Leads / Clientes  -> collection `clients`
                        ("Leads" e "Clientes" sao o MESMO documento
                        Mongo - um Lead e apenas um cliente ainda sem
                        processo criado, `lead_status` preenchido).
    Processos         -> collection `processes`
    Documentos        -> collection `documents`
    Tarefas           -> collection `tasks`
    Logs de Tarefas   -> collection `task_logs`
    Atividades        -> collection `activities`
    Historico         -> collection `history`

Cascata (ordem de eliminacao - filhos antes dos pais, para evitar
registos orfaos a meio da execucao caso o script seja interrompido):

    1. Logs de Tarefas (task_logs) ligados as tarefas/processos encontrados
    2. Tarefas (tasks) ligadas aos processos encontrados
    3. Atividades (activities) ligadas aos processos encontrados
    4. Historico (history) ligado aos processos encontrados
    5. Documentos ligados aos clientes/processos encontrados
    6. Processos ligados aos clientes encontrados (ou com
       `client_email`/`client_name` a corresponder directamente)
    7. Clientes/Leads cujo email ou nome corresponde ao filtro

Campos considerados (cobre variacoes legadas do schema):
    clients.contacto.email
    clients.email
    clients.nome
    processes.client_email
    processes.client_name

Utilizacao:
    cd backend && python -m scripts.cleanup_prod_test_data

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

# Substring "test" cobre tambem "teste" (pt-pt) - case-insensitive.
EMAIL_PATTERN = {"$regex": "test", "$options": "i"}

CLEANUP_SCRIPT_PASSWORD_DEFAULT = "POWERCELL_CLEANUP_2026"


def _confirm_password() -> bool:
    """Pede a password de seguranca no terminal (carateres ocultos)."""
    expected = os.environ.get("CLEANUP_SCRIPT_PASSWORD") or CLEANUP_SCRIPT_PASSWORD_DEFAULT
    entered = getpass.getpass("Password de seguranca para EXECUCAO REAL: ")
    return entered == expected


async def cleanup_prod_test_data(dry_run: bool = True):
    from database import db

    print("=" * 70)
    print("LIMPEZA DE DADOS DE TESTE (cascata total)")
    print("Filtro: email, nome de cliente ou nome de processo contem 'test'/'teste'")
    print(f"Modo: {'SIMULACAO (dry-run)' if dry_run else 'EXECUCAO REAL'}")
    print("=" * 70)

    empty_in = {"id_placeholder_never_matches": True}

    # -- 1) Identificar Leads/Clientes por email OU nome ------------------
    client_query = {
        "$or": [
            {"contacto.email": EMAIL_PATTERN},
            {"email": EMAIL_PATTERN},
            {"nome": EMAIL_PATTERN},
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

    # -- 2) Identificar Processos (por client_id OU client_email/client_name directo) --
    process_id_filter = {"client_id": {"$in": client_ids}} if client_ids else empty_in
    process_query = {
        "$or": [
            process_id_filter,
            {"client_email": EMAIL_PATTERN},
            {"client_name": EMAIL_PATTERN},
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

    process_id_in = {"process_id": {"$in": process_ids}} if process_ids else empty_in

    # -- 3) Identificar Documentos ligados aos clientes/processos acima --
    doc_client_filter = {"client_id": {"$in": client_ids}} if client_ids else empty_in
    document_query = {"$or": [doc_client_filter, process_id_in]}
    documents_count = await db.documents.count_documents(document_query)
    print(f"\nDocumentos encontrados: {documents_count}")

    # -- 4) Identificar Tarefas ligadas aos processos acima ---------------
    task_ids = [t["id"] for t in await db.tasks.find(process_id_in, {"_id": 0, "id": 1}).to_list(None)]
    tasks_count = len(task_ids)
    print(f"Tarefas encontradas: {tasks_count}")

    # -- 5) Identificar Logs de Tarefas (por process_id OU task_id) -------
    task_log_query = {
        "$or": [
            process_id_in,
            {"task_id": {"$in": task_ids}} if task_ids else empty_in,
        ]
    }
    task_logs_count = await db.task_logs.count_documents(task_log_query)
    print(f"Logs de tarefas encontrados: {task_logs_count}")

    # -- 6) Identificar Atividades ligadas aos processos acima ------------
    activities_count = await db.activities.count_documents(process_id_in)
    print(f"Atividades encontradas: {activities_count}")

    # -- 7) Identificar Historico ligado aos processos acima --------------
    history_count = await db.history.count_documents(process_id_in)
    print(f"Entradas de historico encontradas: {history_count}")

    total_records = (
        len(clients) + len(processes) + documents_count + tasks_count
        + task_logs_count + activities_count + history_count
    )
    if total_records == 0:
        print("\nNada para limpar - nao ha dados de teste correspondentes.")
        return

    if dry_run:
        print("\n" + "=" * 70)
        print(
            f"SIMULACAO - seriam eliminados: {task_logs_count} logs de tarefas, "
            f"{tasks_count} tarefas, {activities_count} atividades, "
            f"{history_count} entradas de historico, {documents_count} documentos, "
            f"{len(processes)} processos e {len(clients)} leads/clientes"
        )
        print("=" * 70)
        print("\nPara executar a limpeza real:")
        print("   python -m scripts.cleanup_prod_test_data --execute")
        return

    # -- Execucao real - cascata total: filhos antes dos pais ------------
    if not _confirm_password():
        print("\nERRO DE AUTENTICACAO: password incorreta. Nada foi eliminado.")
        sys.exit(1)
    print("Password validada.\n")

    print("A eliminar em cascata...")

    task_logs_result = await db.task_logs.delete_many(task_log_query)
    print(f"OK: {task_logs_result.deleted_count} logs de tarefas eliminados")

    tasks_result = await db.tasks.delete_many(process_id_in)
    print(f"OK: {tasks_result.deleted_count} tarefas eliminadas")

    activities_result = await db.activities.delete_many(process_id_in)
    print(f"OK: {activities_result.deleted_count} atividades eliminadas")

    history_result = await db.history.delete_many(process_id_in)
    print(f"OK: {history_result.deleted_count} entradas de historico eliminadas")

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
        description="Apaga em cascata total Leads/Clientes/Processos/Documentos/Tarefas/Logs/Atividades/Historico cujo email ou nome contenha 'test' ou 'teste'"
    )
    parser.add_argument("--execute", action="store_true", help="Executar a limpeza real (sem isto e simulacao)")
    args = parser.parse_args()

    asyncio.run(cleanup_prod_test_data(dry_run=not args.execute))
