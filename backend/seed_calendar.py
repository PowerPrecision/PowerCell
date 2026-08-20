#!/usr/bin/env python3
"""
Pacote de Seeding — eventos de calendário para testes de carga e UI.

Gera cerca de 50 prazos/eventos (Escrituras, Reuniões, CPCV, Ausências/Férias)
distribuídos pelo mês passado, mês atual e mês seguinte.

Regra de ouro: na atribuição (assigned_to / assigned_user_ids / user_id)
o script ignora qualquer utilizador com role admin ou index/indexacao.
Só atribui a consultor, intermediario (ou mediador legado) ou diretor.

Os eventos ligam-se a processos/clientes distintos para testar cores
dinâmicas no frontend (hash de process_id / client_name).

Uso:
    cd backend
    MONGO_URL="mongodb://localhost:27017" DB_NAME="PowerCell_dev" python seed_calendar.py
    python seed_calendar.py --keep-existing   # não apaga seeds anteriores
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import uuid
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

SEED_TAG = "seed_calendar"
SEED_ALLOWED_ROLES = ("consultor", "intermediario", "mediador", "diretor")
SEED_EXCLUDED_ROLES = ("admin", "indexacao", "index", "cliente", "parceiro", "ceo")

CLIENT_NAMES = [
    "Ana Costa Silva",
    "Bruno Ferreira Lopes",
    "Catarina Mendes",
    "Diogo Nunes",
    "Eva Rocha Pinto",
    "Francisco Almeida",
    "Gabriela Sousa",
    "Hugo Martins",
    "Inês Carvalho",
    "João Pedro Teixeira",
    "Leonor Vieira",
    "Miguel Santos",
    "Nádia Correia",
    "Oscar Ribeiro",
    "Patrícia Gomes",
    "Rui Filipe Barbosa",
]

ESCRITURA_TITLES = [
    "Escritura — {client}",
    "Escritura no notário — {client}",
    "Confirmação de escritura — {client}",
    "Escritura de compra e venda — {client}",
]
REUNIAO_TITLES = [
    "Reunião com cliente — {client}",
    "Reunião de ponto de situação — {client}",
    "Call de acompanhamento — {client}",
    "Reunião com o banco — {client}",
    "Reunião de proposta — {client}",
]
CPCV_TITLES = [
    "Assinatura CPCV — {client}",
    "Revisão CPCV — {client}",
    "CPCV no cartório — {client}",
    "Entrega de sinal CPCV — {client}",
]
AUSENCIA_TITLES = [
    "Férias",
    "Folga",
    "Ausência — formação",
    "Ausência médica",
    "Férias de Verão",
    "Férias de Natal",
]


def _norm(value) -> str:
    return (value or "").strip().lower()


def is_seed_assignee(user: dict) -> bool:
    primary = _norm(user.get("role"))
    if primary in SEED_EXCLUDED_ROLES:
        return False
    roles = {primary}
    for extra in user.get("additional_roles") or []:
        roles.add(_norm(extra))
    return bool(roles & set(SEED_ALLOWED_ROLES))


def month_window(year: int, month: int) -> tuple[datetime, datetime]:
    last_day = monthrange(year, month)[1]
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year, month, last_day, tzinfo=timezone.utc)
    return start, end


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def random_day(start: datetime, end: datetime, rng: random.Random) -> datetime:
    span = max((end - start).days, 0)
    return start + timedelta(days=rng.randint(0, span))


def iso_date(dt: datetime) -> str:
    return dt.date().isoformat()


def build_event_plan(rng: random.Random) -> list[dict]:
    """~50 eventos: mix de tipos, 3 meses civis."""
    today = datetime.now(timezone.utc)
    months = [shift_month(today.year, today.month, d) for d in (-1, 0, 1)]
    # 16 + 18 + 16 = 50; tipos por mês ~ 4 escritura, 5 reunião, 4 cpcv, 4 ausência
    per_month = [
        [("escritura", 4), ("reuniao", 5), ("cpcv", 4), ("ausencia", 3)],
        [("escritura", 5), ("reuniao", 5), ("cpcv", 4), ("ausencia", 4)],
        [("escritura", 4), ("reuniao", 5), ("cpcv", 4), ("ausencia", 3)],
    ]
    plan = []
    for (year, month), mix in zip(months, per_month):
        start, end = month_window(year, month)
        for kind, count in mix:
            for _ in range(count):
                due = random_day(start, end, rng)
                if kind == "ausencia":
                    length = rng.choice([1, 2, 3, 5, 7])
                    end_dt = min(due + timedelta(days=length - 1), end)
                    plan.append({
                        "kind": kind,
                        "due": due,
                        "end": end_dt,
                    })
                else:
                    plan.append({
                        "kind": kind,
                        "due": due,
                        "end": due,
                    })
    rng.shuffle(plan)
    return plan


async def ensure_diverse_processes(db, staff: list[dict], rng: random.Random) -> list[dict]:
    """Usa processos existentes; cria um lote mínimo se a BD estiver vazia."""
    existing = await db.processes.find(
        {"is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "client_id": 1, "client_name": 1, "company_id": 1, "company": 1},
    ).to_list(80)
    named = [p for p in existing if p.get("id") and (p.get("client_name") or p.get("client_id"))]
    if len(named) >= 8:
        return named

    now = datetime.now(timezone.utc).isoformat()
    created = []
    for i, name in enumerate(CLIENT_NAMES, start=1):
        assignee = staff[i % len(staff)]
        client_id = str(uuid.uuid4())
        process_id = str(uuid.uuid4())
        company = assignee.get("company_id") or assignee.get("company")
        client_doc = {
            "id": client_id,
            "nome": name,
            "name": name,
            "email": f"seed.cal.{i}@example.pt",
            "source": SEED_TAG,
            "created_at": now,
            "is_active": True,
        }
        process_doc = {
            "id": process_id,
            "process_number": f"SEED-CAL-{i:03d}",
            "client_id": client_id,
            "client_ids": [client_id],
            "client_name": name,
            "client_email": client_doc["email"],
            "status": "fase_escritura" if i % 2 == 0 else "fase_documental",
            "is_active": True,
            "source": SEED_TAG,
            "company_id": company,
            "assigned_consultor_id": assignee["id"] if _norm(assignee.get("role")) in (
                "consultor", "diretor",
            ) else None,
            "assigned_mediador_id": assignee["id"] if _norm(assignee.get("role")) in (
                "intermediario", "mediador",
            ) else None,
            "created_at": now,
            "updated_at": now,
        }
        await db.clients.insert_one(client_doc)
        await db.processes.insert_one(process_doc)
        created.append(process_doc)
        print(f"  [PROC] {process_doc['process_number']} — {name}")
    rng.shuffle(created)
    return created + named


def build_deadline_doc(
    *,
    kind: str,
    due: datetime,
    end: datetime,
    assignee: dict,
    process: dict | None,
    rng: random.Random,
    created_by: str,
) -> dict:
    client_name = (process or {}).get("client_name") or rng.choice(CLIENT_NAMES)
    company_id = (
        assignee.get("company_id")
        or assignee.get("company")
        or (process or {}).get("company_id")
        or (process or {}).get("company")
    )
    role = _norm(assignee.get("role"))
    if kind == "escritura":
        title = rng.choice(ESCRITURA_TITLES).format(client=client_name)
        event_type = "event"
        all_day = True
        priority = rng.choice(["high", "high", "medium"])
        process_id = process["id"] if process else None
        visible = True
    elif kind == "cpcv":
        title = rng.choice(CPCV_TITLES).format(client=client_name)
        event_type = "event"
        all_day = rng.choice([True, False])
        priority = "high"
        process_id = process["id"] if process else None
        visible = True
    elif kind == "reuniao":
        title = rng.choice(REUNIAO_TITLES).format(client=client_name)
        event_type = "event"
        all_day = False
        priority = rng.choice(["medium", "low", "medium"])
        process_id = process["id"] if process else None
        visible = False
    else:
        title = rng.choice(AUSENCIA_TITLES)
        event_type = "absence"
        all_day = True
        priority = "low"
        process_id = None
        visible = False

    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "title": title,
        "description": f"[{SEED_TAG}] {kind} gerado para testes de calendário / UI.",
        "due_date": iso_date(due),
        "end_date": iso_date(end),
        "priority": priority,
        "completed": False,
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assigned_user_ids": [assignee["id"]],
        "assigned_consultor_id": assignee["id"] if role in ("consultor", "diretor") else None,
        "assigned_mediador_id": assignee["id"] if role in ("intermediario", "mediador") else None,
        "type": event_type,
        "visible_to_client": visible,
        "reminder_time": ["1d"] if kind != "ausencia" else None,
        "all_day": all_day,
        "company_id": company_id,
        "source": SEED_TAG,
        "seed_tag": SEED_TAG,
    }


async def seed_calendar(keep_existing: bool) -> None:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    rng = random.Random(20260820)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print("=" * 60)
    print("PowerCell — Seed de calendário (Pacote de Seeding)")
    print("=" * 60)
    print(f"MongoDB: {mongo_url}")
    print(f"Database: {db_name}")
    print()

    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(500)
    staff = [u for u in users if u.get("id") and is_seed_assignee(u)]
    rejected = [
        f"{u.get('name')} ({u.get('role')})"
        for u in users
        if _norm(u.get("role")) in SEED_EXCLUDED_ROLES
    ]
    if not staff:
        print("❌ Nenhum consultor / intermediário / diretor encontrado.")
        print("   Corre seed.py primeiro.")
        client.close()
        sys.exit(1)

    print(f"Staff elegível ({len(staff)}):")
    for u in staff:
        print(f"  - {u.get('name')} [{u.get('role')}] {u.get('email')}")
    if rejected:
        print("Ignorados (admin/index/ceo/cliente/parceiro):")
        for line in rejected:
            print(f"  - {line}")
    print()

    if not keep_existing:
        deleted = await db.deadlines.delete_many(
            {"$or": [{"seed_tag": SEED_TAG}, {"source": SEED_TAG}]},
        )
        print(f"Deadlines seed anteriores removidos: {deleted.deleted_count}")

    processes = await ensure_diverse_processes(db, staff, rng)
    print(f"Processos/clientes para cores: {len(processes)}")
    print()

    plan = build_event_plan(rng)
    docs = []
    for i, item in enumerate(plan):
        assignee = staff[i % len(staff)]
        process = None if item["kind"] == "ausencia" else processes[i % len(processes)]
        docs.append(build_deadline_doc(
            kind=item["kind"],
            due=item["due"],
            end=item["end"],
            assignee=assignee,
            process=process,
            rng=rng,
            created_by=assignee["id"],
        ))

    # Garantia extra: nenhum assignee proibido
    bad = [
        d for d in docs
        if any(
            uid in {u["id"] for u in users if not is_seed_assignee(u) and u.get("id")}
            for uid in (d.get("assigned_user_ids") or [])
        )
    ]
    if bad:
        print(f"❌ Recusa: {len(bad)} eventos com assignee inválido.")
        client.close()
        sys.exit(1)

    await db.deadlines.insert_many(docs)

    kind_counts = {"escritura": 0, "reuniao": 0, "cpcv": 0, "ausencia": 0}
    months = {}
    clients = set()
    for d, item in zip(docs, plan):
        kind_counts[item["kind"]] = kind_counts.get(item["kind"], 0) + 1
        month_key = d["due_date"][:7]
        months[month_key] = months.get(month_key, 0) + 1
        if d.get("process_id"):
            clients.add(d["process_id"])

    print(f"Inseridos {len(docs)} eventos:")
    for k, v in kind_counts.items():
        print(f"  - {k}: {v}")
    print("Por mês:")
    for k in sorted(months):
        print(f"  - {k}: {months[k]}")
    print(f"Processos distintos (cores): {len(clients)}")
    print("=" * 60)
    client.close()


def main():
    parser = argparse.ArgumentParser(description="Seed de eventos de calendário")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Não apagar eventos seed_calendar anteriores",
    )
    args = parser.parse_args()
    asyncio.run(seed_calendar(keep_existing=args.keep_existing))


if __name__ == "__main__":
    main()
