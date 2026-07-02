"""
====================================================================
SEED FIXED: Notas do Consultor directamente no campo `notes` do processo
====================================================================
Pacote BE — Script que faz $set em process.notes (não em activities).

Isto garante que a coluna "Notas do Consultor" da tabela de processos
(que lê process.notes directamente) tem conteúdo para validar a UI.

EXECUÇÃO:
  Render Shell: cd /app && python -m scripts.seed_notes_fixed
  Local (dev):  cd backend && python -m scripts.seed_notes_fixed

  Flags:
    --dry-run   Mostra o que seria feito sem alterar a BD
====================================================================
"""
import asyncio
import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_notes_fixed")

NOTE_TEXT = "Nota inserida automaticamente para QA do novo layout e tabela."


async def main():
    parser = argparse.ArgumentParser(description="Seed de notes directamente no campo do processo")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem alterar a BD")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("SEED FIXED: Notas do Consultor (Pacote BE)")
    logger.info("=" * 60)
    if args.dry_run:
        logger.info("⚠️  MODO DRY-RUN — nenhuma alteração será feita")
    logger.info("")

    # Procurar todos os processos ativos (não eliminados)
    query = {"is_deleted": {"$ne": True}}
    cursor = db.processes.find(query, {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, "notes": 1})
    processes = await cursor.to_list(2000)

    logger.info(f"Processos ativos encontrados: {len(processes)}")

    updated = 0
    skipped = 0

    for p in processes:
        pid = p.get("id")
        if not pid:
            skipped += 1
            continue

        # Se já tem notes não vazias, pular
        existing_notes = p.get("notes")
        if existing_notes and isinstance(existing_notes, str) and existing_notes.strip():
            skipped += 1
            continue

        if args.dry_run:
            logger.info(f"[dry-run] Atualizaria processo #{p.get('process_number', '?')} ({p.get('client_name', '?')[:30]})")
            updated += 1
            continue

        try:
            result = await db.processes.update_one(
                {"id": pid},
                {"$set": {"notes": NOTE_TEXT}}
            )
            if result.modified_count > 0:
                updated += 1
        except Exception as e:
            logger.warning(f"Erro ao atualizar processo {pid}: {e}")
            skipped += 1

    logger.info("")
    logger.info(f"Resultado: {updated} processos atualizados, {skipped} ignorados (já tinham notes ou sem ID)")

    if not args.dry_run and updated > 0:
        logger.info("")
        logger.info("✅ Notas inseridas directamente no campo `notes` de cada processo.")
        logger.info("   A coluna 'Notas do Consultor' na tabela vai agora mostrar o texto.")
        logger.info("   (Necessário redeploy do backend para a projection incluir o campo notes)")

    logger.info("")
    logger.info("✅ Seed concluído.")


if __name__ == "__main__":
    asyncio.run(main())
