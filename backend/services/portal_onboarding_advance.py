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
    Gatilho assíncrono para verificar se o cliente completou o onboarding.

    Executado via asyncio.create_task() após cada upload de documento.
    Se o cliente tiver todos os documentos obrigatórios, um Process
    é criado automaticamente e os documentos são ancorados.

    PACOTE BO — Auto-Avanço e Auto-Atribuição:
    Após a verificação de onboarding, se o processo estiver em pre_registo
    e tiver todos os documentos obrigatórios, o sistema avança automaticamente
    para o estado seguinte e invoca assign_to_indexer para o processo cair
    na mesa do Indexador com menos carga. O avanço é silencioso (stealth mode)
    para não gerar ruído no histórico do cliente.

    Esta função é fire-and-forget — erros são logados mas não propagados.
    """
    try:
        from services.onboarding_service import check_onboarding_completion
        result = await check_onboarding_completion(client_id)

        if result.get("completed"):
            logger.info(
                f"[ONBOARDING] Processo criado automaticamente para "
                f"cliente {client_id}: processo #{result.get('process_number')} "
                f"({result.get('anchored_docs', 0)} docs ancorados)"
            )
            # PACOTE BO — Auto-avanço do processo recém-criado (está em pre_registo)
            process_id = result.get("process_id")
            if process_id:
                await _auto_advance_from_pre_registo(process_id, client_id)
        else:
            missing = result.get("missing", [])
            if missing:
                logger.info(
                    f"[ONBOARDING] Cliente {client_id} ainda precisa de: {missing}"
                )
            # PACOTE BO — Verificar se o cliente tem um processo EXISTENTE em
            # pre_registo com todos os docs obrigatórios (Flow 1: processo criado
            # pelo formulário público, docs ancorados diretamente ao processo).
            # O check_onboarding_completion só procura docs órfãos (sem process_id),
            # pelo que não detecta este caso. Precisamos de uma verificação separada.
            await _check_and_advance_existing_pre_registo(client_id)
    except Exception as e:
        logger.error(f"[ONBOARDING] Erro na verificação de onboarding para {client_id}: {e}")


async def _check_and_advance_existing_pre_registo(client_id: str):
    """
    PACOTE BO — Verifica se o cliente tem um processo EXISTENTE em pre_registo
    (ou status vazio/Lead) com todos os documentos obrigatórios já submetidos
    (ancorados ao processo).

    Isto cobre o Flow 1: processo criado pelo formulário público (routes/public.py)
    em pre_registo (PACOTE DB: status=None/Lead), onde os docs são ancorados
    diretamente ao processo via confirm-upload. O check_onboarding_completion não
    detecta este caso porque só procura docs órfãos (sem process_id).

    Se o processo tiver todos os docs obrigatórios, avança automaticamente.
    """
    try:
        client = await db.clients.find_one({"id": client_id}, {"_id": 0, "process_ids": 1})
        if not client:
            return
        process_ids = client.get("process_ids", [])
        if not process_ids:
            return

        # PACOTE DB — Procurar processo em pre_registo OU com status vazio (Lead)
        # (novos registos do formulário público entram com status=None)
        process = await db.processes.find_one(
            {
                "id": {"$in": process_ids},
                "status": {"$in": ["pre_registo", None]},
                "is_deleted": {"$ne": True},
            },
            {"_id": 0, "id": 1, "status": 1}
        )
        if not process:
            return  # Não há processo em pre_registo/Lead

        # Verificar se tem todos os documentos obrigatórios
        if await _has_all_required_documents(process["id"], client_id):
            await _auto_advance_from_pre_registo(process["id"], client_id)
        else:
            logger.debug(
                f"[PACOTE-BO] Processo {process['id']} em pre_registo/Lead mas ainda "
                f"faltam documentos obrigatórios. Cliente {client_id}."
            )
    except Exception as e:
        logger.warning(f"[PACOTE-BO] Erro em _check_and_advance_existing_pre_registo: {e}")


async def _has_all_required_documents(process_id: str, client_id: str) -> bool:
    """
    Verifica se o processo tem todos os documentos obrigatórios submetidos.

    Reutiliza a lógica de validação do onboarding_service (DOCUMENT_REQUIREMENT_MAP
    e REQUIREMENTS_BY_CONTRACT_TYPE) mas procura documentos ancorados AO PROCESSO
    (com process_id definido), em vez de docs órfãos.
    """
    from services.onboarding_service import (
        DOCUMENT_REQUIREMENT_MAP,
        REQUIREMENTS_BY_CONTRACT_TYPE,
        CONTRACT_TYPE_NORMALIZE,
        _detect_contract_type,
    )

    # Buscar documentos do processo (submetidos pelo cliente via portal)
    docs = await db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": ["RECEIVED", "UPLOADED", "SUBMITTED", "received", "uploaded", "submitted"]},
        },
        {"_id": 0, "category": 1, "ai_extracted_data": 1, "extracted_data": 1, "id": 1}
    ).to_list(100)

    # Recolher categorias submetidas
    uploaded_categories = set()
    for doc in docs:
        cat = doc.get("category", "")
        if isinstance(cat, dict):
            cat = cat.get("value", cat.get("label", ""))
        cat_str = str(cat).strip()
        if cat_str:
            uploaded_categories.add(cat_str)

    # Determinar tipo de contrato para saber os requisitos
    client = await db.clients.find_one({"id": client_id})
    contract_type = await _detect_contract_type(client_id, client or {}, docs)
    normalized = (
        CONTRACT_TYPE_NORMALIZE.get(contract_type.lower().strip(), contract_type.lower().strip())
        if contract_type else "default"
    )
    required_groups = REQUIREMENTS_BY_CONTRACT_TYPE.get(normalized, REQUIREMENTS_BY_CONTRACT_TYPE["default"])

    # Verificar cada grupo obrigatório
    for group_name in required_groups:
        acceptable_cats = DOCUMENT_REQUIREMENT_MAP.get(group_name, [])
        is_satisfied = any(
            acc_cat in uploaded_categories
            or acc_cat.lower() in {c.lower() for c in uploaded_categories}
            for acc_cat in acceptable_cats
        )
        if not is_satisfied:
            return False
    return True


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
