"""
Helpers puros para mark-indexed / salto dinâmico de workflow.

Extraído de `routes/processes.py` (`mark_process_indexed`) para testes
unitários isolados da progressão de estado e limpeza do indexador.
"""
from __future__ import annotations

import logging
from typing import Any, Optional  # Any used by side-effect helpers

logger = logging.getLogger(__name__)


def compute_next_workflow_status(
    current_status: Optional[str],
    status_pipeline: list[str],
) -> Optional[str]:
    """
    Calcula o próximo estado na pipeline de workflow_statuses.

    - Se current está na pipeline e não é o último → seguinte
    - Se current está na pipeline e é o último → None
    - Se current NÃO está na pipeline → 1º estado (fallback) ou None se vazia
    """
    if current_status in status_pipeline:
        current_idx = status_pipeline.index(current_status)
        if current_idx < len(status_pipeline) - 1:
            next_status = status_pipeline[current_idx + 1]
            logger.info(
                f"[INDEXACAO-DYNAMIC] Salto dinâmico: '{current_status}' (pos {current_idx}) "
                f"→ '{next_status}' (pos {current_idx + 1})"
            )
            return next_status
        logger.info(
            f"[INDEXACAO-DYNAMIC] Processo já está no último estado da pipeline "
            f"('{current_status}'). Sem salto automático."
        )
        return None

    if status_pipeline:
        next_status = status_pipeline[0]
        logger.warning(
            f"[INDEXACAO-DYNAMIC] Status actual '{current_status}' não encontrado "
            f"na pipeline. Fallback para o 1º estado: '{next_status}'"
        )
        return next_status
    return None


def build_indexacao_update_set(
    user: dict,
    now: str,
    next_status: Optional[str] = None,
) -> dict[str, Any]:
    """Campos $set ao marcar indexação concluída (+ opcional salto de status)."""
    update_set: dict[str, Any] = {
        "is_indexed": True,
        "indexed_at": now,
        "indexed_by": user.get("id"),
        "indexed_by_name": user.get("name", ""),
        "assigned_indexacao_id": None,
        "indexacao_name": None,
        "updated_at": now,
        "is_data_confirmed": True,
        "data_confirmed_at": now,
        "data_confirmed_by": user.get("id"),
        "data_confirmed_by_name": user.get("name", ""),
    }
    if next_status:
        update_set["status"] = next_status
    return update_set


def collect_assigned_user_ids(process: dict) -> list[str]:
    """IDs únicos de consultores/mediadores/indexação atribuídos ao processo."""
    return list(set(filter(None, (
        (process.get("assigned_consultor_ids") or []) +
        ([process["assigned_consultor_id"]] if process.get("assigned_consultor_id") else []) +
        (process.get("assigned_mediador_ids") or []) +
        ([process["assigned_mediador_id"]] if process.get("assigned_mediador_id") else []) +
        ([process["assigned_indexacao_id"]] if process.get("assigned_indexacao_id") else [])
    ))))


def assert_mark_indexed_permission(user_role: str, all_roles: list) -> None:
    """
    Indexação / admin / ceo (effectiveRole ou additional_roles).

    Raises:
        HTTPException(403)
    """
    from fastapi import HTTPException

    role = (user_role or "").lower()
    allowed = {"indexacao", "admin", "ceo"}
    if role not in allowed and not any(r in all_roles for r in allowed):
        raise HTTPException(
            status_code=403,
            detail=(
                "Apenas utilizadores com perfil de Indexação, Admin ou CEO "
                "podem marcar a indexação como concluída."
            ),
        )


async def load_workflow_status_pipeline() -> list[str]:
    """Nomes de workflow_statuses ordenados por `order`."""
    from database import db

    all_statuses = await db.workflow_statuses.find(
        {}, {"_id": 0}
    ).sort("order", 1).to_list(100)
    return [s["name"] for s in all_statuses]


async def log_mark_indexed_history(
    process_id: str,
    user: dict,
    process: dict,
    current_status: Optional[str],
    next_status: Optional[str],
) -> None:
    """Histórico: indexação, dados confirmados, salto de estado, limpeza indexador."""
    from services.history import log_history

    try:
        await log_history(
            process_id,
            user=user,
            action="INDEXACAO_CONCLUIDA",
            field="is_indexed",
            old_value="false",
            new_value="true",
        )
        await log_history(
            process_id,
            user=user,
            action="DADOS_CONFIRMADOS_INDEXACAO",
            field="is_data_confirmed",
            old_value="false",
            new_value="true",
        )
    except Exception as e:
        logger.warning(f"Erro ao registar histórico de indexação: {e}")

    if next_status and next_status != current_status:
        try:
            # PACOTE: Auditoria Stealth — se o ACTOR real (quem marcou a
            # indexação) tem role "indexacao", este registo sintético de
            # sistema também deve ficar silencioso (track_history=False),
            # senão o salto de estado "vazava" para o histórico mesmo
            # quando as duas entradas anteriores (INDEXACAO_CONCLUIDA,
            # DADOS_CONFIRMADOS_INDEXACAO) já tinham sido silenciadas.
            system_user = {
                "id": "system",
                "name": "Sistema",
                "role": "admin",
                "track_history": user.get("role") != "indexacao",
            }
            await log_history(
                process_id,
                user=system_user,
                action=(
                    f"Salto dinâmico: {current_status} → {next_status} "
                    f"(indexação concluída)"
                ),
                field="status",
                old_value=current_status,
                new_value=next_status,
            )
        except Exception as e:
            logger.warning(f"Erro ao registar histórico de salto de estado: {e}")

    if process.get("assigned_indexacao_id"):
        try:
            system_user = {
                "id": "system",
                "name": "Sistema",
                "role": "admin",
                "track_history": user.get("role") != "indexacao",
            }
            await log_history(
                process_id,
                user=system_user,
                action="Responsabilidade do indexador removida (indexação concluída)",
                field="assigned_indexacao_id",
                old_value=process.get("indexacao_name") or process.get("assigned_indexacao_id"),
                new_value=None,
            )
        except Exception as e:
            logger.warning(f"Erro ao registar histórico de limpeza do indexador: {e}")


async def notify_assigned_users_indexing_complete(
    process: dict,
    process_id: str,
    assigned_ids: list[str],
) -> None:
    """Email + notificação in-app para assignees."""
    from database import db
    from services.notification_service import send_notification_with_preference_check

    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process_id[:8]
    notification_message = (
        f"A Indexação concluiu o tratamento documental do processo "
        f"{process_ref} — {client_name}"
    )

    for uid in assigned_ids:
        try:
            user_doc = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if not user_doc:
                continue
            await send_notification_with_preference_check(
                user_doc.get("email"),
                "Indexação Concluída",
                notification_message,
                notification_type="indexing_complete",
            )
            try:
                from services.realtime_notifications import send_realtime_notification
                await send_realtime_notification(
                    user_id=uid,
                    title="Indexação Concluída",
                    message=notification_message,
                    notification_type="indexing_complete",
                    link=f"/process/${process_id}",
                    process_id=process_id,
                )
            except Exception as notif_err:
                logger.debug(
                    f"Erro ao enviar notificação in-app para {uid}: {notif_err}"
                )
        except Exception as e:
            logger.warning(
                f"Erro ao notificar utilizador {uid} sobre indexação concluída: {e}"
            )


async def trigger_indexer_waitlist(process: dict) -> None:
    """Liberta slot do indexador e processa fila de espera."""
    import asyncio
    from database import db

    try:
        from services.process_assignment import check_waitlist_for_indexer
        assigned_indexer_id = process.get("assigned_indexacao_id")
        if assigned_indexer_id:
            asyncio.create_task(check_waitlist_for_indexer(assigned_indexer_id))
            logger.info(
                f"[INDEXACAO] Gatilho de fila de espera disparado "
                f"para indexador {assigned_indexer_id}"
            )
            return

        from services.process_assignment import process_queue_for_freed_indexer
        from services.role_query import build_deep_role_query
        indexers = await db.users.find(
            build_deep_role_query({"is_active": True}, role="indexacao"),
            {"_id": 0, "id": 1},
        ).to_list(length=100)
        for idx in indexers:
            asyncio.create_task(process_queue_for_freed_indexer(idx["id"]))
    except Exception as waitlist_err:
        logger.warning(f"[INDEXACAO] Erro ao verificar fila de espera: {waitlist_err}")


async def auto_assign_after_indexacao(
    process: dict,
    process_id: str,
    user: dict,
    current_status: Optional[str],
    process_ref: str,
) -> tuple[Any, bool]:
    """
    Após indexação: atribui SEMPRE consultor + intermediário (least-busy).

    Antes só fazia dual-assign se ainda estivesse em Lead/pre_registo;
    caso contrário só tentava consultor. O produto exige ambos.
    """
    consultant_result = None
    # Manter flag para resposta/API (Lead na altura do mark-indexed)
    is_pre_registo_transition = current_status in ("pre_registo", None)

    try:
        from services.process_assignment import dual_auto_assign_on_pre_registo_transition
        dual_result = await dual_auto_assign_on_pre_registo_transition(
            process_id=process_id,
            company_id=process.get("company_id") or process.get("company"),
            indexador_user_id=user.get("id"),
            actor_role=user.get("role"),
        )
        consultant_result = dual_result
        logger.info(
            f"[INDEXACAO-DUAL] Dupla auto-atribuição após indexação "
            f"(status_antes={current_status}): "
            f"consultor={dual_result.get('consultant_name', 'N/A')}, "
            f"intermediario={dual_result.get('mediador_name', 'N/A')}"
        )
    except Exception as dual_err:
        logger.warning(f"[INDEXACAO-DUAL] Erro na dupla auto-atribuição: {dual_err}")

    return consultant_result, is_pre_registo_transition


def build_mark_indexed_response(
    *,
    process: dict,
    process_id: str,
    process_ref: str,
    current_status: Optional[str],
    next_status: Optional[str],
    assigned_ids: list[str],
    consultant_result: Any,
    is_pre_registo_transition: bool,
) -> dict[str, Any]:
    """Payload de sucesso do endpoint mark-indexed."""
    return {
        "success": True,
        "message": f"Indexação do processo {process_ref} marcada como concluída.",
        "process_id": process_id,
        "is_indexed": True,
        "notified_users": len(assigned_ids),
        "status_transition": {
            "from": current_status,
            "to": next_status,
        } if next_status and next_status != current_status else None,
        "indexer_cleared": process.get("assigned_indexacao_id") is not None,
        "consultant_auto_assigned": consultant_result,
        "dual_auto_assigned": is_pre_registo_transition,
        "assignment": consultant_result if is_pre_registo_transition else None,
        "is_data_confirmed": True,
    }


async def run_mark_indexed_side_effects(
    *,
    process: dict,
    process_id: str,
    user: dict,
    current_status: Optional[str],
    next_status: Optional[str],
    now: str,
    broadcast_fn,
) -> dict[str, Any]:
    """
    Pós-persist: histórico, notificações, WS, waitlist, auto-assign + response.
    """
    from services.websocket_manager import WSEventType

    await log_mark_indexed_history(
        process_id, user, process, current_status, next_status,
    )

    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process_id[:8]
    assigned_ids = collect_assigned_user_ids(process)

    await notify_assigned_users_indexing_complete(process, process_id, assigned_ids)

    try:
        await broadcast_fn(
            event_type=WSEventType.PROCESS_UPDATED,
            process_id=process_id,
            client_name=client_name,
            status=next_status or current_status,
            old_status=current_status,
            updated_at=now,
        )
    except Exception as ws_err:
        logger.debug(f"Erro ao broadcast indexação concluída via WS: {ws_err}")

    logger.info(
        f"[INDEXACAO] Processo {process_ref} marcado como indexado por "
        f"{user.get('email')}. Estado: {current_status} → "
        f"{next_status or current_status}. "
        f"Indexador limpo: {process.get('assigned_indexacao_id') is not None}. "
        f"Notificações enviadas para {len(assigned_ids)} utilizadores."
    )

    await trigger_indexer_waitlist(process)

    consultant_result, is_pre_registo = await auto_assign_after_indexacao(
        process, process_id, user, current_status, process_ref,
    )

    return build_mark_indexed_response(
        process=process,
        process_id=process_id,
        process_ref=process_ref,
        current_status=current_status,
        next_status=next_status,
        assigned_ids=assigned_ids,
        consultant_result=consultant_result,
        is_pre_registo_transition=is_pre_registo,
    )


async def run_mark_process_indexed(
    process_id: str,
    user: dict,
    *,
    user_role: str,
    all_roles: list,
    broadcast_fn,
) -> dict[str, Any]:
    """Orquestra POST mark-indexed: permissão, persistência e side-effects."""
    from datetime import datetime, timezone

    from fastapi import HTTPException

    from database import db

    assert_mark_indexed_permission(user_role, all_roles)

    process = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if process.get("is_indexed") is True:
        return {
            "success": True,
            "message": "Este processo já estava marcado como indexado.",
            "process_id": process_id,
            "is_indexed": True,
        }

    current_status = process.get("status", "clientes_espera")
    status_pipeline = await load_workflow_status_pipeline()
    next_status = compute_next_workflow_status(current_status, status_pipeline)

    now = datetime.now(timezone.utc).isoformat()
    update_set = build_indexacao_update_set(user, now, next_status)

    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_set},
    )

    if result.matched_count == 0:
        logger.error(
            f"[INDEXACAO] update_one matched 0 documents para processo {process_id}"
        )
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo não encontrado durante atualização. "
                "A indexação pode não ter sido persistida."
            ),
        )
    if result.modified_count == 0 and not process.get("is_indexed"):
        logger.warning(
            f"[INDEXACAO] update_one modified 0 documents para processo "
            f"{process_id} (já estava indexado?)"
        )

    return await run_mark_indexed_side_effects(
        process=process,
        process_id=process_id,
        user=user,
        current_status=current_status,
        next_status=next_status,
        now=now,
        broadcast_fn=broadcast_fn,
    )
