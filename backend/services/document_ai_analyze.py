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
    """Flatten process nested fields → shape esperado pelo analyzer.

    Income uses monthly_income / rendimento_mensal — never renda_habitacao_atual
    (that field is housing rent, not salary).
    """
    personal = process.get("personal_data", {}) or {}
    financial = process.get("financial_data", {}) or {}
    real_estate = process.get("real_estate_data", {}) or {}
    # Canonical income on ProcessDetails form is monthly_income
    income = (
        financial.get("monthly_income")
        or financial.get("rendimento_mensal")
        or financial.get("salario_liquido")
    )
    employer = financial.get("employer_name") or financial.get("empresa")
    return {
        "client_name": process.get("client_name"),
        "nif": personal.get("nif") or process.get("client_nif") or process.get("nif"),
        "birth_date": personal.get("data_nascimento") or process.get("data_nascimento"),
        "documento_id": personal.get("documento_id") or process.get("cc_number"),
        "cc_number": personal.get("documento_id") or process.get("cc_number"),
        "cc_validity": personal.get("cc_validity")
        or personal.get("data_validade_cc")
        or process.get("validade_cc"),
        "nationality": personal.get("nacionalidade"),
        "gender": personal.get("sexo"),
        "address": personal.get("morada"),
        "fiscal_address": personal.get("morada_fiscal"),
        "phone": personal.get("telefone") or process.get("phone"),
        "email": personal.get("email") or process.get("client_email"),
        "estado_civil": personal.get("estado_civil"),
        "monthly_income": income,
        "rendimento_mensal": income,
        "salario_liquido": income,
        "rendimento_bruto": financial.get("rendimento_bruto")
        or financial.get("salario_bruto"),
        "salario_bruto": financial.get("rendimento_bruto")
        or financial.get("salario_bruto"),
        "employer_name": employer,
        "empresa": employer,
        "tipo_contrato": financial.get("tipo_contrato")
        or financial.get("employment_type")
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


def should_skip_ai_analysis(metadata: dict | None) -> bool:
    """Docs já analisados pela IA (extração) não precisam de nova análise."""
    return bool(metadata and metadata.get("ai_analyzed"))


def resolve_ai_category_from_doc_type(doc_type: str | None) -> tuple[str, str]:
    """Mapeia tipo detectado pela IA → (categoria pasta, subcategoria legível)."""
    raw = (doc_type or "").strip().lower()
    if not raw:
        return ("Outros", "Documento")
    folder = DOCUMENT_TYPE_FOLDERS.get(raw, DOCUMENT_TYPE_FOLDERS["default"])
    subcategory = raw.replace("_", " ").strip().title() or "Documento"
    return (folder, subcategory)


async def _read_upload_files(
    files: list[UploadFile],
    file_paths: list[str] | None = None,
) -> list[dict]:
    documents = []
    for idx, file in enumerate(files):
        try:
            content = await file.read()
            if len(content) == 0:
                continue
            source_path = None
            if file_paths and idx < len(file_paths):
                path = (file_paths[idx] or "").strip()
                source_path = path or None
            documents.append(
                {
                    "content": content,
                    "name": file.filename,
                    "mime_type": file.content_type or "application/octet-stream",
                    "source_path": source_path,
                }
            )
        except Exception as e:
            logger.warning(f"Erro ao ler ficheiro {file.filename}: {e}")
            continue
    return documents


async def _filter_already_analyzed_documents(
    process_id: str,
    documents: list[dict],
) -> tuple[list[dict], int]:
    """Remove docs com ai_analyzed=True (por s3_path)."""
    paths = [d.get("source_path") for d in documents if d.get("source_path")]
    if not paths:
        return documents, 0

    analyzed_paths: set[str] = set()
    cursor = db.document_metadata.find(
        {
            "process_id": process_id,
            "s3_path": {"$in": paths},
            "ai_analyzed": True,
        },
        {"_id": 0, "s3_path": 1},
    )
    async for meta in cursor:
        if meta.get("s3_path"):
            analyzed_paths.add(meta["s3_path"])

    if not analyzed_paths:
        return documents, 0

    pending = [
        d
        for d in documents
        if not d.get("source_path") or d["source_path"] not in analyzed_paths
    ]
    skipped = len(documents) - len(pending)
    return pending, skipped


async def _build_titular_matches_for_analysis(
    process: dict,
    extracted_data: dict,
    document_types: list[dict],
    results: Optional[dict],
) -> list[dict]:
    """Compara extracao IA com titular 1 e 2 já definidos no processo."""
    from services.document_titular_match import (
        build_titular_identity_snapshot,
        resolve_titular_match,
    )
    from services.encryption import decrypt_client_data

    client_id = process.get("client_id")
    second_id = process.get("second_client_id")
    titular2_data = process.get("titular2_data") or {}

    personal1 = process.get("personal_data") or {}
    if client_id:
        c1 = await db.clients.find_one({"id": client_id}, {"_id": 0})
        if c1:
            try:
                c1 = decrypt_client_data(c1)
            except Exception:
                pass
            personal1 = {**(c1.get("dados_pessoais") or {}), **personal1}

    titular1 = build_titular_identity_snapshot(
        label="titular1",
        client_id=client_id,
        name=process.get("client_name"),
        personal=personal1,
    )

    titular2 = None
    has_t2 = bool(
        second_id
        or titular2_data.get("name")
        or titular2_data.get("nome")
        or titular2_data.get("email")
    )
    if has_t2:
        personal2 = {}
        t2_name = (
            process.get("second_client_name")
            or titular2_data.get("name")
            or titular2_data.get("nome")
        )
        if second_id:
            c2 = await db.clients.find_one({"id": second_id}, {"_id": 0})
            if c2:
                try:
                    c2 = decrypt_client_data(c2)
                except Exception:
                    pass
                personal2 = c2.get("dados_pessoais") or {}
                t2_name = t2_name or c2.get("nome")
        titular2 = build_titular_identity_snapshot(
            label="titular2",
            client_id=second_id,
            name=t2_name,
            personal=personal2,
            titular2_data=titular2_data,
        )

    matches: list[dict] = []
    analyzed_docs = (results or {}).get("documents_analyzed") or []

    # Um match global com extracted_data agregado + um por documento quando possível
    global_match = resolve_titular_match(extracted_data or {}, titular1, titular2)
    matches.append(
        {
            "scope": "process_aggregate",
            "file_name": None,
            **global_match,
            "titular1_name": titular1.get("name"),
            "titular2_name": (titular2 or {}).get("name") if titular2 else None,
            "has_second_titular": bool(titular2),
        }
    )

    for doc_result in analyzed_docs:
        file_name = doc_result.get("file_name") or ""
        # Prefer fields inside doc_result / dados_extraidos
        doc_extracted = {}
        if isinstance(doc_result.get("dados_extraidos"), dict):
            doc_extracted.update(doc_result["dados_extraidos"])
        for key in ("nif", "nome", "client_name", "documento_id", "cc_number", "name"):
            if doc_result.get(key):
                doc_extracted[key] = doc_result[key]
        if not doc_extracted:
            doc_extracted = extracted_data or {}
        m = resolve_titular_match(doc_extracted, titular1, titular2)
        matches.append(
            {
                "scope": "document",
                "file_name": file_name,
                **m,
                "titular1_name": titular1.get("name"),
                "titular2_name": (titular2 or {}).get("name") if titular2 else None,
                "has_second_titular": bool(titular2),
            }
        )

    return matches


async def _mark_documents_ai_analyzed(
    process_id: str,
    client_name: str,
    documents: list[dict],
    document_types: list[dict],
) -> int:
    """Persiste ai_analyzed (+ categorização leve) após análise com sucesso."""
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    type_by_name = {
        (dt.get("file_name") or ""): dt for dt in (document_types or [])
    }
    marked = 0

    for doc in documents:
        s3_path = doc.get("source_path")
        filename = doc.get("name") or ""
        if not s3_path:
            # Fallback: tentar pelo filename no processo
            existing_by_name = await db.document_metadata.find_one(
                {"process_id": process_id, "filename": filename},
                {"_id": 0, "s3_path": 1},
            )
            s3_path = (existing_by_name or {}).get("s3_path")
        if not s3_path:
            continue

        type_info = type_by_name.get(filename) or {}
        doc_type = type_info.get("type")
        category, subcategory = resolve_ai_category_from_doc_type(doc_type)
        confidence = type_info.get("confidence")

        existing = await db.document_metadata.find_one(
            {"s3_path": s3_path}, {"_id": 0, "id": 1}
        )
        update_fields: dict[str, Any] = {
            "process_id": process_id,
            "client_name": client_name,
            "s3_path": s3_path,
            "filename": filename,
            "ai_analyzed": True,
            "ai_analyzed_at": now,
            "updated_at": now,
        }
        # Categorização leve para permitir Renomear IA depois
        if doc_type:
            update_fields["ai_category"] = category
            update_fields["ai_subcategory"] = subcategory
            update_fields["is_categorized"] = True
            update_fields["categorized_at"] = now
            if confidence is not None:
                update_fields["ai_confidence"] = confidence

        if existing and existing.get("id"):
            await db.document_metadata.update_one(
                {"id": existing["id"]},
                {"$set": update_fields},
            )
        else:
            update_fields["id"] = str(uuid.uuid4())
            update_fields["created_at"] = now
            await db.document_metadata.insert_one(update_fields)
        marked += 1

    return marked


async def run_ai_analyze_documents(
    process_id: str,
    files: list[UploadFile],
    *,
    user: dict,
    file_paths: list[str] | None = None,
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

    documents = await _read_upload_files(files, file_paths=file_paths)
    documents, skipped_analyzed = await _filter_already_analyzed_documents(
        process_id, documents
    )

    if not documents:
        if log_id and finalize_ai_import_log:
            try:
                await finalize_ai_import_log(log_id, duration_ms=0)
            except Exception:
                pass
        if skipped_analyzed > 0:
            return {
                "success": True,
                "process_id": process_id,
                "client_name": client_name,
                "documents_count": 0,
                "skipped_already_analyzed": skipped_analyzed,
                "log_id": log_id,
                "extracted_data": {},
                "field_confidence": {},
                "conflicts": [],
                "documents": [],
                "suggestions": [],
                "analysis": None,
                "message": "Todos os documentos seleccionados já foram analisados pela IA",
            }
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

    # Match titular 1 vs 2 (2.º titular já definido no processo)
    titular_matches = await _build_titular_matches_for_analysis(
        process, extracted_data, document_types, results
    )

    try:
        marked = await _mark_documents_ai_analyzed(
            process_id, client_name, documents, document_types
        )
    except Exception as e:
        logger.warning(f"Erro ao marcar documentos como analisados: {e}")
        marked = 0

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
        "skipped_already_analyzed": skipped_analyzed,
        "marked_analyzed": marked,
        "log_id": log_id,
        "extracted_data": extracted_data,
        "field_confidence": results.get("field_confidence", {}) if results else {},
        "conflicts": conflicts,
        "documents": document_types,
        "suggestions": list(extracted_data.keys()),
        "analysis": results,
        "titular_matches": titular_matches,
        "needs_titular_choice": any(
            m.get("needs_user_choice") for m in titular_matches
        ),
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


# Frontend / analyzer field → Mongo dot-path for apply-suggestions
# Align with ProcessDetails canonical fields (monthly_income, employer_name).
# Never map salary/income → renda_habitacao_atual (that is housing rent).
AI_SUGGESTION_FIELD_MAP = {
    "client_name": "client_name",
    "nif": "personal_data.nif",
    "documento_id": "personal_data.documento_id",
    "cc_number": "personal_data.documento_id",
    "birth_date": "personal_data.data_nascimento",
    "cc_validity": "personal_data.data_validade_cc",
    "data_validade_cc": "personal_data.data_validade_cc",
    "nationality": "personal_data.nacionalidade",
    "gender": "personal_data.sexo",
    "address": "personal_data.morada_fiscal",
    "fiscal_address": "personal_data.morada_fiscal",
    "estado_civil": "personal_data.estado_civil",
    "monthly_income": "financial_data.monthly_income",
    "rendimento_mensal": "financial_data.monthly_income",
    "salario_liquido": "financial_data.monthly_income",
    "rendimento_bruto": "financial_data.rendimento_bruto",
    "salario_bruto": "financial_data.rendimento_bruto",
    "employer_name": "financial_data.employer_name",
    "empresa": "financial_data.employer_name",
    "entidade_empregadora": "financial_data.employer_name",
    "tipo_contrato": "financial_data.tipo_contrato",
    "employment_type": "financial_data.tipo_contrato",
    "categoria_profissional": "financial_data.categoria_profissional",
    "subsidiario_alimentacao": "financial_data.subsidiario_alimentacao",
    "data_referencia": "financial_data.data_referencia",
    "valor_imovel": "real_estate_data.valor_imovel",
    "localizacao": "real_estate_data.localizacao",
    "tipologia": "real_estate_data.tipologia",
    "area": "real_estate_data.area_bruta",
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
