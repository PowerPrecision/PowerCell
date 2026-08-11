"""
Download em massa (ZIP) de documentos S3.

Extraído de `routes/documents.py` (`bulk_download_documents`).
"""
from __future__ import annotations

import asyncio
import logging
import zipfile
from datetime import datetime
from io import BytesIO
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from database import db
from services.document_constants import (
    ERROR_PROCESS_NOT_FOUND,
    ERROR_S3_NOT_CONFIGURED,
)
from services.document_s3_paths import s3_path_variations
from services.history import log_history
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


def _get_s3_file_content(key: str):
    try:
        response = s3_service.s3_client.get_object(
            Bucket=s3_service.bucket_name, Key=key
        )
        return response["Body"].read(), response.get(
            "ContentType", "application/octet-stream"
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "NoSuchKey":
            logger.warning(f"[BULK-DOWNLOAD] Ficheiro não encontrado: {key}")
            return None, None
        raise
    except Exception as e:
        logger.error(f"[BULK-DOWNLOAD] Erro ao obter ficheiro {key}: {e}")
        return None, None


def _unique_zip_filename(filename: str, already: list[str]) -> str:
    if filename not in already:
        return filename
    base_name, ext = (
        filename.rsplit(".", 1) if "." in filename else (filename, "")
    )
    counter = 2
    while f"{base_name}_{counter}.{ext}" in already:
        counter += 1
    return f"{base_name}_{counter}.{ext}"


async def run_bulk_download_documents(data: dict, *, user: dict) -> StreamingResponse:
    """Empacota até 50 paths S3 num ZIP streaming."""
    document_ids = data.get("document_ids", [])
    process_id = data.get("process_id")

    if not document_ids or len(document_ids) == 0:
        raise HTTPException(status_code=400, detail="Lista de documentos vazia")
    if len(document_ids) > 50:
        raise HTTPException(
            status_code=400, detail="Máximo de 50 documentos por download"
        )

    if process_id:
        process = await db.processes.find_one({"id": process_id})
        if not process:
            raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)

    if not s3_service.is_configured():
        raise HTTPException(status_code=500, detail=ERROR_S3_NOT_CONFIGURED)

    zip_buffer = BytesIO()
    files_added: list[tuple[str, str]] = []
    errors: list[dict] = []
    loop = asyncio.get_event_loop()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for doc_path in document_ids:
            try:
                content = None
                used_path = None
                for try_path in s3_path_variations(doc_path):
                    result = await loop.run_in_executor(
                        None, lambda p=try_path: _get_s3_file_content(p)
                    )
                    if result[0] is not None:
                        content, _content_type = result
                        used_path = try_path
                        break

                if content is None:
                    errors.append(
                        {"path": doc_path, "error": "Ficheiro não encontrado"}
                    )
                    continue

                filename = used_path.split("/")[-1] if "/" in used_path else used_path
                filename = _unique_zip_filename(
                    filename, [f[0] for f in files_added]
                )
                zip_file.writestr(filename, content)
                files_added.append((filename, used_path))
                logger.info(f"[BULK-DOWNLOAD] Adicionado ao ZIP: {filename}")
            except Exception as e:
                logger.error(f"[BULK-DOWNLOAD] Erro ao processar {doc_path}: {e}")
                errors.append({"path": doc_path, "error": str(e)})

    if not files_added:
        raise HTTPException(
            status_code=404, detail="Nenhum documento encontrado para download"
        )

    zip_buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"documentos_{timestamp}.zip"

    if process_id:
        try:
            await log_history(
                process_id=process_id,
                user=user,
                action="Download em massa",
                field="documentos",
                new_value=f"{len(files_added)} documentos",
            )
        except Exception as e:
            logger.warning(f"[BULK-DOWNLOAD] Erro ao registar histórico: {e}")

    logger.info(f"[BULK-DOWNLOAD] ZIP criado com {len(files_added)} ficheiros")

    def iter_zip():
        yield zip_buffer.getvalue()

    encoded_filename = quote(zip_filename, safe="")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Content-Type": "application/zip",
    }
    return StreamingResponse(
        iter_zip(), media_type="application/zip", headers=headers
    )
