"""Auto-advance / onboarding após uploads no Portal.

Extraído de `routes/portal.py` (Pacote BO).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from database import db

logger = logging.getLogger(__name__)


async def _trigger_onboarding_check(client_id: str):
    """
    Após upload no portal: se checklist SystemConfig completa → criar processo
    (com titular2 do cliente) + avançar para Index.
    """
    try:
        from services.onboarding_mandatory_config import (
            is_mandatory_checklist_complete,
            create_process_from_client_onboarding,
        )

        # 1) Cliente ainda sem processo — criar quando checklist completa
        client = await db.clients.find_one(
            {"id": client_id}, {"_id": 0, "process_ids": 1}
        )
        process_ids = (client or {}).get("process_ids") or []

        if not process_ids:
            if await is_mandatory_checklist_complete(client_id=client_id):
                result = await create_process_from_client_onboarding(client_id)
                if result.get("completed") and result.get("process_id"):
                    logger.info(
                        f"[ONBOARDING-CFG] Processo criado para cliente {client_id}: "
                        f"{result.get('process_id')} (titular2={result.get('has_titular2')})"
                    )
                    await _auto_advance_from_pre_registo(
                        result["process_id"], client_id
                    )
            else:
                logger.info(
                    f"[ONBOARDING-CFG] Cliente {client_id}: checklist ainda incompleta"
                )
            return

        # 2) Já tem processo (legado Lead/pre_registo) — avançar se checklist OK
        await _check_and_advance_existing_pre_registo(client_id)
    except Exception as e:
        logger.error(f"[ONBOARDING] Erro na verificação de onboarding para {client_id}: {e}")


async def _check_and_advance_existing_pre_registo(client_id: str):
    """Avança Lead/pre_registo quando checklist SystemConfig estiver completa."""
    try:
        from services.onboarding_mandatory_config import is_mandatory_checklist_complete

        client = await db.clients.find_one({"id": client_id}, {"_id": 0, "process_ids": 1})
        if not client:
            return
        process_ids = client.get("process_ids", [])
        if not process_ids:
            return

        process = await db.processes.find_one(
            {
                "id": {"$in": process_ids},
                "status": {"$in": ["pre_registo", None]},
                "is_deleted": {"$ne": True},
            },
            {"_id": 0, "id": 1, "status": 1},
        )
        if not process:
            return

        complete = await is_mandatory_checklist_complete(process_id=process["id"])
        if not complete:
            # Fallback: checklist ainda no client_id (antes de ancorar)
            complete = await is_mandatory_checklist_complete(client_id=client_id)
        if complete:
            await _auto_advance_from_pre_registo(process["id"], client_id)
        else:
            logger.debug(
                f"[PACOTE-BO] Processo {process['id']} em Lead mas checklist incompleta"
            )
    except Exception as e:
        logger.warning(f"[PACOTE-BO] Erro em _check_and_advance_existing_pre_registo: {e}")


async def _has_all_required_documents(process_id: str, client_id: str) -> bool:
    """Compat: delega à checklist SystemConfig (sem hardcode por tipo de contrato)."""
    from services.onboarding_mandatory_config import is_mandatory_checklist_complete

    if await is_mandatory_checklist_complete(process_id=process_id):
        return True
    return await is_mandatory_checklist_complete(client_id=client_id)

async def _auto_advance_from_pre_registo(process_id: str, client_id: str):
    """
    PACOTE BO + DB — Auto-avanço do pre_registo/Lead para a 1ª fase REAL do
    Kanban + assign_to_indexer.

    1. Verifica que o processo está em pre_registo OU com status vazio (Lead).
    2. Calcula a 1ª fase REAL do Kanban (1º status do workflow_statuses que
       NÃO seja pre_registo, fila_espera, nem terminal). Em vez do "próximo
       estado" da pipeline, vai diretamente para a 1ª fase ativa.
    3. Avança o processo para essa fase.
    4. Invoca assign_to_indexer(process_id, update_status=False) para o processo
       cair na mesa do Indexador com menos carga, SEM forçar fase_documental.
    5. O avanço é SILENCIOSO (stealth mode) — usa um system user com
       track_history=False para não gerar ruído no histórico do cliente.
       O assign_to_indexer gera os seus próprios logs de sistema (indexer
       assignment), que são ações de sistema legítimas, não do cliente.
    """
    from services.process_assignment import assign_to_indexer
    from services.history import log_history

    # ── 1. Verificar que o processo está em pre_registo/Lead ──
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "status": 1, "client_name": 1})
    if not process:
        logger.warning(f"[PACOTE-BO] Processo {process_id} não encontrado para auto-avanço.")
        return

    current_status = process.get("status")
    # PACOTE DB — aceitar pre_registo (legacy) OU None (novos registos)
    if current_status not in ("pre_registo", None):
        logger.debug(
            f"[PACOTE-BO] Processo {process_id} não está em pre_registo/Lead "
            f"(status={current_status}). Auto-avanço cancelado."
        )
        return

    # ── 2. Calcular a 1ª fase REAL do Kanban ──
    # Excluir pre_registo (Lead), fila_espera e terminais — queremos a 1ª fase
    # ativa do Kanban onde o processo deve aparecer após submeter os docs.
    EXCLUDED_FROM_KANBAN_START = {
        "pre_registo", "fila_espera",
        "concluido", "arquivo", "perdido", "desistencias",
        # variants legacy
        "concluidos", "desistido", "cancelado", "recusado",
    }
    all_statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)

    target_status = None
    for s in all_statuses:
        name = s.get("name", "")
        if name and name not in EXCLUDED_FROM_KANBAN_START:
            target_status = name
            break

    # Fallback: se TODOS os statuses estiverem excluídos (config inválida),
    # usar o 1º status da pipeline que não seja pre_registo.
    if not target_status:
        for s in all_statuses:
            name = s.get("name", "")
            if name and name != "pre_registo":
                target_status = name
                break

    if not target_status:
        logger.warning(
            f"[PACOTE-BO] Sem fases reais no workflow_statuses para auto-avanço. "
            f"Processo {process_id} mantém status={current_status}."
        )
        return

    # ── 3. Avançar status (STEALTH — track_history=False para não gerar ruído) ──
    now = datetime.now(timezone.utc).isoformat()
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"status": target_status, "workflow_step": target_status, "updated_at": now}}
    )

    # Log silencioso: o system user tem track_history=False, pelo que o
    # _is_stealth_user (Pacote BJ) retorna True e log_history retorna imediatamente
    # sem escrever na coleção history. Isto garante que o auto-avanço não
    # gera ruído no histórico do cliente.
    stealth_system_user = {
        "id": "system",
        "name": "Sistema (Auto-avanço Portal)",
        "role": "system",
        "track_history": False,  # PACOTE BJ — silencia o log
    }
    try:
        await log_history(
            process_id=process_id,
            user=stealth_system_user,
            action=f"Auto-avanço: {current_status or 'Lead'} → {target_status} (documentos obrigatórios submetidos pelo cliente)",
            field="status",
            old_value=current_status or "",
            new_value=target_status,
        )
    except Exception as e:
        logger.warning(f"[PACOTE-BO] Erro ao registar histórico (stealth): {e}")

    client_name = process.get("client_name", "Cliente")
    logger.info(
        f"[PACOTE-BO] Processo {process_id} ({client_name}) avançado de "
        f"{current_status or 'Lead'} → {target_status}. A invocar assign_to_indexer..."
    )

    # ── 4. Invocar assign_to_indexer (PACOTE DB: update_status=False) ──
    # assign_to_indexer atribui o processo ao indexador com menor carga.
    # PACOTE DB: passamos update_status=False para NÃO forçar fase_documental
    # nem fila_espera — o processo fica na 1ª fase real (target_status) e o
    # indexador é atribuído se disponível.
    try:
        success, data, msg = await assign_to_indexer(process_id, update_status=False)
        logger.info(
            f"[PACOTE-BO] assign_to_indexer para processo {process_id}: "
            f"success={success}, data={data}, msg={msg}"
        )
    except Exception as e:
        logger.warning(
            f"[PACOTE-BO] Erro em assign_to_indexer para processo {process_id}: {e}. "
            f"O processo ficou em {target_status} mas sem indexador atribuído."
        )
