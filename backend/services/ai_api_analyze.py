"""Sync document analysis API handlers (URL / base64 / S3).

Extraído de `routes/ai.py`. Prefer `ai_api_*` — do **not** overwrite
`ai_document.py` / analyzers.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from services.ai_document import (
    analyze_document_from_url,
    analyze_document_from_base64,
)
from services.ai_api_helpers import (
    VALID_DOCUMENT_TYPES,
    map_extracted_data,
    normalize_document_type,
)

logger = logging.getLogger(__name__)


class AnalyzeDocumentRequest(BaseModel):
    """Request to analyze a document."""
    document_url: Optional[str] = None
    document_base64: Optional[str] = None
    mime_type: Optional[str] = "image/jpeg"
    document_type: str  # 'cc', 'recibo_vencimento', 'irs', 'outro'
    process_id: Optional[str] = None


class AnalyzeOneDriveDocumentRequest(BaseModel):
    """Request to analyze a document from S3 storage."""
    client_folder: Optional[str] = None
    file_name: str
    document_type: str
    process_id: Optional[str] = None


def _strip_base64_prefix(value: str | None) -> str | None:
    if not value:
        return value
    if "," in value and value.strip().startswith("data:"):
        return value.split(",", 1)[1]
    return value


async def run_analyze_document(request: AnalyzeDocumentRequest, user: dict) -> dict:
    """Analyze a document using AI and extract structured data."""
    document_type = normalize_document_type(request.document_type)
    if not document_type:
        raise HTTPException(status_code=400, detail="document_type inválido")

    document_base64 = _strip_base64_prefix(request.document_base64)
    if not request.document_url and not document_base64:
        raise HTTPException(status_code=400, detail="Forneça document_url ou document_base64")

    if document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="document_type inválido")

    if document_base64:
        result = await analyze_document_from_base64(
            document_base64,
            request.mime_type,
            document_type,
        )
    else:
        result = await analyze_document_from_url(
            request.document_url,
            document_type,
        )

    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao analisar documento"))

    extracted_data = result.get("extracted_data", {})
    mapped_data = map_extracted_data(document_type, extracted_data)

    return {
        "success": True,
        "document_type": document_type,
        "extracted_data": extracted_data,
        "mapped_data": mapped_data,
        "process_id": request.process_id,
    }


async def run_analyze_onedrive_document(
    request: AnalyzeOneDriveDocumentRequest,
    user: dict,
) -> dict:
    """Analyze a document from S3 storage using AI."""
    from database import db
    from services.s3_storage import s3_service

    try:
        document_type = normalize_document_type(request.document_type)
        if not document_type:
            raise HTTPException(status_code=400, detail="document_type inválido")

        process = None
        if request.process_id:
            process = await db.processes.find_one(
                {"id": request.process_id},
                {"id": 1, "client_name": 1, "second_client_name": 1, "titular2_data": 1, "s3_folder": 1},
            )
        if not process and request.client_folder:
            process = await db.processes.find_one(
                {"client_name": {"$regex": f"^{request.client_folder}$", "$options": "i"}},
                {"id": 1, "client_name": 1, "second_client_name": 1, "titular2_data": 1, "s3_folder": 1},
            )
            if not process:
                process = await db.processes.find_one(
                    {"client_name": {"$regex": request.client_folder, "$options": "i"}},
                    {"id": 1, "client_name": 1, "second_client_name": 1, "titular2_data": 1, "s3_folder": 1},
                )
        if not process:
            raise HTTPException(
                status_code=404,
                detail="Processo/cliente não encontrado. Envie process_id ou client_folder.",
            )

        client_id = process.get("id")
        client_name = process.get("client_name", request.client_folder)
        second_client_name = process.get("second_client_name") or process.get("titular2_data", {}).get("nome")
        s3_folder = process.get("s3_folder")

        if not s3_service.is_configured():
            raise HTTPException(status_code=503, detail="Armazenamento S3 não configurado")

        files_data = s3_service.list_files(client_id, client_name, second_client_name, s3_folder=s3_folder)
        files_by_category = files_data.get("files", {})

        target_s3_key = None
        for category, category_files in files_by_category.items():
            if not isinstance(category_files, list):
                continue
            for f in category_files:
                if f.get("name", "").lower() == request.file_name.lower():
                    target_s3_key = f.get("path")
                    break
            if target_s3_key:
                break

        if not target_s3_key:
            raise HTTPException(
                status_code=404,
                detail=f"Ficheiro '{request.file_name}' não encontrado na pasta do cliente '{client_name}'",
            )

        download_url = s3_service.get_presigned_url(target_s3_key)
        if not download_url:
            raise HTTPException(status_code=500, detail="Erro ao gerar URL de download do ficheiro")

        result = await analyze_document_from_url(download_url, document_type)

        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Erro ao analisar documento"))

        extracted_data = result.get("extracted_data", {})
        mapped_data = {}
        if document_type in ("cc", "recibo_vencimento", "irs"):
            mapped_data = map_extracted_data(document_type, extracted_data)

        return {
            "success": True,
            "document_type": document_type,
            "file_name": request.file_name,
            "process_id": client_id,
            "extracted_data": extracted_data,
            "mapped_data": mapped_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing document from S3: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao analisar documento: {str(e)}")


async def run_get_supported_documents(user: dict) -> dict:
    """Get list of supported document types for AI analysis."""
    return {
        "document_types": [
            {
                "type": "cc",
                "name": "Cartão de Cidadão",
                "description": "Extrai nome, NIF, data nascimento, naturalidade, etc.",
                "extracts": ["nome_completo", "nif", "numero_documento", "data_nascimento", "naturalidade", "nacionalidade"],
            },
            {
                "type": "recibo_vencimento",
                "name": "Recibo de Vencimento",
                "description": "Extrai salário líquido, empresa, tipo de contrato, etc.",
                "extracts": ["salario_liquido", "salario_bruto", "empresa", "tipo_contrato", "categoria_profissional"],
            },
            {
                "type": "irs",
                "name": "Declaração de IRS",
                "description": "Extrai rendimentos anuais, estado civil fiscal, etc.",
                "extracts": ["rendimento_bruto_anual", "rendimento_liquido_anual", "estado_civil_fiscal", "numero_dependentes"],
            },
            {
                "type": "outro",
                "name": "Outro Documento",
                "description": "Extrai dados gerais do documento",
                "extracts": ["dados_gerais"],
            },
        ]
    }
