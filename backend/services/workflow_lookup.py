"""Resolução DINÂMICA de fases do workflow (PACOTE 11 — Eixo 1).

ÚNICA fonte de verdade das fases do Kanban e das suas flags de propósito:
a colecção ``workflow_statuses`` da base de dados (configurável pelo admin
em /admin/workflow-statuses). Nenhuma rota/serviço pode cravar listas de
fases em código — este módulo é o ponto central de consulta.

Funcões expostas:
- ``get_first_workflow_status()`` — 1ª fase ACTIVA por ``order`` (fallback:
  1ª fase existente) — usada como fase inicial/restauro quando não existe
  ``previous_status`` gravado.
- ``get_flagged_workflow_status_names(flag)`` — nomes das fases com uma
  flag de propósito (``trigger_finance``, ``trigger_countdown``,
  ``trigger_property_check``, ``trigger_deed_reminder``) marcada como True.
- ``get_inactive_workflow_status_names()`` — nomes das fases terminais
  (``is_active: False``).
- ``ensure_workflow_purpose_flags_backfill()`` — migração idempotente
  (uma única vez, no arranque do server) que SEMEIA as flags de propósito
  nos workflow_statuses criados antes do PACOTE 11 (que não as tinham).
  A semântica inicial fica registada NA BASE DE DADOS — a execução é
  100% dinâmica a partir daí, sem if/else com nomes de fases no fluxo.

Todas as funções degradam graciosamente (devolvem listas vazias / None)
quando a colecção está vazia ou a BD falha — nunca levantam excepção.
"""
from __future__ import annotations

import logging
from typing import Optional

from database import db

logger = logging.getLogger(__name__)

# Flags de propósito suportadas (ver models/workflow.py — PACOTE BS).
WORKFLOW_PURPOSE_FLAGS = (
    "trigger_finance",
    "trigger_countdown",
    "trigger_property_check",
    "trigger_deed_reminder",
)

# Semântica INICIAL semeada UMA única vez no backfill (arranque) para
# instalações pré-PACOTE 11. Depois de semeada, o admin edita-a livremente
# em /admin/workflow-statuses — o runtime apenas LÊ a BD.
_BACKFILL_FLAG_DEFAULTS = {
    # (nome da fase, flag) -> valor
    ("concluidos", "trigger_finance"): True,
    ("fase_bancaria", "trigger_countdown"): True,
    ("ch_aprovado", "trigger_property_check"): True,
    ("fase_escritura", "trigger_property_check"): True,
    ("escritura_agendada", "trigger_property_check"): True,
    ("escritura_agendada", "trigger_deed_reminder"): True,
    ("concluidos", "is_active"): False,
    ("desistencias", "is_active"): False,
}


async def get_first_workflow_status() -> Optional[str]:
    """Nome da 1ª fase ACTIVA do workflow (menor ``order``).

    Fallback: se não existir nenhuma fase com ``is_active`` definido,
    devolve a 1ª fase existente por ``order``. ``None`` se a colecção
    estiver vazia (ambiente sem seed) — os chamadores tratam o None.
    """
    try:
        active = await db.workflow_statuses.find_one(
            {"is_active": {"$ne": False}},
            {"_id": 0},
            sort=[("order", 1)],
        )
        if active and active.get("name"):
            return active["name"]
        any_status = await db.workflow_statuses.find_one(
            {}, {"_id": 0}, sort=[("order", 1)]
        )
        return any_status.get("name") if any_status else None
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.warning(f"[WORKFLOW-LOOKUP] Falha ao resolver 1ª fase: {e}")
        return None


async def get_flagged_workflow_status_names(flag: str) -> list[str]:
    """Nomes das fases com a flag de propósito ``flag`` marcada True."""
    if flag not in WORKFLOW_PURPOSE_FLAGS and flag != "is_active":
        return []
    try:
        docs = await db.workflow_statuses.find(
            {flag: True}, {"_id": 0, "name": 1}
        ).to_list(100)
        return [d["name"] for d in docs if d.get("name")]
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.warning(f"[WORKFLOW-LOOKUP] Falha ao resolver flag '{flag}': {e}")
        return []


async def get_inactive_workflow_status_names() -> list[str]:
    """Nomes das fases terminais (``is_active: False``)."""
    try:
        docs = await db.workflow_statuses.find(
            {"is_active": False}, {"_id": 0, "name": 1}
        ).to_list(100)
        return [d["name"] for d in docs if d.get("name")]
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.warning(f"[WORKFLOW-LOOKUP] Falha ao resolver fases inactivas: {e}")
        return []


async def ensure_workflow_purpose_flags_backfill() -> dict:
    """Migração idempotente (chamada no arranque do server).

    Semeia as flags de propósito nos ``workflow_statuses`` que AINDA NÃO
    AS TÊM (instalações pré-PACOTE 11). Idempotente: docs com a flag já
    definida nunca são tocados; corre de novo sem efeito. Devolve um
    resumo para log ({"updated": n, "skipped": m}).
    """
    updated = 0
    skipped = 0
    try:
        docs = await db.workflow_statuses.find({}, {"_id": 0}).to_list(200)
        for doc in docs:
            name = doc.get("name")
            if not name:
                continue
            set_ops = {}
            for (phase, flag), value in _BACKFILL_FLAG_DEFAULTS.items():
                if phase == name and doc.get(flag) is None:
                    set_ops[flag] = value
            if set_ops:
                await db.workflow_statuses.update_one(
                    {"id": doc.get("id", name)},
                    {"$set": set_ops},
                )
                updated += 1
            else:
                skipped += 1
        if updated:
            logger.info(
                f"[WORKFLOW-LOOKUP] Backfill de flags de propósito: "
                f"{updated} fase(s) actualizada(s), {skipped} já tinham flags."
            )
    except Exception as e:  # pragma: no cover — arranque nunca falha
        logger.warning(
            f"[WORKFLOW-LOOKUP] Backfill de flags falhou (não fatal): {e}"
        )
    return {"updated": updated, "skipped": skipped}
