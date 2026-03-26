"""
Bulk AI Document Analysis Routes
================================
Upload de documentos para análise com IA e preenchimento automático das fichas de clientes.

IMPORTANTE: Os ficheiros são processados um a um pelo frontend.
O endpoint /analyze-single recebe e processa um ficheiro de cada vez.

FUNCIONALIDADES:
- Normalização de nomes de ficheiros
- Junção de CC frente+verso num único PDF para análise
- Conversão de PDFs scan para imagem
- Detecção de documentos duplicados (evita reanalisar recibos/extratos iguais)
- Matching flexível de nomes (suporta acentos, parênteses, nomes compostos)

SEGURANÇA:
- Validação de ficheiros usando Magic Bytes (não confia na extensão)
- Whitelist de MIME types permitidos (PDF, JPEG, PNG, etc.)
- Bloqueio de ficheiros executáveis e scripts

REFATORAÇÃO (SonarQube):
- Código modular extraído para ai_bulk/:
  - constants.py: Constantes e mensagens de erro
  - cache.py: Cache NIF e detecção de duplicados
  - jobs.py: Gestão de background jobs
  - matching.py: Matching de clientes por nome/NIF
  - utils.py: Funções utilitárias
  - nif_cache.py: Endpoints de NIF cache
  - background_jobs.py: Endpoints de background jobs
"""
import os
import re
import uuid
import base64
import logging
from typing import List, Optional, Dict, Tuple, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from database import db
from models.auth import UserRole
from services.auth import require_roles, get_current_user
from services.file_validation import validate_file_content
from services.ai_document import (
    MAX_FILE_SIZE,
    detect_document_type,
    get_mime_type,
    analyze_single_document,
    build_update_data_from_extraction,
    merge_images_to_pdf,
    analyze_document_from_base64
)
from services.documents.data_aggregator import (
    get_or_create_session,
    get_session_async,
    close_session,
    persist_session_to_db,
)
from routes.ai_import_logs import (
    create_ai_import_log,
    update_ai_import_log,
    finalize_ai_import_log
)
from services.s3_storage import s3_service
from io import BytesIO

# ====================================================================
# IMPORTS DOS MÓDULOS REFACTORED (SonarQube)
# ====================================================================
from routes.ai_bulk.constants import (
    ERROR_PROCESS_NOT_FOUND,
    ERROR_SESSION_NOT_FOUND,
    ERROR_JOB_NOT_FOUND,
    ERROR_CLIENT_NOT_FOUND,
    ERROR_AGGREGATION_SESSION_NOT_FOUND,
    ERROR_AGGREGATION_SESSION_EXPIRED,
    MSG_DUPLICATE_DOCUMENT_IGNORED,
    MSG_DUPLICATE_DOCUMENT_CACHED,
    ERROR_ONLY_RUNNING_JOBS_CAN_CANCEL,
    ERROR_ONLY_RUNNING_JOBS_CAN_PAUSE,
    ERROR_ONLY_PAUSED_JOBS_CAN_RESUME,
    REASON_MANUALLY_EDITED,
    CHUNK_SIZE,
    NORMALIZED_NAMES,
    DUPLICATE_PRONE_TYPES,
    DOCUMENT_TYPE_TO_CATEGORY,
)

from routes.ai_bulk.cache import (
    nif_session_cache,
    NIF_CACHE_TTL_SECONDS,
    cc_cache,
    document_hash_cache,
    get_nif_cache_key,
    cache_nif_mapping,
    get_cached_nif_mapping,
    clear_expired_nif_cache,
    calculate_document_hash,
    is_duplicate_document,
    is_duplicate_document_db,
    check_duplicate_comprehensive,
    cache_document_analysis,
    persist_document_analysis,
)

from routes.ai_bulk.jobs import (
    background_processes,
    create_background_job_db,
    update_background_job_db,
    finish_background_job_db,
    load_background_jobs_from_db,
    create_background_job,
    update_background_job,
    finish_background_job,
)

from routes.ai_bulk.matching import (
    normalize_text_for_matching,
    extract_all_names_from_string,
    find_client_by_nif,
    find_client_by_name,
    suggest_similar_clients,
)

from routes.ai_bulk.utils import (
    sanitize_for_log,
    validate_nif,
    is_placeholder_value,
    clean_extracted_value,
    is_cc_frente_or_verso,
    get_normalized_filename,
    categorize_extracted_fields,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/bulk", tags=["AI Bulk Analysis"])


# ====================================================================
# MODELOS PYDANTIC
# ====================================================================

class SingleAnalysisResult(BaseModel):
    success: bool
    client_name: str
    filename: str
    document_type: str = ""
    fields_extracted: List[str] = []
    updated: bool = False
    error: Optional[str] = None
    conflicts: Optional[Dict[str, Any]] = None


class ImportSessionRequest(BaseModel):
    total_files: int
    folder_name: Optional[str] = None
    client_id: Optional[str] = None


class ImportSessionResponse(BaseModel):
    session_id: str
    message: str


class UpdateSessionRequest(BaseModel):
    processed: Optional[int] = None
    errors: Optional[int] = None
    error_message: Optional[str] = None


class AggregatedSessionRequest(BaseModel):
    """Request para iniciar sessão de importação agregada."""
    total_files: int
    client_id: Optional[str] = None
    client_name: Optional[str] = None


class AggregatedSessionResponse(BaseModel):
    """Response da sessão de importação agregada."""
    session_id: str
    message: str
    aggregation_mode: bool = True


class AggregatedFileResult(BaseModel):
    """Resultado do processamento de um ficheiro na sessão agregada."""
    success: bool
    client_name: str
    filename: str
    document_type: str = ""
    fields_extracted: List[str] = []
    aggregated: bool = True
    error: Optional[str] = None


class AggregatedFinishResponse(BaseModel):
    """Response da finalização da sessão agregada."""
    success: bool
    message: str
    clients_updated: int
    total_documents: int
    errors: int
    summary: Dict[str, Any] = {}


class ProgressUpdateRequest(BaseModel):
    """Request para actualizar progresso de um job."""
    processed: Optional[int] = None
    errors: Optional[int] = None
    message: Optional[str] = None


# ====================================================================
# FUNÇÕES DE LEITURA E ACTUALIZAÇÃO
# ====================================================================

async def read_file_with_limit(file: UploadFile) -> bytes:
    """
    Ler ficheiro com limite de tamanho.
    Lê em chunks para não sobrecarregar a memória.
    """
    chunks = []
    total_size = 0
    
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        
        total_size += len(chunk)
        if total_size > MAX_FILE_SIZE:
            raise ValueError(f"Ficheiro excede o limite de {MAX_FILE_SIZE // (1024*1024)}MB")
        
        chunks.append(chunk)
    
    return b''.join(chunks)


async def update_client_data(process_id: str, extracted_data: dict, document_type: str, force_update: bool = False) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Actualizar ficha do cliente com dados extraídos.
    
    REGRAS IMPORTANTES:
    1. Processos concluídos/desistidos/cancelados: NÃO actualizar (retorna conflitos para revisão)
    2. Campos preenchidos manualmente pelo utilizador: NÃO sobrescrever (a menos que force_update=True)
    3. Guarda dados extraídos para comparação posterior
    
    Returns:
        Tuple de (success, list of updated fields, dict of conflicts/skipped)
    """
    updated_fields = []
    conflicts = {}
    
    try:
        logger.info(f"update_client_data: document_type={document_type}")
        logger.info(f"extracted_data: {list(extracted_data.keys())}")
        
        # Validar NIF antes de guardar
        nif = extracted_data.get('nif') or extracted_data.get('NIF')
        if nif and not validate_nif(nif):
            logger.warning("NIF inválido rejeitado")
            if 'nif' in extracted_data:
                del extracted_data['nif']
            if 'NIF' in extracted_data:
                del extracted_data['NIF']
        
        # Obter dados existentes
        process = await db.processes.find_one(
            {"id": process_id},
            {"_id": 0}
        )
        
        if not process:
            logger.error(ERROR_PROCESS_NOT_FOUND)
            return False, [], {"error": ERROR_PROCESS_NOT_FOUND}
        
        # REGRA 1: Processos finalizados não são actualizados
        process_status = process.get("status", "")
        if process_status in ["concluido", "desistido", "cancelado", "arquivado"]:
            logger.info(f"Processo está '{process_status}' - dados guardados para revisão apenas")
            
            await db.processes.update_one(
                {"id": process_id},
                {
                    "$push": {
                        "ai_pending_review": {
                            "document_type": document_type,
                            "extracted_data": extracted_data,
                            "extracted_at": datetime.now(timezone.utc).isoformat(),
                            "status": "pending_review"
                        }
                    }
                }
            )
            
            return True, [], {
                "status": "pending_review",
                "message": f"Processo '{process_status}' - dados guardados para revisão manual",
                "extracted_fields": list(extracted_data.keys())
            }
        
        # REGRA 2: Não sobrescrever dados introduzidos manualmente
        manually_edited = process.get("manually_edited_fields", [])
        
        update_data = build_update_data_from_extraction(
            extracted_data,
            document_type,
            process or {}
        )
        
        if not force_update and manually_edited:
            for field in manually_edited:
                if "." in field:
                    parent, child = field.split(".", 1)
                    if parent in update_data and isinstance(update_data[parent], dict):
                        if child in update_data[parent]:
                            old_value = process.get(parent, {}).get(child)
                            new_value = update_data[parent][child]
                            if old_value != new_value:
                                conflicts[field] = {
                                    "existing": old_value,
                                    "extracted": new_value,
                                    "reason": REASON_MANUALLY_EDITED
                                }
                            del update_data[parent][child]
                            logger.info(f"Campo '{field}' preservado (editado manualmente)")
                else:
                    if field in update_data:
                        old_value = process.get(field)
                        new_value = update_data[field]
                        if old_value != new_value:
                            conflicts[field] = {
                                "existing": old_value,
                                "extracted": new_value,
                                "reason": REASON_MANUALLY_EDITED
                            }
                        del update_data[field]
                        logger.info(f"Campo '{field}' preservado (editado manualmente)")
        
        # Identificar campos que serão actualizados
        for key, value in update_data.items():
            if key != "updated_at" and value:
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        if subvalue:
                            updated_fields.append(f"{key}.{subkey}")
                elif isinstance(value, list):
                    updated_fields.append(f"{key} ({len(value)} items)")
                else:
                    updated_fields.append(key)
        
        logger.info(f"Campos a actualizar: {updated_fields}")
        
        # REGRA 3: Guardar dados extraídos para comparação posterior
        ai_extraction_log = {
            "document_type": document_type,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extracted_data": extracted_data,
            "applied_fields": updated_fields,
            "conflicts": conflicts if conflicts else None
        }
        
        if len(update_data) > 1:
            result = await db.processes.update_one(
                {"id": process_id},
                {
                    "$set": update_data,
                    "$push": {"ai_extraction_history": ai_extraction_log}
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ Cliente actualizado com sucesso! Campos: {updated_fields}")
                if conflicts:
                    logger.info(f"⚠️ Campos com conflitos (preservados): {list(conflicts.keys())}")
                return True, updated_fields, conflicts
            else:
                logger.info("Nenhuma alteração necessária (dados já existentes)")
                return True, updated_fields, conflicts
        else:
            logger.warning(f"Nenhum dado para actualizar (update_data tem apenas {len(update_data)} campos)")
        
        return False, [], conflicts
        
    except Exception as e:
        logger.error(f"Erro ao actualizar cliente: {e}", exc_info=True)
        return False, [], {"error": str(e)}


async def log_import_result(
    client_name: str,
    process_id: Optional[str],
    filename: str,
    document_type: str,
    success: bool,
    extracted_data: Optional[dict] = None,
    updated_fields: Optional[List[str]] = None,
    error: Optional[str] = None,
    user_email: str = None,
    folder_name: str = None,
    full_path: str = None
):
    """
    Registar resultado de importação (sucesso ou erro) na base de dados.
    Organiza os dados por categorias para visualização em tabs.
    """
    try:
        log_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        categorized_data = {}
        if extracted_data:
            categorized_data = categorize_extracted_fields(extracted_data, document_type)
        
        import_log = {
            "id": log_id,
            "timestamp": timestamp,
            "status": "success" if success else "error",
            "client_name": client_name,
            "process_id": process_id,
            "filename": filename,
            "document_type": document_type,
            "folder_name": folder_name or client_name,
            "full_path": full_path or filename,
            "user_email": user_email,
            "categorized_data": categorized_data,
            "updated_fields": updated_fields or [],
            "fields_count": len(updated_fields) if updated_fields else 0,
            "error": error,
            "resolved": success,
        }
        
        await db.ai_import_logs.insert_one(import_log)
        
        if not success and error:
            error_log = {
                "id": log_id,
                "timestamp": timestamp,
                "client_name": client_name,
                "process_id": process_id,
                "filename": filename,
                "document_type": document_type,
                "error": error,
                "user_email": user_email,
                "resolved": False,
                "folder_name": folder_name or client_name,
                "full_path": full_path or filename,
            }
            await db.import_errors.insert_one(error_log)
        
        log_status = "✅ Sucesso" if success else "❌ Erro"
        logger.info(f"Log de importação registado: {log_status}")
        
    except Exception as e:
        logger.error(f"Falha ao registar log de importação: {e}")


async def log_import_error(
    client_name: str,
    process_id: Optional[str],
    filename: str,
    document_type: str,
    error: str,
    user_email: str = None,
    folder_name: str = None,
    attempted_matches: List[str] = None,
    best_match_score: int = None,
    best_match_name: str = None,
    extracted_names: List[str] = None,
    full_path: str = None
):
    """
    Guardar erro de importação na base de dados para análise posterior.
    """
    await log_import_result(
        client_name=client_name,
        process_id=process_id,
        filename=filename,
        document_type=document_type,
        success=False,
        error=error,
        user_email=user_email,
        folder_name=folder_name,
        full_path=full_path
    )
    
    try:
        error_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        error_details = {
            "client_name": client_name,
            "process_id": process_id,
            "filename": filename,
            "document_type": document_type,
            "folder_name": folder_name or client_name,
            "full_path": full_path or filename,
            "user_email": user_email
        }
        
        if any([attempted_matches, best_match_score, extracted_names]):
            error_details["matching_details"] = {
                "attempted_matches": attempted_matches[:10] if attempted_matches else [],
                "best_match_score": best_match_score,
                "best_match_name": best_match_name,
                "extracted_names": list(extracted_names)[:5] if extracted_names else []
            }
        
        system_log = {
            "id": error_id,
            "timestamp": timestamp,
            "severity": "warning",
            "component": "import",
            "error_type": "import_error",
            "message": f"Erro de importação: {error}",
            "details": error_details,
            "resolved": False,
            "context": {
                "filename": filename,
                "client": client_name,
                "user": user_email
            }
        }
        await db.system_error_logs.insert_one(system_log)
        
    except Exception as e:
        logger.error(f"Falha ao registar erro no system_error_logs: {e}")


# ====================================================================
# ENDPOINTS DE SESSÃO DE IMPORTAÇÃO
# ====================================================================

@router.post("/import-session/start", response_model=ImportSessionResponse)
async def start_import_session(
    request: ImportSessionRequest,
    user: dict = Depends(get_current_user)
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


@router.post("/import-session/{session_id}/update")
async def update_import_session(
    session_id: str,
    request: UpdateSessionRequest,
    user: dict = Depends(get_current_user)
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
    
    if update_fields:
        await update_background_job_db(session_id, **update_fields)

    job = background_processes.get(session_id) or await db.background_jobs.find_one({"id": session_id}, {"_id": 0})
    return job or {"error": ERROR_SESSION_NOT_FOUND}


@router.post("/import-session/{session_id}/finish")
async def finish_import_session(
    session_id: str,
    success: bool = True,
    message: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Finalizar uma sessão de importação."""
    await finish_background_job_db(session_id, success, message)

    job = background_processes.get(session_id) or await db.background_jobs.find_one({"id": session_id}, {"_id": 0})
    return job or {"error": ERROR_SESSION_NOT_FOUND}


# ====================================================================
# IMPORTAÇÃO AGREGADA - CLIENTE A CLIENTE
# ====================================================================

@router.post("/aggregated-session/start", response_model=AggregatedSessionResponse)
async def start_aggregated_session(
    request: AggregatedSessionRequest,
    user: dict = Depends(get_current_user)
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


@router.post(
    "/aggregated-session/{session_id}/analyze",
    response_model=AggregatedFileResult,
    responses={
        404: {"description": ERROR_AGGREGATION_SESSION_NOT_FOUND},
        400: {"description": "Ficheiro rejeitado por validação de segurança"}
    }
)
async def analyze_file_aggregated(
    session_id: str,
    file: UploadFile = File(...),
    force_client_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user)
):
    """Analisar ficheiro e AGREGAR dados (não salva ainda)."""
    session = await get_session_async(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=ERROR_AGGREGATION_SESSION_NOT_FOUND)

    filename = file.filename or "documento.pdf"
    
    parts = filename.replace("\\", "/").split("/")
    if len(parts) >= 2:
        folder_name = parts[1]
        doc_filename = parts[-1]
    else:
        doc_filename = parts[0]
        folder_name = doc_filename.rsplit("_", 1)[0] if "_" in doc_filename else "Desconhecido"
    
    client_name = folder_name
    
    result = AggregatedFileResult(
        success=False,
        client_name=client_name,
        filename=doc_filename,
        aggregated=True
    )
    
    try:
        content = await read_file_with_limit(file)
        
        try:
            validate_file_content(content, doc_filename)
        except HTTPException as e:
            result.error = f"Ficheiro rejeitado: {e.detail}"
            session.increment_error()
            return result
        
        process = None
        process_id = None
        
        if force_client_id:
            process = await db.processes.find_one({"id": force_client_id}, {"_id": 0})
            if process:
                process_id = force_client_id
            else:
                result.error = f"Cliente com ID '{force_client_id}' não encontrado"
                session.increment_error()
                return result
        else:
            cached_mapping = await get_cached_nif_mapping(folder_name)
            if cached_mapping:
                process_id = cached_mapping["process_id"]
                process = await db.processes.find_one({"id": process_id}, {"_id": 0})
            
            if not process:
                process = await find_client_by_name(client_name)
        
        if not process:
            result.error = f"Cliente não encontrado: {client_name}"
            session.increment_error()
            return result
        
        process_id = process.get("id")
        actual_client_name = process.get("client_name", client_name)
        result.client_name = actual_client_name
        
        document_type = detect_document_type(doc_filename)
        result.document_type = document_type
        
        duplicate_data = await check_duplicate_comprehensive(process_id, document_type, content)
        if duplicate_data:
            result.success = True
            result.error = MSG_DUPLICATE_DOCUMENT_CACHED
            return result

        analysis_result = await analyze_single_document(
            content=content,
            filename=doc_filename,
            client_name=actual_client_name,
            process_id=process_id
        )
        
        if analysis_result.get("success") and analysis_result.get("extracted_data"):
            extracted_data = analysis_result["extracted_data"]
            
            session.add_file_extraction(
                process_id=process_id,
                client_name=actual_client_name,
                document_type=document_type,
                extracted_data=extracted_data,
                filename=doc_filename
            )
            
            cache_document_analysis(process_id, document_type, content, extracted_data)
            
            await persist_document_analysis(
                process_id, document_type, content, extracted_data, doc_filename
            )
            
            result.success = True
            result.fields_extracted = list(extracted_data.keys())
            logger.info(f"[AGGREGATED] Documento agregado para cliente")
        else:
            result.error = analysis_result.get("error", "Erro na análise")
            session.increment_error()
        
    except Exception as e:
        result.error = f"Erro inesperado: {str(e)}"
        session.increment_error()
        logger.error(f"[AGGREGATED] Erro ao processar documento: {e}", exc_info=True)
    
    try:
        await persist_session_to_db(session)
    except Exception as persist_error:
        logger.warning(f"[AGGREGATED] Erro ao persistir sessão: {persist_error}")
    
    return result


@router.post(
    "/aggregated-session/{session_id}/finish",
    response_model=AggregatedFinishResponse,
    responses={
        404: {"description": ERROR_AGGREGATION_SESSION_EXPIRED},
        500: {"description": "Erro ao finalizar importação"}
    }
)
async def finish_aggregated_session(
    session_id: str,
    user: dict = Depends(get_current_user)
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


@router.get(
    "/aggregated-session/{session_id}/status",
    responses={404: {"description": ERROR_SESSION_NOT_FOUND}}
)
async def get_aggregated_session_status(
    session_id: str,
    user: dict = Depends(get_current_user)
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

@router.post("/analyze-single", response_model=SingleAnalysisResult)
async def analyze_single_file(
    file: UploadFile = File(...),
    force_client_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user)
):
    """
    Analisar um único ficheiro.
    
    O frontend envia um ficheiro de cada vez, evitando problemas de memória
    e ficheiros fechados prematuramente pelo browser.
    """
    filename = file.filename or "documento.pdf"
    
    await clear_expired_nif_cache()
    
    parts = filename.replace("\\", "/").split("/")
    
    if len(parts) >= 2:
        folder_name = parts[1]
        doc_filename = parts[-1]
    else:
        doc_filename = parts[0]
        if "_" in doc_filename:
            folder_name = doc_filename.rsplit("_", 1)[0]
        else:
            folder_name = "Desconhecido"
    
    client_name = folder_name
    
    result = SingleAnalysisResult(
        success=False,
        client_name=client_name,
        filename=doc_filename
    )
    
    try:
        content = await read_file_with_limit(file)
        
        try:
            validate_file_content(content, doc_filename)
        except HTTPException as security_error:
            logger.warning(f"[SECURITY] Ficheiro rejeitado: {security_error.detail}")
            result.error = f"Ficheiro rejeitado: {security_error.detail}"
            return result
        
        mime_type = get_mime_type(doc_filename)
        
        process = None
        process_id = None
        
        if force_client_id:
            process = await db.processes.find_one({"id": force_client_id}, {"_id": 0})
            if process:
                process_id = force_client_id
                logger.info("[FORCE_CLIENT_ID] Usando cliente forçado")
            else:
                result.error = f"Cliente com ID fornecido não encontrado."
                return result
        else:
            cached_mapping = await get_cached_nif_mapping(folder_name)
            
            if cached_mapping:
                process_id = cached_mapping["process_id"]
                process = await db.processes.find_one({"id": process_id}, {"_id": 0})
                if process:
                    logger.info(f"[NIF CACHE] Usando mapeamento em cache para pasta")
            
            if not process:
                process = await find_client_by_name(client_name)
        
        if not process:
            result.error = f"Cliente não encontrado. Verifique se o nome está correcto (acentos, parênteses)."
            return result
        
        process_id = process.get("id")
        actual_client_name = process.get("client_name", client_name)
        result.client_name = actual_client_name
        
        document_type = detect_document_type(doc_filename)
        result.document_type = document_type
        
        duplicate_data = await check_duplicate_comprehensive(process_id, document_type, content)
        if duplicate_data:
            logger.info("Documento duplicado detectado")
            result.success = True
            result.error = MSG_DUPLICATE_DOCUMENT_IGNORED
            return result

        normalized_name = get_normalized_filename(document_type)
        
        # Verificar se é CC frente ou verso
        if document_type == "cc":
            cc_side = is_cc_frente_or_verso(doc_filename)
            
            if cc_side:
                if process_id not in cc_cache:
                    cc_cache[process_id] = {}
                
                cc_cache[process_id][cc_side] = (content, mime_type)
                logger.info(f"CC guardado em cache")
                
                if "frente" in cc_cache[process_id] and "verso" in cc_cache[process_id]:
                    logger.info(f"CC completo (frente+verso), a juntar...")
                    
                    frente_data = cc_cache[process_id]["frente"]
                    verso_data = cc_cache[process_id]["verso"]
                    
                    merged_pdf = merge_images_to_pdf([frente_data, verso_data])
                    
                    if merged_pdf:
                        merged_base64 = base64.b64encode(merged_pdf).decode('utf-8')
                        
                        analysis_result = await analyze_document_from_base64(
                            merged_base64,
                            "application/pdf",
                            "cc"
                        )
                        
                        del cc_cache[process_id]
                        
                        if analysis_result.get("success") or analysis_result.get("extracted_data"):
                            result.success = True
                            result.fields_extracted = list(analysis_result.get("extracted_data", {}).keys())
                            result.filename = normalized_name
                            
                            extracted_data = analysis_result.get("extracted_data", {})
                            extracted_nif = extracted_data.get("nif")
                            if extracted_nif:
                                await cache_nif_mapping(
                                    folder_name=folder_name,
                                    nif=extracted_nif,
                                    process_id=process_id,
                                    client_name=actual_client_name
                                )
                            
                            await persist_document_analysis(
                                process_id,
                                "cc",
                                merged_pdf,
                                extracted_data,
                                "CC_frente_verso.pdf"
                            )
                            
                            updated, fields, conflicts = await update_client_data(
                                process_id,
                                extracted_data,
                                document_type
                            )
                            result.updated = updated
                            if conflicts:
                                result.conflicts = conflicts
                            
                            await log_import_result(
                                client_name=actual_client_name,
                                process_id=process_id,
                                filename="CC_frente_verso.pdf",
                                document_type="cc",
                                success=True,
                                extracted_data=extracted_data,
                                updated_fields=fields,
                                user_email=user.get("email"),
                                folder_name=folder_name,
                                full_path=filename
                            )
                            
                            if s3_service.is_configured():
                                try:
                                    s3_folder = process.get("s3_folder")
                                    second_client_name = process.get("second_client_name") or (process.get("titular2_data") or {}).get("nome")
                                    file_buffer = BytesIO(merged_pdf)
                                    s3_path = s3_service.upload_file(
                                        file_buffer,
                                        process_id,
                                        actual_client_name,
                                        "Documentos Pessoais",
                                        "CC_frente_verso.pdf",
                                        "application/pdf",
                                        second_client_name=second_client_name,
                                        s3_folder=s3_folder
                                    )
                                    if s3_path:
                                        logger.info(f"📁 CC combinado guardado no S3: {s3_path}")
                                except Exception as s3_error:
                                    logger.error(f"Erro ao fazer upload do CC para S3: {s3_error}")
                            
                            logger.info(f"CC (frente+verso) analisado: {len(result.fields_extracted)} campos")
                        else:
                            result.error = analysis_result.get("error", "Erro na análise do CC combinado")
                    else:
                        result.error = "Erro ao juntar CC frente+verso"
                        del cc_cache[process_id]
                else:
                    result.success = True
                    result.filename = f"CC_{cc_side} (a aguardar {'verso' if cc_side == 'frente' else 'frente'})"
                    result.fields_extracted = []
                    logger.info(f"A aguardar outro lado do CC")
                
                return result
        
        # Análise normal (não é CC frente/verso)
        analysis_result = await analyze_single_document(
            content=content,
            filename=doc_filename,
            client_name=actual_client_name,
            process_id=process_id
        )
        
        if analysis_result.get("success") and analysis_result.get("extracted_data"):
            result.success = True
            result.fields_extracted = list(analysis_result["extracted_data"].keys())
            result.filename = normalized_name
            
            extracted_data = analysis_result["extracted_data"]
            
            if document_type == "cc":
                extracted_nif = extracted_data.get("nif")
                if extracted_nif:
                    await cache_nif_mapping(
                        folder_name=folder_name,
                        nif=extracted_nif,
                        process_id=process_id,
                        client_name=actual_client_name
                    )
            
            cache_document_analysis(process_id, document_type, content, extracted_data)
            
            await persist_document_analysis(
                process_id, 
                document_type, 
                content, 
                extracted_data,
                doc_filename
            )
            
            updated, fields, conflicts = await update_client_data(
                process_id,
                extracted_data,
                document_type
            )
            result.updated = updated
            if conflicts:
                result.conflicts = conflicts
            
            await log_import_result(
                client_name=actual_client_name,
                process_id=process_id,
                filename=doc_filename,
                document_type=document_type,
                success=True,
                extracted_data=extracted_data,
                updated_fields=fields,
                user_email=user.get("email"),
                folder_name=folder_name,
                full_path=filename
            )
            
            if s3_service.is_configured():
                try:
                    s3_folder = process.get("s3_folder")
                    second_client_name = process.get("second_client_name") or (process.get("titular2_data") or {}).get("nome")
                    category = DOCUMENT_TYPE_TO_CATEGORY.get(document_type, "Outros")
                    file_buffer = BytesIO(content)
                    s3_path = s3_service.upload_file(
                        file_buffer,
                        process_id,
                        actual_client_name,
                        category,
                        normalized_name,
                        mime_type,
                        second_client_name=second_client_name,
                        s3_folder=s3_folder
                    )
                    if s3_path:
                        logger.info(f"📁 Ficheiro guardado no S3: {s3_path}")
                except Exception as s3_error:
                    logger.error(f"Erro ao fazer upload para S3: {s3_error}")
            
            logger.info(f"Documento processado: {len(result.fields_extracted)} campos extraidos")
        else:
            result.error = analysis_result.get("error", "Erro na análise")
            logger.warning(f"Falha ao analisar documento")
            
            await log_import_error(
                client_name=actual_client_name,
                process_id=process_id,
                filename=doc_filename,
                document_type=document_type,
                error=result.error,
                user_email=user.get("email")
            )
        
    except ValueError as e:
        result.error = str(e)
        await log_import_error(
            client_name=client_name,
            process_id=process_id if 'process_id' in dir() else None,
            filename=doc_filename,
            document_type=document_type if 'document_type' in dir() else "desconhecido",
            error=str(e),
            user_email=user.get("email")
        )
    except Exception as e:
        result.error = f"Erro inesperado: {str(e)}"
        logger.error(f"Erro ao processar documento: {e}", exc_info=True)
        await log_import_error(
            client_name=client_name,
            process_id=process_id if 'process_id' in dir() else None,
            filename=doc_filename,
            document_type=document_type if 'document_type' in dir() else "desconhecido",
            error=str(e),
            user_email=user.get("email")
        )
    
    return result


# ====================================================================
# ENDPOINTS DE BACKGROUND JOBS
# ====================================================================

@router.post("/background-job/{job_id}/progress")
async def update_background_job_progress(
    job_id: str,
    request: ProgressUpdateRequest,
    user: dict = Depends(get_current_user)
):
    """Actualizar progresso de um job em background."""
    update_fields = {}
    
    if request.processed is not None:
        update_fields["processed"] = request.processed
    if request.errors is not None:
        update_fields["errors"] = request.errors
    if request.message:
        update_fields["message"] = request.message

    if update_fields:
        await update_background_job_db(job_id, **update_fields)

    job = background_processes.get(job_id)
    if not job:
        job = await db.background_jobs.find_one({"id": job_id}, {"_id": 0})

    return job or {"error": ERROR_JOB_NOT_FOUND, "updated": bool(update_fields)}


@router.get("/background-jobs")
async def get_background_jobs(
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    user: dict = Depends(get_current_user)
):
    """Listar jobs em background."""
    query = {}
    if status:
        query["status"] = status
    
    db_jobs = await db.background_jobs.find(
        query,
        {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)
    
    memory_jobs = []
    for job_id, job in background_processes.items():
        if status and job.get("status") != status:
            continue
        
        if not any(j.get("id") == job_id for j in db_jobs):
            memory_jobs.append(job)
    
    all_jobs = db_jobs + memory_jobs[:limit - len(db_jobs)]
    
    return {
        "jobs": all_jobs,
        "total": len(all_jobs),
        "from_db": len(db_jobs),
        "from_memory": len(memory_jobs)
    }


@router.get(
    "/background-jobs/{job_id}",
    responses={404: {"description": ERROR_JOB_NOT_FOUND}}
)
async def get_background_job_status(
    job_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter estado de um job específico."""
    if job_id in background_processes:
        return background_processes[job_id]
    
    job = await db.background_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail=ERROR_JOB_NOT_FOUND)
    
    return job


@router.delete(
    "/background-jobs/{job_id}",
    responses={404: {"description": ERROR_JOB_NOT_FOUND}}
)
async def delete_background_job(
    job_id: str,
    user: dict = Depends(get_current_user)
):
    """Remover um job do histórico."""
    job = background_processes.pop(job_id, None)
    
    result = await db.background_jobs.delete_one({"id": job_id})
    
    if not job and result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=ERROR_JOB_NOT_FOUND)
    
    return {
        "success": True,
        "message": f"Job {job_id} removido",
        "job": job
    }


@router.post(
    "/background-jobs/{job_id}/cancel",
    responses={
        404: {"description": ERROR_JOB_NOT_FOUND},
        400: {"description": ERROR_ONLY_RUNNING_JOBS_CAN_CANCEL}
    }
)
async def cancel_background_job(
    job_id: str,
    user: dict = Depends(get_current_user)
):
    """Cancelar um job em execução."""
    job = background_processes.get(job_id)
    
    if not job:
        job = await db.background_jobs.find_one({"id": job_id}, {"_id": 0})
    
    if not job:
        raise HTTPException(status_code=404, detail=ERROR_JOB_NOT_FOUND)
    
    if job.get("status") != "running":
        raise HTTPException(status_code=400, detail=ERROR_ONLY_RUNNING_JOBS_CAN_CANCEL)
    
    update_data = {
        "status": "cancelled",
        "message": "Cancelado pelo utilizador",
        "finished_at": datetime.now(timezone.utc).isoformat()
    }
    
    if job_id in background_processes:
        background_processes[job_id].update(update_data)
    
    await db.background_jobs.update_one(
        {"id": job_id},
        {"$set": update_data}
    )
    
    return {
        "success": True,
        "message": f"Job {job_id} cancelado",
        "status": "cancelled"
    }


@router.post("/background-jobs/cleanup-stuck")
async def cleanup_stuck_jobs(
    hours: int = Query(2, ge=1, le=24),
    user: dict = Depends(get_current_user)
):
    """Limpar jobs stuck há mais de X horas."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    stuck_jobs = await db.background_jobs.find({
        "status": {"$in": ["running", "pending"]},
        "$or": [
            {"updated_at": {"$lt": cutoff.isoformat()}},
            {"updated_at": None, "started_at": {"$lt": cutoff.isoformat()}}
        ]
    }, {"_id": 0, "id": 1}).to_list(100)
    
    cleaned = 0
    for job in stuck_jobs:
        await finish_background_job_db(job["id"], False, f"Limpo automaticamente (stuck > {hours}h)")
        cleaned += 1
    
    return {"cleaned": cleaned}


@router.delete("/background-jobs")
async def clear_finished_jobs(
    user: dict = Depends(get_current_user)
):
    """Remove jobs terminados."""
    result = await db.background_jobs.delete_many({
        "status": {"$in": ["success", "failed", "cancelled"]}
    })
    
    to_remove = [k for k, v in background_processes.items() 
                 if v.get("status") in ["success", "failed", "cancelled"]]
    for k in to_remove:
        del background_processes[k]
    
    return {"deleted": result.deleted_count + len(to_remove)}


# ====================================================================
# ENDPOINTS DE IMPORT ERRORS
# ====================================================================

@router.get("/import-errors")
async def get_import_errors(
    limit: int = 100,
    document_type: Optional[str] = None,
    resolved: Optional[bool] = None,
    user: dict = Depends(get_current_user)
):
    """Obter lista de erros de importação."""
    query = {}
    
    if document_type:
        query["document_type"] = document_type
    if resolved is not None:
        query["resolved"] = resolved
    
    errors = await db.import_errors.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1).to_list(length=limit)
    
    error_summary = {}
    for err in errors:
        error_key = err.get("error", "Desconhecido")[:100]
        if error_key not in error_summary:
            error_summary[error_key] = {
                "count": 0,
                "document_types": set(),
                "clients": set()
            }
        error_summary[error_key]["count"] += 1
        error_summary[error_key]["document_types"].add(err.get("document_type", "?"))
        error_summary[error_key]["clients"].add(err.get("client_name", "?"))
    
    for key in error_summary:
        error_summary[key]["document_types"] = list(error_summary[key]["document_types"])
        error_summary[key]["clients"] = list(error_summary[key]["clients"])[:5]
    
    return {
        "total_errors": len(errors),
        "errors": errors,
        "summary": error_summary
    }


@router.post("/import-errors/{error_id}/resolve")
async def resolve_import_error(
    error_id: str,
    user: dict = Depends(get_current_user)
):
    """Marcar um erro de importação como resolvido."""
    result = await db.import_errors.update_one(
        {"id": error_id},
        {"$set": {"resolved": True, "resolved_by": user.get("email"), "resolved_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count > 0:
        return {"success": True, "message": "Erro marcado como resolvido"}
    else:
        return {"success": False, "message": "Erro não encontrado"}


# ====================================================================
# ENDPOINTS DE SUGESTÕES E CLIENTES
# ====================================================================

@router.get("/suggest-clients")
async def suggest_clients_endpoint(
    query: str,
    limit: int = 5,
    user: dict = Depends(get_current_user)
):
    """Retornar clientes similares para selecção manual."""
    if not query or len(query) < 2:
        return {
            "query": query,
            "suggestions": [],
            "message": "Query deve ter pelo menos 2 caracteres"
        }
    
    limit = min(limit, 10)
    suggestions = await suggest_similar_clients(query, limit)
    
    return {
        "query": query,
        "total_matches": len(suggestions),
        "suggestions": suggestions
    }


@router.get("/check-client")
async def check_client_exists(
    name: str,
    user: dict = Depends(get_current_user)
):
    """Verificar se um cliente existe pelo nome."""
    if not name:
        return {"exists": False, "client": None}
    
    process = await find_client_by_name(name)
    
    if process:
        return {
            "exists": True,
            "client": {
                "id": process.get("id"),
                "name": process.get("client_name"),
                "number": process.get("process_number")
            }
        }
    
    return {"exists": False, "client": None}


@router.get("/clients-list")
async def get_clients_list(
    user: dict = Depends(get_current_user)
):
    """Obter lista de clientes para referência no upload."""
    clients = await db.processes.find(
        {},
        {"_id": 0, "id": 1, "client_name": 1, "process_number": 1}
    ).sort("client_name", 1).to_list(None)
    
    return {
        "total": len(clients),
        "clients": [
            {
                "id": c.get("id"),
                "name": c.get("client_name"),
                "number": c.get("process_number")
            }
            for c in clients
        ]
    }


@router.get("/diagnose-client/{client_name}")
async def diagnose_client_data(
    client_name: str,
    user: dict = Depends(get_current_user)
):
    """Diagnóstico de dados de um cliente."""
    process = await find_client_by_name(client_name)
    
    if not process:
        return {
            "found": False,
            "error": f"Cliente '{client_name}' não encontrado"
        }
    
    personal = process.get("personal_data", {})
    financial = process.get("financial_data", {})
    real_estate = process.get("real_estate_data", {})
    
    def count_filled(data: dict) -> Tuple[int, int, list]:
        if not data:
            return 0, 0, []
        filled = [(k, v) for k, v in data.items() if v is not None and v != ""]
        return len(filled), len(data), [k for k, _ in filled]
    
    personal_filled, personal_total, personal_fields = count_filled(personal)
    financial_filled, financial_total, financial_fields = count_filled(financial)
    real_estate_filled, real_estate_total, real_estate_fields = count_filled(real_estate)
    
    co_buyers = process.get("co_buyers", [])
    co_applicants = process.get("co_applicants", [])
    
    result = {
        "found": True,
        "client_name": process.get("client_name"),
        "process_id": process.get("id"),
        "summary": {
            "personal_data": f"{personal_filled}/{personal_total} campos",
            "financial_data": f"{financial_filled}/{financial_total} campos",
            "real_estate_data": f"{real_estate_filled}/{real_estate_total} campos",
        },
        "filled_fields": {
            "personal": personal_fields,
            "financial": financial_fields,
            "real_estate": real_estate_fields,
        },
        "raw_data": {
            "email": process.get("client_email"),
            "phone": process.get("client_phone"),
            "personal_data": personal,
            "financial_data": financial,
        },
        "analyzed_documents": process.get("analyzed_documents", [])
    }
    
    if co_buyers:
        result["co_buyers"] = co_buyers
        result["summary"]["co_buyers"] = f"{len(co_buyers)} pessoa(s)"
    
    if co_applicants:
        result["co_applicants"] = co_applicants
        result["summary"]["co_applicants"] = f"{len(co_applicants)} pessoa(s)"
    
    return result


@router.get("/analyzed-documents/{process_id}")
async def get_analyzed_documents(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Listar documentos já analisados para um processo."""
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "client_name": 1, "analyzed_documents": 1}
    )
    
    if not process:
        return {"found": False, "error": "Processo não encontrado"}
    
    analyzed_docs = process.get("analyzed_documents", [])
    
    by_type = {}
    for doc in analyzed_docs:
        doc_type = doc.get("document_type", "outro")
        if doc_type not in by_type:
            by_type[doc_type] = []
        by_type[doc_type].append({
            "filename": doc.get("filename"),
            "analyzed_at": doc.get("analyzed_at"),
            "mes_referencia": doc.get("mes_referencia"),
            "fields_extracted": len(doc.get("fields_extracted", []))
        })
    
    return {
        "found": True,
        "client_name": process.get("client_name"),
        "total_documents": len(analyzed_docs),
        "by_type": by_type
    }


# ====================================================================
# ENDPOINTS DE CACHE
# ====================================================================

@router.post("/clear-duplicate-cache")
async def clear_duplicate_cache(
    user: dict = Depends(get_current_user)
):
    """Limpar cache de documentos duplicados."""
    global document_hash_cache
    count = sum(
        sum(len(hashes) for hashes in types.values())
        for types in document_hash_cache.values()
    )
    document_hash_cache = {}
    return {"message": f"Cache limpo. {count} documentos removidos do cache."}


@router.get("/nif-cache/stats")
async def get_nif_cache_stats(
    user: dict = Depends(get_current_user)
):
    """Obter estatísticas do cache de sessão NIF."""
    now = datetime.now(timezone.utc)
    db_count = await db.nif_mappings.count_documents({})
    
    stats = {
        "total_entries_memory": len(nif_session_cache),
        "total_entries_db": db_count,
        "ttl_days": NIF_CACHE_TTL_SECONDS // 86400,
        "entries": []
    }
    
    for folder_key, cached in nif_session_cache.items():
        matched_at = cached.get("matched_at")
        if isinstance(matched_at, str):
            matched_at = datetime.fromisoformat(matched_at.replace("Z", "+00:00"))
        
        age_seconds = (now - matched_at).total_seconds() if matched_at else 0
        
        stats["entries"].append({
            "folder": folder_key,
            "nif": cached.get("nif"),
            "client_name": cached.get("client_name"),
            "age_days": round(age_seconds / 86400, 1),
            "expires_in_days": max(0, round((NIF_CACHE_TTL_SECONDS - age_seconds) / 86400, 1))
        })
    
    return stats


@router.post("/nif-cache/clear")
async def clear_nif_cache_endpoint(
    user: dict = Depends(get_current_user)
):
    """Limpar todo o cache de sessão NIF."""
    global nif_session_cache
    
    memory_count = len(nif_session_cache)
    nif_session_cache = {}
    
    db_result = await db.nif_mappings.delete_many({})
    db_count = db_result.deleted_count
    
    logger.info(f"[NIF CACHE] Cache limpo manualmente. Memória: {memory_count}, DB: {db_count}")
    return {
        "message": f"Cache NIF limpo. {memory_count} mapeamentos removidos da memória, {db_count} da base de dados."
    }


@router.post("/nif-cache/add-mapping")
async def add_nif_mapping_manual(
    folder_name: str,
    nif: str,
    user: dict = Depends(get_current_user)
):
    """Adicionar mapeamento NIF → Cliente manualmente."""
    process = await find_client_by_nif(nif)
    
    if not process:
        process = await find_client_by_name(folder_name)
        
        if process:
            await db.processes.update_one(
                {"id": process["id"]},
                {"$set": {"personal_data.nif": nif, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            logger.info("[NIF] NIF adicionado ao cliente")
        else:
            return {
                "success": False,
                "error": "Nenhum cliente encontrado com o NIF ou nome fornecido"
            }
    
    await cache_nif_mapping(
        folder_name=folder_name,
        nif=nif,
        process_id=process["id"],
        client_name=process.get("client_name")
    )
    
    return {
        "success": True,
        "message": f"Mapeamento adicionado: '{folder_name}' -> NIF {nif} -> '{process.get('client_name')}'"
    }


# ====================================================================
# INCLUIR ROUTER DE BACKGROUND JOBS
# ====================================================================
from routes.ai_bulk.background_jobs import router as background_jobs_router
router.include_router(background_jobs_router)
