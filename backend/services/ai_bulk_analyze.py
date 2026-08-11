"""Single-file and aggregated-file analysis handlers for AI bulk import.

Extraído de `routes/ai_bulk.py`.
"""
from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import Optional

from fastapi import HTTPException, UploadFile

from database import db
from routes.ai_bulk.cache import (
    cache_document_analysis,
    cache_nif_mapping,
    cc_cache,
    check_duplicate_comprehensive,
    clear_expired_nif_cache,
    get_cached_nif_mapping,
    persist_document_analysis,
)
from routes.ai_bulk.constants import (
    DOCUMENT_TYPE_TO_CATEGORY,
    ERROR_AGGREGATION_SESSION_NOT_FOUND,
    MSG_DUPLICATE_DOCUMENT_CACHED,
    MSG_DUPLICATE_DOCUMENT_IGNORED,
)
from routes.ai_bulk.matching import find_client_by_name
from routes.ai_bulk.utils import get_normalized_filename, is_cc_frente_or_verso
from services.ai_bulk_helpers import (
    log_import_error,
    log_import_result,
    read_file_with_limit,
    update_client_data,
)
from services.ai_bulk_models import AggregatedFileResult, SingleAnalysisResult
from services.ai_document import (
    analyze_document_from_base64,
    analyze_single_document,
    detect_document_type,
    get_mime_type,
    merge_images_to_pdf,
)
from services.documents.data_aggregator import get_session_async, persist_session_to_db
from services.file_validation import validate_file_content
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


async def run_analyze_file_aggregated(
    session_id: str,
    file: UploadFile,
    user: dict,
    force_client_id: Optional[str] = None,
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



async def run_analyze_single_file(
    file: UploadFile,
    user: dict,
    force_client_id: Optional[str] = None,
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
