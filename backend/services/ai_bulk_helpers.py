"""Shared helpers for AI bulk import handlers.

Extraído de `routes/ai_bulk.py`. Prefer `ai_bulk_*` — leave
`routes/ai_bulk/*` package helpers (cache/jobs/matching/utils) in place.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile

from database import db
from routes.ai_bulk.constants import (
    CHUNK_SIZE,
    ERROR_PROCESS_NOT_FOUND,
    REASON_MANUALLY_EDITED,
)
from routes.ai_bulk.utils import categorize_extracted_fields, validate_nif
from services.ai_document import MAX_FILE_SIZE, build_update_data_from_extraction

logger = logging.getLogger(__name__)


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

