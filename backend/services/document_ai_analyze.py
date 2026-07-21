"""
Análise IA multi-documento + organização pós-análise em pastas S3.

Extraído de `routes/documents.py` (`ai_analyze_documents`,
`organize_documents_after_analysis`).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import HTTPException, UploadFile

from database import db
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    ERROR_NO_VALID_FILES,
    ERROR_PROCESS_NOT_FOUND,
)
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

# Mapeamento tipo IA → pasta S3 (alinhado com ai_document_analyzer)
DOCUMENT_TYPE_FOLDERS = {
    "cc": "Identificação",
    "bi": "Identificação",
    "passport": "Identificação",
    "cartao_cidadao": "Identificação",
    "nif": "Identificação",
    "comprovativo_morada": "Morada",
    "irs": "Financeiros",
    "declaracao_irs": "Financeiros",
    "nota_liquidacao": "Financeiros",
    "recibo_vencimento": "Financeiros",
    "extrato_bancario": "Bancários",
    "comprovativo_poupanca": "Bancários",
    "mapa_responsabilidades": "Bancários",
    "caderneta_predial": "Imóvel",
    "certidao_teor": "Imóvel",
    "certidao_permanente": "Imóvel",
    "licenca_habitacao": "Imóvel",
    "licenca_utilizacao": "Imóvel",
    "plantas": "Imóvel",
    "planta": "Imóvel",
    "ficha_tecnica": "Imóvel",
    "certificado_energetico": "Imóvel",
    "contrato": "Outros",
    "procuracao": "Outros",
    "cpcv": "CPCV",
    "contrato_promessa": "CPCV",
    "escritura": "Escritura",
    "simulacao": "Simulações",
    "proposta": "Propostas",
    "minuta": "Minutas",
    "default": "Outros",
}

STANDARD_ORGANIZE_FOLDERS = [
    "Identificação",
    "Financeiros",
    "Bancários",
    "Morada",
    "Imóvel",
    "CPCV",
    "Simulações",
    "Propostas",
    "Minutas",
    "Escritura",
    "Outros",
]


def build_existing_data_for_ai_compare(process: dict) -> dict:
    """Flatten process nested fields → shape esperado pelo analyzer."""
    personal = process.get("personal_data", {}) or {}
    financial = process.get("financial_data", {}) or {}
    real_estate = process.get("real_estate_data", {}) or {}
    return {
        "client_name": process.get("client_name"),
        "nif": personal.get("nif") or process.get("client_nif") or process.get("nif"),
        "birth_date": personal.get("data_nascimento") or process.get("data_nascimento"),
        "documento_id": personal.get("documento_id") or process.get("cc_number"),
        "cc_number": personal.get("documento_id") or process.get("cc_number"),
        "cc_validity": personal.get("cc_validity") or process.get("validade_cc"),
        "nationality": personal.get("nacionalidade"),
        "gender": personal.get("sexo"),
        "address": personal.get("morada"),
        "fiscal_address": personal.get("morada_fiscal"),
        "phone": personal.get("telefone") or process.get("phone"),
        "email": personal.get("email") or process.get("client_email"),
        "estado_civil": personal.get("estado_civil"),
        "rendimento_mensal": financial.get("rendimento_mensal")
        or financial.get("renda_habitacao_atual"),
        "rendimento_bruto": financial.get("rendimento_bruto"),
        "salario_liquido": financial.get("rendimento_mensal")
        or financial.get("renda_habitacao_atual"),
        "salario_bruto": financial.get("rendimento_bruto"),
        "empresa": financial.get("empresa") or financial.get("employer_name"),
        "tipo_contrato": financial.get("tipo_contrato")
        or ("sim" if financial.get("efetivo") == "sim" else None),
        "valor_imovel": real_estate.get("valor_imovel"),
        "localizacao": real_estate.get("localizacao"),
        "tipologia": real_estate.get("tipologia"),
        "area": real_estate.get("area"),
    }


def process_ai_analyze_results(
    results: Optional[dict],
    documents: list[dict],
) -> tuple[dict, list, list]:
    """
    Deriva extracted_data, conflicts e document_types a partir do analyzer.

    Returns:
        (extracted_data, conflicts, document_types)
    """
    extracted_data: dict = {}
    conflicts: list = []
    document_types: list = []

    if not results or not isinstance(results, dict):
        return extracted_data, conflicts, document_types

    auto_fill = results.get("auto_fill_suggestions", {})
    for field, suggestion in auto_fill.items():
        value = suggestion.get("value")
        if value is not None and str(value).strip():
            extracted_data[field] = value
            if suggestion.get("type") == "override":
                current_val = suggestion.get("current_value")
                if current_val:
                    conflicts.append(
                        {
                            "field": field,
                            "existing_value": current_val,
                            "new_value": value,
                            "source": suggestion.get("source", "documento"),
                            "type": "override",
                        }
                    )

    comparison = results.get("comparison", {})
    for empty_field in comparison.get("empty_fields", []):
        field = empty_field.get("field")
        suggested = empty_field.get("suggested_value")
        if field and suggested and field not in extracted_data:
            extracted_data[field] = suggested

    for doc_result in results.get("documents_analyzed", []):
        doc_type = (
            doc_result.get("tipo_documento")
            or doc_result.get("type")
            or doc_result.get("document_type")
        )
        file_name = doc_result.get("file_name", "")
        if doc_type:
            source_path = None
            for orig_doc in documents:
                if orig_doc.get("name") == file_name:
                    source_path = orig_doc.get("source_path")
                    break
            document_types.append(
                {
                    "file_name": file_name,
                    "type": doc_type,
                    "confidence": doc_result.get("confianca", 0.5),
                    "source_path": source_path,
                }
            )

    return extracted_data, conflicts, document_types


async def _read_upload_files(files: list[UploadFile]) -> list[dict]:
    documents = []
    for file in files:
        try:
            content = await file.read()
            if len(content) == 0:
                continue
            documents.append(
                {
                    "content": content,
                    "name": file.filename,
                    "mime_type": file.content_type or "application/octet-stream",
                }
            )
        except Exception as e:
            logger.warning(f"Erro ao ler ficheiro {file.filename}: {e}")
            continue
    return documents


async def run_ai_analyze_documents(
    process_id: str,
    files: list[UploadFile],
    *,
    user: dict,
) -> dict[str, Any]:
    """Analisa múltiplos documentos com IA e devolve comparação/sugestões."""
    start_time = time.time()

    try:
        from services.ai_document_analyzer import analyze_multiple_documents
    except ImportError as e:
        logger.error(f"Erro ao importar ai_document_analyzer: {e}")
        raise HTTPException(
            status_code=500, detail=f"Serviço de análise não disponível: {str(e)}"
        )

    try:
        from routes.ai_import_logs import create_ai_import_log, finalize_ai_import_log
    except ImportError as e:
        logger.warning(f"ai_import_logs não disponível: {e}")
        create_ai_import_log = None
        finalize_ai_import_log = None

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)

    log_id = None
    if create_ai_import_log:
        try:
            log_id = await create_ai_import_log(
                process_id=process_id,
                client_name=client_name,
                created_by=user.get("id"),
                created_by_name=user.get("name"),
            )
        except Exception as e:
            logger.warning(f"Erro ao criar log de importação: {e}")

    documents = await _read_upload_files(files)
    if not documents:
        if log_id and finalize_ai_import_log:
            try:
                await finalize_ai_import_log(log_id, duration_ms=0)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=ERROR_NO_VALID_FILES)

    existing_data = build_existing_data_for_ai_compare(process)

    try:
        results = await analyze_multiple_documents(
            documents, existing_data, log_id=log_id
        )
    except Exception as e:
        logger.error(f"Erro na análise de documentos: {e}", exc_info=True)
        total_duration = int((time.time() - start_time) * 1000)
        if log_id and finalize_ai_import_log:
            try:
                await finalize_ai_import_log(log_id, duration_ms=total_duration)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Erro na análise: {str(e)}")

    extracted_data, conflicts, document_types = process_ai_analyze_results(
        results, documents
    )

    total_duration = int((time.time() - start_time) * 1000)
    if log_id and finalize_ai_import_log:
        try:
            await finalize_ai_import_log(log_id, duration_ms=total_duration)
        except Exception as e:
            logger.warning(f"Erro ao finalizar log: {e}")

    return {
        "success": True,
        "process_id": process_id,
        "client_name": client_name,
        "documents_count": len(documents),
        "log_id": log_id,
        "extracted_data": extracted_data,
        "field_confidence": results.get("field_confidence", {}) if results else {},
        "conflicts": conflicts,
        "documents": document_types,
        "suggestions": list(extracted_data.keys()),
        "analysis": results,
    }


def _ensure_standard_folders(base_path: str, results: dict) -> None:
    for folder in STANDARD_ORGANIZE_FOLDERS:
        try:
            folder_key = f"{base_path}/{folder}/.keep"
            try:
                s3_service.s3_client.head_object(
                    Bucket=s3_service.bucket_name, Key=folder_key
                )
            except (KeyError, AttributeError):
                s3_service.s3_client.put_object(
                    Bucket=s3_service.bucket_name, Key=folder_key, Body=b""
                )
                results["folders_created"].append(folder)
            except Exception as e:
                if "NotFound" in str(type(e).__name__) or "404" in str(e):
                    s3_service.s3_client.put_object(
                        Bucket=s3_service.bucket_name, Key=folder_key, Body=b""
                    )
                    results["folders_created"].append(folder)
                else:
                    raise
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            logger.warning(f"Erro ao criar pasta {folder}: {e}")


async def run_organize_documents_after_analysis(
    process_id: str,
    *,
    documents: list[dict],
    create_folders: bool = True,
) -> dict[str, Any]:
    """Cria pastas standard e move ficheiros S3 conforme tipo IA."""
    process = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, "client_name": 1}
    )
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    results = {"organized": [], "errors": [], "folders_created": []}
    base_path = None

    if create_folders and s3_service.is_configured():
        base_path = s3_service._get_client_base_path_for_upload(
            process_id, client_name, None
        )
        logger.info(f"Organizar documentos: usando pasta {base_path} para {client_name}")
        _ensure_standard_folders(base_path, results)

    if s3_service.is_configured():
        if base_path is None:
            base_path = s3_service._get_client_base_path_for_upload(
                process_id, client_name, None
            )
        for doc in documents:
            try:
                doc_type = (doc.get("type") or "").lower()
                file_name = doc.get("file_name", "")
                source_path = doc.get("source_path")
                if not file_name:
                    continue

                target_folder = DOCUMENT_TYPE_FOLDERS.get(
                    doc_type, DOCUMENT_TYPE_FOLDERS["default"]
                )
                moved = False
                if source_path and base_path:
                    target_path = f"{base_path}/{target_folder}/{file_name}"
                    if source_path.endswith(f"/{target_folder}/{file_name}"):
                        logger.info(
                            f"Ficheiro já está na pasta correcta: {file_name}"
                        )
                        moved = True
                    else:
                        try:
                            moved = s3_service.rename_file(source_path, target_path)
                            if moved:
                                logger.info(
                                    f"Ficheiro movido: {source_path} -> {target_path}"
                                )
                        except Exception as move_err:
                            logger.warning(
                                f"Erro ao mover {file_name}: {move_err}"
                            )

                results["organized"].append(
                    {
                        "file": file_name,
                        "type": doc_type,
                        "folder": target_folder,
                        "moved": moved,
                        "source_path": source_path,
                    }
                )
            except (IOError, OSError, ValueError, KeyError, TypeError) as e:
                results["errors"].append(
                    {"file": doc.get("file_name", "?"), "error": str(e)}
                )

    return {
        "success": True,
        "organized_count": len(results["organized"]),
        "folders_created_count": len(results["folders_created"]),
        "results": results,
    }


# Frontend field → Mongo dot-path for apply-suggestions
AI_SUGGESTION_FIELD_MAP = {
    "client_name": "client_name",
    "nif": "personal_data.nif",
    "documento_id": "personal_data.documento_id",
    "cc_number": "personal_data.documento_id",
    "birth_date": "personal_data.data_nascimento",
    "cc_validity": "personal_data.cc_validity",
    "nationality": "personal_data.nacionalidade",
    "gender": "personal_data.sexo",
    "address": "personal_data.morada",
    "fiscal_address": "personal_data.morada_fiscal",
    "estado_civil": "personal_data.estado_civil",
    "rendimento_mensal": "financial_data.rendimento_mensal",
    "salario_liquido": "financial_data.rendimento_mensal",
    "rendimento_bruto": "financial_data.rendimento_bruto",
    "salario_bruto": "financial_data.rendimento_bruto",
    "empresa": "financial_data.empresa",
    "entidade_empregadora": "financial_data.empresa",
    "tipo_contrato": "financial_data.tipo_contrato",
    "categoria_profissional": "financial_data.categoria_profissional",
    "subsidiario_alimentacao": "financial_data.subsidiario_alimentacao",
    "valor_imovel": "real_estate_data.valor_imovel",
    "localizacao": "real_estate_data.localizacao",
    "tipologia": "real_estate_data.tipologia",
    "area": "real_estate_data.area",
    "artigo_matricial": "real_estate_data.artigo_matricial",
}


def map_ai_suggestions_to_mongo_update(suggestions: dict) -> dict:
    """Converte sugestões frontend → campos com dot-notation Mongo."""
    update_data = {}
    for field, value in suggestions.items():
        if field in AI_SUGGESTION_FIELD_MAP:
            update_data[AI_SUGGESTION_FIELD_MAP[field]] = value
    return update_data


async def run_apply_ai_suggestions(
    process_id: str,
    suggestions: dict | None,
    *,
    user: dict,
) -> dict[str, Any]:
    """Aplica sugestões IA aos subdocumentos do processo (com ACL)."""
    from datetime import datetime, timezone

    from services.document_constants import ERROR_NO_SUGGESTIONS
    from services.document_filenames import sanitize_for_log
    from services.process_service import can_edit_process_data

    if not suggestions:
        raise HTTPException(status_code=400, detail=ERROR_NO_SUGGESTIONS)

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    can_edit, reason = can_edit_process_data(user, process)
    if not can_edit:
        logger.warning(
            f"IDOR attempt: User {user.get('id')} ({user.get('role')}) "
            f"tried to apply AI suggestions on process {process_id}: {reason}"
        )
        raise HTTPException(
            status_code=403,
            detail=f"Não tem permissões para alterar este processo. {reason}",
        )

    update_data = map_ai_suggestions_to_mongo_update(suggestions)
    if not update_data:
        return {
            "success": True,
            "updated_fields": 0,
            "message": "Nenhum campo válido para atualizar",
        }

    mongo_update = dict(update_data)
    mongo_update["updated_at"] = datetime.now(timezone.utc).isoformat()
    mongo_update["updated_by"] = user.get("id")

    await db.processes.update_one({"id": process_id}, {"$set": mongo_update})
    logger.info(
        f"Campos atualizados via IA para processo: {sanitize_for_log(process_id)}"
    )
    return {
        "success": True,
        "updated_fields": len(update_data),
        "fields": list(update_data.keys()),
    }


async def run_organize_files_in_folders(
    process_id: str,
    organization: list[dict] | None,
) -> dict[str, Any]:
    """Move ficheiros S3 conforme lista {source_path, target_folder, file_name}."""
    from services.document_constants import ERROR_NO_ORGANIZATION

    if not organization:
        raise HTTPException(status_code=400, detail=ERROR_NO_ORGANIZATION)

    process = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, "client_name": 1}
    )
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    results = {"moved": [], "errors": []}

    for item in organization:
        try:
            source_path = item.get("source_path")
            target_folder = item.get("target_folder")
            file_name = item.get("file_name")
            if not all([source_path, target_folder, file_name]):
                results["errors"].append(
                    {"file": file_name, "error": "Dados incompletos"}
                )
                continue
            success = s3_service.move_file(
                source_path, client_name, target_folder, file_name
            )
            if success:
                results["moved"].append({"file": file_name, "to": target_folder})
            else:
                results["errors"].append(
                    {"file": file_name, "error": "Falha ao mover"}
                )
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            results["errors"].append(
                {"file": item.get("file_name", "?"), "error": str(e)}
            )

    return {
        "success": True,
        "moved_count": len(results["moved"]),
        "error_count": len(results["errors"]),
        "results": results,
    }
