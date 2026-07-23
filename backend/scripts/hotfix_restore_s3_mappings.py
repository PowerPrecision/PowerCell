#!/usr/bin/env python3
"""
====================================================================
HOTFIX — RESTORE S3 MAPPINGS — PowerCell CRM
====================================================================
Script de recuperação ISOLADO para o bug crítico de mapeamentos S3
em falta em `processes` e `clients`.

CONTEXTO DO BUG:
- Alguns clientes/processos existentes não têm o campo `s3_folder`
  preenchido (nunca foi criado, ou foi perdido por um overwrite
  anterior no MongoDB), pelo que o Portal do Cliente e o CRM não
  conseguem listar/mostrar corretamente as pastas de documentos.

O QUE ESTE SCRIPT FAZ:
1. Procura em `processes` (fonte principal usada pelo Portal para
   upload/listagem de documentos) e em `clients` (usado em fluxos
   de onboarding) todos os documentos com `s3_folder` em falta,
   vazio, ou com valores inválidos ("undefined", "null", "None").
2. Para cada um, chama `s3_service.ensure_client_folder_mapping(...)`
   — a mesma função robusta usada nos fluxos normais de criação —
   que:
     a) reutiliza o mapeamento existente se ainda for válido,
     b) reutiliza uma pasta já existente no S3 com nome semelhante
        (evita duplicados), ou
     c) cria a estrutura de pastas padrão no S3 caso não exista.
3. Grava a referência resultante de volta no documento, usando
   ESTRITAMENTE `$set` apenas na chave `s3_folder` (+ metadados de
   auditoria `s3_mapping_restored_at`/`s3_mapping_restored_by`).
   NUNCA substitui o documento inteiro, nem toca em qualquer outro
   campo (contacto, dados_pessoais, process_ids, etc.).

REGRAS DE SEGURANÇA:
- Idempotente: correr o script múltiplas vezes é seguro — documentos
  que já têm `s3_folder` válido são ignorados.
- Nunca apaga, substitui ou faz overwrite de campos não relacionados
  com o mapeamento S3.
- Suporta --dry-run para simular sem escrever na BD.

USO:
    cd backend
    python scripts/hotfix_restore_s3_mappings.py --dry-run           # simular
    python scripts/hotfix_restore_s3_mappings.py                     # executar
    python scripts/hotfix_restore_s3_mappings.py --collection clients
    python scripts/hotfix_restore_s3_mappings.py --limit 20 --dry-run
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


# Valores que consideramos "em falta" para efeitos de mapeamento S3.
_INVALID_S3_FOLDER_VALUES = {None, "", "undefined", "null", "None"}


def _is_missing_mapping(value) -> bool:
    if value in _INVALID_S3_FOLDER_VALUES:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _missing_mapping_query() -> dict:
    """Query Mongo para documentos sem mapeamento S3 válido."""
    return {
        "$or": [
            {"s3_folder": {"$exists": False}},
            {"s3_folder": None},
            {"s3_folder": ""},
            {"s3_folder": "undefined"},
            {"s3_folder": "null"},
            {"s3_folder": "None"},
        ]
    }


async def restore_processes(db, s3_service, dry_run: bool = False, limit: int = 0) -> dict:
    """Repara mapeamentos S3 em falta na coleção `processes`.

    `processes` é a fonte de verdade usada pelo Portal do Cliente para
    upload/listagem de documentos (ver `s3_folder` em routes/portal.py).
    """
    stats = {"total": 0, "restored": 0, "skipped_no_name": 0, "failed": 0}

    query = {**_missing_mapping_query(), "is_deleted": {"$ne": True}}
    cursor = db.processes.find(
        query,
        {"_id": 0, "id": 1, "client_name": 1, "second_client_name": 1, "titular2_data": 1, "s3_folder": 1},
    )

    async for process in cursor:
        stats["total"] += 1
        if limit and stats["total"] > limit:
            stats["total"] -= 1
            break

        process_id = process.get("id")
        if not process_id:
            continue

        client_name = process.get("client_name")
        if not client_name or not client_name.strip():
            stats["skipped_no_name"] += 1
            print(f"  ⚠️  Processo {process_id[:8]}... sem client_name — ignorado.")
            continue

        titular2 = process.get("titular2_data") or {}
        second_client_name = process.get("second_client_name") or titular2.get("nome") or titular2.get("name")

        result = await _restore_one(
            s3_service=s3_service,
            collection=db.processes,
            doc_id=process_id,
            client_name=client_name,
            second_client_name=second_client_name,
            existing_s3_folder=process.get("s3_folder"),
            dry_run=dry_run,
            label=f"Processo {process_id[:8]}... ({client_name})",
        )
        if result:
            stats["restored"] += 1
        else:
            stats["failed"] += 1

    return stats


async def restore_clients(db, s3_service, dry_run: bool = False, limit: int = 0) -> dict:
    """Repara mapeamentos S3 em falta na coleção `clients`.

    Cobre clientes que ainda não têm processo associado (fluxo de
    onboarding/lead), onde o mapeamento é guardado diretamente no
    documento do cliente (ver routes/public.py e onboarding_service.py).
    """
    stats = {"total": 0, "restored": 0, "skipped_no_name": 0, "failed": 0}

    query = {**_missing_mapping_query(), "is_active": {"$ne": False}}
    cursor = db.clients.find(
        query,
        {"_id": 0, "id": 1, "nome": 1, "s3_folder": 1},
    )

    async for client in cursor:
        stats["total"] += 1
        if limit and stats["total"] > limit:
            stats["total"] -= 1
            break

        client_id = client.get("id")
        if not client_id:
            continue

        client_name = client.get("nome")
        if not client_name or not client_name.strip():
            stats["skipped_no_name"] += 1
            print(f"  ⚠️  Cliente {client_id[:8]}... sem nome — ignorado.")
            continue

        result = await _restore_one(
            s3_service=s3_service,
            collection=db.clients,
            doc_id=client_id,
            client_name=client_name,
            second_client_name=None,
            existing_s3_folder=client.get("s3_folder"),
            dry_run=dry_run,
            label=f"Cliente {client_id[:8]}... ({client_name})",
        )
        if result:
            stats["restored"] += 1
        else:
            stats["failed"] += 1

    return stats


async def _restore_one(
    s3_service,
    collection,
    doc_id: str,
    client_name: str,
    second_client_name,
    existing_s3_folder,
    dry_run: bool,
    label: str,
) -> bool:
    """Resolve/cria o mapeamento S3 para um único documento e persiste-o.

    Retorna True se um mapeamento válido foi encontrado/criado (mesmo em
    dry-run, para efeitos de estatísticas), False se falhou.
    """
    if not _is_missing_mapping(existing_s3_folder):
        # Defesa extra: nunca devia acontecer dado o filtro da query,
        # mas evita qualquer escrita se o campo já for válido.
        return True

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
    # CRÍTICO: $set estrito apenas nestas 3 chaves. Nunca substitui o
    # documento inteiro nem qualquer outro campo (contacto, dados
    # pessoais, process_ids, financial_data, etc.).
    await collection.update_one(
        {"id": doc_id},
        {
            "$set": {
                "s3_folder": folder_path,
                "s3_mapping_restored_at": now,
                "s3_mapping_restored_by": "hotfix_restore_s3_mappings",
            }
        },
    )
    print(f"  ✅ {label}: pasta {action} -> {folder_path}")
    return True


def print_summary(processes_stats: dict, clients_stats: dict, dry_run: bool):
    mode = "DRY RUN (simulação)" if dry_run else "EXECUÇÃO REAL"
    print("\n" + "=" * 70)
    print(f"  HOTFIX RESTORE S3 MAPPINGS — {mode}")
    print("=" * 70)

    print("\n📁 PROCESSOS:")
    print(f"   Total com mapeamento em falta: {processes_stats['total']}")
    print(f"   Restaurados:                   {processes_stats['restored']}")
    print(f"   Ignorados (sem nome):          {processes_stats['skipped_no_name']}")
    print(f"   Falhados:                      {processes_stats['failed']}")

    print("\n📋 CLIENTES:")
    print(f"   Total com mapeamento em falta: {clients_stats['total']}")
    print(f"   Restaurados:                   {clients_stats['restored']}")
    print(f"   Ignorados (sem nome):          {clients_stats['skipped_no_name']}")
    print(f"   Falhados:                      {clients_stats['failed']}")

    total_restored = processes_stats["restored"] + clients_stats["restored"]
    total_failed = processes_stats["failed"] + clients_stats["failed"]
    print(f"\n📊 TOTAL: {total_restored} mapeamentos restaurados, {total_failed} falhas")

    if dry_run:
        print("\n⚠️  DRY RUN — nenhum dado foi alterado. Execute sem --dry-run para aplicar.")
    else:
        print("\n✅ Recuperação concluída.")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Hotfix — Restaura mapeamentos S3 em falta (PowerCell CRM)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Simular sem escrever na BD")
    parser.add_argument("--limit", type=int, default=0, help="Limitar N documentos por coleção (0 = sem limite)")
    parser.add_argument(
        "--collection",
        choices=["processes", "clients", "all"],
        default="all",
        help="Restringir a uma coleção específica (default: all)",
    )
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
        print(f"🚀 Hotfix Restore S3 Mappings — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"   BD: {db_name}")
        print(f"   Bucket S3: {s3_service.bucket_name}")
        print(f"   Dry run: {args.dry_run}")
        print(f"   Coleção: {args.collection}")
        print(f"   Limit: {args.limit or 'sem limite'}\n")

        processes_stats = {"total": 0, "restored": 0, "skipped_no_name": 0, "failed": 0}
        clients_stats = {"total": 0, "restored": 0, "skipped_no_name": 0, "failed": 0}

        if args.collection in ("processes", "all"):
            print("📁 A procurar processos com mapeamento S3 em falta...")
            processes_stats = await restore_processes(db, s3_service, dry_run=args.dry_run, limit=args.limit)

        if args.collection in ("clients", "all"):
            print("\n📋 A procurar clientes com mapeamento S3 em falta...")
            clients_stats = await restore_clients(db, s3_service, dry_run=args.dry_run, limit=args.limit)

        print_summary(processes_stats, clients_stats, args.dry_run)

    asyncio.run(_run())
    mongo_client.close()


if __name__ == "__main__":
    main()
