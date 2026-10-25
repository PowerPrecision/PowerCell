"""Marcar como indexado + fecho em segundo plano (Lote 12, Fase 3).

«MARCAR COMO INDEXADO» NUNCA É BLOQUEADO
----------------------------------------
Decisão da direcção: nada do módulo Index bloqueia a indexação — só avisa. Esta função
não pergunta pelo estado da IA, por campos em falta nem por alertas abertos. As únicas
recusas são as de sempre (permissão do perfil, processo inexistente/fora da rede/fechado).
Os NIFs das entidades patronais são um pedido OPCIONAL: sem eles marca-se na mesma, e um
NIF que não passa o dígito de controlo fica a rever em vez de recusar o pedido.

O FECHO (`INDEX_FINALIZE`)
--------------------------
Depois de a indexação ficar gravada (e a pasta `Index` libertada, e o motor financeiro
lançado — tudo em `process_indexing.run_mark_indexed_side_effects`) corre UM job em
background por processo (índice único parcial, como a análise):

  1. analisa o que falta (impressão digital: o que já foi analisado não volta ao modelo);
  2. sanitiza os PDFs que o Index carregou (Fase 5; só se ligada);
  3. notifica no fim, com números e nunca nomes.

Falhar um passo regista-se e segue para o seguinte; o job nunca desfaz a indexação.
A IA automática só corre aqui, nos uploads posteriores à indexação e a pedido (botões),
nunca como condição de nada.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db
from models.task_log import TaskStatus, TaskType
from services import index_jobs
from services import index_store as store
from services.background_tasks import spawn_background_task
from services.document_ai_trigger import ia_da_entrada_ligada
from services.index_access import e_upload_do_index
from services.index_status import exigir_titularidade
from services.task_log_service import TaskLogService

logger = logging.getLogger(__name__)


# ====================================================================
# O FECHO EM BACKGROUND
# ====================================================================
async def correr_finalizacao(task_id: str, process_id: str, user: Optional[dict], *, gatilho: str) -> dict[str, Any]:
    """O trabalho do job. Termina SEMPRE o TaskLog e liberta a chave; nunca levanta."""
    try:
        await TaskLogService.update_task(task_id, status=TaskStatus.PROCESSING, progress=1,
                                         progress_message="A tratar os documentos do processo…")
        process = await db.processes.find_one({"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0})
        if not process:
            await TaskLogService.update_task(task_id, status=TaskStatus.FAILED, error_message="Processo não encontrado.")
            return {}

        async def progresso(pct: int, msg: str) -> None:
            await TaskLogService.update_task(task_id, progress=max(1, min(90, pct)), progress_message=msg)

        resumo: dict[str, Any] = {}
        try:
            resumo = await index_jobs.analisar_e_concluir(
                process, force=False, gatilho=gatilho, user=user, progresso=progresso)
        except Exception:  # noqa: BLE001 — a análise falhar não impede o resto
            logger.exception("[INDEX] Análise do fecho falhou no processo %s", process_id)

        resumo.update(await _sanitizar_sem_falhar(process, user))

        await TaskLogService.update_task(task_id, status=TaskStatus.COMPLETED, progress=100,
                                         progress_message="Documentos tratados.", result_data=resumo)
        await index_jobs.notificar_fim(process, (user or {}).get("id"), resumo)
        return resumo
    except Exception:  # noqa: BLE001
        logger.exception("[INDEX] O fecho do processo %s falhou", process_id)
        try:
            await TaskLogService.update_task(task_id, status=TaskStatus.FAILED,
                                             error_message="O tratamento dos documentos não terminou. A indexação mantém-se.")
        except Exception:  # noqa: BLE001
            pass
        return {}
    finally:
        await index_jobs.libertar_job(task_id)


async def _sanitizar_sem_falhar(process: dict, user: Optional[dict]) -> dict[str, Any]:
    """Passo de sanitização (Fase 5). Sem módulo/interruptor ligado não faz nada; nunca levanta."""
    try:
        from services import index_sanitize

        return await index_sanitize.sanitizar_do_fecho(process, user)
    except ImportError:
        return {}
    except Exception:  # noqa: BLE001
        logger.exception("[INDEX] Sanitização do processo %s falhou", process.get("id"))
        return {"sanitizacao_falhou": True}


async def agendar_finalizacao(process: dict, user: Optional[dict], *, gatilho: str = "automatico") -> dict[str, Any]:
    """Cria o job do fecho e devolve JÁ. `{"agendado", "task_id"}`. Nunca levanta."""
    if not ia_da_entrada_ligada():
        return {"agendado": False, "task_id": None, "motivo": "ia_desligada"}
    try:
        task_id, existente = await index_jobs.reivindicar_job(
            process["id"], TaskType.INDEX_FINALIZE, (user or {}).get("id") or "system",
            metadata={"gatilho": gatilho},
        )
        if task_id is None:
            return {"agendado": False, "task_id": existente, "motivo": "ja_a_correr"}
        spawn_background_task(
            correr_finalizacao(task_id, process["id"], user, gatilho=gatilho),
            name=f"index-fecho-{process['id']}",
        )
        return {"agendado": True, "task_id": task_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Fecho do processo %s não agendado: %s", process.get("id"), type(exc).__name__)
        return {"agendado": False, "task_id": None, "motivo": "erro"}


async def agendar_analise_pos_indexacao(
    process_id: Optional[str],
    user: Optional[dict],
    *,
    s3_path: Optional[str] = None,
    filename: Optional[str] = None,
    client_name: str = "",
    categoria: Optional[str] = None,
) -> None:
    """Um upload a um processo JÁ indexado: regista o ficheiro e lança a análise.

    O ficheiro de um processo indexado NÃO passa pela fila da IA (desvio inteligente, poupança
    de custos), logo não tinha registo em `document_metadata` — e sem registo a análise não o
    via. Cria-se um registo mínimo, sem `in_index_queue`. A IA só é chamada para tipos
    analisáveis (recibo, extrato, identificação) ainda não analisados. Nunca levanta e nunca
    falha o upload.
    """
    if not process_id or not ia_da_entrada_ligada():
        return
    try:
        if s3_path:
            await _garantir_registo(process_id, user, s3_path, filename, client_name, categoria)
        await index_jobs.iniciar_analise(process_id, user, force=False, gatilho="automatico")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Análise pós-indexação de %s não agendada: %s", process_id, type(exc).__name__)


async def _garantir_registo(
    process_id: str, user: Optional[dict], s3_path: str, filename: Optional[str],
    client_name: str, categoria: Optional[str],
) -> None:
    from datetime import datetime, timezone
    import uuid

    existente = await db.document_metadata.find_one({"s3_path": s3_path}, {"_id": 0, "id": 1})
    agora = datetime.now(timezone.utc).isoformat()
    if existente:
        await db.document_metadata.update_one(
            {"s3_path": s3_path}, {"$set": {"uploaded_by_index": e_upload_do_index(user), "updated_at": agora}})
        return
    await db.document_metadata.insert_one({
        "id": str(uuid.uuid4()), "process_id": process_id, "client_name": client_name,
        "s3_path": s3_path, "filename": filename or s3_path.rsplit("/", 1)[-1],
        "category": categoria, "is_categorized": False, "in_index_queue": False,
        "uploaded_by_index": e_upload_do_index(user), "created_at": agora, "updated_at": agora,
    })


# ====================================================================
# MARCAR COMO INDEXADO
# ====================================================================
async def aplicar_nifs_confirmados(
    process_id: str, network_id: Optional[str], employers: list[dict]
) -> dict[str, Any]:
    """Aplica os NIFs que o Index confirmou no diálogo. NUNCA recusa o pedido: o que não se
    aplica (sem metadados ainda, NIF sem forma) volta em `rejected` e a indexação segue."""
    aplicados, recusados = 0, []
    for item in employers or []:
        job_id, nif = (item or {}).get("job_id"), (item or {}).get("nif")
        try:
            await store.editar_trabalho(process_id, network_id, str(job_id), {"employer_nif": nif})
            aplicados += 1
        except store.EdicaoInvalida as exc:
            recusados.append({"job_id": job_id, "reason": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("[INDEX] NIF não aplicado (%s)", type(exc).__name__)
            recusados.append({"job_id": job_id, "reason": "Não foi possível aplicar."})
    return {"applied": aplicados, "rejected": recusados}


async def run_mark_indexed(
    process_id: str,
    user: dict,
    *,
    user_role: str,
    all_roles: list,
    broadcast_fn,
    employers: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """`POST /index/processes/{id}/mark-indexed` — o mesmo fluxo canónico do `mark-indexed` do CRM."""
    from services.process_indexing import assert_mark_indexed_permission, run_mark_process_indexed

    # a permissão vem ANTES de tocar nos metadados (um 403 não pode ter escrito nada)
    assert_mark_indexed_permission(user_role, all_roles)
    # ... e a titularidade também: o processo de um colega não recebe NIFs de quem não o pode indexar
    proc = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0, "network_id": 1, "assigned_indexacao_id": 1})
    exigir_titularidade(proc or {}, user, user_role)
    resultado_nifs: dict[str, Any] = {"applied": 0, "rejected": []}
    if employers:
        resultado_nifs = await aplicar_nifs_confirmados(process_id, (proc or {}).get("network_id"), employers)
    resposta = await run_mark_process_indexed(
        process_id, user, user_role=user_role, all_roles=all_roles, broadcast_fn=broadcast_fn)
    resposta["employers"] = resultado_nifs
    return resposta
