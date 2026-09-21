#!/usr/bin/env python3
"""
====================================================================
LIMPEZA DE DADOS DE TESTE — POWERCELL CRM (PACOTE 11 — actualização)
====================================================================

Procura, TRANSVERSALMENTE, a string "test"/"teste" (case-insensitive)
em todas as colecções principais do CRM e apaga os registos com
cascata (soft-delete ou hard-delete seguro), com log descritivo no
terminal.

COLECÇÕES E CAMPOS PESQUISADOS (match próprio, não só cascata):

    Clientes (leads incluídos) -> `clients`
        contacto.email, email, nome, notas
    Processos                  -> `processes`
        client_email, client_name, process_type, notes, observations
    Leads (imóveis)            -> `property_leads`
        title, notes, client_name, url
    Empresas                   -> `companies`
        name, email, smtp_email, imap_email
    Atividades                 -> `activities`
        comment
    Tarefas                    -> `tasks`
        title, description
    + cascata pelos filhos: documents, tasks, task_logs, activities,
      history (ligados por client_id/process_id/task_id dos matches
      acima).
    + PACOTE 12 — filhos dependentes por process_id (cascade infalível,
      zero órfãos): rgpd_requests, document_metadata, portal_tokens,
      portal_messages, deadlines, process_finances, notifications,
      annotations, temp_links, data_suggestions, emails; e visits por
      process_id OU client_id. Hard-delete em AMBOS os modos (são filhos,
      como task_logs/history). process_activities (auditoria) e minutas
      (templates) NÃO são tocados por design.

CASCADE DELETE FORTE (PACOTE 11 — Eixo 4): ao apagar um cliente de
teste são obrigatoriamente apagados, sem deixar órfãos, todos os
processos, leads (property_leads com client_id dele) e role-mappings
(user_company_roles dos utilizadores/empresas de teste) pertencentes
a esse cliente.

PADRÃO DE MATCH:
    regex ``\\btest`` (case-insensitive) — apanha "test", "teste",
    "Teste 123", "testing", "test@exemplo.pt", mas NÃO apanha falsos
    positivos comuns em português como "atestado", "testamento" ou
    "latest" (exigem fronteira de palavra antes de "test").

MODOS DE APAGAMENTO (flag --mode):
    soft (predefinição) — Marca os PAIS (clients, processes, tasks,
        property_leads, companies) com is_deleted=True + deleted_at/
        deleted_by/previous_status e apaga (hard) os filhos puramente
        logarítmicos (task_logs, history, activities, documents) e as
        ligações user_company_roles — os pais já ficam escondidos de
        todas as listas do produto. Reversível nos pais.
    hard — Apaga fisicamente tudo (comportamento original do script).

UTILIZAÇÃO:
    cd backend && python -m scripts.cleanup_prod_test_data

FLAGS:
    --execute       Executa a eliminação real. Sem esta flag, o script
                    corre em modo SIMULAÇÃO (dry-run) e só reporta o que
                    seria apagado, sem tocar em nada. Ao usar --execute,
                    é pedida uma password de segurança no terminal
                    (variável de ambiente CLEANUP_SCRIPT_PASSWORD, com
                    fallback para "POWERCELL_CLEANUP_2026" se não estiver
                    definida).
    --mode soft     Soft-delete dos pais (predefinição).
    --mode hard     Hard-delete de tudo.

Nota de segurança: este script NÃO cria nenhum ficheiro de log nem
guarda rasto do que foi eliminado - toda a informação é apenas
impressa na consola durante a execução.
====================================================================
"""

import asyncio
import argparse
import getpass
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# PACOTE 9 — padrão transversal de "teste": apanha "test"/"teste"/
# "testes"/"testing" (com sufixos técnicos: test@..., test_1, test123) mas
# NÃO apanha falsos positivos comuns em português ("atestado",
# "testamento", "testemunho", "protesto", "Contestação") nem ingleses
# ("latest", "contest"). Lookarounds em vez de \b porque o underscore é
# word-char para \b ("user_test" deixaria de ser apanhado) — aqui a
# fronteira é apenas letras, cobrindo também user_test/test123.
TEST_PATTERN = {
    "$regex": r"(?<![a-zA-Z])test(e|es|ing)?(?![a-zA-Z])",
    "$options": "i",
}

CLEANUP_SCRIPT_PASSWORD_DEFAULT = "POWERCELL_CLEANUP_2026"
DELETED_BY_TAG = "cleanup_test_data_script"

# PACOTE 12 (Eixo 3 — cascade infalível, zero órfãos): colecções FILHAS
# dependentes por ``process_id`` que o P11 não cobria — apagar o processo
# sem apagar estas dependências deixava-as órfãs. São filhos (como
# task_logs/history/activities/documents): hard-delete em AMBOS os modos.
# NÃO inclui ``process_activities`` (trilho de auditoria por design) nem
# ``minutas`` (biblioteca de templates). ``visits`` liga-se por process_id
# OU client_id (tratada à parte no corpo do script); ``emails`` apenas por
# process_id.
PROCESS_CHILD_COLLECTIONS = [
    "rgpd_requests",      # pedidos RGPD por processo
    "document_metadata",  # metadados de documentos por processo
    "portal_tokens",      # tokens de acesso ao Portal por processo
    "portal_messages",    # mensagens do Portal por processo
    "deadlines",          # prazos por processo
    "process_finances",   # dados financeiros por processo
    "notifications",      # notificações por processo
    "annotations",        # anotações por processo
    "temp_links",         # links temporários por processo
    "data_suggestions",   # sugestões de dados por processo
    "emails",             # emails do webmail por processo
]


def _confirm_password() -> bool:
    """Pede a password de segurança no terminal (caracteres ocultos)."""
    expected = os.environ.get("CLEANUP_SCRIPT_PASSWORD") or CLEANUP_SCRIPT_PASSWORD_DEFAULT
    entered = getpass.getpass("Password de segurança para EXECUÇÃO REAL: ")
    return entered == expected


# ====================================================================
# QUERIES (funções puras — testáveis em tests/unit)
# ====================================================================

def build_client_test_query() -> dict:
    """Clientes/Leads cujo nome, email ou notas contêm "test"/"teste"."""
    return {
        "$or": [
            {"contacto.email": TEST_PATTERN},
            {"email": TEST_PATTERN},
            {"nome": TEST_PATTERN},
            {"notas": TEST_PATTERN},
        ]
    }


def build_process_test_query(client_ids: list) -> dict:
    """Processos por título/notes/observações OU ligados aos clientes."""
    clauses = [
        {"client_email": TEST_PATTERN},
        {"client_name": TEST_PATTERN},
        {"process_type": TEST_PATTERN},
        {"notes": TEST_PATTERN},
        {"observations": TEST_PATTERN},
        {"observation_notes": TEST_PATTERN},
    ]
    if client_ids:
        clauses.append({"client_id": {"$in": client_ids}})
    return {"$or": clauses}


def build_property_lead_test_query(client_ids: list = None) -> dict:
    """Leads de imóveis (property_leads) por título/notas/cliente/url.

    PACOTE 11 (Eixo 4 — cascade forte): inclui também as leads ligadas
    por ``client_id`` aos clientes de teste encontrados — apagar um
    cliente de teste SEM apagar as leads dele deixaria-as órfãs.
    """
    clauses = [
        {"title": TEST_PATTERN},
        {"notes": TEST_PATTERN},
        {"client_name": TEST_PATTERN},
        {"url": TEST_PATTERN},
    ]
    if client_ids:
        clauses.append({"client_id": {"$in": client_ids}})
    return {"$or": clauses}


def build_company_test_query() -> dict:
    """PACOTE 11 (Eixo 4) — Empresas de teste (`companies`).

    Match próprio por nome/emails de contacto técnicos (o NIF é
    numérico — não interessa para o match de 'teste').
    """
    return {
        "$or": [
            {"name": TEST_PATTERN},
            {"email": TEST_PATTERN},
            {"smtp_email": TEST_PATTERN},
            {"imap_email": TEST_PATTERN},
        ]
    }


def build_user_company_roles_test_query(user_ids: list, company_ids: list) -> dict:
    """PACOTE 11 (Eixo 4) — role-mappings (user_company_roles) de teste.

    Ligações dos utilizadores de teste (por user_id) e das empresas de
    teste (por company_id OU company_name). Nunca casa nada quando
    ambas as listas estão vazias.
    """
    clauses = []
    if user_ids:
        clauses.append({"user_id": {"$in": user_ids}})
    if company_ids:
        clauses.append({"company_id": {"$in": company_ids}})
        clauses.append({"company_name": {"$in": company_ids}})
    if not clauses:
        return {"id_placeholder_never_matches": True}
    return {"$or": clauses}


def build_activity_test_query(process_ids: list) -> dict:
    """Atividades cujo comentário contém "teste" OU ligadas aos processos."""
    clauses = [{"comment": TEST_PATTERN}]
    if process_ids:
        clauses.append({"process_id": {"$in": process_ids}})
    return {"$or": clauses}


def build_task_test_query(process_ids: list) -> dict:
    """Tarefas por título/descrição OU ligadas aos processos."""
    clauses = [
        {"title": TEST_PATTERN},
        {"description": TEST_PATTERN},
    ]
    if process_ids:
        clauses.append({"process_id": {"$in": process_ids}})
    return {"$or": clauses}


def build_soft_delete_set(now_iso: str, previous_status=None) -> dict:
    """$set do soft-delete (pais) — espelha services/process_delete.py."""
    payload = {
        "is_deleted": True,
        "deleted": True,
        "deleted_at": now_iso,
        "deleted_by": DELETED_BY_TAG,
        "updated_at": now_iso,
    }
    if previous_status is not None:
        payload["previous_status"] = previous_status
    return payload


# ====================================================================
# EXECUÇÃO
# ====================================================================

async def _soft_delete_parents(db, collection_name: str, query: dict, now_iso: str) -> int:
    """Soft-delete dos documentos que correspondem à query (pais).

    Nota: ``getattr(db, name)`` funciona com Motor, com o DatabaseProxy
    e com os fakes de teste (tests/unit/conftest.py).
    """
    coll = getattr(db, collection_name)
    docs = await coll.find(query, {"_id": 0, "id": 1, "status": 1}).to_list(None)
    for doc in docs:
        await coll.update_one(
            {"id": doc["id"]},
            {"$set": build_soft_delete_set(now_iso, doc.get("status"))},
        )
    return len(docs)


async def cleanup_prod_test_data(dry_run: bool = True, mode: str = "soft"):
    """Corre a limpeza transversal (dry-run por omissão)."""
    from database import db

    hard = mode == "hard"
    now_iso = datetime.now(timezone.utc).isoformat()
    empty_in = {"id_placeholder_never_matches": True}

    print("=" * 70)
    print("LIMPEZA DE DADOS DE TESTE (transversal — Pacote 11)")
    print("Filtro: 'test'/'teste' (case-insensitive, \\btest) em:")
    print("       clientes (nome/email/notas), processos (título/notas),")
    print("       leads, empresas, atividades e tarefas + cascata por IDs")
    print(f"Modo: {'SIMULAÇÃO (dry-run)' if dry_run else f'EXECUÇÃO REAL ({mode})'}")
    print("=" * 70)

    # ── 1) Clientes/Leads (clients) por campos próprios ───────────
    client_query = build_client_test_query()
    clients = await db.clients.find(
        client_query, {"_id": 0, "id": 1, "nome": 1, "contacto": 1, "email": 1}
    ).to_list(None)
    client_ids = [c["id"] for c in clients if c.get("id")]
    client_emails = [
        (c.get("contacto") or {}).get("email") or c.get("email")
        for c in clients
    ]
    client_emails = [e for e in client_emails if e]

    print(f"\n[CLIENTES] Leads/Clientes encontrados: {len(clients)}")
    for c in clients[:10]:
        email = (c.get("contacto") or {}).get("email") or c.get("email") or "?"
        print(f"   - {c.get('nome', '?')} | {email} | id={c.get('id')}")
    if len(clients) > 10:
        print(f"   ... e mais {len(clients) - 10}")

    # ── 2) Processos por campos próprios OU cascade dos clientes ──
    process_query = build_process_test_query(client_ids)
    processes = await db.processes.find(
        process_query,
        {"_id": 0, "id": 1, "process_number": 1, "client_name": 1,
         "client_email": 1, "process_type": 1, "notes": 1},
    ).to_list(None)
    process_ids = [p["id"] for p in processes if p.get("id")]

    print(f"\n[PROCESSOS] Encontrados: {len(processes)}")
    for p in processes[:10]:
        print(
            f"   - #{p.get('process_number', '?')} | {p.get('client_name', '?')} "
            f"| {p.get('client_email', '?')} | tipo={p.get('process_type', '?')} "
            f"| id={p.get('id')}"
        )
    if len(processes) > 10:
        print(f"   ... e mais {len(processes) - 10}")

    process_id_in = {"process_id": {"$in": process_ids}} if process_ids else empty_in

    # ── 3) Leads de imóveis (property_leads) por campos próprios ──
    # PACOTE 11 — cascade forte: a query inclui as leads ligadas por
    # client_id aos clientes de teste (sem isso ficariam órfãs).
    property_lead_query = build_property_lead_test_query(client_ids)
    property_leads = await db.property_leads.find(
        property_lead_query,
        {"_id": 0, "id": 1, "title": 1, "client_name": 1, "url": 1, "client_id": 1},
    ).to_list(None)

    print(f"\n[LEADS] Leads de imóveis encontrados: {len(property_leads)}")
    for l in property_leads[:10]:
        print(
            f"   - {str(l.get('title', '?'))[:60]} | {l.get('client_name', '?')} "
            f"| id={l.get('id')}"
        )
    if len(property_leads) > 10:
        print(f"   ... e mais {len(property_leads) - 10}")

    # ── 3b) Empresas (companies) — PACOTE 11 ─────────────────────
    company_query = build_company_test_query()
    companies = await db.companies.find(
        company_query,
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(None)
    company_ids = [comp["id"] for comp in companies if comp.get("id")]

    print(f"\n[EMPRESAS] Empresas de teste encontradas: {len(companies)}")
    for comp in companies[:10]:
        print(f"   - {comp.get('name', '?')} | {comp.get('email', '?')} | id={comp.get('id')}")
    if len(companies) > 10:
        print(f"   ... e mais {len(companies) - 10}")

    # ── 3c) Role-mappings (user_company_roles) — PACOTE 11 ────────
    # Utilizadores de teste: emails apanhados pelo padrão OU emails dos
    # clientes de teste (utilizadores de portal criados para eles).
    _test_email_users = await db.users.find(
        {"email": TEST_PATTERN}, {"_id": 0, "email": 1, "id": 1}
    ).to_list(None)
    test_user_emails = list({
        *client_emails,
        *[u["email"] for u in _test_email_users if u.get("email")],
    })
    test_user_ids = []
    if test_user_emails:
        _test_users = await db.users.find(
            {"email": {"$in": test_user_emails}}, {"_id": 0, "id": 1}
        ).to_list(None)
        test_user_ids = [u["id"] for u in _test_users if u.get("id")]
    ucr_query = build_user_company_roles_test_query(test_user_ids, company_ids)
    user_company_roles_count = await db.user_company_roles.count_documents(ucr_query)

    print(
        f"\n[ROLE-MAPPINGS] user_company_roles de teste: "
        f"{user_company_roles_count} (users: {len(test_user_ids)}, "
        f"empresas: {len(company_ids)})"
    )

    # ── 4) Atividades por comentário OU cascade dos processos ─────
    activity_query = build_activity_test_query(process_ids)
    activities = await db.activities.find(
        activity_query, {"_id": 0, "id": 1, "process_id": 1, "comment": 1}
    ).to_list(None)

    print(f"\n[ATIVIDADES] Encontradas: {len(activities)}")
    for a in activities[:10]:
        print(
            f"   - {str(a.get('comment', '?'))[:60]} | processo={a.get('process_id', '?')} "
            f"| id={a.get('id')}"
        )
    if len(activities) > 10:
        print(f"   ... e mais {len(activities) - 10}")

    # ── 5) Tarefas por título/descrição OU cascade dos processos ──
    task_query = build_task_test_query(process_ids)
    tasks = await db.tasks.find(
        task_query, {"_id": 0, "id": 1, "title": 1, "description": 1, "process_id": 1}
    ).to_list(None)
    task_ids = [t["id"] for t in tasks if t.get("id")]

    print(f"\n[TAREFAS] Encontradas: {len(tasks)}")
    for t in tasks[:10]:
        print(
            f"   - {t.get('title', '?')} | processo={t.get('process_id', '?')} "
            f"| id={t.get('id')}"
        )
    if len(tasks) > 10:
        print(f"   ... e mais {len(tasks) - 10}")

    # ── 6) Filhos em cascata (documentos, logs, histórico) ────────
    doc_client_filter = {"client_id": {"$in": client_ids}} if client_ids else empty_in
    document_query = {"$or": [doc_client_filter, process_id_in]}
    documents_count = await db.documents.count_documents(document_query)

    task_log_query = {
        "$or": [
            process_id_in,
            {"task_id": {"$in": task_ids}} if task_ids else empty_in,
        ]
    }
    task_logs_count = await db.task_logs.count_documents(task_log_query)
    history_count = await db.history.count_documents(process_id_in)

    print(f"\n[CASCADE] Documentos: {documents_count} | "
          f"Logs de tarefas: {task_logs_count} | "
          f"Entradas de histórico: {history_count}")

    # ── 6b) PACOTE 12 — filhos dependentes por process_id/client_id ──
    # Colecções que o P11 deixava órfãs (rgpd_requests, document_metadata,
    # portal_tokens, portal_messages, deadlines, process_finances,
    # notifications, annotations, temp_links, data_suggestions, emails —
    # todas por process_id; visits por process_id OU client_id).
    # Reutiliza os filtros EXACTOS já construídos (process_id_in /
    # doc_client_filter) — sem semânticas de match novas.
    visits_query = {"$or": [process_id_in, doc_client_filter]}
    process_child_counts = {}
    for coll_name in PROCESS_CHILD_COLLECTIONS:
        process_child_counts[coll_name] = await getattr(
            db, coll_name
        ).count_documents(process_id_in)
    visits_count = await db.visits.count_documents(visits_query)
    children_total = sum(process_child_counts.values()) + visits_count

    print(f"\n[CASCADE-DEPENDENTES] Filhos adicionais (PACOTE 12): "
          f"{children_total} registos")
    for coll_name, count in process_child_counts.items():
        if count:
            print(f"   - {coll_name}: {count}")
    if visits_count:
        print(f"   - visits: {visits_count}")

    total_records = (
        len(clients) + len(processes) + len(property_leads)
        + len(companies) + user_company_roles_count
        + len(activities) + len(tasks)
        + documents_count + task_logs_count + history_count
        + children_total
    )
    if total_records == 0:
        print("\nNada para limpar - não há dados de teste correspondentes.")
        return 0

    if dry_run:
        print("\n" + "=" * 70)
        print(
            f"SIMULAÇÃO ({mode}) — seriam processados: "
            f"{len(clients)} leads/clientes, {len(processes)} processos, "
            f"{len(property_leads)} leads, {len(companies)} empresas, "
            f"{user_company_roles_count} role-mappings, {len(activities)} "
            f"atividades, {len(tasks)} tarefas, {documents_count} documentos, "
            f"{task_logs_count} logs de tarefas, {history_count} entradas "
            f"de histórico e {children_total} registos dependentes em "
            f"cascata (PACOTE 12) (total {total_records})"
        )
        print("=" * 70)
        print("\nPara executar a limpeza real:")
        print("   python -m scripts.cleanup_prod_test_data --execute [--mode hard]")
        return total_records

    # ── Execução real ─────────────────────────────────────────────
    if not _confirm_password():
        print("\nERRO DE AUTENTICAÇÃO: password incorreta. Nada foi eliminado.")
        sys.exit(1)
    print("Password validada.\n")

    print(f"A limpar (modo {mode})...")

    def _report(label: str, deleted: int, total_expected: int) -> None:
        status = "OK" if deleted == total_expected else "⚠️ PARCIAL"
        print(f"{status}: {label} → {deleted} de {total_expected} processados")

    # Filhos logarísmicos primeiro (hard delete em ambos os modos —
    # os pais soft-deletados já os escondem da UI)
    r = await db.task_logs.delete_many(task_log_query)
    _report("Logs de tarefas eliminados", r.deleted_count, task_logs_count)

    r = await db.history.delete_many(process_id_in)
    _report("Entradas de histórico eliminadas", r.deleted_count, history_count)

    r = await db.activities.delete_many(activity_query)
    _report("Atividades eliminadas", r.deleted_count, len(activities))

    r = await db.documents.delete_many(document_query)
    _report("Documentos eliminados", r.deleted_count, documents_count)

    # PACOTE 12 — filhos dependentes (cascade forte, SEM óRFÃOS): apagados
    # em AMBOS os modos (como os filhos logarítmicos acima), com os mesmos
    # filtros contabilizados na simulação.
    for coll_name in PROCESS_CHILD_COLLECTIONS:
        r = await getattr(db, coll_name).delete_many(process_id_in)
        _report(
            f"Dependentes eliminados ({coll_name})",
            r.deleted_count, process_child_counts[coll_name],
        )

    r = await db.visits.delete_many(visits_query)
    _report("Visitas eliminadas", r.deleted_count, visits_count)

    # PACOTE 11 (Eixo 4 — cascade forte): role-mappings são LIGAÇÕES —
    # hard-delete em AMBOS os modos (igual aos filhos logarítmicos) para
    # não deixar user_company_roles órfãs de utilizadores/empresas de
    # teste escondidos.
    r = await db.user_company_roles.delete_many(ucr_query)
    _report("Role-mappings eliminados", r.deleted_count, user_company_roles_count)

    if hard:
        r = await db.tasks.delete_many(task_query)
        _report("Tarefas eliminadas", r.deleted_count, len(tasks))

        r = await db.property_leads.delete_many(property_lead_query)
        _report("Leads de imóveis eliminados", r.deleted_count, len(property_leads))

        r = await db.companies.delete_many(company_query)
        _report("Empresas eliminadas", r.deleted_count, len(companies))

        r = await db.processes.delete_many(process_query)
        _report("Processos eliminados", r.deleted_count, len(processes))

        r = await db.clients.delete_many(client_query)
        _report("Leads/Clientes eliminados", r.deleted_count, len(clients))
    else:
        # SOFT-DELETE dos pais (reversível) — is_deleted/deleted_at/deleted_by
        n = await _soft_delete_parents(db, "tasks", task_query, now_iso)
        _report("Tarefas marcadas como eliminadas (soft)", n, len(tasks))

        n = await _soft_delete_parents(db, "property_leads", property_lead_query, now_iso)
        _report("Leads de imóveis marcados como eliminados (soft)", n, len(property_leads))

        n = await _soft_delete_parents(db, "companies", company_query, now_iso)
        _report("Empresas marcadas como eliminadas (soft)", n, len(companies))

        n = await _soft_delete_parents(db, "processes", process_query, now_iso)
        _report("Processos marcados como eliminados (soft)", n, len(processes))

        n = await _soft_delete_parents(db, "clients", client_query, now_iso)
        _report("Leads/Clientes marcados como eliminados (soft)", n, len(clients))

    print("\n" + "=" * 70)
    print(f"LIMPEZA CONCLUÍDA ({mode}) — {total_records} registos processados")
    print(f"Executor: {DELETED_BY_TAG} @ {now_iso}")
    print("=" * 70)
    return total_records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Apaga transversalmente (soft/hard) Clientes, Processos, Leads, "
            "Empresas, Atividades e Tarefas cujos campos contenham "
            "'test'/'teste' (case-insensitive), com cascata forte para "
            "processos/leads/role-mappings e filhos logarítmicos."
        )
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Executar a limpeza real (sem isto é simulação)",
    )
    parser.add_argument(
        "--mode", choices=["soft", "hard"], default="soft",
        help="Modo de apagamento: soft (pais marcados is_deleted; predefinição) "
             "ou hard (apagamento físico total)",
    )
    args = parser.parse_args()

    asyncio.run(cleanup_prod_test_data(dry_run=not args.execute, mode=args.mode))
