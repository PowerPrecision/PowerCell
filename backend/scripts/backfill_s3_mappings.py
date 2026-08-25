#!/usr/bin/env python3
"""
====================================================================
BACKFILL S3 MAPPINGS (clients) — PowerCell CRM
====================================================================
Script de manutenção que percorre a coleção ``clients`` e garante que
todo o cliente tem um mapeamento de pasta S3 (``s3_folder``) válido.

CONTEXTO:
- Clientes criados antes do fluxo de onboarding ter passado a gerar
  o mapeamento S3 automaticamente (ou cujo campo foi perdido por um
  overwrite anterior) ficam sem ``s3_folder``, impedindo o Portal do
  Cliente e o CRM de listarem/mostrarem as pastas de documentos.

O QUE ESTE SCRIPT FAZ:
1. Itera a coleção ``clients`` e seleciona apenas os documentos cujo
   campo ``s3_folder`` seja ``None``/inexistente (ou vazio).
2. Para cada um, invoca ``s3_service.ensure_client_folder_mapping``
   — a mesma função robusta usada nos fluxos normais de criação —
   que reutiliza um mapeamento/pasta já existente sempre que possível
   e só cria uma pasta nova quando realmente não existe nenhuma.
3. Persiste o resultado com um ``$set`` estrito apenas na chave
   ``s3_folder`` (+ metadados de auditoria). Nunca substitui o
   documento inteiro nem toca noutros campos.

REGRAS DE SEGURANÇA:
- Idempotente: correr o script múltiplas vezes é seguro — clientes
  que já têm ``s3_folder`` válido são ignorados.
- Suporta --dry-run para simular sem escrever na BD.

USO:
    cd backend
    python scripts/backfill_s3_mappings.py --dry-run     # simular
    python scripts/backfill_s3_mappings.py                # executar
    python scripts/backfill_s3_mappings.py --limit 20 --dry-run
====================================================================
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def _missing_s3_folder_query() -> dict:
    """Query Mongo para clientes sem ``s3_folder`` válido (None ou inexistente)."""
    return {
        "$or": [
            {"s3_folder": {"$exists": False}},
            {"s3_folder": None},
            {"s3_folder": ""},
        ]
    }


async def backfill_clients(db, s3_service, dry_run: bool = False, limit: int = 0) -> dict:
    """Preenche o mapeamento S3 em falta para clientes existentes."""
    stats = {"total": 0, "restored": 0, "skipped_no_name": 0, "failed": 0}

    query = {**_missing_s3_folder_query(), "is_active": {"$ne": False}}
    cursor = db.clients.find(
        query,
        {"_id": 0, "id": 1, "nome": 1, "titular2_data": 1, "s3_folder": 1},
    )

    async for client in cursor:
        stats["total"] += 1
        if limit and stats["total"] > limit:
            stats["total"] -= 1
            break

        client_id = client.get("id")
        if not client_id:
            continue

        client_name = (client.get("nome") or "").strip()
        if not client_name:
            stats["skipped_no_name"] += 1
            print(f"  ⚠️  Cliente {client_id[:8]}... sem nome — ignorado.")
            continue

        titular2 = client.get("titular2_data") or {}
        second_client_name = titular2.get("nome") or titular2.get("name")

        result = await _backfill_one(
            s3_service=s3_service,
            collection=db.clients,
            doc_id=client_id,
            client_name=client_name,
            second_client_name=second_client_name,
            existing_s3_folder=client.get("s3_folder"),
            dry_run=dry_run,
            label=f"Cliente {client_id[:8]}... ({client_name})",
        )
        if result:
            stats["restored"] += 1
        else:
            stats["failed"] += 1

    return stats


async def _backfill_one(
    s3_service,
    collection,
    doc_id: str,
    client_name: str,
    second_client_name,
    existing_s3_folder,
    dry_run: bool,
    label: str,
) -> bool:
    """Resolve/cria o mapeamento S3 para um único cliente e persiste-o."""
    if existing_s3_folder:
        # Defesa extra: nunca devia acontecer dado o filtro da query, mas
        # evita qualquer escrita se o campo já estiver preenchido.
        return True

    # ``ensure_client_folder_mapping`` usa boto3 (síncrono) — corre em thread
    # para não bloquear o event loop.
    mapping = await asyncio.to_thread(
        s3_service.ensure_client_folder_mapping,
        doc_id,
        client_name,
        second_client_name,
        existing_s3_folder,
    )

    if not mapping.get("success") or not mapping.get("s3_folder"):
        print(f"  ❌ {label}: falha ao criar/resolver pasta S3.")
        return False

    folder_path = mapping["s3_folder"]
    action = "criada" if mapping.get("created") else "recuperada (já existia)"

    if dry_run:
        print(f"  [DRY] {label}: pasta {action} -> {folder_path}")
        return True

    now = datetime.now(timezone.utc).isoformat()
    # CRÍTICO: $set estrito apenas nestas chaves. Nunca substitui o
    # documento inteiro nem qualquer outro campo do cliente.
    await collection.update_one(
        {"id": doc_id},
        {
            "$set": {
                "s3_folder": folder_path,
                "s3_mapping_backfilled_at": now,
                "s3_mapping_backfilled_by": "backfill_s3_mappings",
            }
        },
    )
    print(f"  ✅ {label}: pasta {action} -> {folder_path}")
    return True


def print_summary(stats: dict, dry_run: bool):
    mode = "DRY RUN (simulação)" if dry_run else "EXECUÇÃO REAL"
    print("\n" + "=" * 70)
    print(f"  BACKFILL S3 MAPPINGS (clients) — {mode}")
    print("=" * 70)

    print("\n📋 CLIENTES:")
    print(f"   Total com mapeamento em falta: {stats['total']}")
    print(f"   Preenchidos:                   {stats['restored']}")
    print(f"   Ignorados (sem nome):          {stats['skipped_no_name']}")
    print(f"   Falhados:                      {stats['failed']}")

    if dry_run:
        print("\n⚠️  DRY RUN — nenhum dado foi alterado. Execute sem --dry-run para aplicar.")
    else:
        print("\n✅ Backfill concluído.")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill — Garante mapeamento S3 para clientes sem s3_folder (PowerCell CRM)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Simular sem escrever na BD")
    parser.add_argument("--limit", type=int, default=0, help="Limitar N clientes (0 = sem limite)")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME devem estar definidos em backend/.env")
        sys.exit(1)

    # Importado depois do sys.path.insert, para reutilizar exatamente a
    # mesma lógica robusta de criação/validação de pastas usada em produção.
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        print("❌ Serviço S3 não está configurado (credenciais AWS em falta).")
        print("   Defina AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY e AWS_BUCKET_NAME.")
        sys.exit(1)

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    async def _run():
        print(f"🚀 Backfill S3 Mappings (clients) — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"   BD: {db_name}")
        print(f"   Bucket S3: {s3_service.bucket_name}")
        print(f"   Dry run: {args.dry_run}")
        print(f"   Limit: {args.limit or 'sem limite'}\n")

        print("📋 A procurar clientes com s3_folder em falta...")
        stats = await backfill_clients(db, s3_service, dry_run=args.dry_run, limit=args.limit)

        print_summary(stats, args.dry_run)

    asyncio.run(_run())
    mongo_client.close()


if __name__ == "__main__":
    main()
