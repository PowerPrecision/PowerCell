"""GDPR mutate/export endpoints (anonymize, batch, export).

Extraído de `routes/gdpr.py`.
Do **not** overwrite services/gdpr.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.gdpr import (
    anonymize_process_data,
    anonymize_user_data,
    run_anonymization_batch,
    export_personal_data,
    gdpr_config,
)
from services.gdpr_api_models import AnonymizeRequest, BatchAnonymizeRequest
from services.tenant_network import processo_no_ambito, resolve_tenant_scope, PROJECCAO_DO_CARIMBO
from services.user_management_scope import carregar_utilizador_gerivel


async def _exigir_processo_no_ambito(process_id: str, user: dict) -> None:
    """404 se o processo não é da rede de quem actua (nem convidada).

    `require_roles` autoriza o VERBO; sem esta verificação, o CEO de uma
    empresa anonimizava ou exportava os dados pessoais de um cliente de
    qualquer outra pelo id — uma operação irreversível (a anonimização).
    """
    processo = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, "id": 1, "partner_network_ids": 1, **PROJECCAO_DO_CARIMBO},
    )
    scope = await resolve_tenant_scope(user)
    if not processo or not processo_no_ambito(processo, scope):
        raise HTTPException(404, "Processo não encontrado")

logger = logging.getLogger(__name__)


async def run_anonymize_single(request: AnonymizeRequest, current_user: dict):
    if not request.process_id and not request.user_id:
        raise HTTPException(400, "Especifique process_id ou user_id")

    results = {}

    # A fronteira vem ANTES de qualquer escrita (e do dry-run): o resultado
    # de uma simulação sobre um processo alheio já confirma que ele existe.
    if request.process_id:
        await _exigir_processo_no_ambito(request.process_id, current_user)
    if request.user_id:
        await carregar_utilizador_gerivel(
            request.user_id, current_user, projeccao={"_id": 0, "id": 1, "role": 1},
        )

    if request.process_id:
        results["process"] = await anonymize_process_data(
            request.process_id,
            request.dry_run
        )

    if request.user_id:
        results["user"] = await anonymize_user_data(
            request.user_id,
            request.dry_run
        )

    if not request.dry_run:
        await db.gdpr_audit.insert_one({
            "action": "manual_anonymize",
            "process_id": request.process_id,
            "user_id": request.user_id,
            "performed_by": current_user.get("id"),
            "performed_by_email": current_user.get("email"),
            "timestamp": datetime.now(timezone.utc)
        })

    return {
        "success": True,
        "dry_run": request.dry_run,
        "results": results
    }


async def run_anonymize_batch(request: BatchAnonymizeRequest, current_user: dict):
    if not request.dry_run:
        logger.warning(
            f"[GDPR] Anonimização em lote iniciada por {current_user.get('email')} "
            f"(batch_size={request.batch_size})"
        )

    result = await run_anonymization_batch(
        retention_days=request.retention_days,
        dry_run=request.dry_run,
        batch_size=request.batch_size
    )

    await db.gdpr_audit.insert_one({
        "action": "batch_anonymize",
        "dry_run": request.dry_run,
        "batch_size": request.batch_size,
        "retention_days": request.retention_days or gdpr_config.retention_period_days,
        "processed": result.get("processed", 0),
        "succeeded": result.get("succeeded", 0),
        "performed_by": current_user.get("id"),
        "performed_by_email": current_user.get("email"),
        "timestamp": datetime.now(timezone.utc)
    })

    return {
        "success": True,
        **result
    }


async def run_export_data(process_id: str, current_user: dict):
    await _exigir_processo_no_ambito(process_id, current_user)
    data = await export_personal_data(process_id=process_id)

    if not data.get("data"):
        raise HTTPException(404, "Processo não encontrado")

    return {
        "success": True,
        **data
    }
