"""Import-session and aggregated-session handlers for AI bulk import.

Extraído de `routes/ai_bulk.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from routes.ai_bulk.constants import (
    ERROR_AGGREGATION_SESSION_EXPIRED,
    ERROR_SESSION_NOT_FOUND,
)
from routes.ai_bulk.jobs import (
    background_processes,
    create_background_job_db,
    finish_background_job_db,
    update_background_job_db,
)
from routes.ai_import_logs import (
    create_ai_import_log,
    finalize_ai_import_log,
    update_ai_import_log,
)
from services.ai_bulk_models import (
    AggregatedFinishResponse,
    AggregatedSessionRequest,
    AggregatedSessionResponse,
    ImportSessionRequest,
    ImportSessionResponse,
    UpdateSessionRequest,
)
from services.documents.data_aggregator import (
    close_session,
    get_or_create_session,
    get_session_async,
    persist_session_to_db,
)

logger = logging.getLogger(__name__)


async def run_start_import_session(
    request: ImportSessionRequest,
    user: dict,
):
    """Iniciar uma sessão de importação em massa."""
    details = {
        "folder_name": request.folder_name,
        "client_id": request.client_id
    }
    
    session_id = await create_background_job_db(
        job_type="bulk_import",
        user_email=user.get("email"),
        details=details,
        total_files=request.total_files
    )
    
    return ImportSessionResponse(
        session_id=session_id,
        message=f"Sessão de importação iniciada com {request.total_files} ficheiros"
    )



async def run_update_import_session(
    session_id: str,
    request: UpdateSessionRequest,
    user: dict,
):
    """Actualizar o progresso de uma sessão de importação."""
    update_fields = {}
    if request.processed is not None:
        update_fields["processed"] = request.processed
    if request.errors is not None:
        update_fields["errors"] = request.errors
    if request.error_message:
        if session_id in background_processes:
            error_messages = background_processes[session_id].get("error_messages", [])
            error_messages.append(request.error_message)
            update_fields["error_messages"] = error_messages[-50:]
    if request.current_step:
        update_fields["current_step"] = request.current_step
    
    if update_fields:
        await update_background_job_db(session_id, **update_fields)

    job = background_processes.get(session_id) or await db.background_jobs.find_one({"id": session_id}, {"_id": 0})
    return job or {"error": ERROR_SESSION_NOT_FOUND}



async def run_finish_import_session(
    session_id: str,
    user: dict,
    success: bool = True,
    message: Optional[str] = None,
):
    """Finalizar uma sessão de importação."""
    await finish_background_job_db(session_id, success, message)

    job = background_processes.get(session_id) or await db.background_jobs.find_one({"id": session_id}, {"_id": 0})
    return job or {"error": ERROR_SESSION_NOT_FOUND}



async def run_start_aggregated_session(
    request: AggregatedSessionRequest,
    user: dict,
):
    """Iniciar sessão de importação AGREGADA."""
    details = {
        "aggregation_mode": True,
        "client_id": request.client_id,
        "client_name": request.client_name
    }
    
    session_id = await create_background_job_db(
        job_type="aggregated_import",
        user_email=user.get("email"),
        details=details,
        total_files=request.total_files
    )
    
    session = get_or_create_session(session_id, user.get("email"))
    session.total_files = request.total_files
    
    await persist_session_to_db(session)
    
    logger.info(f"[AGGREGATED] Sessão iniciada com {request.total_files} ficheiros")
    
    return AggregatedSessionResponse(
        session_id=session_id,
        message=f"Sessão agregada iniciada com {request.total_files} ficheiros",
        aggregation_mode=True
    )



async def run_finish_aggregated_session(
    session_id: str,
    user: dict,
):
    """Finalizar sessão de importação AGREGADA."""
    session = await get_session_async(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=ERROR_AGGREGATION_SESSION_EXPIRED)

    clients_updated = 0
    errors_count = session.errors
    import_start_time = datetime.now(timezone.utc)
    
    try:
        all_consolidated = session.get_all_consolidated_data()
        
        for process_id, consolidated_data in all_consolidated.items():
            try:
                existing_process = await db.processes.find_one({"id": process_id}, {"_id": 0})
                if not existing_process:
                    logger.warning("[AGGREGATED] Processo não encontrado")
                    continue
                
                update_data = {}
                
                if consolidated_data.get("personal_data"):
                    existing_personal = existing_process.get("personal_data") or {}
                    existing_personal.update(consolidated_data["personal_data"])
                    update_data["personal_data"] = existing_personal
                
                if consolidated_data.get("financial_data"):
                    existing_financial = existing_process.get("financial_data") or {}
                    existing_financial.update(consolidated_data["financial_data"])
                    update_data["financial_data"] = existing_financial
                
                if consolidated_data.get("real_estate_data"):
                    existing_real_estate = existing_process.get("real_estate_data") or {}
                    existing_real_estate.update(consolidated_data["real_estate_data"])
                    update_data["real_estate_data"] = existing_real_estate
                
                if consolidated_data.get("co_buyers"):
                    update_data["co_buyers"] = consolidated_data["co_buyers"]
                if consolidated_data.get("co_applicants"):
                    update_data["co_applicants"] = consolidated_data["co_applicants"]
                
                update_data["updated_at"] = consolidated_data.get("updated_at")
                update_data["ai_import_aggregated"] = True
                update_data["ai_import_timestamp"] = consolidated_data.get("ai_import_timestamp")
                update_data["ai_documents_count"] = consolidated_data.get("ai_documents_count", 0)
                
                if consolidated_data.get("ai_extraction_history"):
                    update_data["$push"] = {
                        "ai_extraction_history": {
                            "$each": consolidated_data["ai_extraction_history"]
                        }
                    }
                    push_data = update_data.pop("$push")
                    
                    await db.processes.update_one(
                        {"id": process_id},
                        {"$set": update_data, "$push": push_data}
                    )
                else:
                    await db.processes.update_one(
                        {"id": process_id},
                        {"$set": update_data}
                    )
                
                clients_updated += 1
                client_name = existing_process.get("client_name", process_id)
                logger.info(f"[AGGREGATED] Cliente actualizado com dados agregados")
                
                try:
                    log_id = await create_ai_import_log(
                        process_id=process_id,
                        client_name=client_name,
                        created_by=user.get("id"),
                        created_by_name=user.get("name") or user.get("email")
                    )
                    
                    client_aggregator = session.clients.get(process_id)
                    if client_aggregator:
                        for doc_info in client_aggregator.document_history:
                            doc_result = {
                                "file_name": doc_info.get("filename", ""),
                                "document_type": doc_info.get("document_type", ""),
                                "status": "success",
                                "extracted_fields": doc_info.get("extracted_fields", {}),
                                "applied_fields": list(doc_info.get("extracted_fields", {}).keys())
                            }
                            await update_ai_import_log(log_id, document_result=doc_result)
                    
                    duration_ms = int((datetime.now(timezone.utc) - import_start_time).total_seconds() * 1000)
                    
                    auto_filled = {}
                    if consolidated_data.get("personal_data"):
                        auto_filled["personal_data"] = consolidated_data["personal_data"]
                    if consolidated_data.get("financial_data"):
                        auto_filled["financial_data"] = consolidated_data["financial_data"]
                    if consolidated_data.get("real_estate_data"):
                        auto_filled["real_estate_data"] = consolidated_data["real_estate_data"]
                    
                    await update_ai_import_log(log_id, auto_filled_fields=auto_filled)
                    await finalize_ai_import_log(log_id, duration_ms)
                    
                    logger.info(f"[AI_IMPORT_LOG] Log criado para cliente")
                    
                except Exception as log_error:
                    logger.warning(f"[AI_IMPORT_LOG] Erro ao criar log para cliente")
                
            except Exception as e:
                errors_count += 1
                logger.error(f"[AGGREGATED] Erro ao actualizar cliente")
        
        summary = session.get_session_summary()
        
        await finish_background_job_db(
            session_id,
            success=clients_updated > 0,
            message=f"{clients_updated} clientes actualizados, {session.processed_files} documentos processados"
        )
        
        try:
            await db.aggregated_sessions.update_one(
                {"session_id": session_id},
                {"$set": {"is_active": False, "finished_at": datetime.now(timezone.utc).isoformat()}}
            )
        except Exception:
            pass
        
        close_session(session_id)
        
        return AggregatedFinishResponse(
            success=clients_updated > 0,
            message=f"Importação agregada concluída: {clients_updated} clientes actualizados",
            clients_updated=clients_updated,
            total_documents=session.processed_files,
            errors=errors_count,
            summary=summary
        )
        
    except Exception as e:
        logger.error(f"[AGGREGATED] Erro ao finalizar sessão: {e}", exc_info=True)
        try:
            await db.aggregated_sessions.update_one(
                {"session_id": session_id},
                {"$set": {"is_active": False, "error": str(e)}}
            )
        except Exception:
            pass
        close_session(session_id)
        raise HTTPException(status_code=500, detail=f"Erro ao finalizar importação: {str(e)}")



async def run_get_aggregated_session_status(
    session_id: str,
    user: dict,
):
    """Obter estado da sessão de importação agregada."""
    session = await get_session_async(session_id)
    if not session:
        job = await db.background_jobs.find_one({"id": session_id}, {"_id": 0})
        if job:
            return {
                "session_id": session_id,
                "status": job.get("status", "unknown"),
                "from_db": True,
                **job
            }
        raise HTTPException(status_code=404, detail=ERROR_SESSION_NOT_FOUND)
    
    return {
        "session_id": session_id,
        "status": "active",
        "in_memory": True,
        **session.get_session_summary()
    }


# ====================================================================
# ENDPOINT DE ANÁLISE SINGLE
# ====================================================================
