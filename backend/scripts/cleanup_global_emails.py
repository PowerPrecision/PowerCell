"""
====================================================================
CLEANUP - Remover emails legados do sync global "geral"
====================================================================

Este script marca como ARCHIVED todos os emails que NÃO têm
created_by nem synced_for_user — ou seja, emails descarregados
pelo antigo worker de sync global da conta "geral".

APÓS executar, estes emails deixarão de aparecer nos filtros
de qualquer utilizador (incluindo admins, já que o filtro
is_archived=True é aplicado no webmail).

Utilização:
    cd backend && python -m scripts.cleanup_global_emails

Flags:
    --dry-run   Mostra o que seria apagado sem executar
    --delete    Em vez de arquivar, APAGA permanentemente
====================================================================
"""

import asyncio
import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from database import db

    parser = argparse.ArgumentParser(description="Cleanup emails legados do sync global")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria afetado sem executar")
    parser.add_argument("--delete", action="store_true", help="Apaga permanentemente em vez de arquivar")
    args = parser.parse_args()

    # Query: emails sem created_by E sem synced_for_user
    # Estes são os emails do antigo sync global "geral"
    orphan_query = {
        "$and": [
            {"created_by": None},
            {"synced_for_user": {"$exists": False}},
            {"source": {"$in": ["webmail_sync", "imap_sync"]}},
        ]
    }

    # Contar
    total_count = await db.emails.count_documents(orphan_query)
    print(f"🔍 Encontrados {total_count} emails órfãos (sem user_id, do sync global)")

    if total_count == 0:
        print("✅ Nenhum email para limpar.")
        return

    if args.dry_run:
        print(f"\n📋 DRY RUN: {total_count} emails seriam {'APAGADOS' if args.delete else 'ARQUIVADOS'}")
        # Mostrar amostra
        sample = await db.emails.find(orphan_query, {"_id": 0, "id": 1, "subject": 1, "from_email": 1, "account": 1}).limit(5).to_list(5)
        for doc in sample:
            print(f"   - [{doc.get('account', '?')}] {doc.get('subject', 'Sem assunto')[:60]} (de: {doc.get('from_email', '?')})")
        return

    if args.delete:
        result = await db.emails.delete_many(orphan_query)
        print(f"🗑️ {result.deleted_count} emails APAGADOS permanentemente")
    else:
        result = await db.emails.update_many(
            orphan_query,
            {"$set": {
                "is_archived": True,
                "archive_reason": "global_sync_cleanup",
                "archived_at": asyncio.get_event_loop().time() if False else __import__('datetime').datetime.utcnow().isoformat(),
            }}
        )
        print(f"📦 {result.modified_count} emails ARQUIVADOS (is_archived=True)")

    print("\n✅ Cleanup concluído com sucesso.")


if __name__ == "__main__":
    asyncio.run(main())
