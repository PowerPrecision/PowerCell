#!/usr/bin/env python3
"""
====================================================================
CLEAN STUCK BACKUPS — PowerCell CRM
====================================================================
Script de manutenção que procura registos de backup "encravados" na
coleção ``backup_history`` — execuções que ficaram em estado de
progresso (``running`` / equivalentes) há mais de 24 horas sem nunca
terem sido marcadas como concluídas ou falhadas (normalmente porque o
processo do servidor foi reiniciado/crashou a meio do backup) — e
corrige o seu estado para ``failed``.

CONTEXTO:
- Cada execução de backup regista um documento em ``backup_history``
  com ``status="running"`` no início (ver
  ``services/backup.py::run_scheduled_backup`` e
  ``services/backup_trigger.py``) e é depois atualizado para
  ``"completed"`` ou ``"failed"``.
- Se o processo morrer a meio (crash, restart, deploy) esse
  ``update_one`` final nunca corre, e o registo fica "presa" em
  ``running`` para sempre. O frontend (``BackupsPage.js``) mostra
  qualquer status que não seja ``completed``/``failed`` como
  "Em Progresso", o que dá a falsa impressão de um backup em curso
  indefinidamente.

O QUE ESTE SCRIPT FAZ:
1. Procura em ``backup_history`` registos cujo ``status`` indique
   progresso (``running``, ``in_progress``, ``pending`` — e variantes
   em português, por segurança) e cujo ``started_at`` seja anterior a
   24 horas.
2. Para cada um, faz ``$set`` estrito do ``status`` para ``"failed"``,
   preenchendo ``completed_at`` e um ``error`` descritivo. Nunca toca
   em outros campos do documento (triggered_by, trigger_type, etc.).

REGRAS DE SEGURANÇA:
- Idempotente: correr múltiplas vezes é seguro — só atua sobre
  registos ainda "encravados".
- Suporta --dry-run para simular sem escrever na BD.
- Suporta --hours para ajustar o limiar de "encravado" (default 24h).

USO:
    cd backend
    python scripts/clean_stuck_backups.py --dry-run      # simular
    python scripts/clean_stuck_backups.py                 # executar
    python scripts/clean_stuck_backups.py --hours 12
====================================================================
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# Valores de status que consideramos "em progresso" para efeitos deste
# script (o valor canónico usado em `services/backup.py` é "running",
# mas cobrimos variantes/equivalentes por segurança).
_IN_PROGRESS_STATUSES = [
    "running",
    "in_progress",
    "pending",
    "em_progresso",
    "Em Progresso",
    "Em progresso",
]

FAILED_STATUS = "failed"


def _stuck_query(cutoff: datetime) -> dict:
    """Query Mongo para backups encravados há mais de `cutoff`."""
    return {
        "status": {"$in": _IN_PROGRESS_STATUSES},
        "started_at": {"$lt": cutoff},
    }


async def clean_stuck_backups(db, dry_run: bool = False, hours: int = 24) -> dict:
    """Marca como `failed` os backups encravados há mais de `hours` horas."""
    stats = {"total": 0, "cleaned": 0, "failed": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = _stuck_query(cutoff)

    cursor = db.backup_history.find(
        query,
        {"_id": 0, "id": 1, "status": 1, "started_at": 1, "trigger_type": 1, "triggered_by_email": 1},
    )

    async for backup in cursor:
        stats["total"] += 1
        backup_id = backup.get("id")
        if not backup_id:
            stats["failed"] += 1
            continue

        started_at = backup.get("started_at")
        label = f"Backup {str(backup_id)[:8]}... (status={backup.get('status')}, started_at={started_at})"

        if dry_run:
            print(f"  [DRY] {label} -> seria marcado como '{FAILED_STATUS}'")
            stats["cleaned"] += 1
            continue

        now = datetime.now(timezone.utc)
        # CRÍTICO: $set estrito apenas nestas chaves. Nunca substitui o
        # documento inteiro nem outros campos (triggered_by, trigger_type,
        # result, etc.).
        result = await db.backup_history.update_one(
            {"id": backup_id},
            {
                "$set": {
                    "status": FAILED_STATUS,
                    "completed_at": now,
                    "error": f"Backup encravado em '{backup.get('status')}' há mais de {hours}h — marcado como falhado automaticamente por clean_stuck_backups.",
                    "cleaned_stuck_at": now,
                    "cleaned_stuck_by": "clean_stuck_backups",
                }
            },
        )
        if result.modified_count:
            print(f"  ✅ {label} -> marcado como '{FAILED_STATUS}'")
            stats["cleaned"] += 1
        else:
            print(f"  ❌ {label} -> falha ao atualizar")
            stats["failed"] += 1

    return stats


def print_summary(stats: dict, dry_run: bool, hours: int):
    mode = "DRY RUN (simulação)" if dry_run else "EXECUÇÃO REAL"
    print("\n" + "=" * 70)
    print(f"  CLEAN STUCK BACKUPS — {mode}")
    print("=" * 70)

    print(f"\n⏱️  Limiar de 'encravado': > {hours}h desde started_at")
    print("\n📦 BACKUPS:")
    print(f"   Total encontrados (encravados):  {stats['total']}")
    print(f"   Marcados como '{FAILED_STATUS}':          {stats['cleaned']}")
    print(f"   Falhados ao atualizar:            {stats['failed']}")

    if dry_run:
        print("\n⚠️  DRY RUN — nenhum dado foi alterado. Execute sem --dry-run para aplicar.")
    else:
        print("\n✅ Limpeza concluída.")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Clean Stuck Backups — Marca como 'failed' backups encravados em progresso (PowerCell CRM)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Simular sem escrever na BD")
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Limiar de horas desde started_at para considerar um backup 'encravado' (default: 24)",
    )
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME devem estar definidos em backend/.env")
        sys.exit(1)

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    async def _run():
        print(f"🚀 Clean Stuck Backups — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"   BD: {db_name}")
        print(f"   Dry run: {args.dry_run}")
        print(f"   Limiar: {args.hours}h\n")

        stats = await clean_stuck_backups(db, dry_run=args.dry_run, hours=args.hours)
        print_summary(stats, args.dry_run, args.hours)

    asyncio.run(_run())
    mongo_client.close()


if __name__ == "__main__":
    main()
