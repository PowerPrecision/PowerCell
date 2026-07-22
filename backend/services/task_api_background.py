"""Background / async job tasks surfaced on the /tasks router.

Extraído de `routes/tasks.py`. Uses `task_api_*` to avoid colliding with
`task_queue.py` / `task_log_service.py`. Reads `background_jobs` collection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def run_get_active_background_tasks(current_user: dict):
    """
    Buscar tarefas assíncronas ativas do utilizador actual.

    Usado pelo TasksContext (frontend polling) para mostrar
    notificações de jobs em execução (PDF, IA, emails, etc.).

    Retorna:
    - tasks: Lista de jobs activos/concluídos não confirmados
    - active_count: Número de jobs em progresso
    - completed_unacknowledged: Jobs concluídos sem acknowledgement

    NOTA: A coleção background_jobs usa valores de status inconsistentes
    consoante o serviço que cria o job:
    - create_background_job_db (ai_bulk): "running", "success", "failed", "paused", "pending"
    - BackgroundJobService (services/background_jobs.py): "pending", "processing", "completed", "failed"
    Este endpoint normaliza todos esses valores para o formato esperado pelo frontend.
    """
    try:
        # ── Query: incluir TODOS os status possíveis ──
        # O sistema tem dois subsistemas que usam nomes diferentes:
        #   - "running" (ai_bulk) vs "processing" (BackgroundJobService)
        #   - "success" (ai_bulk) vs "completed" (BackgroundJobService)
        # Precisamos de incluir ambos para que os jobs apareçam.
        query = {
            "user_email": current_user.get("email", ""),
            "status": {"$in": [
                "running", "pending", "processing",   # estados ativos
                "success", "completed", "failed",      # estados terminais
                "paused", "cancelled",                  # estados de pausa/cancelamento
            ]},
        }

        # Buscar jobs - tentar sort por started_at (usado por ai_bulk)
        # com fallback para created_at (usado por BackgroundJobService)
        try:
            jobs = await db.background_jobs.find(
                query,
                {"_id": 0}
            ).sort("started_at", -1).to_list(50)
        except Exception:
            jobs = await db.background_jobs.find(
                query,
                {"_id": 0}
            ).sort("created_at", -1).to_list(50)

        # Mapear para o formato esperado pelo frontend TasksContext
        tasks = []
        active_count = 0
        completed_unacknowledged = 0

        for job in jobs:
            raw_status = job.get("status", "unknown")

            # ── Normalizar status para o formato do frontend ──
            # "running" (ai_bulk) → "processing" (frontend espera este)
            # "success" (ai_bulk) → "completed" (frontend espera este)
            # "processing", "completed", "failed", "pending" → mantém-se
            # "paused" → mantém-se
            # "cancelled" → mapear para "failed" no frontend
            status_map = {
                "running": "processing",
                "success": "completed",
                "cancelled": "failed",
            }
            status = status_map.get(raw_status, raw_status)

            is_active = status in ["processing", "pending", "paused"]
            is_done = status in ["completed", "failed"]
            is_unack = not job.get("acknowledged_at")

            if is_active:
                active_count += 1

            if is_done and is_unack:
                completed_unacknowledged += 1

            # Determine priority based on status and duration
            priority = "normal"
            if status == "failed":
                priority = "alta"
            elif status == "processing":
                # Check if running for > 5 minutes
                try:
                    # Tentar started_at (ai_bulk) ou created_at (BackgroundJobService)
                    started_str = job.get("started_at") or job.get("created_at", "")
                    if started_str:
                        started_dt = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
                        minutes_running = (datetime.now(timezone.utc) - started_dt).total_seconds() / 60
                        if minutes_running > 5:
                            priority = "alta"
                except (ValueError, TypeError):
                    pass
            elif status == "pending":
                priority = "media"

            # Só incluir jobs que ainda são relevantes
            if is_active or (is_done and is_unack):
                # ── Extrair progresso (compatível com ambos os schemas) ──
                # ai_bulk: progress é um número (0-100)
                # BackgroundJobService: progress é um objecto {current, total, percentage, message}
                progress_obj = job.get("progress")
                if isinstance(progress_obj, dict):
                    progress_pct = progress_obj.get("percentage", 0)
                    progress_message = progress_obj.get("message", "")
                elif isinstance(progress_obj, (int, float)):
                    progress_pct = progress_obj
                    progress_message = job.get("current_step", "")
                else:
                    progress_pct = 0
                    progress_message = ""

                # ── Mapear tipo de job para TaskType do frontend ──
                # O campo pode ser "type" (ambos os schemas) ou "job_type"
                raw_type = job.get("type") or job.get("job_type", "CUSTOM")
                # Mapear tipos do ai_bulk para TaskTypes do frontend
                task_type_map = {
                    "bulk_import": "BULK_IMPORT",
                    "excel_import": "BULK_IMPORT",
                    "aggregated_import": "BULK_IMPORT",
                    "bulk_analysis": "AI_ANALYSIS",
                    "data_export": "DATA_EXPORT",
                    "email_sync": "EMAIL_SEND",
                    "pdf_gen": "PDF_GEN",
                    "async_import": "BULK_IMPORT",
                    "sync_import": "BULK_IMPORT",
                }
                task_type = task_type_map.get(raw_type, raw_type if raw_type in [
                    "PDF_GEN", "AI_ANALYSIS", "EMAIL_SEND", "DOCUMENT_UPLOAD",
                    "BULK_IMPORT", "REPORT_GEN", "DATA_EXPORT", "DOC_CATEGORIZE",
                    "TEMPLATE_FILL", "S3_UPLOAD", "CUSTOM"
                ] else "CUSTOM")

                # ── Extrair título e descrição ──
                title = job.get("name") or job.get("title", "")
                if not title:
                    # Gerar título a partir do tipo
                    type_labels = {
                        "bulk_import": "Importação Massiva",
                        "excel_import": "Importação Excel",
                        "aggregated_import": "Importação Agregada",
                        "bulk_analysis": "Análise em Massa",
                        "data_export": "Exportação de Dados",
                        "email_sync": "Sincronização de Email",
                        "pdf_gen": "Geração de PDF",
                    }
                    title = type_labels.get(raw_type, f"Tarefa: {raw_type}")

                description = job.get("message", "") or job.get("current_step", "")
                if raw_status == "failed":
                    error_msg = job.get("error_log") or job.get("error") or job.get("message", "")
                else:
                    error_msg = None

                # ── Buscar nome do processo se disponível ──
                process_name = None
                details = job.get("details") or job.get("metadata") or {}
                if isinstance(details, dict):
                    process_name = details.get("client_name") or details.get("process_name")

                tasks.append({
                    "task_id": job.get("id", ""),
                    "task_type": task_type,  # Campo correcto para o frontend (era "type")
                    "title": title,
                    "description": description,
                    "status": status,
                    "progress": progress_pct,
                    "progress_message": progress_message,
                    "created_at": job.get("created_at") or job.get("started_at", ""),
                    "started_at": job.get("started_at"),
                    "updated_at": job.get("updated_at", ""),
                    "acknowledged_at": job.get("acknowledged_at"),
                    "result_url": job.get("result_url"),
                    "error_message": error_msg,
                    "process_name": process_name,
                    "priority": priority,
                })

                # Auto-acknowledge: marcar jobs concluídos/falhados como acknowledged
                # na primeira leitura para evitar loops de toast no frontend.
                # O utilizador já recebeu a notificação (via TasksDropdown ou toast).
                if is_done and is_unack:
                    job_id_val = job.get("id", "")
                    if job_id_val:
                        await db.background_jobs.update_one(
                            {"id": job_id_val},
                            {"$set": {"acknowledged_at": datetime.now(timezone.utc).isoformat()}}
                        )

        return {
            "tasks": tasks,
            "active_count": active_count,
            "completed_unacknowledged": completed_unacknowledged,
        }

    except Exception as e:
        logger.warning(f"Erro ao buscar tarefas activas: {e}")
        return {"tasks": [], "active_count": 0, "completed_unacknowledged": 0}


async def run_acknowledge_background_task(task_id: str, current_user: dict):
    """
    Confirmar visualização de uma tarefa assíncrona.
    Marca o job como acknowledged para parar de notificar.
    """
    result = await db.background_jobs.update_one(
        {"id": task_id, "user_email": current_user.get("email", "")},
        {"$set": {"acknowledged_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return {"success": True}


async def run_cancel_background_task(task_id: str, current_user: dict):
    """
    Cancelar uma tarefa pendente/em execução.
    """
    job = await db.background_jobs.find_one({"id": task_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    if job.get("status") not in ["pending", "running", "processing", "paused"]:
        raise HTTPException(status_code=400, detail="Apenas tarefas pendentes/em execução podem ser canceladas")

    await db.background_jobs.update_one(
        {"id": task_id},
        {"$set": {
            "status": "failed",
            "error": "Cancelada pelo utilizador",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    return {"success": True, "message": "Tarefa cancelada"}
