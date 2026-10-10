"""
Reabrir um processo fechado — a única saída do modo de leitura.

Um processo em fase terminal não se altera (`process_closed_guard`). Para
mexer, a equipa reabre-o para uma fase ACTIVA: é um movimento de fase como o
do Kanban (mesmos efeitos: relógio de fases, atribuição da fase, histórico,
Portal a reabrir sozinho), com três diferenças deliberadas:

  * só se reabre o que está FECHADO (reabrir um aberto é um 400, não um
    movimento silencioso que dispara automações);
  * o destino tem de ser uma fase ACTIVA do motor — «reabrir» para outra fase
    terminal seria mudar o motivo do fecho, que é o movimento do Kanban;
  * o destino é obrigatório: não se adivinha a fase anterior (o histórico de
    fases pode não a ter, e uma fase errada põe o processo no sítio errado).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from database import db
from services.process_closed_guard import processo_esta_fechado
from services.process_kanban_move import run_move_process_kanban
from services.workflow_phases import carregar_fases, nomes_activos

logger = logging.getLogger(__name__)


async def run_reopen_process(
    process_id: str,
    new_status: str,
    user: dict,
    *,
    can_view_fn,
    inject_cdc_fn,
    broadcast_fn,
    create_finance_snapshot_fn,
) -> dict[str, Any]:
    """Reabre `process_id` para a fase activa `new_status`."""
    processo = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    if not can_view_fn(user, processo):
        raise HTTPException(
            status_code=403, detail="Sem permissão para reabrir este processo",
        )
    if not await processo_esta_fechado(processo):
        raise HTTPException(status_code=400, detail="O processo já está aberto.")

    activas = nomes_activos(await carregar_fases())
    if new_status not in activas:
        raise HTTPException(
            status_code=400,
            detail="Escolha uma fase activa para reabrir o processo.",
        )

    logger.info(
        "[REABRIR] %s reabre o processo %s: %s → %s",
        (user or {}).get("id"), process_id, processo.get("status"), new_status,
    )
    resultado = await run_move_process_kanban(
        process_id,
        new_status,
        user,
        deed_date=None,
        can_view_fn=can_view_fn,
        inject_cdc_fn=inject_cdc_fn,
        broadcast_fn=broadcast_fn,
        create_finance_snapshot_fn=create_finance_snapshot_fn,
    )
    return {**resultado, "message": "Processo reaberto", "reopened": True}
