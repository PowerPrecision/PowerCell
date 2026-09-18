#!/usr/bin/env python3
"""
====================================================================
BACKFILL S3 MAPPINGS (clients + processes) — PowerCell CRM
====================================================================
Script de manutenção que percorre as coleções ``clients`` E
``processes`` e garante que todo o documento tem um mapeamento de
pasta S3 (``s3_folder``) válido — criando a estrutura real no bucket
(marcadores ``.keep`` via boto3) quando necessário.

PACOTE 9 — actualização face à versão anterior (só clients):
1. COBERTURA DE PROCESSOS: os processos também têm hoje ``s3_folder``
   (criado na criação pelo hook Pacote 9 ou lazy pelo Portal) e
   ficavam de fora do backfill — a principal causa de "clientes não
   mapeados com o S3" reportada em produção.
2. FILTROS CORRIGIDOS:
   - clients: o filtro antigo usava ``is_active`` (campo de PROCESS,
     não de client) — agora exclui apenas soft-deleted
     (``is_deleted``/status "eliminado"), que não precisam de pasta.
   - processos: exclui soft-deleted (``is_deleted``) e inactivos.
   - Valores "lixo" (``"undefined"``/``"null"``/``"None"``) no campo
     ``s3_folder`` passam a contar como SEM mapeamento (antes só
     missing/None/vazio eram apanhados — docs com lixo ficavam de fora
     e quebravam o Explorer S3).
3. 2º TITULAR: lido do sítio certo para cada coleção — processos:
   ``second_client_name``; clients: legacy ``titular2_data``
   (retrocompatibilidade).

O QUE ESTE SCRIPT FAZ:
1. Itera ``clients`` e ``processes`` e selecciona os documentos sem
   ``s3_folder`` válido (None/inexistente/vazio/"undefined"/"null").
2. Para cada um, invoca ``s3_service.ensure_client_folder_mapping``
   — a mesma função robusta usada nos fluxos normais de criação —
   que reutiliza uma pasta já existente (match fuzzy por nome) sempre
   que possível e só cria uma pasta nova quando não existe nenhuma
   (marcadores ``.keep`` via boto3/put_object).
3. Persiste o resultado com um ``$set`` estrito apenas na chave
   ``s3_folder`` (+ metadados de auditoria). Nunca substitui o
   documento inteiro nem toca noutros campos.

REGRAS DE SEGURANÇA:
- Idempotente: correr o script múltiplas vezes é seguro — documentos
  que já têm ``s3_folder`` válido são ignorados.
- Suporta --dry-run para simular sem escrever na BD nem no S3.
- Degradação graciosa: falhas pontuais (S3/BD) são logadas e o script
  continua para o documento seguinte.

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

# Valores de "lixo" que contam como SEM mapeamento (o admin S3 rejeita-os)
GARBAGE_S3_FOLDERS = ("undefined", "null", "none", "")


def _missing_s3_folder_query() -> dict:
    """Query Mongo para docs sem ``s3_folder`` válido (missing/None/vazio)."""
    return {
        "$or": [
            {"s3_folder": {"$exists": False}},
            {"s3_folder": None},
            {"s3_folder": ""},
            {"s3_folder": {"$in": list(GARBAGE_S3_FOLDERS)}},
        ]
    }


def _not_deleted_query() -> dict:
    """Exclui documentos soft-deleted (não precisam de pasta S3)."""
    return {
        "is_deleted": {"$ne": True},
        "status": {"$ne": "eliminado"},
    }


def _has_garbage_s3_folder(folder) -> bool:
    """True se o valor gravado é lixo ("undefined"/"null"/"None"/"")."""
    if not folder or not isinstance(folder, str):
        return True
    return folder.strip().lower() in GARBAGE_S3_FOLDERS


async def backfill_collection(
    db,
    s3_service,
    collection_name: str,
    *,
    label: str,
    dry_run: bool = False,
    limit: int = 0,
    backfill_by: str = "backfill_s3_mappings",
) -> dict:
    """
    Preenche o mapeamento S3 em falta para UMA coleção (clients/processes).

    A resolução do 2º titular adapta-se à coleção:
    - processes: ``second_client_name`` (campo actual do modelo)
    - clients: ``titular2_data`` (legacy — retrocompatibilidade)
    """
    stats = {"total": 0, "restored": 0, "skipped_no_name": 0, "failed": 0}

    # getattr funciona com Motor, DatabaseProxy e fakes de teste (conftest)
    collection = getattr(db, collection_name)
    query = {"$and": [_missing_s3_folder_query(), _not_deleted_query()]}

    async for doc in collection.find(
        query,
        {"_id": 0, "id": 1, "nome": 1, "client_name": 1,
         "second_client_name": 1, "titular2_data": 1, "s3_folder": 1},
    ):
        stats["total"] += 1
        if limit and stats["total"] > limit:
            stats["total"] -= 1
            break

        doc_id = doc.get("id")
        if not doc_id:
            continue

        # Nome principal: clients → nome; processes → client_name
        primary_name = (doc.get("nome") or doc.get("client_name") or "").strip()
        if not primary_name:
            stats["skipped_no_name"] += 1
            print(f"  ⚠️  {label} {doc_id[:8]}... sem nome — ignorado.")
            continue

        # 2º titular: processes → second_client_name; clients → legacy
        second_client_name = doc.get("second_client_name")
        if not second_client_name:
            titular2 = doc.get("titular2_data") or {}
            second_client_name = titular2.get("nome") or titular2.get("name")

        result = await _backfill_one(
            s3_service=s3_service,
            collection=collection,
            doc_id=doc_id,
            client_name=primary_name,
            second_client_name=second_client_name,
            existing_s3_folder=doc.get("s3_folder"),
            dry_run=dry_run,
            backfill_by=backfill_by,
            label=f"{label} {doc_id[:8]}... ({primary_name})",
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
    backfill_by: str,
    label: str,
) -> bool:
    """Resolve/cria o mapeamento S3 para um único documento e persiste-o."""
    if existing_s3_folder and not _has_garbage_s3_folder(existing_s3_folder):
        # Defesa extra: nunca devia acontecer dado o filtro da query, mas
        # evita qualquer escrita se o campo já estiver preenchido.
        return True

    # ``ensure_client_folder_mapping`` usa boto3 (síncrono) — corre em thread
    # para não bloquear o event loop. Nota: valores de lixo no campo
    # existente são passados como None — o ensure trata "undefined"/"null"
    # como inválidos, mas enviamos já limpos para o caminho 1 (reutilização).
    mapping = await asyncio.to_thread(
        s3_service.ensure_client_folder_mapping,
        doc_id,
        client_name,
        second_client_name,
        None,  # existing_s3_folder lixo → procurar/criar de novo
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
    # documento inteiro nem qualquer outro campo.
    await collection.update_one(
        {"id": doc_id},
        {
            "$set": {
                "s3_folder": folder_path,
                "s3_mapping_backfilled_at": now,
                "s3_mapping_backfilled_by": backfill_by,
            }
        },
    )
    print(f"  ✅ {label}: pasta {action} -> {folder_path}")
    return True


def print_summary(clients_stats: dict, processes_stats: dict, dry_run: bool):
    mode = "DRY RUN (simulação)" if dry_run else "EXECUÇÃO REAL"
    print("\n" + "=" * 70)
    print(f"  BACKFILL S3 MAPPINGS (clients + processes) — {mode}")
    print("=" * 70)

    for label, stats in (("CLIENTES", clients_stats), ("PROCESSOS", processes_stats)):
        print(f"\n📋 {label}:")
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
        description=(
            "Backfill — Garante mapeamento S3 (boto3 + persistência) para "
            "CLIENTES e PROCESSOS sem s3_folder válido (PowerCell CRM)"
        )
    )
    parser.add_argument("--dry-run", action="store_true", help="Simular sem escrever na BD")
    parser.add_argument("--limit", type=int, default=0, help="Limitar N documentos por coleção (0 = sem limite)")
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
        print(f"🚀 Backfill S3 Mappings (clients + processes) — "
              f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"   BD: {db_name}")
        print(f"   Bucket S3: {s3_service.bucket_name}")
        print(f"   Dry run: {args.dry_run}")
        print(f"   Limit: {args.limit or 'sem limite'}\n")

        print("📋 A procurar CLIENTES com s3_folder em falta...")
        clients_stats = await backfill_collection(
            db, s3_service, "clients", label="Cliente",
            dry_run=args.dry_run, limit=args.limit,
        )

        print("\n📋 A procurar PROCESSOS com s3_folder em falta...")
        processes_stats = await backfill_collection(
            db, s3_service, "processes", label="Processo",
            dry_run=args.dry_run, limit=args.limit,
        )

        print_summary(clients_stats, processes_stats, args.dry_run)

    asyncio.run(_run())
    mongo_client.close()


if __name__ == "__main__":
    main()
