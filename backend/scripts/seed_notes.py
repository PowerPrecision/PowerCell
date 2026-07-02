"""
====================================================================
SEED: Notas do Consultor em processos ativos
====================================================================
Pacote BB — Script para popular notas/atividades em processos ativos.

Cria uma atividade (comment) realista em cada processo ativo para
validar a coluna "Notas do Consultor" (Pacote AP) e a Timeline
(Pacote AQ) no frontend.

EXECUÇÃO:
  Local (dev):  cd backend && python -m scripts.seed_notes
  Render Shell: cd /app && python -m scripts.seed_notes

  Flags:
    --dry-run   Mostra o que seria feito sem alterar a BD
    --limit N   Processa apenas os primeiros N processos (default: todos)
====================================================================
"""
import asyncio
import argparse
import logging
import sys
import os
import random
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_notes")

# Notas realistas para Consultores de Crédito Habitação
SAMPLE_NOTES = [
    "Cliente confirmou entrega do IRS. Aguardamos avaliação bancária.",
    "Contactado por telefone — cliente vai enviar comprovativo de rendimento esta semana.",
    "Aguarda resposta do BCP sobre taxa fixa. Proposta submetida há 3 dias.",
    "Cliente pediu reunião para discutir spread. Agendar para próxima semana.",
    "Documentação completa. Processo pronto para submissão ao banco.",
    "Cliente tem 2 propostas de imóvel. A decidir qual avançar.",
    "Banco pediu avaliação independente. Já foi solicitada à empresa parceira.",
    "Cliente trabalha no estrangeiro — comprovativos em inglês, em tradução.",
    "Aguarda CPCV assinado pelo vendedor. Prometido para esta sexta.",
    "Cliente preocupado com prazos. Garantido acompanhamento semanal.",
    "Processo em fase de pré-aprovação. Banco solicitou extratos dos últimos 3 meses.",
    "Cliente vai mudar de banco atual — pedido transferência de conta.",
    "2º titular sem NIF válido. Cliente vai regularizar no portal das finanças.",
    "Avaliação do imóvel concluída: €235.000. Valor de compra: €220.000. LTV favorável.",
    "Cliente pediu simulação com taxa mista (3 anos fixa + variável). Enviada.",
    "Aguarda certidão permanente do registo predial. Pedido via portal.",
    "Cliente reune com contabilista para preparar mapa de créditos.",
    "Spread negociado: 0,85%. Cliente satisfeito, aguarda formalização.",
    "Processo parado há 15 dias — cliente em férias. Retomar contacto na próxima semana.",
    "Cliente pediu para adiar escritura para janeiro (motivos fiscais).",
]

# Utilizadores para atribuir as notas (procura admin/consultor)
PREFERRED_ROLES = ["admin", "ceo", "consultor", "intermediario", "diretor", "administrativo"]


async def get_sample_user():
    """Procura um utilizador staff para atribuir as notas."""
    user = await db.users.find_one(
        {"role": {"$in": PREFERRED_ROLES}, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    )
    if not user:
        user = await db.users.find_one({}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1})
    return user


async def main():
    parser = argparse.ArgumentParser(description="Seed de notas do consultor em processos ativos")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem alterar a BD")
    parser.add_argument("--limit", type=int, default=0, help="Processar apenas N processos (0 = todos)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("SEED: Notas do Consultor (Pacote BB)")
    logger.info("=" * 60)
    if args.dry_run:
        logger.info("⚠️  MODO DRY-RUN — nenhuma alteração será feita")
    logger.info("")

    # 1. Procurar utilizador staff
    sample_user = await get_sample_user()
    if not sample_user:
        logger.error("Nenhum utilizador encontrado. Abortar.")
        return

    logger.info(f"Utilizador para atribuição: {sample_user.get('name')} ({sample_user.get('role')})")
    logger.info("")

    # 2. Procurar processos ativos (não eliminados, não terminais)
    active_filter = {
        "is_deleted": {"$ne": True},
        "status": {"$nin": ["concluidos", "desistencias", "eliminado", "eliminados"]},
    }

    cursor = db.processes.find(
        active_filter,
        {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, "status": 1}
    )

    if args.limit > 0:
        processes = await cursor.to_list(args.limit)
    else:
        processes = await cursor.to_list(1000)

    logger.info(f"Processos ativos encontrados: {len(processes)}")
    logger.info("")

    # 3. Para cada processo, criar uma atividade/nota
    created = 0
    skipped = 0

    for p in processes:
        process_id = p.get("id")
        if not process_id:
            skipped += 1
            continue

        # Verificar se já tem atividades (não duplicar)
        existing = await db.activities.count_documents({
            "process_id": process_id,
            "user_id": sample_user["id"],
        })

        if existing > 0:
            skipped += 1
            continue

        # Escolher nota aleatória
        note_text = random.choice(SAMPLE_NOTES)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Criar documento de atividade
        activity_doc = {
            "id": f"seed-note-{process_id[:8]}-{random.randint(1000, 9999)}",
            "process_id": process_id,
            "user_id": sample_user["id"],
            "user_name": sample_user.get("name", "Sistema"),
            "comment": note_text,
            "type": "comment",
            "created_at": now_iso,
            "source": "seed_script",
        }

        if args.dry_run:
            logger.info(f"[dry-run] Criaria nota para processo #{p.get('process_number', '?')} ({p.get('client_name', '?')[:30]}): {note_text[:60]}...")
            created += 1
            continue

        try:
            await db.activities.insert_one(activity_doc)
            created += 1
        except Exception as e:
            logger.warning(f"Erro ao criar nota para {process_id}: {e}")
            skipped += 1

    logger.info("")
    logger.info(f"Resultado: {created} notas criadas, {skipped} processos ignorados (já tinham notas ou sem ID)")

    if not args.dry_run and created > 0:
        logger.info("")
        logger.info("✅ Notas criadas com sucesso. A coluna 'Notas do Consultor' na tabela")
        logger.info("   de processos e a Timeline nos detalhes do processo vão mostrar estas notas.")

    logger.info("")
    logger.info("✅ Seed concluído.")


if __name__ == "__main__":
    asyncio.run(main())
